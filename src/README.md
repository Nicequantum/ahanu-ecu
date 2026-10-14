# src/

## `grok_pilot/`: software-only logic (Python ≥ 3.10, no hardware needed)

| Module | What it does |
|---|---|
| `envelope.py` | Deterministic validation envelope: max cell delta (VE ±5 %, spark ±2°), AFR floor/ceiling (10.5–16.0), absolute spark/VE limits, per-cell rate limiting, freshness/replay/stale-basis/wrong-engine/off-table checks. It's the reference model for the Teensy gate |
| `curriculum.py` | Staged curriculum state machine, cold_start → warm_idle → cruise → load_test (street is gated off), with green/yellow/red status, aborts and regressions |
| `schema.py` | Machine-readable log schema v0.1 and v0.2, plus the record and stream validator |
| `synth.py` | Synthetic dual-engine log generator, driven by the real curriculum and envelope |
| `stress.py` | Schema stress-test report (see `docs/SCHEMA-STRESS-TEST.md`) |
| `grok.py` + `schemas/proposal-response.v1.schema.json` | Grok context/prompt builder, response contract, and response-to-envelope evaluation |

Placeholder thresholds are marked TODO in the code and need validating on the real engines.

### Run

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"
pytest -q                                              # all tests
python -m grok_pilot.synth --out logs.jsonl --samples 6000   # synthetic logs (JSONL, schema v0.2)
python -m grok_pilot.synth --version 0.1 --out v01.jsonl     # project to v0.1
python -m grok_pilot.stress                            # coverage report
```

## Planned (firmware side, not started)
- `third_party/speeduino` holds upstream Speeduino as a submodule (already present)
- `custom/` will hold marine-specific firmware changes, once we fork
- `gateway/` will be the serial-to-Ahanu bridge
- `contracts/` will hold copies of Ahanu's EngineReading types
