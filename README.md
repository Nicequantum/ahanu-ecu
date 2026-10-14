# ahanu-ecu

Teensy 4.1 ECU firmware for twin Mercruiser 5.7 marine engines.

## Current Status (2026-10-13)

- ✅ Speeduino is a submodule at `third_party/speeduino`, pinned to upstream tag `202501` (`29bdaa3`). Clone with `--recurse-submodules`. `pio run -e teensy41` builds; not yet flashed to hardware.
- ✅ The zero-hardware Ardu-Stim bench procedure is written. The hardware loop is not run yet (no hardware).
- ✅ **Software-only logic in [`src/grok_pilot`](src/README.md)** (Python, 137 pytest tests, CI in `.github/workflows/python-tests.yml`):
  - deterministic validation envelope, with adversarial and boundary tests
  - staged curriculum state machine: cold_start → warm_idle → cruise → load_test, green/yellow/red status, aborts and regressions
  - log schema v0.2 validator and a synthetic dual-engine log generator ([stress test](docs/SCHEMA-STRESS-TEST.md))
  - Grok integration API: prompt, context, response JSON Schema, and gateway checks
- ✅ Teensy log schema is at **v0.2**. All rates and resolutions are still targets.
- ⏳ No custom firmware yet. The envelope must still be ported to the Teensy (#7). AI is advisory only in v1.
- Run the tests: `pip install -e ".[test]" && pytest -q`

### Docs
- [Open-source audit](docs/OPEN_SOURCE_AUDIT.md)
- [AI auto-tune architecture](docs/AI_AUTOTUNE_ARCHITECTURE.md)
- [AI tuning safety](docs/AI_TUNING_SAFETY.md)
- [Three-tier architecture](docs/three-tier-architecture.md)
- [Grok Pilot vision](docs/grok-pilot-vision.md)
- [Roadmap](docs/ROADMAP.md)
- [Fork notes (Speeduino, marine notes)](docs/FORK-NOTES.md)
- [Data schema (Teensy logs)](docs/DATA-SCHEMA.md)
- [Ardu-Stim bench](docs/ARDU-STIM-BENCH.md)
- [Schema stress test](docs/SCHEMA-STRESS-TEST.md)
- [Grok integration API](docs/GROK-INTEGRATION-API.md) · [response JSON Schema](src/grok_pilot/schemas/proposal-response.v1.schema.json)
- [Python package README](src/README.md)

### Issues
- [#1 Speeduino submodule + Ardu-Stim bench loop](https://github.com/Nicequantum/ahanu-ecu/issues/1)
- [#2 Validation envelope implementation](https://github.com/Nicequantum/ahanu-ecu/issues/2)
- [#3 Staged curriculum state machine](https://github.com/Nicequantum/ahanu-ecu/issues/3)
- [#4 Dual-wideband cross-check + audit trail](https://github.com/Nicequantum/ahanu-ecu/issues/4)
- [#5 Watchdog Teensy spec](https://github.com/Nicequantum/ahanu-ecu/issues/5)
- [#6 Grok integration design](https://github.com/Nicequantum/ahanu-ecu/issues/6)
- [#7 Port envelope to Teensy firmware + proposal transport](https://github.com/Nicequantum/ahanu-ecu/issues/7)
- [#8 Schema v0.3 open items](https://github.com/Nicequantum/ahanu-ecu/issues/8)
- [#9 Calibrate placeholder thresholds from real data](https://github.com/Nicequantum/ahanu-ecu/issues/9)
- [#10 Per-bank wideband offset model](https://github.com/Nicequantum/ahanu-ecu/issues/10)

## Architecture

- **ECU core**: upstream Speeduino firmware (git submodule at `third_party/speeduino`, pinned to tag `202501`; not forked — see [FORK-NOTES](docs/FORK-NOTES.md)) running on Teensy 4.1 — fuel and spark control, injector drivers, coil driver via BIP373
- **Sensors**: RPM (HEI tach wire), MAP, coolant temp, intake air temp, TPS, battery voltage, wideband AFR (14Point7 Spartan 3 Lite UART), EGT (MAX31855 + K-type thermocouple), oil pressure (VDO 360-004 sender, 10–180 Ω, plus 87-805605A1 low-oil alarm switch)
- **Tuning loop (v1: advisory only)**: the AI runs off-Teensy (Mac Studio / iPhone) and only *proposes* cell changes; the Teensy *disposes* via a fixed deterministic validation envelope (max cell delta, spark limits, AFR floor/ceiling, rate limiting) and a hardware lean cutoff independent of software. Every proposal is logged with accept/reject reason. No AI runs on the Teensy.
- **NMEA 2000**: publishes EngineReading PGNs to the backbone for Ahanu consumption
- **Gateway**: Speeduino serial protocol on one side, normalized EngineReading objects on Ahanu's UDP JSON / TCP 39150 path on the other

## Interface contract

The shared types live in the Ahanu repo:

- `Nicequantum/Ahanu` → `src/lib/ahanu/types.ts` — `EngineReading`, `EngineSourceKind` (includes `standalone`), `EngineRoomMode` (`carb` | `efi`), `EngineFeed`, `EngineDtc`
- Engine instance map is assigned at first run (port/starboard), not hardcoded

This repo must not diverge from those types. If Ahanu's contract changes, update here in the same PR.

## Cross-repo tracking

- Dashboard: https://github.com/Nicequantum/Ahanu
- Integration issues are opened in both repos and cross-linked

## Toolchain

- PlatformIO + Arduino framework for Teensy 4.1
- Speeduino upstream: https://github.com/speeduino/speeduino
