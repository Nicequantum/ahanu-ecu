from carb_helpers import load_samples
from grok_pilot.carb import EngineRoomMode, analyze_afr
from grok_pilot.carb_curriculum import ModeCurriculum
from grok_pilot.curriculum import ORDER, Curriculum, Observation, Stage

GOOD = Observation(rpm=4000, coolant_c=75, afr_a=12.0, afr_b=12.1)


def at_load(mode=EngineRoomMode.CARB):
    return ModeCurriculum(mode, Curriculum(stage=Stage.LOAD_TEST))


def good_wot():
    return analyze_afr(load_samples(afr=11.6), "secondary")


def test_carb_jetting_not_in_efi_order():
    assert Stage.CARB_JETTING not in ORDER


def test_efi_passthrough_identical():
    a, b = Curriculum(), ModeCurriculum(EngineRoomMode.EFI)
    obs = [Observation(rpm=800, coolant_c=20 + i * 0.05, afr_a=14.0, afr_b=14.1) for i in range(1500)]
    for o in obs:
        assert a.step(o) == b.step(o)
    assert b.cell_allowed()("ve", 1, 1) == (a.allowed_rpm_band() is not None)


def test_carb_mode_spark_only():
    m = at_load()
    f = m.cell_allowed()
    assert f("spark", 10, 10) and not f("ve", 10, 10) and not f("afr_target", 10, 10)
    assert at_load(EngineRoomMode.EFI).cell_allowed()("ve", 10, 10)


def test_enter_jetting_happy_path():
    m = at_load()
    t, why = m.enter_jetting(good_wot(), operator_confirm=True)
    assert why == [] and t == (Stage.LOAD_TEST, Stage.CARB_JETTING, "criteria_met")
    assert m.stage is Stage.CARB_JETTING and m.step(GOOD).stage is Stage.CARB_JETTING


def test_refuse_on_variance_low_samples_disagree_and_confirm():
    m = at_load()
    assert "afr_variance" in m.enter_jetting(analyze_afr(load_samples(spread=2.0), "secondary"), True)[1]
    assert "insufficient_samples" in m.enter_jetting(analyze_afr(load_samples(n=40), "secondary"), True)[1]
    assert "wideband_disagree" in m.enter_jetting(analyze_afr(load_samples(b_offset=0.5), "secondary"), True)[1]
    assert m.enter_jetting(good_wot(), False)[1] == ["operator_confirm_required"]
    assert m.stage is Stage.LOAD_TEST


def test_refuse_wrong_mode_or_stage():
    assert "not_carb_mode" in at_load(EngineRoomMode.EFI).enter_jetting(good_wot(), True)[1]
    m = ModeCurriculum(EngineRoomMode.CARB, Curriculum(stage=Stage.CRUISE))
    assert "requires_load_test" in m.enter_jetting(good_wot(), True)[1]


def test_red_leaves_jetting():
    m = at_load()
    m.enter_jetting(good_wot(), True)
    r = m.step(Observation(rpm=4000, coolant_c=75, afr_a=12.0, afr_b=14.0))  # gross disagreement -> regress
    assert m.stage is Stage.CRUISE and r.transition[0] is Stage.CARB_JETTING
    m = at_load()
    m.enter_jetting(good_wot(), True)
    r = m.step(Observation(rpm=4000, coolant_c=75, afr_a=12.0, afr_b=12.0, oil_alarm=True))
    assert m.stage is Stage.ABORTED and r.transition == (Stage.CARB_JETTING, Stage.ABORTED, "oil_alarm")


def test_mode_switch_needs_ack_and_resets():
    m = at_load()
    m.enter_jetting(good_wot(), True)
    assert not m.set_mode(EngineRoomMode.EFI, operator_ack=False) and m.mode is EngineRoomMode.CARB
    assert m.set_mode(EngineRoomMode.EFI, operator_ack=True)
    assert m.stage is Stage.COLD_START and not m.jetting
