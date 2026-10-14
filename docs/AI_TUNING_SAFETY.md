# AI Tuning Safety Architecture

Design document for the Grok-assisted auto-tune system. The AI proposes corrections; deterministic interlocks decide what actually gets written.

## Core Principle

The AI is the operator. The interlocks are analog and independent. The AI never has a path to disable a safety system.

## Layer 1: Deterministic Validation Envelope

Every map write proposed by the AI passes through a fixed validator before touching the map:

- **Max fuel change per cell**: configurable, default ±5% per proposal
- **Max spark advance delta**: configurable, default ±2 degrees per proposal
- **AFR floor**: default 10.5:1 (hard reject below)
- **AFR ceiling**: default 16.0:1 (hard reject above)
- **Min samples per cell before trust**: default 20 readings
- **Cell trust window**: AFR must fall within ±0.3 of target for the cell to count as learned

If any rule breaks, the proposal is rejected silently and logged with the rejection reason.

## Layer 2: Hardware Interlocks (bypass the AI entirely)

- **Lean cutoff**: a comparator watching the wideband pulls fuel or grounds the coil directly. The AI cannot disable this.
- **Over-temp cutoff**: coolant or EGT above threshold kills spark independently of firmware.
- **Watchdog heartbeat**: separate Teensy monitors Speeduino serial; timeout pulls the fuel pump relay.

## Layer 3: Rate Limiting

- AI may touch at most 5 cells per minute
- Bad loops converge slowly instead of detonating instantly
- Burst protection: if 3 consecutive proposals are rejected, AI is paused for 10 minutes

## Layer 4: Audit Trail

Every map write logs: timestamp, cell coordinates, proposed value, accepted value, rejection reason (if any), and the AI's reasoning text. Logs are append-only and replayable.

## Staged Curriculum

The AI advances through phases only when data earns it:

1. **Cold start** — cranking enrichment, until coolant reaches operating temp band
2. **Warm idle** — idle cells populated, AFR stable within trust window for N consecutive minutes
3. **Cruise** — mid-load cells, progressive RPM sweep
4. **Load test** — WOT cells, dual-wideband cross-check required before graduation
5. **Street tune** — full map, all cells trusted

Each phase has a green/yellow/red status exposed to Ahanu. Yellow means in progress. Red means a safety event blocked advancement and requires manual review.

## Dual-Wideband Redundancy

Two Spartan 3 Lites on separate exhaust banks. If the two AFR readings diverge beyond 0.5, the AI pauses and flags for inspection — this is the case where most DIY tuners grenade an engine.

## Open Questions

- [ ] Exact pin mapping for Teensy 4.1 + Dropbear V2
- [ ] Speeduino serial protocol command set for map writes
- [ ] NMEA 2000 PGN for AI phase status (custom or existing)
- [ ] Whether the AI loop runs on the Teensy or on a gateway host
