# ahanu-ecu

Teensy 4.1 ECU firmware for twin Mercruiser 5.7 marine engines.

## Current Status (2026-10-13)

- ✅ Speeduino is a submodule at `third_party/speeduino` pointing at the **Nicequantum/speeduino fork**, tracking branch `grok-pilot`, pinned at `29bdaa3`. That's still identical to upstream release tag `202501`; no marine changes have merged yet. See [speeduino-fork.md](docs/speeduino-fork.md). Clone with `--recurse-submodules`. `pio run -e teensy41` builds; not yet flashed to hardware.
- 🔧 **Speeduino fork work (#11):**
  - The `'Y'` AI proposal command is implemented on the fork's `feat/proposal-command` branch ([fork PR #1](https://github.com/Nicequantum/speeduino/pull/1), draft). It uses the vendored C++ envelope and writes RAM only, with no auto-burn. 15 native tests pass.
  - teensy41 cost: +44.7 KB RAM, +2.4 KB flash.
  - Spec: [PROPOSAL-WIRE-PROTOCOL](docs/PROPOSAL-WIRE-PROTOCOL.md).
  - The envelope PR [#12](https://github.com/Nicequantum/ahanu-ecu/pull/12) is now merged into main. Fork PR #1 is still a draft and still needs bench verification.
- ✅ The zero-hardware Ardu-Stim bench procedure is written. The hardware loop is not run yet (no hardware).
- ✅ **Software-only logic in [`src/grok_pilot`](src/README.md)** (Python, 178 pytest tests, CI in `.github/workflows/python-tests.yml`):
  - deterministic validation envelope, with adversarial and boundary tests
  - staged curriculum state machine: cold_start → warm_idle → cruise → load_test, green/yellow/red status, aborts and regressions
  - log schema v0.2 validator and a synthetic dual-engine log generator ([stress test](docs/SCHEMA-STRESS-TEST.md))
  - Grok integration API: prompt, context, response JSON Schema, and gateway checks
  - **versioned prompt templates v1** (`src/grok_pilot/prompts/v1/`): system prompt, deterministic context assembly, token budget and truncation, good/bad examples. See [PROMPT-TEMPLATES](docs/PROMPT-TEMPLATES.md)
  - **Mac Studio ingest pipeline** (`src/grok_pilot/ingest/`): validated, idempotent SQLite/WAL store with quarantine, plus a query API, CLI and local HTTP endpoint. See [INGEST-PIPELINE](docs/INGEST-PIPELINE.md). Tested on synthetic data only
- ✅ Teensy log schema is at **v0.2**. All rates and resolutions are still targets.
- 🔧 **Envelope C++ port (#7), merged to main via PR #12:**
  - Header-only `firmware/envelope/envelope.h` with no heap, exceptions or RTTI, about 43 KB of static RAM.
  - Results: 28 GoogleTest tests pass; the cross-check against Python-generated vectors gives 6,543 steps with **0 mismatches**; the Teensy 4.1 PlatformIO build compiles.
  - Not yet wired into Speeduino's map-write path. That needs a fork (#11). See [ENVELOPE-CPP-PORT](docs/ENVELOPE-CPP-PORT.md).
- ⚠️ **Wideband UART divider corrected** to 10k top / 20k bottom (≈ 3.33 V). The old 10k/2k gave ≈ 0.83 V. This is a pending hardware change; see [WIRING-NOTES](docs/WIRING-NOTES.md) and #4.
- 🔧 **Carb jetting mode** (branch `feature/carb-jetting-mode`, draft PR, not merged). In carb mode Speeduino does spark only and AI tuning is limited to timing. Jet changes are advice only: one ladder step at a time, based on WOT/on-plane AFR with an 11.0–12.0 target band. A person swaps the jet, and the system logs it as a `jet_change` experiment. Adds schema v0.3, response schema v2 and prompts v2. See [CARB_JETTING_MODE](docs/CARB_JETTING_MODE.md).
- 📱 iOS prototype on branch `prototype/ios-dash`, draft PR [#18](https://github.com/Nicequantum/ahanu-ecu/pull/18) (do not merge), tracking issue [#17](https://github.com/Nicequantum/ahanu-ecu/issues/17), docs/IOS-PROTOTYPE.md on that branch. Swift core (sim, curriculum, proposal decoding, envelope preview, view-model): 24 tests pass on Linux Swift 6.0.3 and CI. SwiftUI views uncompiled pending Xcode.
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
- [Speeduino fork: rationale, sync procedure, #11 plan](docs/speeduino-fork.md)
- [AI proposal command wire protocol](docs/PROPOSAL-WIRE-PROTOCOL.md)
- [Data schema (Teensy logs)](docs/DATA-SCHEMA.md)
- [Ardu-Stim bench](docs/ARDU-STIM-BENCH.md)
- [Schema stress test](docs/SCHEMA-STRESS-TEST.md)
- [Grok integration API](docs/GROK-INTEGRATION-API.md) · [response JSON Schema](src/grok_pilot/schemas/proposal-response.v1.schema.json)
- [Python package README](src/README.md)
- [Envelope C++ port](docs/ENVELOPE-CPP-PORT.md)
- [Wiring notes (wideband divider)](docs/WIRING-NOTES.md)
- [Prompt templates v1](docs/PROMPT-TEMPLATES.md)
- [Ingest pipeline](docs/INGEST-PIPELINE.md)
- [Carb jetting mode](docs/CARB_JETTING_MODE.md)

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
- [#11 Integrate envelope into Speeduino map-write path (fork)](https://github.com/Nicequantum/ahanu-ecu/issues/11)

## Architecture

- **ECU core**: Speeduino firmware (git submodule at `third_party/speeduino` → [Nicequantum/speeduino](https://github.com/Nicequantum/speeduino) fork, pinned to upstream tag `202501`; branch `grok-pilot`; marine changes in review on the fork — see [speeduino-fork.md](docs/speeduino-fork.md)) running on Teensy 4.1 — fuel and spark control, injector drivers, coil driver via BIP373
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
- Speeduino fork (submodule): https://github.com/Nicequantum/speeduino · upstream: https://github.com/speeduino/speeduino
