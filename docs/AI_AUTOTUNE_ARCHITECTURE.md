# AI Auto-Tune Architecture

## Goal

An autonomous EFI tuning system that safely builds fuel and spark maps over hours of engine operation, progressing through staged phases (cold start, warm idle, cruise, load) with green/yellow/red status indicators, and eventually enabling street tuning with multi-wideband redundancy.

## Core Principle: AI Proposes, Deterministic Layer Disposes

The AI (Grok or equivalent) never writes directly to the fuel map. It proposes corrections. A separate, non-AI validation layer checks every proposal against a fixed safety envelope before it touches memory.

## Safety Envelope (hard limits, not AI-configurable)

- Max fuel change per cell per cycle: configurable, default ±2.5%
- Max spark advance delta per cell: configurable, default ±2 degrees
- AFR floor: 10.5 (instant fuel cut if breached)
- AFR ceiling: 16.0 (instant fuel enrichment if breached)
- Min samples per cell before trust: 20
- Max cells touched per minute: 10
- Dual-wideband disagreement threshold: 0.3 AFR — freeze learning on disagreement

## Hardware Interlocks (independent of AI)

- Lean cutoff comparator watches wideband directly, pulls fuel or grounds coil, bypasses AI entirely
- Watchdog Teensy monitors Speeduino heartbeat; kills fuel pump relay on timeout
- AI has no software path to disable interlocks

## Staged Curriculum

1. **Cold start** — cranking enrichment, first-fire AFR, idle stabilization. Green when AFR holds 12-14 for 5 minutes.
2. **Warm idle** — closed-loop trim converges. Green when idle AFR variance < 0.5 for 10 minutes.
3. **Cruise** — low-load cells populated. Green when 80% of cruise cells have 20+ samples.
4. **Light load** — mid-range transition cells. Green when AFR error < 0.3 across band.
5. **Load test** — progressive RPM/load sweeps. Green when all cells in sweep have 20+ samples and AFR within 0.5 of target.
6. **Street tune** — full map, multi-wideband cross-check. Green when dual sensors agree within 0.3 AFR across all operating cells.

Each stage refuses to advance if data doesn't earn it. Red = unsafe condition, freeze all learning.

## Dual-Engine Support

One Teensy per engine (Speeduino instance). Shared AI tuning service watches both ECUs, compares AFRs and load cells independently. Port and starboard learn separately so one engine's fault can't mask the other's.

## Audit Trail

Every map write logs: timestamp, cell, proposed value, accepted value, rejection reason, AI reasoning. Replayable for post-incident analysis.

## Stack

- Speeduino firmware (forked) on Teensy 4.1 / Dropbear V2
- Lappalainen NMEA2000 library for backbone
- Spartan 3 Lite + LSU 4.9 wideband(s) via UART
- Ahanu dashboard (Nicequantum/Ahanu) as observer + manual override console
- AI tuning loop: gateway service or in-firmware, reads AFR/RPM/temps, proposes corrections through validation layer
