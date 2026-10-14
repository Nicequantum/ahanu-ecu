# Open Source EFI Platform Audit

Landscape survey for ahanu-ecu. Goal: understand what every platform runs and why, so we build the edge (AI tuning) on top of solved problems instead of re-solving them.

## Firmware Platforms

| Platform | Stars | License | Key Strength | Gap |
|----------|-------|---------|--------------|-----|
| Speeduino | ~1,800 | GPL-2.0 | Teensy 4.1 target, full fuel+spark, Ardu-Stim simulator | TunerStudio dependency for map editing |
| rusEFI | ~1,200 | GPL-3.0 | Sequential injection, drive-by-wire, Lua scripting, built-in wideband | Steeper learning curve |
| FOME | newer fork of rusEFI | GPL-3.0 | OEM-quality stability focus | Smaller community |
| MegaSquirt | mature | Proprietary firmware, free TunerStudio | Cell-trust counters, lean-spike cutoffs in autotune | Closed firmware |

## Tooling

| Tool | Role | Notes |
|------|------|-------|
| Ardu-Stim | Engine simulator | Test firmware without a running motor |
| Speeduino Tunes repo | Base maps | Starting points per engine type |
| SpeedyLoader | Flash without compiling | Convenience |
| SpeedyKnock | Knock sensing | rusEFI ecosystem |
| Hypertuner-cloud | TypeScript tune sharing | Closest to web-native tuner, but sharing not control |

## Marine-Specific

| Project | Role | Notes |
|---------|------|-------|
| Timo Lappalainen NMEA2000 | Teensy NMEA 2000 library | De facto standard, used by Ahanu DigitalAdapter |
| ESP32 NMEA2000 gateway | Signal K + NMEA 0183 + Actisense broadcast | Web dashboard included |
| SenseESP engine monitor | Publishes 127488, 127489, 127505, 127508 | Exact PGNs Ahanu reads |

## What Nobody Has Built

1. An open-source ECU whose tuning client is not TunerStudio
2. An AI that runs the staged curriculum autonomously with hardware interlocks
3. Dual-wideband cross-check as a first-class safety feature
4. Audit-trail replay for AI map writes

## Decision

Fork Speeduino (Teensy 4.1, GPL-2.0, closest to our planned hardware). Layer the AI safety architecture and Ahanu integration on top. Do not fork rusEFI — its complexity is not needed for a carb-to-TBI-to-MPI marine path.
