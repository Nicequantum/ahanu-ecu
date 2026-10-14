# AI Tuning Safety Architecture

Design document for the autonomous tuning layer. The AI proposes corrections; deterministic interlocks decide what actually gets written.

## Core Principle

The AI is the operator. The interlocks are analog and independent. The AI never has a path to disable a safety system.

## Layer 1: Deterministic Validation Envelope

Every map write proposed by the AI passes through a fixed validator before touching the map:

- **Max fuel change per cell**: configurable, default ±5% per proposal
- **Max spark advance delta**: configurable, default ±2 degrees per proposal
- **AFR floor**: default 10.5:1 (hard reject below)
- **AFR ceiling**: default 16.0:1 (hard reject above)
- **Min samples per cell before trust**: default 20
- **Max cells touched per minute**: default 5 (rate limit)

If any rule breaks, the proposal is rejected silently and logged with the reason.

## Layer 2: Hardware Interlocks (bypass the AI entirely)

- **Lean cutoff**: a comparator watching the wideband pulls fuel or grounds the coil directly. The AI cannot disable this.
- **Over-temp cutoff**: coolant or EGT threshold triggers independent shutdown.
- **Watchdog heartbeat**: separate Teensy monitors Speeduino serial; timeout kills fuel pump relay.

## Layer 3: Audit Trail

Every map write records: timestamp, proposed value, accepted value, rejection reason (if any), and the AI's reasoning text. Full replay capability for post-incident analysis.

## Layer 4: Staged Curriculum

The AI advances through phases only when data earns it:

1. **Cold start** — cranking enrichment, until stable idle samples accumulate
2. **Warm idle** — target AFR band held for N consecutive minutes
3. **Cruise** — mid-load cells populated with trusted samples
4. **Load test** — progressive RPM/load sweeps, each cell must pass before advancing
5. **Street tune** — closed-loop fine trim across the full map

Each phase has a green/yellow/red status exposed to Ahanu. Yellow means data is accumulating. Red means a safety event blocked progress.

## Dual Wideband Redundancy

Two Spartan 3 Lites on separate exhaust banks. If AFR readings disagree beyond a threshold, the system freezes map writes and flags for manual review. This is the case where most DIY tuners grenade an engine.

## Open Questions

- [ ] Exact sample-count thresholds per phase (needs bench data from Ardu-Stim)
- [ ] Whether the AI loop runs on the Teensy itself or in the gateway service
- [ ] Grok API integration point: on-device inference vs cloud-assisted reasoning
- [ ] How the audit trail syncs to Ahanu for the dashboard view
