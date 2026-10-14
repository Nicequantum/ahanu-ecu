# ahanu-ecu Roadmap

## Phase 0 — Foundation (current)
- [x] Repo created, README + interface contract pointing at Nicequantum/Ahanu types.ts
- [x] Open source audit committed (docs/OPEN_SOURCE_AUDIT.md)
- [x] AI tuning safety architecture committed (docs/AI_TUNING_SAFETY.md)
- [ ] Fork Speeduino into this repo as a submodule or subtree
- [ ] Ardu-Stim bench loop: minimal fuel-and-spark on simulated engine

## Phase 1 — Marine Layer
- [ ] Teensy 4.1 pin map for Dropbear V2
- [ ] NMEA 2000 PGN publisher (Lappalainen's library) — 127488 RPM, 127489 engine params, 127505 fluid level, 127508 battery
- [ ] Dual-engine support: one Teensy per engine, shared AI brain
- [ ] Watchdog Teensy spec: heartbeat monitor, fuel-pump kill, independent AFR lean cutoff

## Phase 2 — AI Tuning Loop
- [ ] Deterministic validation envelope (max fuel/spark delta, AFR floor/ceiling, rate limits)
- [ ] Staged curriculum state machine: cold start → warm idle → cruise → load test → street tune
- [ ] Green/yellow/red phase status exposed to Ahanu
- [ ] Dual Spartan 3 Lite cross-check: freeze map writes on AFR disagreement
- [ ] Audit trail: timestamp, proposed, accepted, reasoning — replayable
- [ ] Grok integration: on-device vs cloud-assisted reasoning

## Phase 3 — Ahanu Integration
- [ ] Gateway service: Speeduino serial ↔ Ahanu UDP JSON / TCP 39150
- [ ] Ahanu custom tuner front end replacing TunerStudio
- [ ] Dashboard gauges bound to live EngineReading objects
- [ ] AI phase status visible in Ahanu UI

## Phase 4 — Validation
- [ ] Bench: Ardu-Stim full curriculum run
- [ ] Single-engine water test
- [ ] Twin-engine deployment on the boat
