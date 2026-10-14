# Open Source EFI Platform Audit

Purpose: understand what every major open-source tuning platform runs, why, and where the gaps are — so ahanu-ecu can differentiate with AI auto-tune rather than cloning existing workflows.

## Speeduino (github.com/speeduino/speeduino)

- ~1,800 stars, GPL v2
- Firmware: C++ on Arduino/Teensy. Fuel map is a 16x16 VE table. Batch or sequential injection. Single-table spark. No AI, no staged curriculum, no dual-engine concept.
- TunerStudio (EFI Analytics, proprietary) is the only tuning client. No open web-native control surface.
- Related: Ardu-Stim (engine simulator), Hardware repo (board designs), Tunes repo (base maps), SpeedyLoader (flash tool), SpeedyKnock (knock sensing), SpeedyLogger.
- Gap: no autonomous progression, no safety envelope, no AI loop, no NMEA 2000 publisher.

## rusEFI (github.com/rusefi/rusefi)

- ~1,200 stars. More powerful: sequential injection, drive-by-wire, Lua scripting, built-in wideband control, CAN.
- TunerStudio still the client. Lua gives some extensibility but no AI.
- Gap: same as Speeduino on the tuning-client and safety side.

## FOME (rusEFI fork)

- Newer, focused on OEM-quality stability and emissions-style robustness.
- Gap: same tuning-client limitation.

## MegaSquirt (msextra.com)

- Proprietary firmware, free TunerStudio client. Autotune exists with cell-trust counters and lean-spike cutoffs — closest existing analog to staged learning, but human-driven.
- Gap: no AI, no curriculum, no dual-wideband cross-check.

## Hypertuner-cloud

- TypeScript project for sharing tunes and logs across Speeduino/rusEFI/FOME.
- Sharing tool, not a control surface. No live control, no AI.

## Marine-specific

- Timo Lappalainen NMEA2000 library (Teensy driver) — de facto standard, used by Ahanu DigitalAdapter.
- ESP32 NMEA2000 multiprotocol gateway (Signal K, NMEA 0183, Actisense) with web dashboard.
- SenseESP-based engine monitor publishing PGNs 127488/127489/127505/127508.
- No open-source marine EFI with NMEA 2000 integration and AI tuning.

## The Gap (ahanu-ecu's opportunity)

1. AI as the tuner, not a cell-nudger — reasons about engine state in plain language, proposes corrections.
2. Deterministic safety envelope that the AI cannot override.
3. Staged curriculum with autonomous advancement and refusal.
4. Dual-wideband redundancy with disagreement freeze.
5. Dual-engine independent learning with shared strategy.
6. NMEA 2000 native — Ahanu as the dashboard, not TunerStudio.
7. Open web-native tuning client (TypeScript) instead of proprietary desktop app.
