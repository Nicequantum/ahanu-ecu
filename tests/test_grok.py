import copy
import json
import math

import jsonschema
import pytest

from grok_pilot.envelope import Decision, Envelope, EnvelopeConfig, Reason
from grok_pilot.grok import build_context, check_response, evaluate_response, load_schema, render_prompt

NOW = 5000.0


def env():
    e = Envelope(EnvelopeConfig(engine_id=1))
    for r in range(16):
        for m in range(16):
            e.tables["ve"][(r, m)] = 80.0
            e.tables["spark"][(r, m)] = 24.0
            e.tables["afr_target"][(r, m)] = 14.7
    return e


def resp(**kw):
    base = {"schema": "grok-pilot.proposal-response.v1", "request_id": "req-1", "model_version": "grok-q4-test",
            "engine_id": 1, "stage": "cruise", "mode": "copilot",
            "proposals": [{"table": "ve", "rpm_idx": 7, "map_idx": 10, "value_before": 80.0, "value_proposed": 82.0,
                           "evidence_samples": 120, "confidence": 0.8, "rationale": "lean 0.3 AFR in cell"}],
            "explanation": "Cruise cell 7/10 runs slightly lean; small VE increase.", "anomalies": []}
    base.update(kw)
    return base


SCHEMA = load_schema()


def test_schema_is_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(SCHEMA)


def test_good_response_validates_and_is_accepted():
    r = resp()
    jsonschema.validate(r, SCHEMA)
    assert check_response(r, "req-1", 1) == []
    [(p, res)] = evaluate_response(r, env(), NOW, "req-1", context_ts_s=NOW - 1)
    assert res.decision is Decision.ACCEPTED and res.value_accepted == 82.0


@pytest.mark.parametrize("mut", [
    lambda r: r.pop("explanation"), lambda r: r.update(mode="yolo"), lambda r: r.update(engine_id=3),
    lambda r: r["proposals"][0].update(rpm_idx=16), lambda r: r["proposals"][0].update(table="boost"),
    lambda r: r["proposals"][0].update(confidence=1.5), lambda r: r.update(extra=1),
    lambda r: r.update(proposals=[r["proposals"][0]] * 17)])
def test_schema_rejects_bad(mut):
    r = resp()
    mut(r)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(r, SCHEMA)


def test_schema_allows_autopilot_but_gateway_rejects_in_v1():
    r = resp(mode="autopilot")
    jsonschema.validate(r, SCHEMA)
    with pytest.raises(ValueError, match="copilot"):
        evaluate_response(r, env(), NOW, "req-1", NOW)


@pytest.mark.parametrize("rid,eng,frag", [("req-0", 1, "request_id"), ("req-1", 0, "engine_id")])
def test_gateway_rejects_mismatched_batch(rid, eng, frag):
    e = env()
    with pytest.raises(ValueError, match=frag):
        evaluate_response(resp(), Envelope(EnvelopeConfig(engine_id=eng)) if eng != 1 else e, NOW, rid, NOW)


def test_nan_in_response_rejected_at_gateway():
    # JSON can't carry NaN under strict parsing, but Python json allows it; gateway must catch it
    r = json.loads(json.dumps(resp()).replace("82.0", "NaN"))
    assert any("non-finite" in e for e in check_response(r, "req-1", 1))


def test_schema_valid_but_envelope_violating_proposals():
    """The JSON Schema says nothing about safety; the envelope decides every proposal."""
    props = [
        {"table": "ve", "rpm_idx": 7, "map_idx": 10, "value_before": 80.0, "value_proposed": 120.0},   # clamp
        {"table": "spark", "rpm_idx": 7, "map_idx": 10, "value_before": 24.0, "value_proposed": 40.0}, # spark limit
        {"table": "afr_target", "rpm_idx": 7, "map_idx": 10, "value_before": 14.7, "value_proposed": 9.0},  # floor
        {"table": "ve", "rpm_idx": 8, "map_idx": 10, "value_before": 70.0, "value_proposed": 71.0},    # stale basis
        {"table": "ve", "rpm_idx": 9, "map_idx": 10, "value_before": 80.0, "value_proposed": 81.0, "evidence_samples": 3},
    ]
    full = [{"evidence_samples": 100, "confidence": 0.5, "rationale": "x", **p} for p in props]
    r = resp(proposals=full)
    jsonschema.validate(r, SCHEMA)
    out = evaluate_response(r, env(), NOW, "req-1", NOW - 0.5)
    got = [(res.decision, res.reason) for _, res in out]
    assert got == [(Decision.CLAMPED, Reason.FUEL_DELTA_EXCEEDED), (Decision.REJECTED, Reason.SPARK_LIMIT),
                   (Decision.REJECTED, Reason.AFR_FLOOR), (Decision.REJECTED, Reason.STALE_BASIS),
                   (Decision.REJECTED, Reason.INSUFFICIENT_SAMPLES)]
    assert out[0][1].value_accepted == pytest.approx(84.0)


def test_stale_context_rejects_all():
    out = evaluate_response(resp(), env(), NOW, "req-1", context_ts_s=NOW - 30)
    assert out[0][1].reason is Reason.STALE_TIMESTAMP


def test_stage_lock_via_cell_allowed():
    out = evaluate_response(resp(), env(), NOW, "req-1", NOW, cell_allowed=lambda t, r, m: r <= 5)
    assert out[0][1].reason is Reason.STAGE_LOCKED


def test_context_and_prompt_contain_required_parts():
    e = env()
    ctx = build_context("req-1", 1, "cruise", "green", {0: [{"rpm": 2800}], 1: [{"rpm": 2810}]}, e.cfg,
                        {"ve": {(7, 10): 80.0}}, allowed_rpm_idx=[5, 6, 7, 8])
    p = render_prompt(ctx)
    for frag in ("ADVISORY ONLY", "grok-pilot.proposal-response.v1", "max_fuel_delta_pct", "afr_floor", "\"0\"", "\"1\"", "7,10", "copilot"):
        assert frag in p
    json.dumps(ctx)  # serialisable
