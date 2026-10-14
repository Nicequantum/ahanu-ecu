import json

import jsonschema
import pytest

from grok_pilot.envelope import Envelope, EnvelopeConfig
from grok_pilot.grok import evaluate_response, load_schema
from grok_pilot.prompts import BudgetError, assemble_context, estimate_tokens, load_examples, render
from grok_pilot.synth import generate

SCHEMA = load_schema()
EXAMPLES = load_examples()


@pytest.fixture(scope="module")
def recs():
    return list(generate(seed=5, max_samples=6000))


def ctx_from(recs, engine_id=1, window_s=120.0, **kw):
    samples = [r for r in recs if r["record_type"] == "sample"]
    cws = [r for r in recs if r["record_type"] == "cell_write"]
    now = max(s["timestamp_us"] for s in samples)
    last = max((s for s in samples if s["engine_id"] == engine_id), key=lambda s: s["timestamp_us"])
    tables = {"ve": {(r, m): 60.0 + r * 1.5 + m for r in range(5, 9) for m in range(8, 12)}}
    return assemble_context(request_id="req-t-1", engine_id=engine_id, stage=last["stage"], status=last["status"],
                            allowed_rpm_idx=range(5, 9), envelope_cfg=EnvelopeConfig(engine_id=engine_id),
                            samples=samples, cell_writes=cws, tables=tables, now_us=now, window_s=window_s, **kw)


def test_render_is_deterministic(recs):
    a, b = render(ctx_from(recs)), render(ctx_from(list(reversed(recs))))
    assert a.system == b.system and a.user == b.user and a.tokens_total == b.tokens_total


def test_required_sections_present(recs):
    p = render(ctx_from(recs))
    for sec in ("## REQUEST", "## ENVELOPE LIMITS", "## ENGINE STATE", "## TABLE CELLS", "## RECENT AUDIT TRAIL",
                "## RECENT HISTORY", "## RESPONSE", "grok-pilot.proposal-response.v1", "req-t-1"):
        assert sec in p.user, sec
    for phrase in ("ADVISORY ONLY", "copilot", "stale_basis", "separate exhaust banks"):
        assert phrase in p.system
    state = json.loads(p.user.split("## ENGINE STATE (latest sample per engine)\n")[1].split("\n")[0])
    assert set(state) == {"0", "1"} and state["0"] and state["1"]  # both engines
    env = json.loads(p.user.split("## ENVELOPE LIMITS\n")[1].split("\n")[0])
    assert env["max_fuel_delta_pct"] == 5.0 and env["afr_floor"] == 10.5


def test_audit_trail_has_reasons(recs):
    p = render(ctx_from(recs, engine_id=0))
    audit = json.loads(p.user.split("## RECENT AUDIT TRAIL (newest last; target engine)\n")[1].split("\n")[0])
    assert audit and all("reject_reason" in a and "decision" in a for a in audit)
    assert len(audit) <= 20


def test_no_nan_in_prompt(recs):
    rs = [dict(r) for r in recs]
    for r in rs:
        if r["record_type"] == "sample":
            r["afr_a"] = float("nan")
    p = render(ctx_from(rs))
    assert "NaN" not in p.user and "Infinity" not in p.user


def test_budget_truncates_history_first(recs):
    full = render(ctx_from(recs), budget_tokens=100000)
    assert not full.truncated
    small = render(ctx_from(recs), budget_tokens=full.tokens_total - 500)
    assert small.tokens_total <= small.budget
    assert small.truncated.get("history_rows", 0) > 0 and "audit" not in small.truncated


def test_budget_cap_respected_and_mandatory_never_cut(recs):
    ctx = ctx_from(recs)
    tiny = render(ctx, budget_tokens=2500)
    assert tiny.tokens_total <= 2500
    assert "## ENVELOPE LIMITS" in tiny.user and "## ENGINE STATE" in tiny.user
    with pytest.raises(BudgetError):
        render(ctx, budget_tokens=500)


def test_estimate_tokens_heuristic():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 4000) == 1000
    assert estimate_tokens("12") == 1 and estimate_tokens("{}") == 2
    assert estimate_tokens("é" * 3) == 3
    assert estimate_tokens("  \n\t ") == 0


def _env():
    e = Envelope(EnvelopeConfig(engine_id=1))
    for r in range(16):
        for m in range(16):
            e.tables["ve"][(r, m)] = 80.0
            e.tables["spark"][(r, m)] = 24.0
            e.tables["afr_target"][(r, m)] = 14.7
    return e


def test_examples_inventory():
    kinds = [v["kind"] for v in EXAMPLES.values()]
    assert kinds.count("good") >= 3 and kinds.count("bad") >= 6


@pytest.mark.parametrize("name", sorted(EXAMPLES))
def test_example_behaves_as_documented(name):
    ex = EXAMPLES[name]
    exp = ex["expect"]
    if "raw" in ex:
        with pytest.raises(json.JSONDecodeError):
            json.loads(ex["raw"])
        assert exp["parse_ok"] is False
        return
    resp = ex["response"]
    valid = True
    try:
        jsonschema.validate(resp, SCHEMA)
    except jsonschema.ValidationError:
        valid = False
    assert valid is exp["schema_valid"], name
    if not valid:
        assert ex["kind"] == "bad"
        return
    try:
        out = evaluate_response(resp, _env(), 5000.0, "req-ex-1", context_ts_s=4999.5,
                                cell_allowed=lambda t, r, m: 5 <= r <= 9)
        gateway_ok = True
    except ValueError:
        gateway_ok = False
    assert gateway_ok is exp["gateway_ok"], name
    if gateway_ok:
        got = [[res.decision.value, res.reason.value] for _, res in out]
        assert got == exp["decisions"], name
        if ex["kind"] == "bad":
            assert any(d != "accepted" for d, _ in got)  # bad => envelope intervened
        else:
            assert all(d == "accepted" for d, _ in got)
