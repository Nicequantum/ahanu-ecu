import copy

import pytest

from grok_pilot.schema import SCHEMAS, validate_record
from grok_pilot.synth import generate

BASE = {"schema_version": "0.3", "record_type": "jet_change", "engine_id": 0, "boot_id": 7, "seq": 100,
        "timestamp_us": 1791000100000000, "stage": "carb_jetting", "proposal_id": 1, "request_id": "req-j-1",
        "source": "mac_studio", "model_version": "grok-x", "phase": "proposed", "engine_room_mode": "carb",
        "bank": "secondary", "jet_before": 0.107, "jet_proposed": 0.110, "jet_accepted": 0.110, "rod": "0.071x0.047",
        "spring": "orange", "decision": "accepted", "reject_reason": "none", "rationale": "WOT 12.6 lean of 11-12",
        "afr_target_lo": 11.0, "afr_target_hi": 12.0, "before_start_us": 1791000000000000,
        "before_end_us": 1791000060000000, "afr_before_mean": 12.6, "afr_before_std": 0.2, "afr_before_n": 240}
EVAL = {**BASE, "seq": 200, "phase": "evaluated", "swap_declared_us": 1791000070000000,
        "after_start_us": 1791000080000000, "after_end_us": 1791000140000000, "afr_after_mean": 11.8,
        "afr_after_std": 0.2, "afr_after_n": 230, "afr_delta": -0.8, "moved_toward_target": True}


def test_v02_records_valid_as_v03():
    for r in generate(seed=3, max_samples=500):
        r = dict(r, schema_version="0.3")
        assert validate_record(r) == [], r


def test_v02_unchanged():
    assert "jet_change" not in SCHEMAS["0.2"] and "carb_jetting" not in SCHEMAS["0.2"]["sample"]["stage"].enum


@pytest.mark.parametrize("rec", [BASE, EVAL])
def test_jet_change_valid(rec):
    assert validate_record(rec) == []


def test_jet_change_rejected_valid():
    r = dict(BASE, decision="rejected", reject_reason="jet_step_exceeded", jet_accepted=0.107, jet_proposed=0.116)
    assert validate_record(r) == []


@pytest.mark.parametrize("mut,frag", [
    (dict(decision="rejected", reject_reason="none", jet_accepted=0.107), "needs a reason"),
    (dict(decision="rejected", reject_reason="wrong_direction"), "jet_accepted"),
    (dict(decision="accepted", reject_reason="afr_variance"), "reason none"),
    (dict(bank="tertiary"), "bank"), (dict(spring="green"), "spring"), (dict(engine_room_mode="efi"), "engine_room_mode"),
    (dict(before_end_us=1), "before window"), (dict(afr_target_hi=10.0), "afr_target_hi"),
    (dict(afr_after_mean=11.9), "after-swap"), (dict(schema_version="0.2"), "unknown record_type")])
def test_jet_change_invalid(mut, frag):
    errs = validate_record({**BASE, **mut})
    assert errs and any(frag in e for e in errs), errs


@pytest.mark.parametrize("mut,frag", [
    (dict(afr_delta=-0.5), "afr_delta"), (dict(swap_declared_us=1791000000000001), "ordered"),
    (dict(moved_toward_target=None), "moved_toward_target"),
    (dict(decision="rejected", reject_reason="wrong_direction", jet_accepted=0.107), "cannot be evaluated")])
def test_jet_change_evaluated_invalid(mut, frag):
    errs = validate_record({k: v for k, v in {**EVAL, **mut}.items() if v is not None})
    assert errs and any(frag in e for e in errs), errs
