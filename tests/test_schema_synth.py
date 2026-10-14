import copy
import json
import math

import pytest

from grok_pilot.schema import validate_record, validate_stream
from grok_pilot.stress import run
from grok_pilot.synth import generate, main


@pytest.fixture(scope="module")
def recs():
    return list(generate(seed=3, max_samples=6000))


def test_generator_volume_and_types(recs):
    types = {r["record_type"] for r in recs}
    assert types == {"sample", "cell_write", "event"}
    assert sum(r["record_type"] == "sample" for r in recs) == 12000
    assert {r["engine_id"] for r in recs} == {0, 1}


def test_every_record_valid_v02(recs):
    res = validate_stream(recs)
    assert res["invalid"] == 0, res["errors"][:5]


def test_covers_all_stages(recs):
    stages = {r["stage"] for r in recs if r["record_type"] == "sample"}
    assert {"cold_start", "warm_idle", "cruise", "load_test"} <= stages


def test_every_proposal_has_decision_and_reason(recs):
    cws = [r for r in recs if r["record_type"] == "cell_write"]
    assert cws and {r["decision"] for r in cws} >= {"accepted", "rejected"}
    for r in cws:
        if r["decision"] == "rejected":
            assert r["reject_reason"] != "none" and r["value_accepted"] == r["value_before"]
        if r["decision"] == "clamped":
            assert abs(r["value_accepted"] - r["value_before"]) <= abs(r["value_before"]) * 0.05 + 0.01


def test_deterministic():
    assert list(generate(seed=9, max_samples=300)) == list(generate(seed=9, max_samples=300))


def test_v01_projection_reveals_gaps():
    res = validate_stream(list(generate(seed=1, max_samples=6000, version="0.1")))
    assert res["invalid"] > 0  # status_change / new reject reasons not representable in v0.1


@pytest.mark.parametrize("mut,frag", [
    (lambda r: r.update(rpm=-1), "rpm"), (lambda r: r.update(rpm=1.5), "rpm"),
    (lambda r: r.update(map_kpa=math.nan), "non-finite"), (lambda r: r.update(engine_id=2), "engine_id"),
    (lambda r: r.pop("afr_target"), "missing"), (lambda r: r.update(bogus=1), "unknown field"),
    (lambda r: r.update(inj_pw_us=[1] * 7), "inj_pw_us"), (lambda r: r.update(oil_alarm=1), "bool"),
    (lambda r: r.update(stage="load"), "stage"), (lambda r: r.update(schema_version="9"), "schema_version"),
    (lambda r: r.update(rpm=True), "rpm")])
def test_validator_catches_bad_samples(recs, mut, frag):
    r = copy.deepcopy(next(x for x in recs if x["record_type"] == "sample" and x["afr_a"] is not None))
    mut(r)
    errs = validate_record(r)
    assert errs and any(frag in e for e in errs)


def test_validator_cell_write_cross_rules(recs):
    r = copy.deepcopy(next(x for x in recs if x["record_type"] == "cell_write" and x["decision"] == "rejected"))
    r["reject_reason"] = "none"
    assert validate_record(r)
    r = copy.deepcopy(next(x for x in recs if x["record_type"] == "cell_write" and x["decision"] == "rejected"))
    r["value_accepted"] = r["value_before"] + 1
    assert validate_record(r)


def test_stream_monotonicity(recs):
    s = [copy.deepcopy(r) for r in recs[:50]]
    e0 = [r for r in s if r["engine_id"] == 0]
    e0[3]["seq"] = e0[2]["seq"]
    assert validate_stream(s)["invalid"] >= 1


def test_cli_writes_jsonl(tmp_path):
    p = tmp_path / "x.jsonl"
    main(["--out", str(p), "--samples", "200"])
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    assert validate_stream(lines)["invalid"] == 0


def test_stress_report_shape():
    r = run(samples=3000)
    assert r["v02_invalid"] == 0 and r["fields_added_v02"]["sample"]
