"""Engine-room mode wiring for the curriculum, plus the carb_jetting branch.

``ModeCurriculum`` wraps the unchanged EFI ``Curriculum``:

* mode EFI: a pure pass-through. Stages, status and cell gates are identical to ``Curriculum``.
* mode CARB: the same stages and safety checks, but only spark is learnable at any
  stage (``cell_allowed``). From ``load_test`` the operator can enter the
  ``carb_jetting`` branch, gated on WOT/on-plane AFR evidence:
  - refuses on low sample count, high AFR variance under load, wideband
    disagreement, or AFR outside floor/ceiling (the same gates as ``carb.analyze_afr``);
  - needs operator confirmation.
  Any red step (abort or regress) leaves the branch. A non-fatal yellow keeps it.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Optional

from .carb import AfrAnalysis, EngineRoomMode, JetConfig, carb_cell_allowed
from .curriculum import Curriculum, Observation, Stage, StepResult


class ModeCurriculum:
    def __init__(self, mode: EngineRoomMode = EngineRoomMode.EFI, curriculum: Optional[Curriculum] = None,
                 jet_cfg: JetConfig = JetConfig()):
        self.mode = EngineRoomMode(mode)
        self.cur = curriculum or Curriculum()
        self.jet_cfg = jet_cfg
        self.jetting = False

    @property
    def stage(self) -> Stage:
        return Stage.CARB_JETTING if self.jetting else self.cur.stage

    def set_mode(self, mode: EngineRoomMode, operator_ack: bool) -> bool:
        """Switching engine-room mode needs an operator ack; it leaves jetting and restarts the
        curriculum at cold_start (data learned under the other fuel authority doesn't carry over)."""
        mode = EngineRoomMode(mode)
        if mode is self.mode:
            return True
        if not operator_ack:
            return False
        self.mode, self.jetting = mode, False
        self.cur.stage, self.cur.good = Stage.COLD_START, 0
        return True

    def can_enter_jetting(self, analysis: AfrAnalysis) -> list:
        """Reasons it can't enter (empty = OK)."""
        why = []
        if self.mode is not EngineRoomMode.CARB:
            why.append("not_carb_mode")
        if self.cur.stage is not Stage.LOAD_TEST:
            why.append("requires_load_test")
        why += [r.value for r in analysis.issues]
        return why

    def enter_jetting(self, analysis: AfrAnalysis, operator_confirm: bool):
        why = self.can_enter_jetting(analysis)
        if not operator_confirm:
            why.append("operator_confirm_required")
        if why:
            return None, why
        self.jetting = True
        return (Stage.LOAD_TEST, Stage.CARB_JETTING, "criteria_met"), []

    def exit_jetting(self, cause: str = "operator"):
        if not self.jetting:
            return None
        self.jetting = False
        return (Stage.CARB_JETTING, self.cur.stage, cause)

    def step(self, o: Observation) -> StepResult:
        r = self.cur.step(o)
        if not self.jetting:
            return r
        if r.transition is not None or self.cur.stage is not Stage.LOAD_TEST:
            self.jetting = False
            t = (Stage.CARB_JETTING, self.cur.stage, r.transition[2] if r.transition else "left_load_test")
            return replace(r, transition=t)
        return replace(r, stage=Stage.CARB_JETTING)

    def cell_allowed(self, rpm_bins=None):
        """Predicate for Envelope.evaluate. ``rpm_bins``: optional callable rpm_idx -> (lo, hi) rpm."""
        band = self.cur.allowed_rpm_band()

        def base(table, r, m):
            if band is None:
                return False
            if rpm_bins is None:
                return True
            lo, hi = rpm_bins(r)
            return lo >= band[0] and hi <= band[1]
        return carb_cell_allowed(base) if self.mode is EngineRoomMode.CARB else base
