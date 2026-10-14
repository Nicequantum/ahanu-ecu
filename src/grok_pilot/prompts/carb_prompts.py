"""Prompt template v2 (src/grok_pilot/prompts/v2/): engine-room mode + carb jetting context. v1 is unchanged.

Usage::

    ctx = assemble_context(...)                       # same v1 context (history, audit, ...)
    carb = carb_block(mode, current_jets, rod, spring, analyses, experiments, experiment_open)
    bundle = render_v2(ctx, mode, carb, budget_tokens=6000)

The CARB / JETTING block is mandatory (never truncated). Its per-bank cell list is
capped at ``max_cells`` (highest sample count first) to keep it bounded.
"""
from __future__ import annotations

from typing import Optional

from ..carb import JET_LADDER, AfrAnalysis, EngineRoomMode, JetConfig, part_number, recommend
from .assemble import Context, PromptBundle, _dump, _r, load_examples, render

PROMPT_VERSION_V2 = "v2"
RESPONSE_SCHEMA_ID_V2 = "grok-pilot.proposal-response.v2"
EXPERIMENT_FIELDS = ("timestamp_us", "proposal_id", "phase", "bank", "jet_before", "jet_proposed", "jet_accepted",
                     "decision", "reject_reason", "afr_before_mean", "afr_before_n", "afr_after_mean", "afr_after_n",
                     "afr_delta", "moved_toward_target")


def carb_block(*, current_jets: dict, rod: str, spring: str, analyses: dict, cfg: JetConfig = JetConfig(),
               experiments: Optional[list] = None, experiment_open: bool = False, max_cells: int = 12,
               max_experiments: int = 6) -> dict:
    """analyses: {"primary": AfrAnalysis, "secondary": AfrAnalysis}; experiments: jet_change records."""
    banks = {}
    for bank in ("primary", "secondary"):
        cur = current_jets[bank]
        a: Optional[AfrAnalysis] = analyses.get(bank)
        entry = {"installed": {"size": cur, "part_number": part_number(cur)}}
        if a is None:
            entry["analysis"] = None
        else:
            top = sorted(a.cells.items(), key=lambda kv: (-kv[1]["n"], kv[0]))[:max_cells]
            rec = recommend(a, cur, cfg)
            entry["analysis"] = {"evidence": "WOT cells" if bank == "secondary" else "on-plane cells",
                                 "n": a.n, "mean": _r(a.mean, 3), "std": _r(a.std, 3), "cells_used": len(a.cells),
                                 "thin_cells_excluded": a.thin_cells, "cells": dict(sorted(top)),
                                 "issues": [x.value for x in a.issues]}
            entry["deterministic_recommendation"] = {"direction": rec.direction, "proposed_size": rec.proposed,
                                                     "reason": rec.reason.value}
        banks[bank] = entry
    exps = sorted(experiments or [], key=lambda r: (r["timestamp_us"], r.get("seq", 0)))[-max_experiments:]
    return {
        "carb": "Edelbrock 1410 (750 CFM marine)",
        "installed": {"rod": rod, "spring": spring},
        "jet_ladder": [{"part_number": pn, "size": s} for pn, s in JET_LADDER],
        "target_afr_band": [cfg.afr_target_lo, cfg.afr_target_hi],
        "limits": {"max_jet_steps": cfg.max_jet_steps, "afr_floor": cfg.afr_floor, "afr_ceiling": cfg.afr_ceiling,
                   "wideband_disagree_afr": cfg.wideband_disagree_afr,
                   "min_samples_per_cell": cfg.min_samples_per_cell, "min_total_samples": cfg.min_total_samples,
                   "max_afr_std": cfg.max_afr_std},
        "experiment_open": experiment_open,
        "banks": banks,
        "experiments": [{k: _r(e.get(k)) for k in EXPERIMENT_FIELDS} for e in exps],
    }


def render_v2(ctx: Context, mode: EngineRoomMode, carb: Optional[dict], budget_tokens: int = 6000) -> PromptBundle:
    mode = EngineRoomMode(mode)
    if mode is EngineRoomMode.CARB and carb is None:
        raise ValueError("carb mode needs a carb block")
    extra = {"engine_room_mode": mode.value,
             "allowed_tables": _dump(["spark"] if mode is EngineRoomMode.CARB else ["ve", "spark", "afr_target"]),
             "carb_json": _dump(carb if mode is EngineRoomMode.CARB else None)}
    return render(ctx, budget_tokens, version=PROMPT_VERSION_V2, extra=extra)


def load_examples_v2() -> dict:
    return load_examples(PROMPT_VERSION_V2)
