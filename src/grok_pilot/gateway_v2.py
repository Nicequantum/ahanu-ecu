"""Gateway for proposal-response v2 (engine-room mode aware). v1 (``grok.py``) is unchanged.

* EFI mode: proposals go to the envelope exactly as in v1. A ``jetting`` object is
  rejected as ``stage_locked``.
* Carb mode: spark proposals go to the envelope (with the cell gate restricted to
  spark). VE/AFR-target proposals are rejected as ``carb_fuel_locked`` without
  touching the envelope. ``jetting`` is checked by ``carb.evaluate_jet`` (advice only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Optional

from .carb import (AfrAnalysis, CarbReason, EngineRoomMode, JetConfig, JetResult, carb_cell_allowed,
                   evaluate_jet, fuel_locked_result)
from .envelope import Decision, Envelope, Proposal, Result, Table
from .grok import _PREQ, _num

SCHEMA_ID_V2 = "grok-pilot.proposal-response.v2"
_REQ2 = ["schema", "request_id", "model_version", "engine_id", "stage", "mode", "engine_room_mode", "proposals",
         "explanation", "anomalies"]
_JREQ = ["table", "bank", "current_size", "proposed_size", "rod", "spring", "rationale"]


def load_schema_v2() -> dict:
    return json.loads(resources.files("grok_pilot").joinpath("schemas/proposal-response.v2.schema.json").read_text())


def check_response_v2(resp: Any, expected_request_id: str, expected_engine_id: int, mode: EngineRoomMode) -> list:
    if not isinstance(resp, dict):
        return ["response is not an object"]
    errs = [f"missing {k}" for k in _REQ2 if k not in resp]
    if errs:
        return errs
    if resp["schema"] != SCHEMA_ID_V2:
        errs.append("wrong schema id")
    if resp["request_id"] != expected_request_id:
        errs.append("request_id mismatch (stale or replayed response)")
    if resp["engine_id"] != expected_engine_id or isinstance(resp["engine_id"], bool):
        errs.append("engine_id mismatch")
    if resp["mode"] != "copilot":
        errs.append("mode must be copilot")
    if resp["engine_room_mode"] != EngineRoomMode(mode).value:
        errs.append("engine_room_mode mismatch")
    if not isinstance(resp["proposals"], list) or len(resp["proposals"]) > 16:
        errs.append("proposals must be a list of <=16")
        return errs
    for i, p in enumerate(resp["proposals"]):
        if not isinstance(p, dict) or any(k not in p for k in _PREQ):
            errs.append(f"proposals[{i}] missing fields")
            continue
        if not (_num(p["value_before"]) and _num(p["value_proposed"]) and _num(p["confidence"])):
            errs.append(f"proposals[{i}] non-finite number")
    j = resp.get("jetting")
    if j is not None:
        if not isinstance(j, dict) or any(k not in j for k in _JREQ):
            errs.append("jetting missing fields")
        elif not (_num(j["current_size"]) and _num(j["proposed_size"])):
            errs.append("jetting non-finite size")
    return errs


@dataclass
class GatewayResult:
    cells: list = field(default_factory=list)   # [(Proposal, Result)]; log each as a cell_write
    jet: Optional[JetResult] = None             # log as a jet_change (phase=proposed) if present


def evaluate_response_v2(resp: dict, env: Envelope, now_s: float, request_id: str, context_ts_s: float, *,
                         mode: EngineRoomMode = EngineRoomMode.EFI, stage: Optional[str] = None,
                         cell_allowed=None, jet_current: Optional[dict] = None,
                         jet_analysis: Optional[AfrAnalysis] = None, jet_cfg: JetConfig = JetConfig(),
                         experiment_open: bool = False) -> GatewayResult:
    mode = EngineRoomMode(mode)
    errs = check_response_v2(resp, request_id, env.cfg.engine_id, mode)
    if errs:
        raise ValueError("; ".join(errs))
    out = GatewayResult()
    gate = carb_cell_allowed(cell_allowed) if mode is EngineRoomMode.CARB else cell_allowed
    for i, p in enumerate(resp["proposals"]):
        prop = Proposal(engine_id=resp["engine_id"], table=p["table"], rpm_idx=p["rpm_idx"], map_idx=p["map_idx"],
                        value_before=p["value_before"], value_proposed=p["value_proposed"], timestamp_s=context_ts_s,
                        evidence_samples=p["evidence_samples"], proposal_id=i)
        if mode is EngineRoomMode.CARB and p["table"] in (Table.VE.value, Table.AFR_TARGET.value):
            out.cells.append((prop, fuel_locked_result(p["value_before"])))
        else:
            out.cells.append((prop, env.evaluate(prop, now_s, cell_allowed=gate)))
    j = resp.get("jetting")
    if j is not None:
        out.jet = evaluate_jet(j, mode=mode, stage=stage or resp["stage"], current=jet_current or {},
                               analysis=jet_analysis, cfg=jet_cfg, experiment_open=experiment_open)
    return out
