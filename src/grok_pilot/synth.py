"""Synthetic Teensy log generator (schema v0.1 / v0.2).

Simulates both Mercruiser 5.7s from a cold start through warm idle, cruise
and load test. The curriculum state machine and validation envelope drive the
simulation, so the stage, status and cell_write records are what the real
logic would produce. Physics is deliberately crude: this is for checking the
schema and pipeline, not for modelling the engine.

    python -m grok_pilot.synth --out logs.jsonl --version 0.2 --seed 1
"""
from __future__ import annotations

import argparse
import json
import random
from typing import Iterator

from .curriculum import Curriculum, CurriculumConfig, Observation, Stage
from .envelope import Envelope, EnvelopeConfig, Proposal
from .schema import SCHEMAS

RPM_BIN, MAP_BIN, BINS = 400.0, 7.0, 16
T0_US = 1_791_000_000_000_000  # fixed epoch for reproducibility
STAGE_RPM = {Stage.COLD_START: 750, Stage.WARM_IDLE: 800, Stage.CRUISE: 2800,
             Stage.LOAD_TEST: 4200, Stage.ABORTED: 0, Stage.STREET: 2500}
STAGE_MAP = {Stage.COLD_START: 38, Stage.WARM_IDLE: 36, Stage.CRUISE: 70,
             Stage.LOAD_TEST: 95, Stage.ABORTED: 101, Stage.STREET: 60}


def cell(rpm, map_kpa):
    return min(BINS - 1, int(rpm // RPM_BIN)), min(BINS - 1, int(map_kpa // MAP_BIN))


class EngineSim:
    def __init__(self, engine_id: int, rng: random.Random, inject_fault: bool):
        self.id, self.rng = engine_id, rng
        self.boot_id = rng.randrange(1, 2**31)
        self.seq = 0
        self.cur = Curriculum(CurriculumConfig())
        self.env = Envelope(EnvelopeConfig(engine_id=engine_id))
        # true VE error per cell (fraction); the "AI" should learn it away
        self.ve_err = {(r, m): rng.uniform(-0.08, 0.08) for r in range(BINS) for m in range(BINS)}
        for r in range(BINS):
            for m in range(BINS):
                self.env.tables["ve"][(r, m)] = 60.0 + r * 1.5 + m * 1.0
        self.coolant, self.iat = 15.0, 20.0
        self.pid = 0
        self.bank_b_offset = 0.25 if engine_id == 1 else 0.0
        self.inject_fault = inject_fault
        self.fault_window = None
        self.inj_bias = [rng.uniform(-0.02, 0.02) for _ in range(8)]
        self.afr_hist: list = []
        self.sync_loss = 0
        self.last_status = None

    def hdr(self, rtype, t_us):
        self.seq += 1
        return {"schema_version": "0.2", "record_type": rtype, "engine_id": self.id, "boot_id": self.boot_id,
                "seq": self.seq, "timestamp_us": t_us, "stage": self.cur.stage.value}

    def step(self, i: int, t_us: int, hz: float) -> list[dict]:
        rng, out = self.rng, []
        st = self.cur.stage
        rpm = max(0.0, STAGE_RPM[st] + rng.gauss(0, 15 if st in (Stage.COLD_START, Stage.WARM_IDLE) else 40))
        mapk = max(10.0, STAGE_MAP[st] + rng.gauss(0, 1.0))
        thermostat = 72.0
        self.coolant += (thermostat - self.coolant) * (0.0006 + rpm / 4e6) * (10 / hz)
        self.iat += (45.0 - self.iat) * 0.0005 * (10 / hz)  # closed engine box heat-soak
        r, m = cell(rpm, mapk)
        target = 14.7 if st in (Stage.COLD_START, Stage.WARM_IDLE, Stage.CRUISE) else 12.8
        warm_enrich = max(0.0, (60.0 - self.coolant) * 0.6)
        afr_true = target / (1 + self.ve_err[(r, m)]) / (1 + warm_enrich / 100)
        wb_ready = i > 30 * hz
        a = round(afr_true + rng.gauss(0, 0.08), 2) if wb_ready else None
        b = round(afr_true + self.bank_b_offset + rng.gauss(0, 0.08), 2) if wb_ready else None
        # injected fault on one engine: bank-B sensor drifts during cruise
        if self.inject_fault and st is Stage.CRUISE and self.fault_window is None and self.cur.good > 300:
            self.fault_window = (i, i + int(5 * hz))
        if self.fault_window and self.fault_window[0] <= i < self.fault_window[1] and b is not None:
            b = round(b + 2.5, 2)
        oil = max(0.0, 180 + rpm * 0.05 + rng.gauss(0, 5)) if rpm > 0 else 0.0
        egt = 250 + rpm * 0.08 + (mapk - 30) * 1.5 + rng.gauss(0, 5)
        obs = Observation(rpm=rpm, coolant_c=self.coolant, afr_a=a, afr_b=b, afr_a_ok=wb_ready, afr_b_ok=wb_ready,
                          battery_v=13.9 + rng.gauss(0, 0.05), oil_press_kpa=oil, egt_c=egt, operator_confirm=True)
        res = self.cur.step(obs)
        self.env.frozen = res.status.value == "red"
        if res.transition:
            frm, to, cause = res.transition
            e = self.hdr("event", t_us)
            e.update(event="stage_transition", from_stage=frm.value, to_stage=to.value, detail=cause)
            out.append(e)
        # status_change events are debounced: emitted once a status holds for 1 s
        # (raw per-sample status lives in the sample record)
        if res.status.value != getattr(self, "_pending", None):
            self._pending, self._pending_n = res.status.value, 0
        self._pending_n += 1
        if self._pending != self.last_status and self._pending_n >= hz:
            e = self.hdr("event", t_us)
            e.update(event="status_change", detail=f"{self.last_status}->{self._pending}:{','.join(res.reasons) or 'ok'}")
            out.append(e)
            self.last_status = self._pending
        ve = self.env.tables["ve"][(r, m)]
        pw_base = ve * mapk * 0.15 * (1 + warm_enrich / 100)
        s = self.hdr("sample", t_us)
        s.update(rpm=int(rpm), map_kpa=round(mapk, 1), tps_pct=round(min(100, rpm / 50), 1),
                 coolant_c=round(self.coolant, 1), iat_c=round(self.iat, 1),
                 afr_a=a, afr_b=b, afr_a_status="ok" if wb_ready else "warming",
                 afr_b_status="ok" if wb_ready else "warming", battery_v=round(obs.battery_v, 2),
                 spark_adv_deg=round(10 + min(rpm, 3200) / 160 - (mapk - 30) / 10, 1),
                 inj_pw_us=[int(pw_base * (1 + bb)) for bb in self.inj_bias],
                 ve_cell_rpm_idx=r, ve_cell_map_idx=m, egt_c=round(egt, 2), oil_press_kpa=round(oil, 0),
                 oil_alarm=False, ecu_temp_c=round(self.iat + 5, 0), lean_cut_active=False,
                 afr_target=target, ego_correction_pct=0.0, warmup_enrich_pct=round(warm_enrich, 1),
                 accel_enrich_active=False, sync_loss_count=self.sync_loss, status=res.status.value)
        out.append(s)
        if a is not None:
            self.afr_hist.append((r, m, a, b, target))
            self.afr_hist = self.afr_hist[-200:]
        # "AI" proposal every 5 s during learning stages
        if self.cur.learning_allowed() and i % int(5 * hz) == 0 and self.afr_hist:
            out.append(self.propose(t_us, r, m))
        return out

    def propose(self, t_us, r, m):
        rng = self.rng
        same = [h for h in self.afr_hist if h[0] == r and h[1] == m]
        n = len(same)
        afr_mean = sum(h[2] for h in same) / n if n else 14.7
        afr_b_mean = sum(h[3] for h in same) / n if n else 14.7
        target = same[-1][4] if n else 14.7
        ve = self.env.tables["ve"][(r, m)]
        prop = ve * afr_mean / target
        if rng.random() < 0.1:
            prop = ve * 1.3  # misbehaving model: must be clamped
        self.pid += 1
        band = self.cur.allowed_rpm_band()
        allowed = (lambda tb, rr, mm: band is not None and band[0] <= rr * RPM_BIN + RPM_BIN / 2 <= band[1] + RPM_BIN)
        p = Proposal(self.id, "ve", r, m, ve, round(prop, 2), t_us / 1e6, evidence_samples=n, proposal_id=self.pid)
        res = self.env.evaluate(p, now_s=t_us / 1e6, cell_allowed=allowed)
        if res.applied:  # learned correction removes part of the true error
            self.ve_err[(r, m)] *= max(0.0, 1 - abs(res.value_accepted - ve) / max(1e-9, abs(prop - ve) or 1))
        rec = self.hdr("cell_write", t_us)
        rec.update(proposal_id=self.pid, source="mac_studio", model_version="synthetic-0", table="ve",
                   cell_rpm_idx=r, cell_map_idx=m, value_before=ve, value_proposed=round(prop, 2),
                   value_accepted=round(res.value_accepted, 2) if res.applied else ve,
                   decision=res.decision.value, reject_reason=res.reason.value, evidence_samples=n,
                   afr_mean=round(afr_mean, 2), afr_target=target, request_id=f"req-{self.id}-{self.pid}",
                   afr_b_mean=round(afr_b_mean, 2))
        return rec


def to_version(rec: dict, version: str) -> dict:
    """Project a rich (v0.2) record down to a schema version."""
    if version == "0.2":
        return rec
    spec = SCHEMAS[version][rec["record_type"]]
    out = {k: v for k, v in rec.items() if k in spec}
    out["schema_version"] = version
    m = {"load_test": "load"}
    for k in ("stage", "from_stage", "to_stage"):
        if k in out:
            out[k] = m.get(out[k], out[k])
    return out


def generate(seed: int = 1, hz: float = 10.0, max_samples: int = 6000, version: str = "0.2",
             inject_fault: bool = True) -> Iterator[dict]:
    rng = random.Random(seed)
    sims = [EngineSim(0, random.Random(rng.random()), False), EngineSim(1, random.Random(rng.random()), inject_fault)]
    for s in sims:
        e = s.hdr("event", T0_US)
        e.update(event="boot", detail="synthetic")
        yield to_version(e, version)
    dt = int(1e6 / hz)
    for i in range(1, max_samples + 1):
        t = T0_US + i * dt
        for s in sims:
            for rec in s.step(i, t, hz):
                yield to_version(rec, version)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="-")
    ap.add_argument("--version", default="0.2", choices=sorted(SCHEMAS))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--hz", type=float, default=10.0)
    ap.add_argument("--samples", type=int, default=6000, help="samples per engine")
    a = ap.parse_args(argv)
    f = open(a.out, "w") if a.out != "-" else None
    import sys
    w = f or sys.stdout
    for r in generate(a.seed, a.hz, a.samples, a.version):
        w.write(json.dumps(r) + "\n")
    if f:
        f.close()


if __name__ == "__main__":
    main()
