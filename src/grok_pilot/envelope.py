"""Deterministic validation envelope.

Every AI proposal passes through ``Envelope.evaluate`` before any map write.
Pure logic, no I/O, no randomness: identical inputs give identical decisions.
Defaults mirror docs/AI_TUNING_SAFETY.md (±5 % fuel, ±2° spark, AFR 10.5–16.0).

This Python implementation is the reference model / test oracle; the
authoritative copy must eventually live on the Teensy (fixed, not AI-writable).
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class Table(str, Enum):
    VE = "ve"
    SPARK = "spark"
    AFR_TARGET = "afr_target"


class Decision(str, Enum):
    ACCEPTED = "accepted"
    CLAMPED = "clamped"
    REJECTED = "rejected"


class Reason(str, Enum):
    NONE = "none"
    FUEL_DELTA_EXCEEDED = "fuel_delta_exceeded"
    SPARK_DELTA_EXCEEDED = "spark_delta_exceeded"
    SPARK_LIMIT = "spark_limit"
    AFR_FLOOR = "afr_floor"
    AFR_CEILING = "afr_ceiling"
    VE_LIMIT = "ve_limit"
    RATE_LIMITED = "rate_limited"
    WIDEBAND_DISAGREE = "wideband_disagree"
    INSUFFICIENT_SAMPLES = "insufficient_samples"
    STAGE_LOCKED = "stage_locked"
    SENSOR_FAULT = "sensor_fault"
    # v0.2 additions (found by adversarial tests / schema stress test)
    INVALID_VALUE = "invalid_value"
    OFF_TABLE = "off_table"
    WRONG_ENGINE = "wrong_engine"
    STALE_TIMESTAMP = "stale_timestamp"
    STALE_BASIS = "stale_basis"
    LEARNING_FROZEN = "learning_frozen"


@dataclass(frozen=True)
class EnvelopeConfig:
    engine_id: int
    rpm_bins: int = 16
    map_bins: int = 16
    max_fuel_delta_pct: float = 5.0      # per proposal, relative to value_before
    max_spark_delta_deg: float = 2.0     # per proposal
    spark_min_deg: float = 0.0           # absolute table limits
    spark_max_deg: float = 36.0          # TODO: confirm for marinized 350 + Mallory/HEI
    afr_floor: float = 10.5
    afr_ceiling: float = 16.0
    ve_min: float = 10.0
    ve_max: float = 150.0
    min_evidence_samples: int = 50
    rate_limit_touches: int = 3          # applied writes per cell...
    rate_limit_window_s: float = 60.0    # ...per this window
    max_age_s: float = 2.0               # proposal older than this vs. now → stale
    max_future_skew_s: float = 0.5       # proposal timestamp ahead of now → reject
    clamp_deltas: bool = True            # delta overshoot → clamp (True) or reject (False)


@dataclass(frozen=True)
class Proposal:
    engine_id: int
    table: str
    rpm_idx: int
    map_idx: int
    value_before: float
    value_proposed: float
    timestamp_s: float
    evidence_samples: int = 0
    proposal_id: int = 0


@dataclass(frozen=True)
class Result:
    decision: Decision
    reason: Reason
    value_before: float
    value_accepted: float

    @property
    def applied(self) -> bool:
        return self.decision in (Decision.ACCEPTED, Decision.CLAMPED)


def _finite(x) -> bool:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return False
    return math.isfinite(x)


def _is_int(x) -> bool:
    return isinstance(x, int) and not isinstance(x, bool)


class Envelope:
    """Stateful only for the current table snapshot and rate-limit history."""

    def __init__(self, config: EnvelopeConfig, tables: Optional[dict] = None):
        self.cfg = config
        # tables[name][(rpm_idx, map_idx)] = current value
        self.tables: dict[str, dict[tuple[int, int], float]] = tables or {t.value: {} for t in Table}
        self._touches: dict[tuple[str, int, int], deque] = defaultdict(deque)
        self._last_ts: dict[tuple[str, int, int], float] = {}
        self.frozen = False  # set by wideband cross-check / curriculum abort

    def current(self, table: str, r: int, m: int) -> Optional[float]:
        return self.tables.get(table, {}).get((r, m))

    def _reject(self, p, reason: Reason) -> Result:
        vb = p.value_before if _finite(p.value_before) else float("nan")
        return Result(Decision.REJECTED, reason, vb, vb)

    def evaluate(
        self,
        p: Proposal,
        now_s: float,
        cell_allowed: Optional[Callable[[str, int, int], bool]] = None,
        commit: bool = True,
    ) -> Result:
        c = self.cfg
        # 1. identity & structure
        if not _is_int(p.engine_id) or p.engine_id != c.engine_id:
            return self._reject(p, Reason.WRONG_ENGINE)
        if p.table not in {t.value for t in Table}:
            return self._reject(p, Reason.OFF_TABLE)
        if not (_is_int(p.rpm_idx) and _is_int(p.map_idx)) or not (
            0 <= p.rpm_idx < c.rpm_bins and 0 <= p.map_idx < c.map_bins
        ):
            return self._reject(p, Reason.OFF_TABLE)
        if not (_finite(p.value_before) and _finite(p.value_proposed) and _finite(p.timestamp_s) and _finite(now_s)):
            return self._reject(p, Reason.INVALID_VALUE)
        if not _is_int(p.evidence_samples) or p.evidence_samples < 0:
            return self._reject(p, Reason.INVALID_VALUE)
        # 2. freshness
        if now_s - p.timestamp_s > c.max_age_s or p.timestamp_s - now_s > c.max_future_skew_s:
            return self._reject(p, Reason.STALE_TIMESTAMP)
        key = (p.table, p.rpm_idx, p.map_idx)
        if key in self._last_ts and p.timestamp_s <= self._last_ts[key]:
            return self._reject(p, Reason.STALE_TIMESTAMP)  # replay / out of order
        cur = self.current(p.table, p.rpm_idx, p.map_idx)
        if cur is not None and cur != p.value_before:
            return self._reject(p, Reason.STALE_BASIS)  # proposal based on an old map
        # 3. gates
        if self.frozen:
            return self._reject(p, Reason.LEARNING_FROZEN)
        if cell_allowed is not None and not cell_allowed(p.table, p.rpm_idx, p.map_idx):
            return self._reject(p, Reason.STAGE_LOCKED)
        if p.evidence_samples < c.min_evidence_samples:
            return self._reject(p, Reason.INSUFFICIENT_SAMPLES)
        # 4. absolute limits on the proposed value (hard reject, never clamp)
        v, vb = float(p.value_proposed), float(p.value_before)
        if p.table == Table.AFR_TARGET.value:
            if v < c.afr_floor:
                return self._reject(p, Reason.AFR_FLOOR)
            if v > c.afr_ceiling:
                return self._reject(p, Reason.AFR_CEILING)
        elif p.table == Table.SPARK.value:
            if not (c.spark_min_deg <= v <= c.spark_max_deg):
                return self._reject(p, Reason.SPARK_LIMIT)
        else:
            if not (c.ve_min <= v <= c.ve_max) or vb <= 0:
                return self._reject(p, Reason.VE_LIMIT)
        # 5. rate limit
        q = self._touches[key]
        while q and p.timestamp_s - q[0] >= c.rate_limit_window_s:
            q.popleft()
        if len(q) >= c.rate_limit_touches:
            return self._reject(p, Reason.RATE_LIMITED)
        # 6. delta limits
        decision, reason, out = Decision.ACCEPTED, Reason.NONE, v
        if p.table == Table.SPARK.value:
            lim, r = c.max_spark_delta_deg, Reason.SPARK_DELTA_EXCEEDED
        elif p.table == Table.VE.value:
            lim, r = abs(vb) * c.max_fuel_delta_pct / 100.0, Reason.FUEL_DELTA_EXCEEDED
        else:
            lim, r = None, None  # afr_target bounded by floor/ceiling only
        if lim is not None and abs(v - vb) > lim + 1e-9:
            if not c.clamp_deltas:
                return self._reject(p, r)
            out = vb + math.copysign(lim, v - vb)
            decision, reason = Decision.CLAMPED, r
        res = Result(decision, reason, vb, out)
        if commit:
            q.append(p.timestamp_s)
            self._last_ts[key] = p.timestamp_s
            self.tables.setdefault(p.table, {})[(p.rpm_idx, p.map_idx)] = out
        return res
