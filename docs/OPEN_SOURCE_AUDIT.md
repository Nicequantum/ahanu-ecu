# Open Source EFI Platform Audit

Landscape survey for ahanu-ecu. Goal: understand what every platform runs, why, and where the gaps are that an AI-native tuner can exploit.

## Platforms Surveyed

### Speeduino (github.com/speeduino/speeduino)
- ~1,800 stars, GPL v2, Teensy 4.1 target (Dropbear V2 board)
- Fuel + spark, batch or sequential, TunerStudio client (proprietary, EFI Analytics)
- Ardu-Stim engine simulator, Tunes repo, SpeedyKnock, SpeedyLoader
- **Gap**: no autonomous progression, no AI layer, TunerStudio is the only map editor

### rusEFI (github.com/rusefi/rusefi)
- ~1,200 stars, more powerful: sequential injection, drive-by-wire, Lua scripting, built-in wideband control
- **Gap**: still routes through TunerStudio or rusEFI console; no staged curriculum

### FOME (rusEFI fork)
- Focused on OEM-quality stability
- **Gap**: same client dependency

### MegaSquirt (msextra.com)
- Proprietary firmware, free TunerStudio client
- Autotune with cell-trust counters and lean-spike cutoffs — closest existing analog to staged learning
- **Gap**: no AI, no hardware interlock philosophy, no dual-wideband cross-check as standard

### Holley Sniper / Dominator
- Closed source. Sniper wizard does staged cold-start/idle/cruise. Dominator has dual widebands.
- **Gap**: proprietary, no extensibility, no AI

### FuelTech FT600
- Race ECU, dual wideband, touchscreen, CAN. Closed.
- **Gap**: expensive, no open AI layer

## What Nobody Has Built

1. An open-source ECU whose tuning client is not TunerStudio
2. An AI that proposes corrections through deterministic interlocks
3. A staged curriculum with green/yellow/red progression that refuses to advance without data
4. Dual-wideband disagreement handling as a first-class safety feature
5. Audit-trail replay for every map write

## Edge Strategy

Build on Speeduino (Teensy 4.1, mature, Ardu-Stim available) and replace the client layer entirely with Ahanu. The AI safety architecture in AI_TUNING_SAFETY.md is the differentiator.
