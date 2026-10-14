# ahanu-ecu

Teensy 4.1 ECU firmware for twin Mercruiser 5.7 marine engines.

## Current Status (2026-10-13)

- ✅ Speeduino added as a submodule at `third_party/speeduino`, pinned to upstream tag `202501` (`29bdaa3`). Clone with `--recurse-submodules`.
- ✅ `pio run -e teensy41` builds cleanly from the pinned submodule. It hasn't been flashed to hardware yet.
- ✅ Teensy log schema v0.1 is drafted.
- ✅ Zero-hardware Ardu-Stim bench procedure is written. Ardu-Stim's `nano` build is verified; the hardware loop hasn't been run yet.
- ⏳ No custom firmware, pin map, or AI code yet. AI is advisory only in v1.
- Grok Pilot work is tracked in issues #1–#6 (below).

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

### Issues
- [#1 Speeduino submodule + Ardu-Stim bench loop](https://github.com/Nicequantum/ahanu-ecu/issues/1)
- [#2 Validation envelope implementation](https://github.com/Nicequantum/ahanu-ecu/issues/2)
- [#3 Staged curriculum state machine](https://github.com/Nicequantum/ahanu-ecu/issues/3)
- [#4 Dual-wideband cross-check + audit trail](https://github.com/Nicequantum/ahanu-ecu/issues/4)
- [#5 Watchdog Teensy spec](https://github.com/Nicequantum/ahanu-ecu/issues/5)
- [#6 Grok integration design](https://github.com/Nicequantum/ahanu-ecu/issues/6)

## Architecture

- **ECU core**: Speeduino firmware (forked) running on Teensy 4.1 — fuel and spark control, injector drivers, coil driver via BIP373
- **Sensors**: RPM (HEI tach wire), MAP, coolant temp, intake air temp, TPS, battery voltage, wideband AFR (14Point7 Spartan 3 Lite UART), EGT (MAX31855 + K-type thermocouple), oil pressure (SMX Cummins HD via ADS1115)
- **Self-tuning loop**: conservative learning algorithm with hard cell limits, minimum sample counts, and lean-limit cutoff — runs on the Teensy alongside fuel math, no laptop required
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
