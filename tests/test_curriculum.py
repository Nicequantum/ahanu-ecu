import math

import pytest

from grok_pilot.curriculum import Curriculum, CurriculumConfig, Observation, Stage, Status

FAST = CurriculumConfig(samples_to_advance={Stage.COLD_START: 5, Stage.WARM_IDLE: 5, Stage.CRUISE: 5, Stage.LOAD_TEST: 5})


def obs(rpm=800, cool=75, a=14.7, b=14.7, **kw):
    return Observation(rpm=rpm, coolant_c=cool, afr_a=a, afr_b=b, oil_press_kpa=250, egt_c=500,
                       operator_confirm=kw.pop("confirm", True), **kw)


def feed(c, o, n):
    out = [c.step(o) for _ in range(n)]
    return out[-1]


def drive_to(c, stage):
    plan = [(Stage.COLD_START, obs(800, 65)), (Stage.WARM_IDLE, obs(800, 75)),
            (Stage.CRUISE, obs(2800, 75)), (Stage.LOAD_TEST, obs(4200, 75))]
    for st, o in plan:
        if c.stage is stage:
            return
        feed(c, o, 5)
    assert c.stage is stage


def test_full_progression_mock_stream():
    c = Curriculum(FAST)
    seen = [c.stage]
    coolant = 15.0
    for i in range(400):
        coolant = min(75.0, coolant + 0.5)
        rpm = {Stage.COLD_START: 750, Stage.WARM_IDLE: 800, Stage.CRUISE: 2800, Stage.LOAD_TEST: 4200}[c.stage]
        r = c.step(obs(rpm, coolant))
        assert r.status is Status.GREEN
        if seen[-1] is not c.stage:
            seen.append(c.stage)
    assert seen == [Stage.COLD_START, Stage.WARM_IDLE, Stage.CRUISE, Stage.LOAD_TEST]


def test_street_disabled_by_default_and_enableable():
    c = Curriculum(FAST)
    drive_to(c, Stage.LOAD_TEST)
    feed(c, obs(4200), 50)
    assert c.stage is Stage.LOAD_TEST
    c2 = Curriculum(CurriculumConfig(samples_to_advance=FAST.samples_to_advance, enable_street=True))
    drive_to(c2, Stage.LOAD_TEST)
    feed(c2, obs(4200), 5)
    assert c2.stage is Stage.STREET


def test_cold_start_waits_for_coolant():
    c = Curriculum(FAST)
    feed(c, obs(800, 40), 100)
    assert c.stage is Stage.COLD_START
    c.step(obs(800, 60))
    assert c.stage is Stage.WARM_IDLE


@pytest.mark.parametrize("cool,stays", [(69.9, True), (70.0, False)])
def test_warm_idle_coolant_boundary(cool, stays):
    c = Curriculum(FAST, stage=Stage.WARM_IDLE)
    feed(c, obs(800, cool), 10)
    assert (c.stage is Stage.WARM_IDLE) is stays


def test_operator_confirm_required():
    c = Curriculum(FAST, stage=Stage.WARM_IDLE)
    feed(c, obs(800, 75, confirm=False), 50)
    assert c.stage is Stage.WARM_IDLE
    c.step(obs(800, 75, confirm=True))
    assert c.stage is Stage.CRUISE


def test_out_of_band_rpm_does_not_count():
    c = Curriculum(FAST, stage=Stage.CRUISE)
    feed(c, obs(800), 50)  # idling while in cruise stage
    assert c.stage is Stage.CRUISE and c.good == 0


@pytest.mark.parametrize("kw,reason", [
    ({"a": 14.7, "b": 15.5}, "wideband_mismatch"), ({"cool": 90}, "coolant_warm"),
    ({"battery_v": 11.0}, "battery_low"), ({"a": 10.0, "b": 10.2}, "afr_out_of_band")])
def test_yellow_holds_progress(kw, reason):
    c = Curriculum(FAST, stage=Stage.WARM_IDLE)
    feed(c, obs(800, 75, confirm=False), 3)
    good = c.good
    a, b, cool = kw.pop("a", 14.7), kw.pop("b", 14.7), kw.pop("cool", 75)
    r = c.step(Observation(rpm=800, coolant_c=cool, afr_a=a, afr_b=b, operator_confirm=True, **kw))
    assert r.status is Status.YELLOW and reason in r.reasons
    assert c.good == good and c.stage is Stage.WARM_IDLE


@pytest.mark.parametrize("kw,reason", [
    ({"lean_cut_active": True}, "lean_cut"), ({"oil_alarm": True}, "oil_alarm"),
    ({"coolant_c": 95.0}, "overheat"), ({"egt_c": 760.0}, "egt_high"),
    ({"oil_press_kpa": 69.0, "rpm": 2800}, "low_oil_pressure")])
def test_severe_fault_aborts(kw, reason):
    c = Curriculum(FAST)
    drive_to(c, Stage.CRUISE)
    base = dict(rpm=2800, coolant_c=75, afr_a=14.7, afr_b=14.7, oil_press_kpa=250, egt_c=500)
    base.update(kw)
    r = c.step(Observation(**base))
    assert r.status is Status.RED and c.stage is Stage.ABORTED and reason in r.reasons
    assert r.transition[0] is Stage.CRUISE and r.transition[1] is Stage.ABORTED
    assert not c.learning_allowed() and c.allowed_rpm_band() is None


def test_low_oil_ignored_at_cranking_rpm():
    c = Curriculum(FAST)
    r = c.step(Observation(rpm=200, coolant_c=20, afr_a=None, afr_b=None, afr_a_ok=False, afr_b_ok=False, oil_press_kpa=0))
    assert c.stage is Stage.COLD_START and r.status is not Status.RED


def test_abort_is_sticky_until_operator_reset():
    c = Curriculum(FAST)
    c.step(obs(lean_cut_active=True))
    feed(c, obs(), 100)
    assert c.stage is Stage.ABORTED
    assert not c.reset(operator_ack=False)
    assert c.reset(operator_ack=True) and c.stage is Stage.COLD_START


@pytest.mark.parametrize("kw", [{"sensor_fault": True}, {"a": 14.7, "b": 16.2}, {"afr_a_ok": False}])
def test_moderate_fault_regresses_once_per_episode(kw):
    c = Curriculum(FAST)
    drive_to(c, Stage.LOAD_TEST)
    a, b = kw.pop("a", 14.7), kw.pop("b", 14.7)
    bad = obs(4200, 75, a, b, **kw)
    r = c.step(bad)
    assert r.status is Status.RED and c.stage is Stage.CRUISE
    feed(c, bad, 20)  # persistent fault: no cascade
    assert c.stage is Stage.CRUISE
    c.step(obs(2800))  # clears
    c.step(bad)       # new episode
    assert c.stage is Stage.WARM_IDLE


def test_cold_start_moderate_fault_resets_counter():
    c = Curriculum(FAST)
    feed(c, obs(800, 40), 3)
    c.step(obs(800, 40, sensor_fault=True))
    assert c.stage is Stage.COLD_START and c.good == 0


@pytest.mark.parametrize("bad", [math.nan, math.inf, None])
def test_invalid_core_sensor_is_red(bad):
    c = Curriculum(FAST, stage=Stage.CRUISE)
    r = c.step(Observation(rpm=bad, coolant_c=75, afr_a=14.7, afr_b=14.7))
    assert r.status is Status.RED and c.stage is Stage.WARM_IDLE


def test_widebands_warming_ok_in_cold_start_only():
    c = Curriculum(FAST)
    r = c.step(Observation(rpm=800, coolant_c=20, afr_a=None, afr_b=None, afr_a_ok=False, afr_b_ok=False))
    assert r.status is Status.YELLOW


def test_learning_band_per_stage():
    c = Curriculum(FAST)
    assert c.allowed_rpm_band() is None
    drive_to(c, Stage.CRUISE)
    assert c.allowed_rpm_band() == FAST.cruise_rpm
