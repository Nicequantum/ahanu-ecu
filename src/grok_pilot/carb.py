"""Carburetor jetting mode (pure logic). See docs/CARB_JETTING_MODE.md.

In carb mode the carburetor is the fuel authority and Speeduino drives spark only
(GM 7/8-pin HEI). So in carb mode:

* auto-tune may propose **timing (spark) only**. VE/AFR-target proposals are rejected
  as ``carb_fuel_locked`` before they reach the envelope;
* jetting is **advice only**. The deterministic layer computes the recommendation from
  logged load AFR (``analyze_afr`` -> ``recommend``) and checks any model-suggested
  jet change against it (``evaluate_jet``). At most one ladder step per change;
* nothing writes to the carb. A jet swap is a physical job done by a person, who
  declares it; the experiment record then pairs the AFR windows before and after
  (``jet_change_record``).

All of this applies only when ``EngineRoomMode.CARB`` is selected. EFI behaviour is
unchanged (the default mode is EFI).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

from .envelope import Decision, Result, Table


class EngineRoomMode(str, Enum):
    """Mirrors Ahanu's EngineRoomMode (carb / efi)."""
    EFI = "efi"
    CARB = "carb"


class CarbReason(str, Enum):
    """Reject/clamp reasons used by the carb layer (values match schema v0.3 REASONS_V03)."""
    NONE = "none"
    CARB_FUEL_LOCKED = "carb_fuel_locked"
    JET_STEP_EXCEEDED = "jet_step_exceeded"
    OFF_LADDER = "off_ladder"
    WRONG_DIRECTION = "wrong_direction"
    AFR_VARIANCE = "afr_variance"
    EXPERIMENT_OPEN = "experiment_open"
    AFR_FLOOR = "afr_floor"
    AFR_CEILING = "afr_ceiling"
    WIDEBAND_DISAGREE = "wideband_disagree"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    STAGE_LOCKED = "stage_locked"
    STALE_BASIS = "stale_basis"
    OFF_TABLE = "off_table"
    INVALID_VALUE = "invalid_value"


# Edelbrock Performer/Marine (AVS-type) main metering jets, verified against Edelbrock's published
# #1407/#1410 calibration chart and product pages (docs/CARB_JETTING_MODE.md §5). This is the
# 0.003 in staging ladder. #1428 (0.100 in) exists but is off-ladder, so it isn't used for steps.
JET_LADDER: tuple = ((1427, 0.098), (1429, 0.101), (1430, 0.104), (1431, 0.107), (1432, 0.110),
                     (1433, 0.113), (1434, 0.116))
JET_SIZES = tuple(s for _, s in JET_LADDER)
STOCK_1410 = {"primary": 0.113, "secondary": 0.107, "rod": "0.071x0.047", "spring": "orange"}
SPRINGS_INHG = {"blue": 3, "yellow": 4, "orange": 5, "pink": 7, "silver": 8}
BANKS = ("primary", "secondary")


def ladder_index(size) -> Optional[int]:
    if isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(size):
        return None
    for i, s in enumerate(JET_SIZES):
        if abs(size - s) < 5e-4:
            return i
    return None


def part_number(size) -> Optional[int]:
    i = ladder_index(size)
    return None if i is None else JET_LADDER[i][0]


@dataclass(frozen=True)
class JetConfig:
    # Target band for WOT/load AFR. Default 11.0-12.0, biased rich: marine engines run long at
    # sustained high load, so they need detonation margin (user spec).
    afr_target_lo: float = 11.0
    afr_target_hi: float = 12.0
    # The existing safety rules, applied to the evidence cells. Values are as quoted by the user for jetting.
    # The EFI envelope defaults are NOT changed (min_evidence_samples=50 and wideband fault 1.5 there).
    afr_floor: float = 10.5
    afr_ceiling: float = 16.0
    wideband_disagree_afr: float = 0.3
    min_samples_per_cell: int = 20
    min_total_samples: int = 100
    max_afr_std: float = 0.6               # TODO: tune on real data
    max_jet_steps: int = 1
    clamp_jet_steps: bool = True           # >1 step -> clamp to 1 (True) or reject (False)
    # Load filters (placeholders until measured on the boat; TODO hardware)
    wot_tps_pct: float = 85.0              # secondary evidence: WOT
    wot_min_rpm: float = 3000.0
    onplane_tps_pct: tuple = (25.0, 70.0)  # primary evidence: on-plane cruise, secondaries assumed closed
    onplane_rpm: tuple = (2500.0, 4200.0)
    onplane_min_map_kpa: float = 55.0


def _ok(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def is_load_sample(s: dict, bank: str, cfg: JetConfig = JetConfig()) -> bool:
    """Idle is never evidence. primary -> on-plane cells, secondary -> WOT cells."""
    if s.get("afr_a_status", "ok") != "ok" or s.get("afr_b_status", "ok") != "ok":
        return False
    if s.get("accel_enrich_active") or s.get("lean_cut_active"):
        return False
    if not all(_ok(s.get(k)) for k in ("afr_a", "afr_b", "rpm", "tps_pct", "map_kpa")):
        return False
    if bank == "secondary":
        return s["tps_pct"] >= cfg.wot_tps_pct and s["rpm"] >= cfg.wot_min_rpm
    lo, hi = cfg.onplane_tps_pct
    rlo, rhi = cfg.onplane_rpm
    return lo <= s["tps_pct"] < hi and rlo <= s["rpm"] <= rhi and s["map_kpa"] >= cfg.onplane_min_map_kpa


@dataclass
class AfrAnalysis:
    bank: str
    n: int = 0
    mean: Optional[float] = None
    std: Optional[float] = None
    start_us: Optional[int] = None
    end_us: Optional[int] = None
    cells: dict = field(default_factory=dict)        # "r,m" -> {"n", "mean", "afr_a", "afr_b", "disagree"}
    thin_cells: int = 0                              # cells below min_samples_per_cell (not used)
    issues: list = field(default_factory=list)       # ordered CarbReason values blocking a recommendation

    @property
    def usable(self) -> bool:
        return not self.issues


def analyze_afr(samples: Iterable[dict], bank: str, cfg: JetConfig = JetConfig(),
                engine_id: Optional[int] = None) -> AfrAnalysis:
    """Per-cell load AFR stats for one carb circuit. A sample's AFR is the mean of both widebands
    (one carb feeds both exhaust banks)."""
    if bank not in BANKS:
        raise ValueError(f"bank must be one of {BANKS}")
    raw: dict = {}
    for s in samples:
        if s.get("record_type", "sample") != "sample" or (engine_id is not None and s.get("engine_id") != engine_id):
            continue
        if not is_load_sample(s, bank, cfg):
            continue
        k = f"{s.get('ve_cell_rpm_idx')},{s.get('ve_cell_map_idx')}"
        raw.setdefault(k, []).append(s)
    a = AfrAnalysis(bank)
    vals = []
    for k in sorted(raw):
        rs = raw[k]
        if len(rs) < cfg.min_samples_per_cell:
            a.thin_cells += 1
            continue
        ma = sum(r["afr_a"] for r in rs) / len(rs)
        mb = sum(r["afr_b"] for r in rs) / len(rs)
        a.cells[k] = {"n": len(rs), "afr_a": round(ma, 3), "afr_b": round(mb, 3), "mean": round((ma + mb) / 2, 3),
                      "disagree": round(abs(ma - mb), 3)}
        for r in rs:
            vals.append(((r["afr_a"] + r["afr_b"]) / 2, r["timestamp_us"]))
    a.n = len(vals)
    if vals:
        m = sum(v for v, _ in vals) / len(vals)
        a.mean = round(m, 3)
        a.std = round(math.sqrt(sum((v - m) ** 2 for v, _ in vals) / len(vals)), 3)
        a.start_us = min(t for _, t in vals)
        a.end_us = max(t for _, t in vals)
    if a.n < cfg.min_total_samples or not a.cells:
        a.issues.append(CarbReason.INSUFFICIENT_SAMPLES)
    if any(c["disagree"] > cfg.wideband_disagree_afr for c in a.cells.values()):
        a.issues.append(CarbReason.WIDEBAND_DISAGREE)
    if any(c["mean"] < cfg.afr_floor for c in a.cells.values()):
        a.issues.append(CarbReason.AFR_FLOOR)       # implausibly/dangerously rich: inspect, don't jet
    if any(c["mean"] > cfg.afr_ceiling for c in a.cells.values()):
        a.issues.append(CarbReason.AFR_CEILING)     # dangerously lean: stop and inspect before any jetting
    if a.std is not None and a.std > cfg.max_afr_std:
        a.issues.append(CarbReason.AFR_VARIANCE)
    return a


@dataclass(frozen=True)
class JetRecommendation:
    bank: str
    current: float
    proposed: Optional[float]       # None = hold
    direction: str                  # "richer" | "leaner" | "hold"
    reason: CarbReason
    rationale: str


def recommend(a: AfrAnalysis, current: float, cfg: JetConfig = JetConfig()) -> JetRecommendation:
    """Deterministic recommendation: at most one ladder step, toward the target band."""
    i = ladder_index(current)
    if i is None:
        return JetRecommendation(a.bank, current, None, "hold", CarbReason.OFF_LADDER, "current jet not on ladder")
    if a.issues:
        return JetRecommendation(a.bank, current, None, "hold", a.issues[0],
                                 f"evidence not usable: {', '.join(x.value for x in a.issues)}")
    band = f"{cfg.afr_target_lo:g}-{cfg.afr_target_hi:g}"
    base = f"{a.bank} load AFR mean {a.mean:.2f} (std {a.std:.2f}, n={a.n}, {len(a.cells)} cells) vs band {band}"
    if a.mean > cfg.afr_target_hi:
        j = i + 1
        d = "richer"
    elif a.mean < cfg.afr_target_lo:
        j = i - 1
        d = "leaner"
    else:
        return JetRecommendation(a.bank, current, None, "hold", CarbReason.NONE, base + ": in band, no change")
    if not 0 <= j < len(JET_SIZES):
        return JetRecommendation(a.bank, current, None, "hold", CarbReason.OFF_LADDER,
                                 base + f": would go {d} but already at end of ladder; check rods/float/fuel supply")
    return JetRecommendation(a.bank, current, JET_SIZES[j], d, CarbReason.NONE,
                             base + f": one step {d}, #{JET_LADDER[i][0]} ({JET_SIZES[i]:.3f}) -> "
                                    f"#{JET_LADDER[j][0]} ({JET_SIZES[j]:.3f})")


@dataclass(frozen=True)
class JetResult:
    decision: Decision
    reason: CarbReason
    jet_before: float
    jet_accepted: float

    @property
    def advised(self) -> bool:
        return self.decision in (Decision.ACCEPTED, Decision.CLAMPED)


def evaluate_jet(p: dict, *, mode: EngineRoomMode, stage: str, current: dict, analysis: Optional[AfrAnalysis],
                 cfg: JetConfig = JetConfig(), experiment_open: bool = False) -> JetResult:
    """Deterministic check of a jetting proposal ({table:'jet', bank, current_size, proposed_size, ...}).

    The outcome is advice to a human, never a write. Order: mode/stage, structure, basis,
    ladder, one-experiment-at-a-time, evidence gates, direction, step limit.
    """
    cur = p.get("current_size") if isinstance(p, dict) else None
    vb = float(cur) if _ok(cur) else float("nan")

    def rej(r):
        return JetResult(Decision.REJECTED, r, vb, vb)

    if mode != EngineRoomMode.CARB or stage != "carb_jetting":
        return rej(CarbReason.STAGE_LOCKED)
    if not isinstance(p, dict) or p.get("table") != "jet" or p.get("bank") not in BANKS:
        return rej(CarbReason.OFF_TABLE)
    prop = p.get("proposed_size")
    if not (_ok(cur) and _ok(prop)):
        return rej(CarbReason.INVALID_VALUE)
    cb = (current or {}).get(p["bank"])
    if not _ok(cb) or abs(cur - cb) > 5e-4:
        return rej(CarbReason.STALE_BASIS)     # model saw a different installed jet than declared
    i, j = ladder_index(cur), ladder_index(prop)
    if i is None or j is None:
        return rej(CarbReason.OFF_LADDER)
    if experiment_open:
        return rej(CarbReason.EXPERIMENT_OPEN)  # one jet change per cycle: evaluate the last swap first
    if analysis is None or analysis.bank != p["bank"]:
        return rej(CarbReason.INSUFFICIENT_SAMPLES)
    if analysis.issues:
        return rej(analysis.issues[0])
    if j == i:
        return rej(CarbReason.INVALID_VALUE)    # no-op proposal
    need = recommend(analysis, cur, cfg)
    want = "richer" if j > i else "leaner"
    if need.direction != want:
        return rej(CarbReason.WRONG_DIRECTION)  # disagrees with the logged-AFR analysis (or no change needed)
    if abs(j - i) > cfg.max_jet_steps:
        if not cfg.clamp_jet_steps:
            return rej(CarbReason.JET_STEP_EXCEEDED)
        k = i + cfg.max_jet_steps * (1 if j > i else -1)
        return JetResult(Decision.CLAMPED, CarbReason.JET_STEP_EXCEEDED, vb, JET_SIZES[k])
    return JetResult(Decision.ACCEPTED, CarbReason.NONE, vb, JET_SIZES[j])


def fuel_locked_result(value_before) -> Result:
    """Result for any VE/AFR-target proposal in carb mode (the envelope is never consulted)."""
    vb = float(value_before) if _ok(value_before) else float("nan")
    return Result(Decision.REJECTED, CarbReason.CARB_FUEL_LOCKED, vb, vb)  # type: ignore[arg-type]


def carb_cell_allowed(base=None):
    """Wrap a cell_allowed predicate: in carb mode only the spark table is learnable."""
    def f(table, r, m):
        if table != Table.SPARK.value:
            return False
        return True if base is None else base(table, r, m)
    return f


def moved_toward(before: float, after: float, lo: float, hi: float) -> bool:
    def dist(x):
        return 0.0 if lo <= x <= hi else (lo - x if x < lo else x - hi)
    return dist(after) < dist(before) or dist(after) == 0.0


def jet_change_record(*, header: dict, proposal_id: int, request_id: str, model_version: str, source: str,
                      proposal: dict, result: JetResult, before: AfrAnalysis, cfg: JetConfig = JetConfig(),
                      swap_declared_us: Optional[int] = None, after: Optional[AfrAnalysis] = None) -> dict:
    """Build a schema v0.3 ``jet_change`` record. Pass ``after`` + ``swap_declared_us`` for phase=evaluated."""
    rec = {**header, "schema_version": "0.3", "record_type": "jet_change", "proposal_id": proposal_id,
           "request_id": request_id, "model_version": model_version, "source": source,
           "phase": "proposed" if after is None else "evaluated", "engine_room_mode": "carb",
           "bank": proposal["bank"], "jet_before": result.jet_before,
           "jet_proposed": float(proposal["proposed_size"]), "jet_accepted": result.jet_accepted,
           "decision": result.decision.value, "reject_reason": result.reason.value,
           "afr_target_lo": cfg.afr_target_lo, "afr_target_hi": cfg.afr_target_hi,
           "before_start_us": before.start_us, "before_end_us": before.end_us, "afr_before_mean": before.mean,
           "afr_before_std": before.std, "afr_before_n": before.n}
    for k in ("rod", "spring", "rationale"):
        if proposal.get(k):
            rec[k] = proposal[k][:500] if k == "rationale" else proposal[k]
    if after is not None:
        rec.update({"swap_declared_us": swap_declared_us, "after_start_us": after.start_us,
                    "after_end_us": after.end_us, "afr_after_mean": after.mean, "afr_after_std": after.std,
                    "afr_after_n": after.n, "afr_delta": round(after.mean - before.mean, 3),
                    "moved_toward_target": moved_toward(before.mean, after.mean, cfg.afr_target_lo,
                                                        cfg.afr_target_hi)})
    return rec
