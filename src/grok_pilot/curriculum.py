"""Staged curriculum state machine (pure logic).

cold_start -> warm_idle -> cruise -> load_test   (street: future, disabled)

Each ``step(obs)`` returns a ``StepResult`` with the current stage, a
green/yellow/red status, and any transition. Thresholds are placeholders
(TODO: validate on the real engines); they live in ``CurriculumConfig``.

Status semantics:
  green  - all checks pass; good-sample counters advance.
  yellow - soft warning (mild wideband disagreement, warm coolant, low
           battery, AFR out of band); counters HOLD, no progression.
  red    - fault. Severe faults (lean cut, low oil, overheat, EGT, oil alarm)
           ABORT (learning frozen, needs operator reset). Moderate faults
           (sensor fault, gross wideband disagreement) REGRESS one stage
           once per fault episode (latched until a non-red sample).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Stage(str, Enum):
    COLD_START = "cold_start"
    WARM_IDLE = "warm_idle"
    CRUISE = "cruise"
    LOAD_TEST = "load_test"
    STREET = "street"      # future; only reachable if enable_street
    ABORTED = "aborted"
    CARB_JETTING = "carb_jetting"  # carb mode only; a branch off load_test, never in ORDER (carb_curriculum.py)


ORDER = [Stage.COLD_START, Stage.WARM_IDLE, Stage.CRUISE, Stage.LOAD_TEST, Stage.STREET]


class Status(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


@dataclass(frozen=True)
class CurriculumConfig:
    warm_coolant_c: float = 60.0          # cold_start -> warm_idle
    cruise_coolant_c: float = 70.0        # min coolant to leave warm_idle
    overheat_c: float = 95.0              # red/abort (raw-water cooled marine 5.7 ~ 60-80 °C thermostat)
    warn_coolant_c: float = 88.0          # yellow
    idle_rpm: tuple = (500.0, 1200.0)
    cruise_rpm: tuple = (2000.0, 3500.0)
    load_rpm: tuple = (3500.0, 5000.0)
    afr_band: tuple = (11.0, 15.5)        # sane-measurement band for "good" samples
    wideband_warn_afr: float = 0.7        # |A-B| yellow
    wideband_fault_afr: float = 1.5       # |A-B| red -> regress
    min_oil_kpa_running: float = 70.0     # red/abort above 1000 rpm (TODO: VDO 360-004 calibration)
    oil_check_rpm: float = 1000.0
    max_egt_c: float = 760.0              # red/abort (TODO: riser-position-specific)
    min_battery_v: float = 11.5           # yellow
    samples_to_advance: dict = field(default_factory=lambda: {
        Stage.COLD_START: 300, Stage.WARM_IDLE: 600, Stage.CRUISE: 900, Stage.LOAD_TEST: 1200})
    require_operator_confirm: frozenset = frozenset({Stage.WARM_IDLE, Stage.CRUISE, Stage.LOAD_TEST})
    enable_street: bool = False


@dataclass(frozen=True)
class Observation:
    rpm: float
    coolant_c: float
    afr_a: Optional[float]
    afr_b: Optional[float]
    afr_a_ok: bool = True
    afr_b_ok: bool = True
    battery_v: float = 13.8
    oil_press_kpa: Optional[float] = None
    oil_alarm: bool = False
    egt_c: Optional[float] = None
    lean_cut_active: bool = False
    sensor_fault: bool = False
    operator_confirm: bool = False


@dataclass(frozen=True)
class StepResult:
    stage: Stage
    status: Status
    reasons: tuple
    transition: Optional[tuple] = None   # (from, to, cause)


def _bad(x) -> bool:
    return x is None or isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)


class Curriculum:
    def __init__(self, config: CurriculumConfig = CurriculumConfig(), stage: Stage = Stage.COLD_START):
        self.cfg = config
        self.stage = stage
        self.good = 0
        self._regress_latched = False  # one regression per fault episode

    # ---- helpers -------------------------------------------------------
    def _rpm_band(self, stage: Stage):
        c = self.cfg
        return {Stage.COLD_START: c.idle_rpm, Stage.WARM_IDLE: c.idle_rpm, Stage.CRUISE: c.cruise_rpm,
                Stage.LOAD_TEST: c.load_rpm, Stage.STREET: (c.idle_rpm[0], c.load_rpm[1])}[stage]

    def learning_allowed(self) -> bool:
        return self.stage not in (Stage.ABORTED, Stage.COLD_START)

    def allowed_rpm_band(self):
        """RPM band whose cells the AI may propose for, or None."""
        return None if not self.learning_allowed() else self._rpm_band(self.stage)

    def reset(self, operator_ack: bool) -> bool:
        """Leave ABORTED only with explicit operator acknowledgement; restart at cold_start."""
        if self.stage is Stage.ABORTED and operator_ack:
            self.stage, self.good = Stage.COLD_START, 0
            return True
        return False

    def _move(self, to: Stage, cause: str):
        frm = self.stage
        self.stage, self.good = to, 0
        return (frm, to, cause)

    # ---- main ----------------------------------------------------------
    def step(self, o: Observation) -> StepResult:
        c = self.cfg
        if self.stage is Stage.ABORTED:
            return StepResult(Stage.ABORTED, Status.RED, ("aborted_await_reset",))

        severe, moderate, warn = [], [], []
        if _bad(o.rpm) or _bad(o.coolant_c) or _bad(o.battery_v):
            moderate.append("invalid_core_sensor")
        if o.lean_cut_active:
            severe.append("lean_cut")
        if o.oil_alarm:
            severe.append("oil_alarm")
        if not _bad(o.coolant_c) and o.coolant_c >= c.overheat_c:
            severe.append("overheat")
        if o.egt_c is not None and not _bad(o.egt_c) and o.egt_c >= c.max_egt_c:
            severe.append("egt_high")
        if (o.oil_press_kpa is not None and not _bad(o.oil_press_kpa) and not _bad(o.rpm)
                and o.rpm >= c.oil_check_rpm and o.oil_press_kpa < c.min_oil_kpa_running):
            severe.append("low_oil_pressure")
        if o.sensor_fault:
            moderate.append("sensor_fault")
        a_ok = o.afr_a_ok and not _bad(o.afr_a)
        b_ok = o.afr_b_ok and not _bad(o.afr_b)
        if not (a_ok and b_ok):
            # widebands not ready: fine during cold start, a fault once learning
            (warn if self.stage is Stage.COLD_START else moderate).append("wideband_not_ready")
        else:
            d = abs(o.afr_a - o.afr_b)
            if d >= c.wideband_fault_afr:
                moderate.append("wideband_disagree")
            elif d >= c.wideband_warn_afr:
                warn.append("wideband_mismatch")
            lo, hi = c.afr_band
            if not (lo <= o.afr_a <= hi and lo <= o.afr_b <= hi):
                warn.append("afr_out_of_band")
        if not _bad(o.coolant_c) and c.warn_coolant_c <= o.coolant_c < c.overheat_c:
            warn.append("coolant_warm")
        if not _bad(o.battery_v) and o.battery_v < c.min_battery_v:
            warn.append("battery_low")

        if severe:
            t = self._move(Stage.ABORTED, ",".join(severe))
            return StepResult(self.stage, Status.RED, tuple(severe + moderate + warn), t)
        if moderate:
            t = None
            idx = ORDER.index(self.stage)
            if idx > 0 and not self._regress_latched:
                t = self._move(ORDER[idx - 1], ",".join(moderate))
            else:
                self.good = 0
            self._regress_latched = True
            return StepResult(self.stage, Status.RED, tuple(moderate + warn), t)
        if warn:
            self._regress_latched = False
            return StepResult(self.stage, Status.YELLOW, tuple(warn))

        self._regress_latched = False
        # green: count samples that are actually in this stage's operating band
        lo, hi = self._rpm_band(self.stage)
        if lo <= o.rpm <= hi:
            self.good += 1
        t = self._maybe_advance(o)
        return StepResult(self.stage, Status.GREEN, (), t)

    def _maybe_advance(self, o: Observation):
        c = self.cfg
        s = self.stage
        if s is Stage.STREET:
            return None
        need = c.samples_to_advance.get(s)
        if need is None or self.good < need:
            return None
        nxt = ORDER[ORDER.index(s) + 1]
        if nxt is Stage.STREET and not c.enable_street:
            return None
        if s is Stage.COLD_START and o.coolant_c < c.warm_coolant_c:
            return None
        if s is Stage.WARM_IDLE and o.coolant_c < c.cruise_coolant_c:
            return None
        if s in c.require_operator_confirm and not o.operator_confirm:
            return None
        return self._move(nxt, "criteria_met")
