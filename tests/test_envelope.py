import math

import pytest

from grok_pilot.envelope import Decision, Envelope, EnvelopeConfig, Proposal, Reason

NOW = 1000.0


def env(**kw):
    e = Envelope(EnvelopeConfig(engine_id=0, **kw))
    for r in range(16):
        for m in range(16):
            e.tables["ve"][(r, m)] = 100.0
            e.tables["spark"][(r, m)] = 20.0
            e.tables["afr_target"][(r, m)] = 14.7
    return e


def P(table="ve", r=5, m=5, before=None, prop=None, ts=NOW, n=100, eng=0):
    before = {"ve": 100.0, "spark": 20.0, "afr_target": 14.7}[table] if before is None else before
    prop = before if prop is None else prop
    return Proposal(eng, table, r, m, before, prop, ts, n)


# ---- happy path / exact boundaries ---------------------------------------
def test_accept_within_limits():
    res = env().evaluate(P(prop=103.0), NOW)
    assert res.decision is Decision.ACCEPTED and res.value_accepted == 103.0


@pytest.mark.parametrize("v", [105.0, 95.0])
def test_fuel_delta_exact_boundary_accepted(v):
    assert env().evaluate(P(prop=v), NOW).decision is Decision.ACCEPTED


@pytest.mark.parametrize("v,exp", [(105.0001, 105.0), (94.9, 95.0), (140.0, 105.0)])
def test_fuel_delta_over_is_clamped(v, exp):
    res = env().evaluate(P(prop=v), NOW)
    assert res.decision is Decision.CLAMPED and res.reason is Reason.FUEL_DELTA_EXCEEDED
    assert res.value_accepted == pytest.approx(exp)


def test_fuel_delta_reject_mode():
    res = env(clamp_deltas=False).evaluate(P(prop=106.0), NOW)
    assert res.decision is Decision.REJECTED and res.reason is Reason.FUEL_DELTA_EXCEEDED


@pytest.mark.parametrize("v,dec", [(22.0, Decision.ACCEPTED), (18.0, Decision.ACCEPTED), (22.01, Decision.CLAMPED), (17.0, Decision.CLAMPED)])
def test_spark_delta_boundary(v, dec):
    res = env().evaluate(P("spark", prop=v), NOW)
    assert res.decision is dec
    assert 18.0 <= res.value_accepted <= 22.0


@pytest.mark.parametrize("v,reason", [(-0.1, Reason.SPARK_LIMIT), (36.01, Reason.SPARK_LIMIT)])
def test_spark_absolute_limits(v, reason):
    e = env()
    e.tables["spark"][(5, 5)] = 35.0 if v > 30 else 1.0
    res = e.evaluate(P("spark", before=e.tables["spark"][(5, 5)], prop=v), NOW)
    assert res.decision is Decision.REJECTED and res.reason is reason


def test_spark_exact_absolute_limits_ok():
    e = env()
    e.tables["spark"][(5, 5)] = 35.0
    assert e.evaluate(P("spark", before=35.0, prop=36.0), NOW).decision is Decision.ACCEPTED


@pytest.mark.parametrize("v,dec,reason", [
    (10.5, Decision.ACCEPTED, Reason.NONE), (16.0, Decision.ACCEPTED, Reason.NONE),
    (10.49, Decision.REJECTED, Reason.AFR_FLOOR), (16.01, Decision.REJECTED, Reason.AFR_CEILING),
    (0.0, Decision.REJECTED, Reason.AFR_FLOOR), (-14.7, Decision.REJECTED, Reason.AFR_FLOOR)])
def test_afr_floor_ceiling(v, dec, reason):
    res = env().evaluate(P("afr_target", prop=v), NOW)
    assert (res.decision, res.reason) == (dec, reason)


@pytest.mark.parametrize("v", [9.99, 150.01, -5.0, 0.0])
def test_ve_absolute_limits(v):
    assert env().evaluate(P(prop=v), NOW).reason is Reason.VE_LIMIT


# ---- adversarial inputs ----------------------------------------------------
@pytest.mark.parametrize("field,val", [
    ("prop", math.nan), ("prop", math.inf), ("prop", -math.inf), ("before", math.nan),
    ("ts", math.nan), ("ts", math.inf), ("prop", "105"), ("prop", None), ("prop", True)])
def test_non_finite_or_wrong_type_rejected(field, val):
    kw = {"prop": 101.0, "before": 100.0, "ts": NOW}
    kw[field] = val
    res = env().evaluate(Proposal(0, "ve", 5, 5, kw["before"], kw["prop"], kw["ts"], 100), NOW)
    assert res.decision is Decision.REJECTED and res.reason is Reason.INVALID_VALUE


def test_huge_values_rejected_not_clamped_into_table():
    e = env()
    for v in (1e308, -1e308, 2**63):
        res = e.evaluate(P(prop=v), NOW)
        assert res.decision is Decision.REJECTED and res.reason is Reason.VE_LIMIT
    assert e.tables["ve"][(5, 5)] == 100.0


def test_now_nan_rejected():
    assert env().evaluate(P(prop=101.0), math.nan).reason is Reason.INVALID_VALUE


@pytest.mark.parametrize("r,m", [(-1, 0), (0, -1), (16, 0), (0, 16), (10**9, 0), (1.5, 2), ("3", 3), (True, 1)])
def test_off_table(r, m):
    assert env().evaluate(P(r=r, m=m, before=100.0, prop=101.0), NOW).reason is Reason.OFF_TABLE


def test_unknown_table():
    assert env().evaluate(Proposal(0, "boost", 1, 1, 1.0, 1.0, NOW, 100), NOW).reason is Reason.OFF_TABLE


@pytest.mark.parametrize("eng", [1, -1, 2, "0", None, True, 0.0])
def test_wrong_engine(eng):
    assert env().evaluate(P(eng=eng, prop=101.0), NOW).reason is Reason.WRONG_ENGINE


@pytest.mark.parametrize("ts", [NOW - 2.0001, NOW - 3600, 0.0, NOW + 0.5001, NOW + 1e9])
def test_stale_or_future_timestamp(ts):
    assert env().evaluate(P(prop=101.0, ts=ts), NOW).reason is Reason.STALE_TIMESTAMP


@pytest.mark.parametrize("ts", [NOW - 2.0, NOW + 0.5])
def test_timestamp_exact_boundary_ok(ts):
    assert env().evaluate(P(prop=101.0, ts=ts), NOW).decision is Decision.ACCEPTED


def test_replay_rejected():
    e = env()
    assert e.evaluate(P(prop=101.0, ts=NOW), NOW).applied
    # same timestamp, rebased to the new value: still a replay
    assert e.evaluate(P(before=101.0, prop=102.0, ts=NOW), NOW).reason is Reason.STALE_TIMESTAMP


def test_stale_basis_rejected():
    e = env()
    assert e.evaluate(P(before=90.0, prop=92.0), NOW).reason is Reason.STALE_BASIS


@pytest.mark.parametrize("n,ok", [(49, False), (50, True), (-1, False)])
def test_evidence_boundary(n, ok):
    res = env().evaluate(P(prop=101.0, n=n), NOW)
    assert res.applied is ok


def test_frozen_rejects():
    e = env()
    e.frozen = True
    assert e.evaluate(P(prop=101.0), NOW).reason is Reason.LEARNING_FROZEN


def test_stage_lock():
    res = env().evaluate(P(prop=101.0), NOW, cell_allowed=lambda t, r, m: r < 5)
    assert res.reason is Reason.STAGE_LOCKED


# ---- rate limiting -------------------------------------------------------
def test_rate_limit_and_window_boundary():
    e = env()
    v = 100.0
    for k in range(3):
        res = e.evaluate(P(before=v, prop=v + 1, ts=NOW + k), NOW + k)
        assert res.applied
        v = res.value_accepted
    assert e.evaluate(P(before=v, prop=v + 1, ts=NOW + 3), NOW + 3).reason is Reason.RATE_LIMITED
    # first touch at NOW expires exactly at NOW+60
    assert e.evaluate(P(before=v, prop=v + 1, ts=NOW + 60), NOW + 60).applied


def test_rate_limit_is_per_cell():
    e = env()
    for k in range(3):
        e.evaluate(P(before=100.0 + k, prop=101.0 + k, ts=NOW + k), NOW + k)
    assert e.evaluate(P(r=6, prop=101.0, ts=NOW + 3), NOW + 3).applied


def test_rejections_do_not_mutate_or_consume_rate_budget():
    e = env()
    for k in range(10):
        e.evaluate(P(prop=math.nan, ts=NOW + k), NOW + k)
    assert e.tables["ve"][(5, 5)] == 100.0
    assert e.evaluate(P(prop=101.0, ts=NOW + 10), NOW + 10).applied


def test_ratchet_attack_bounded_by_rate_limit():
    """A model asking +5 % repeatedly can move a cell at most 3 x 5 % per minute."""
    e = env()
    v = 100.0
    for k in range(100):
        t = NOW + k * 0.5
        res = e.evaluate(P(before=v, prop=v * 10, ts=t), t)
        if res.applied:
            v = res.value_accepted
    assert v <= 100.0 * 1.05 ** 3 * 1.05 + 1e-6  # 50 s elapsed → one window (+ at most one extra after expiry)


def test_determinism():
    a, b = env(), env()
    props = [P(prop=x, ts=NOW + i) for i, x in enumerate([101, 130, math.nan, 99])]
    ra = [a.evaluate(p, p.timestamp_s) for p in props]
    rb = [b.evaluate(p, p.timestamp_s) for p in props]
    assert [(r.decision, r.reason) for r in ra] == [(r.decision, r.reason) for r in rb]


def test_commit_false_is_dry_run():
    e = env()
    e.evaluate(P(prop=104.0), NOW, commit=False)
    assert e.tables["ve"][(5, 5)] == 100.0
