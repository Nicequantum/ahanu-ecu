"""Context assembly + deterministic rendering for prompt template v1.

Pure functions: the same inputs give byte-identical prompts (sorted keys, fixed
float rounding, no clocks or randomness). Inputs are DATA-SCHEMA v0.2 records
(``sample`` and ``cell_write`` dicts) as produced by the Teensy, the synthetic
generator, or the ingest store.

Token budgets use a documented, conservative heuristic (``estimate_tokens``).
The production model's tokenizer isn't available offline. See
docs/PROMPT-TEMPLATES.md for the calibration against tiktoken o200k_base.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from importlib import resources
from typing import Iterable, Optional

PROMPT_VERSION = "v1"
RESPONSE_SCHEMA_ID = "grok-pilot.proposal-response.v1"

# Heuristic (character classes), calibrated to OVER-estimate tiktoken o200k_base
# by 1.07-1.53x on rendered v1 prompts and examples (docs/PROMPT-TEMPLATES.md):
#   tokens = ceil(letters/4 + digits*0.5 + punctuation*1.0 + non-ASCII chars*1.0)
# Whitespace is free. JSON digits and punctuation dominate, so bytes/4 would undercount ~2x.
K_ALPHA, K_DIGIT, K_PUNCT, K_NONASCII = 4.0, 0.5, 1.0, 1.0

STATE_FIELDS = ("timestamp_us", "stage", "status", "rpm", "map_kpa", "tps_pct", "coolant_c", "iat_c", "afr_a",
                "afr_b", "afr_target", "afr_a_status", "afr_b_status", "spark_adv_deg", "battery_v", "egt_c",
                "oil_press_kpa", "oil_alarm", "lean_cut_active", "ego_correction_pct", "warmup_enrich_pct",
                "accel_enrich_active", "sync_loss_count", "ve_cell_rpm_idx", "ve_cell_map_idx")
HISTORY_COLS = ("t_s", "rpm", "map_kpa", "tps_pct", "coolant_c", "afr_a", "afr_b", "afr_target", "spark_adv_deg",
                "ve_cell_rpm_idx", "ve_cell_map_idx", "status")
AUDIT_FIELDS = ("timestamp_us", "proposal_id", "table", "cell_rpm_idx", "cell_map_idx", "value_before",
                "value_proposed", "value_accepted", "decision", "reject_reason", "evidence_samples")


class BudgetError(ValueError):
    """Mandatory sections alone exceed the budget."""


def estimate_tokens(text: str) -> int:
    """Conservative token estimate by character class. A heuristic, not a real tokenizer."""
    a = d = o = n = 0
    for ch in text:
        if not ch.isascii():
            n += 1
        elif ch.isalpha():
            a += 1
        elif ch.isdigit():
            d += 1
        elif not ch.isspace():
            o += 1
    return math.ceil(a / K_ALPHA + d * K_DIGIT + o * K_PUNCT + n * K_NONASCII)


def _r(x, nd=2):
    if isinstance(x, bool) or x is None or isinstance(x, (int, str)):
        return x
    if isinstance(x, float):
        if not math.isfinite(x):
            return None  # never put NaN/inf into a prompt
        return round(x, nd)
    return x


def _dump(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _read(name: str) -> str:
    return resources.files("grok_pilot.prompts").joinpath(f"{PROMPT_VERSION}/{name}").read_text(encoding="utf-8")


def system_prompt() -> str:
    return _read("system.md")


def _downsample(samples: list, every_s: float) -> list:
    out, last = [], None
    for s in samples:
        t = s["timestamp_us"] / 1e6
        if last is None or t - last >= every_s - 1e-9:
            out.append(s)
            last = t
    return out


@dataclass
class Context:
    request_id: str
    engine_id: int
    stage: str
    status: str
    allowed_rpm_idx: list
    envelope: dict
    engine_state: dict          # {"0": {...}, "1": {...}}
    tables: dict                # {"ve": {"r,m": v}, ...} target engine
    audit: list                 # newest last
    history: dict               # {"0": {"cols": [...], "rows": [[...]]}, "1": ...}
    max_proposals: int = 8
    wideband_fault_afr: float = 1.5
    history_every_s: float = 1.0


def assemble_context(*, request_id: str, engine_id: int, stage: str, status: str, allowed_rpm_idx: Iterable[int],
                     envelope_cfg, samples: Iterable[dict], cell_writes: Iterable[dict], tables: dict,
                     now_us: int, window_s: float = 120.0, history_every_s: float = 1.0, audit_max: int = 20,
                     max_proposals: int = 8, wideband_fault_afr: float = 1.5) -> Context:
    """Build the v1 context from schema records. ``samples`` may hold both engines."""
    lo = now_us - int(window_s * 1e6)
    per = {0: [], 1: []}
    for s in samples:
        if s.get("record_type", "sample") == "sample" and lo <= s["timestamp_us"] <= now_us and s["engine_id"] in per:
            per[s["engine_id"]].append(s)
    for v in per.values():
        v.sort(key=lambda s: (s["timestamp_us"], s.get("seq", 0)))
    state = {str(e): ({k: _r(v[-1].get(k)) for k in STATE_FIELDS} if v else None) for e, v in per.items()}
    hist = {}
    for e, v in per.items():
        rows = [[_r((s["timestamp_us"] - now_us) / 1e6, 1)] + [_r(s.get(c)) for c in HISTORY_COLS[1:]]
                for s in _downsample(v, history_every_s)]
        hist[str(e)] = {"cols": list(HISTORY_COLS), "rows": rows}
    aud = sorted((c for c in cell_writes if c["engine_id"] == engine_id and c["timestamp_us"] <= now_us),
                 key=lambda c: (c["timestamp_us"], c.get("proposal_id", 0)))[-audit_max:]
    c = envelope_cfg
    env = {"max_fuel_delta_pct": c.max_fuel_delta_pct, "max_spark_delta_deg": c.max_spark_delta_deg,
           "spark_min_deg": c.spark_min_deg, "spark_max_deg": c.spark_max_deg, "afr_floor": c.afr_floor,
           "afr_ceiling": c.afr_ceiling, "ve_min": c.ve_min, "ve_max": c.ve_max,
           "min_evidence_samples": c.min_evidence_samples,
           "rate_limit": {"touches": c.rate_limit_touches, "window_s": c.rate_limit_window_s},
           "max_age_s": c.max_age_s}
    tbl = {t: {(k if isinstance(k, str) else f"{k[0]},{k[1]}"): _r(v) for k, v in cells.items()}
           for t, cells in tables.items()}
    return Context(request_id=request_id, engine_id=engine_id, stage=stage, status=status,
                   allowed_rpm_idx=sorted(set(int(i) for i in allowed_rpm_idx)), envelope=env, engine_state=state,
                   tables=tbl, audit=[{k: _r(a.get(k)) for k in AUDIT_FIELDS} for a in aud], history=hist,
                   max_proposals=max_proposals, wideband_fault_afr=wideband_fault_afr,
                   history_every_s=history_every_s)


@dataclass
class PromptBundle:
    version: str
    system: str
    user: str
    tokens_system: int
    tokens_user: int
    budget: int
    truncated: dict = field(default_factory=dict)  # section -> items dropped

    @property
    def tokens_total(self) -> int:
        return self.tokens_system + self.tokens_user


def _fill(ctx: Context, history: dict, audit: list, tables: dict) -> str:
    n_rows = sum(len(h["rows"]) for h in history.values())
    note = (f"both engines, newest {n_rows} rows, ~{ctx.history_every_s:g} s spacing, t_s relative to now; "
            "compact columns/rows")
    return _read("user.md").format(
        request_id=ctx.request_id, engine_id=ctx.engine_id,
        engine_label=("port" if ctx.engine_id == 0 else "starboard") + ", assigned at first run",
        stage=ctx.stage, status=ctx.status, allowed_rpm_idx=_dump(ctx.allowed_rpm_idx),
        max_proposals=ctx.max_proposals, wideband_fault_afr=ctx.wideband_fault_afr,
        envelope_json=_dump(ctx.envelope), engine_state_json=_dump(ctx.engine_state), tables_json=_dump(tables),
        audit_json=_dump(audit), history_note=note, history_json=_dump(history))


def render(ctx: Context, budget_tokens: int = 6000) -> PromptBundle:
    """Render system + user prompt within ``budget_tokens`` (prompt only; reserve output separately).

    Truncation order when over budget: history (oldest rows first, alternating
    engines), then audit trail (oldest first), then table cells (outside the
    allowed rpm band first). REQUEST, ENVELOPE and ENGINE STATE are never cut.
    """
    sysp = system_prompt()
    ts = estimate_tokens(sysp)
    hist = {e: {"cols": h["cols"], "rows": list(h["rows"])} for e, h in ctx.history.items()}
    audit = list(ctx.audit)
    tables = {t: dict(c) for t, c in ctx.tables.items()}
    dropped = {"history_rows": 0, "audit": 0, "table_cells": 0}

    def size():
        return ts + estimate_tokens(_fill(ctx, hist, audit, tables))

    while size() > budget_tokens:
        longest = max(hist.values(), key=lambda h: len(h["rows"]), default=None)
        if longest and longest["rows"]:
            # drop in chunks for speed, keep determinism
            k = max(1, len(longest["rows"]) // 10)
            del longest["rows"][:k]
            dropped["history_rows"] += k
            continue
        if audit:
            audit.pop(0)
            dropped["audit"] += 1
            continue
        removable = [(t, k) for t in sorted(tables) for k in sorted(tables[t])
                     if int(k.split(",")[0]) not in ctx.allowed_rpm_idx]
        if not removable:
            removable = [(t, k) for t in sorted(tables) for k in sorted(tables[t])]
        if removable:
            t, k = removable[0]
            del tables[t][k]
            dropped["table_cells"] += 1
            continue
        raise BudgetError(f"mandatory sections need {size()} tokens > budget {budget_tokens}")
    user = _fill(ctx, hist, audit, tables)
    return PromptBundle(PROMPT_VERSION, sysp, user, ts, estimate_tokens(user), budget_tokens,
                        {k: v for k, v in dropped.items() if v})


def load_examples() -> dict:
    """{name: {"kind": "good"|"bad", "expect": ..., "response": {...}}} from v1/examples/."""
    out = {}
    d = resources.files("grok_pilot.prompts").joinpath(f"{PROMPT_VERSION}/examples")
    for f in sorted(d.iterdir(), key=lambda p: p.name):
        if f.name.endswith(".json"):
            out[f.name[:-5]] = json.loads(f.read_text(encoding="utf-8"))
    return out
