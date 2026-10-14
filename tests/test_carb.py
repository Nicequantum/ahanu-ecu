import math

import jsonschema
import pytest

from carb_helpers import T0, load_samples
from grok_pilot.carb import (JET_LADDER, JET_SIZES, STOCK_1410, CarbReason, EngineRoomMode, JetConfig,
                             analyze_afr, evaluate_jet, jet_change_record, ladder_index, moved_toward,
                             part_number, recommend)
from grok_pilot.envelope import Decision, Envelope, EnvelopeConfig
from grok_pilot.gateway_v2 import check_response_v2, evaluate_response_v2, load_schema_v2
from grok_pilot.schema import validate_record

CARB, EFI = EngineRoomMode.CARB, EngineRoomMode.EFI
CUR = {"primary": 0.113, "secondary": 0.107}


def jp(cur=0.107, prop=0.110, bank="secondary"):
    return {"table": "jet", "bank": bank, "current_size": cur, "proposed_size": prop, "rod": "0.071x0.047",
            "spring": "orange", "rationale": "WOT lean"}


def ev(p, a, **kw):
    kw.setdefault("mode", CARB)
    kw.setdefault("stage", "carb_jetting")
    kw.setdefault("current", CUR)
    return evaluate_jet(p, analysis=a, **kw)


def test_ladder_is_published_0p003_staging():
    assert JET_SIZES == (0.098, 0.101, 0.104, 0.107, 0.110, 0.113, 0.116)
    assert [pn for pn, _ in JET_LADDER] == [1427, 1429, 1430, 1431, 1432, 1433, 1434]
    assert all(abs(b - a - 0.003) < 1e-9 for a, b in zip(JET_SIZES, JET_SIZES[1:]))
    assert part_number(0.113) == 1433 and ladder_index(0.100) is None and ladder_index(float("nan")) is None
    assert STOCK_1410["primary"] == 0.113 and STOCK_1410["secondary"] == 0.107


def test_idle_never_evidence():
    a = analyze_afr(load_samples(afr=11.5, idle_afr=16.5), "secondary")
    assert a.usable and a.mean == pytest.approx(11.5, abs=0.01)
    assert analyze_afr(load_samples(afr=11.5, bank="secondary"), "primary").issues == [CarbReason.INSUFFICIENT_SAMPLES]


@pytest.mark.parametrize("afr,direction,expect", [(12.6, "richer", 0.110), (10.8, "leaner", 0.104), (11.5, "hold", None)])
def test_recommend_one_step_toward_band(afr, direction, expect):
    r = recommend(analyze_afr(load_samples(afr=afr), "secondary"), 0.107)
    assert r.direction == direction and r.proposed == expect


def test_recommend_end_of_ladder():
    r = recommend(analyze_afr(load_samples(afr=12.8), "secondary"), 0.116)
    assert r.proposed is None and r.reason is CarbReason.OFF_LADDER


@pytest.mark.parametrize("kw,reason", [
    (dict(n=30), CarbReason.INSUFFICIENT_SAMPLES),                      # < min_total_samples
    (dict(n=200, cells=tuple((i, 13) for i in range(16))), CarbReason.INSUFFICIENT_SAMPLES),  # 12-13/cell < 20
    (dict(b_offset=0.4), CarbReason.WIDEBAND_DISAGREE),
    (dict(afr=10.2), CarbReason.AFR_FLOOR), (dict(afr=16.4), CarbReason.AFR_CEILING),
    (dict(spread=2.0), CarbReason.AFR_VARIANCE)])
def test_evidence_gates(kw, reason):
    a = analyze_afr(load_samples(**kw), "secondary")
    assert reason in a.issues
    assert ev(jp(), a).reason is a.issues[0]


def test_accept_one_step_richer():
    r = ev(jp(0.107, 0.110), analyze_afr(load_samples(afr=12.6), "secondary"))
    assert r.decision is Decision.ACCEPTED and r.jet_accepted == 0.110


def test_accept_one_step_leaner_primary():
    a = analyze_afr(load_samples(afr=10.8, bank="primary"), "primary")
    r = ev(jp(0.113, 0.110, "primary"), a)
    assert r.decision is Decision.ACCEPTED and r.jet_accepted == 0.110


def test_two_step_clamped_or_rejected():
    a = analyze_afr(load_samples(afr=12.9), "secondary")
    r = ev(jp(0.107, 0.113), a)
    assert (r.decision, r.reason, r.jet_accepted) == (Decision.CLAMPED, CarbReason.JET_STEP_EXCEEDED, 0.110)
    r = ev(jp(0.107, 0.113), a, cfg=JetConfig(clamp_jet_steps=False))
    assert (r.decision, r.reason, r.jet_accepted) == (Decision.REJECTED, CarbReason.JET_STEP_EXCEEDED, 0.107)


@pytest.mark.parametrize("p,kw,reason", [
    (jp(0.107, 0.104), {}, CarbReason.WRONG_DIRECTION),        # lean data, leaner jet
    (jp(0.107, 0.100), {}, CarbReason.OFF_LADDER),
    (jp(0.110, 0.113), {}, CarbReason.STALE_BASIS),
    (jp(0.107, 0.107), {}, CarbReason.INVALID_VALUE),
    (jp(0.107, float("nan")), {}, CarbReason.INVALID_VALUE),
    ({**jp(), "table": "ve"}, {}, CarbReason.OFF_TABLE),
    ({**jp(), "bank": "rear"}, {}, CarbReason.OFF_TABLE),
    (jp(), {"mode": EFI}, CarbReason.STAGE_LOCKED),
    (jp(), {"stage": "load_test"}, CarbReason.STAGE_LOCKED),
    (jp(), {"experiment_open": True}, CarbReason.EXPERIMENT_OPEN)])
def test_jet_rejections(p, kw, reason):
    r = ev(p, analyze_afr(load_samples(afr=12.6), "secondary"), **kw)
    assert r.decision is Decision.REJECTED and r.reason is reason
    assert r.jet_accepted == r.jet_before or math.isnan(r.jet_before)


def test_in_band_rejects_any_change():
    r = ev(jp(0.107, 0.110), analyze_afr(load_samples(afr=11.6), "secondary"))
    assert r.reason is CarbReason.WRONG_DIRECTION


def test_deterministic():
    a1 = analyze_afr(load_samples(afr=12.6), "secondary")
    a2 = analyze_afr(list(reversed(load_samples(afr=12.6))), "secondary")
    assert a1 == a2 and ev(jp(), a1) == ev(jp(), a2)


def test_moved_toward():
    assert moved_toward(12.6, 11.9, 11, 12) and moved_toward(12.6, 12.3, 11, 12)
    assert not moved_toward(12.6, 12.9, 11, 12) and not moved_toward(10.8, 10.5, 11, 12)


def test_jet_change_records_validate():
    before = analyze_afr(load_samples(afr=12.6), "secondary")
    p = jp()
    res = ev(p, before)
    hdr = {"engine_id": 0, "boot_id": 9, "seq": 500, "timestamp_us": T0 + 30_000_000, "stage": "carb_jetting"}
    r1 = jet_change_record(header=hdr, proposal_id=1, request_id="r", model_version="m", source="mac_studio",
                           proposal=p, result=res, before=before)
    assert validate_record(r1) == [] and r1["phase"] == "proposed"
    after = analyze_afr(load_samples(afr=11.8, t0=T0 + 60_000_000), "secondary")
    r2 = jet_change_record(header={**hdr, "seq": 900, "timestamp_us": T0 + 90_000_000}, proposal_id=1,
                           request_id="r", model_version="m", source="mac_studio", proposal=p, result=res,
                           before=before, swap_declared_us=T0 + 40_000_000, after=after)
    assert validate_record(r2) == [], validate_record(r2)
    assert r2["moved_toward_target"] is True and r2["afr_delta"] == pytest.approx(-0.8, abs=0.01)
    rj = ev(jp(0.107, 0.113), before, cfg=JetConfig(clamp_jet_steps=False))
    r3 = jet_change_record(header={**hdr, "seq": 501}, proposal_id=2, request_id="r", model_version="m",
                           source="mac_studio", proposal=jp(0.107, 0.113), result=rj, before=before)
    assert validate_record(r3) == [] and r3["reject_reason"] == "jet_step_exceeded"


# ---------------------------------------------------------------- gateway v2
NOW = 5000.0


def resp(mode="carb", proposals=None, jetting=None, stage="carb_jetting"):
    r = {"schema": "grok-pilot.proposal-response.v2", "request_id": "q", "model_version": "m", "engine_id": 0,
         "stage": stage, "mode": "copilot", "engine_room_mode": mode, "explanation": "x", "anomalies": [],
         "proposals": proposals if proposals is not None else []}
    if jetting is not None:
        r["jetting"] = jetting
    return r


def prop(table, before, after, r=7, m=10):
    return {"table": table, "rpm_idx": r, "map_idx": m, "value_before": before, "value_proposed": after,
            "evidence_samples": 100, "confidence": 0.8, "rationale": "x"}


def env():
    return Envelope(EnvelopeConfig(engine_id=0), tables={"ve": {(7, 10): 80.0}, "spark": {(7, 10): 24.0},
                                                         "afr_target": {(7, 10): 14.7}})


def test_schema_v2_validates_examples():
    s = load_schema_v2()
    jsonschema.validate(resp(jetting=jp()), s)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(resp(jetting={**jp(), "table": "ve"}), s)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({k: v for k, v in resp().items() if k != "engine_room_mode"}, s)


def test_carb_mode_rejects_fuel_accepts_spark():
    e = env()
    out = evaluate_response_v2(resp(proposals=[prop("ve", 80.0, 82.0), prop("afr_target", 14.7, 14.5),
                                               prop("spark", 24.0, 25.0)]), e, NOW, "q", NOW - 0.5, mode=CARB)
    d = [(r.decision.value, r.reason.value) for _, r in out.cells]
    assert d == [("rejected", "carb_fuel_locked"), ("rejected", "carb_fuel_locked"), ("accepted", "none")]
    assert e.current("ve", 7, 10) == 80.0 and e.current("spark", 7, 10) == 25.0


def test_carb_gate_blocks_fuel_even_via_cell_allowed():
    out = evaluate_response_v2(resp(proposals=[prop("spark", 24.0, 25.0, r=3)]), env(), NOW, "q", NOW,
                               mode=CARB, cell_allowed=lambda t, r, m: r >= 5)
    assert out.cells[0][1].reason.value == "stage_locked"


def test_efi_mode_v2_matches_envelope_and_locks_jetting():
    out = evaluate_response_v2(resp(mode="efi", stage="cruise", proposals=[prop("ve", 80.0, 82.0)], jetting=jp()),
                               env(), NOW, "q", NOW, mode=EFI)
    assert out.cells[0][1].decision is Decision.ACCEPTED
    assert out.jet.reason is CarbReason.STAGE_LOCKED


def test_gateway_jetting_paths():
    a = analyze_afr(load_samples(afr=12.6), "secondary")
    out = evaluate_response_v2(resp(jetting=jp(0.107, 0.113)), env(), NOW, "q", NOW, mode=CARB,
                               jet_current=CUR, jet_analysis=a)
    assert out.jet.decision is Decision.CLAMPED and out.jet.jet_accepted == 0.110


@pytest.mark.parametrize("r,frag", [(resp(mode="efi"), "engine_room_mode"), (dict(resp(), schema="grok-pilot.proposal-response.v1"), "schema"),
                                    (resp(jetting={"table": "jet"}), "jetting")])
def test_check_response_v2(r, frag):
    errs = check_response_v2(r, "q", 0, CARB)
    assert any(frag in e for e in errs)
    with pytest.raises(ValueError):
        evaluate_response_v2(r, env(), NOW, "q", NOW, mode=CARB)
