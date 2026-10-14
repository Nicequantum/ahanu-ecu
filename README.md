# ahanu-ecu

Teensy 4.1 ECU firmware for twin Mercruiser 5.7 marine engines.

## Status

Scaffold only. Firmware not yet written.

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
