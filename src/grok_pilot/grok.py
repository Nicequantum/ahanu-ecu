"""Grok integration glue: build the context payload and prompt, then turn a
model response into envelope decisions plus audit records.

See docs/GROK-INTEGRATION-API.md. The JSON Schema in
schemas/proposal-response.v1.schema.json is the authoritative response
contract. ``check_response`` is a dependency-free structural check that the
gateway can run anywhere; tests also validate against the JSON Schema itself
using ``jsonschema``.
"""
from __future__ import annotations

import json
import math
from importlib import resources
from typing import Any

from .envelope import Envelope, Proposal, Result

SCHEMA_ID = "grok-pilot.proposal-response.v1"
PROMPT_TEMPLATE = """You are Grok Pilot's tuning co-pilot for a marine Mercruiser 5.7 (engine_id={engine_id}, {engine_label}).
You are ADVISORY ONLY. Your proposals go through a fixed validation envelope on the Teensy, which may clamp or reject them.
Do not try to work around the envelope limits. Proposals outside them will be rejected and logged.

Current stage: {stage}. Status: {status}. You may propose only for cells in rpm_idx {allowed_rpm_idx}.
Envelope limits: {envelope_json}

Recent samples for this engine and the other one are in CONTEXT below. AFR A and B are separate exhaust banks, so a steady
offset between them can be real. If they disagree by more than {wb_fault} AFR, propose nothing and raise an anomaly.

Respond with ONLY a JSON object that matches schema "{schema_id}". Use mode "copilot". At most {max_props} proposals.
Base each proposal on the cell's current value (value_before must equal the table value in CONTEXT).

CONTEXT:
{context_json}
"""


def load_schema() -> dict:
    return json.loads(resources.files("grok_pilot").joinpath("schemas/proposal-response.v1.schema.json").read_text())


def build_context(request_id: str, engine_id: int, stage: str, status: str, samples: dict,
                  envelope_cfg, tables: dict, allowed_rpm_idx: list, window_s: float = 60.0) -> dict:
    """samples: {engine_id: [sample records]} for both engines (most recent window)."""
    def summarize(recs):
        keys = ("timestamp_us", "rpm", "map_kpa", "tps_pct", "coolant_c", "iat_c", "afr_a", "afr_b", "afr_target",
                "spark_adv_deg", "battery_v", "ve_cell_rpm_idx", "ve_cell_map_idx", "egt_c", "oil_press_kpa", "status")
        return [{k: r.get(k) for k in keys} for r in recs]
    c = envelope_cfg
    return {
        "request_id": request_id, "engine_id": engine_id, "stage": stage, "status": status, "window_s": window_s,
        "allowed_rpm_idx": allowed_rpm_idx,
        "envelope": {"max_fuel_delta_pct": c.max_fuel_delta_pct, "max_spark_delta_deg": c.max_spark_delta_deg,
                     "spark_min_deg": c.spark_min_deg, "spark_max_deg": c.spark_max_deg, "afr_floor": c.afr_floor,
                     "afr_ceiling": c.afr_ceiling, "ve_min": c.ve_min, "ve_max": c.ve_max,
                     "min_evidence_samples": c.min_evidence_samples,
                     "rate_limit": {"touches": c.rate_limit_touches, "window_s": c.rate_limit_window_s}},
        "tables": {t: {f"{r},{m}": v for (r, m), v in cells.items()} for t, cells in tables.items()},
        "samples": {str(e): summarize(v) for e, v in samples.items()},
    }


def render_prompt(ctx: dict, wb_fault: float = 1.5, max_props: int = 8) -> str:
    return PROMPT_TEMPLATE.format(engine_id=ctx["engine_id"], engine_label=("port" if ctx["engine_id"] == 0 else "starboard") + " (assigned at first run)",
                                  stage=ctx["stage"], status=ctx["status"], allowed_rpm_idx=ctx["allowed_rpm_idx"],
                                  envelope_json=json.dumps(ctx["envelope"]), wb_fault=wb_fault, schema_id=SCHEMA_ID,
                                  max_props=max_props, context_json=json.dumps({k: ctx[k] for k in ("tables", "samples")}))


_REQ = ["schema", "request_id", "model_version", "engine_id", "stage", "mode", "proposals", "explanation", "anomalies"]
_PREQ = ["table", "rpm_idx", "map_idx", "value_before", "value_proposed", "evidence_samples", "confidence", "rationale"]


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def check_response(resp: Any, expected_request_id: str, expected_engine_id: int) -> list[str]:
    """Gateway-side structural check (subset of the JSON Schema plus cross-field rules)."""
    if not isinstance(resp, dict):
        return ["response is not an object"]
    errs = [f"missing {k}" for k in _REQ if k not in resp]
    if errs:
        return errs
    if resp["schema"] != SCHEMA_ID:
        errs.append("wrong schema id")
    if resp["request_id"] != expected_request_id:
        errs.append("request_id mismatch (stale or replayed response)")
    if resp["engine_id"] != expected_engine_id or isinstance(resp["engine_id"], bool):
        errs.append("engine_id mismatch")
    if resp["mode"] != "copilot":
        errs.append("mode must be copilot in v1")
    if not isinstance(resp["proposals"], list) or len(resp["proposals"]) > 16:
        errs.append("proposals must be a list of <=16")
        return errs
    for i, p in enumerate(resp["proposals"]):
        if not isinstance(p, dict) or any(k not in p for k in _PREQ):
            errs.append(f"proposals[{i}] missing fields")
            continue
        if not (_num(p["value_before"]) and _num(p["value_proposed"]) and _num(p["confidence"])):
            errs.append(f"proposals[{i}] non-finite number")
    return errs


def evaluate_response(resp: dict, env: Envelope, now_s: float, request_id: str, context_ts_s: float, cell_allowed=None) -> list[tuple[Proposal, Result]]:
    """Every proposal gets a decision. A structurally bad response rejects the whole
    batch (nothing applied). Callers must log every returned pair as a cell_write."""
    errs = check_response(resp, request_id, env.cfg.engine_id)
    if errs:
        raise ValueError("; ".join(errs))
    out = []
    for i, p in enumerate(resp["proposals"]):
        prop = Proposal(engine_id=resp["engine_id"], table=p["table"], rpm_idx=p["rpm_idx"], map_idx=p["map_idx"],
                        value_before=p["value_before"], value_proposed=p["value_proposed"], timestamp_s=context_ts_s,  # age = time since the context snapshot
                        evidence_samples=p["evidence_samples"], proposal_id=i)
        out.append((prop, env.evaluate(prop, now_s, cell_allowed=cell_allowed)))
    return out
