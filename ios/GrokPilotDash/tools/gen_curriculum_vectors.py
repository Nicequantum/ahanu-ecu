"""Regenerate Tests/GrokPilotCoreTests/Fixtures/curriculum-vectors.json from the
Python reference curriculum. Run from the ahanu-ecu repo root."""
import json, random, sys
sys.path.insert(0, 'src')
from grok_pilot.curriculum import Curriculum, Observation, CurriculumConfig, Stage

random.seed(7)
cases = []
for k in range(40):
    cfg = CurriculumConfig(samples_to_advance={Stage.COLD_START: 20, Stage.WARM_IDLE: 30, Stage.CRUISE: 30, Stage.LOAD_TEST: 30})
    c = Curriculum(cfg); steps = []; cool = 45.0
    for i in range(500):
        st = c.stage.value
        tgt = {'cold_start': 800, 'warm_idle': 900, 'cruise': 2800, 'load_test': 4200}.get(st, 800)
        rpm = tgt + random.uniform(-150, 150); cool = min(cool + random.uniform(0, 0.5), 80)
        a = 14.2 + random.gauss(0, 0.3); b = a + random.choice([0] * 12 + [0.2, 0.9, 1.8])
        o = dict(rpm=rpm, coolant_c=cool if random.random() > 0.002 else 96, afr_a=a if random.random() > 0.005 else None, afr_b=b,
                 battery_v=random.choice([13.8] * 60 + [11.2]), oil_press_kpa=random.choice([300.0] * 600 + [50.0]),
                 egt_c=600.0, sensor_fault=random.random() < 0.005, operator_confirm=random.random() < 0.3)
        if c.stage is Stage.ABORTED and random.random() < 0.2:
            c.reset(True); steps.append({"reset": True}); continue
        r = c.step(Observation(**o))
        steps.append({"obs": o, "stage": r.stage.value, "status": r.status.value, "reasons": list(r.reasons),
                      "transition": None if r.transition is None else [r.transition[0].value, r.transition[1].value, r.transition[2]]})
    cases.append(steps)
json.dump(cases, open('ios/GrokPilotDash/Tests/GrokPilotCoreTests/Fixtures/curriculum-vectors.json', 'w'))
