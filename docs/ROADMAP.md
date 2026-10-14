# ahanu-ecu Roadmap

## Phase 0 — Foundation (current)

- [x] Repo created, README, interface contract pointing at Nicequantum/Ahanu types.ts
- [x] C++ EngineReading type mirror for compile-time checking
- [x] Open-source platform audit committed
- [x] AI auto-tune architecture documented
- [ ] Fork Speeduino into this repo as upstream baseline

## Phase 1 — Bench Loop

- [ ] Speeduino firmware boots on Ardu-Stim (no hardware needed)
- [ ] Minimal fuel-and-spark loop verified on simulator
- [ ] Serial protocol handler: read RPM/AFR/temps, write map cells
- [ ] NMEA 2000 PGN publisher stub (Lappalainen library)

## Phase 2 — Safety Layer

- [ ] Deterministic validation envelope (fuel delta, spark delta, AFR floor/ceiling)
- [ ] Lean-cutoff comparator design (hardware interlock spec)
- [ ] Watchdog Teensy spec (heartbeat timeout, fuel pump kill)
- [ ] Audit trail logger

## Phase 3 — Staged Curriculum

- [ ] Cold-start phase state machine
- [ ] Warm-idle phase
- [ ] Cruise / light-load / load-test phases
- [ ] Green/yellow/red status per phase
- [ ] Advancement refusal logic

## Phase 4 — AI Loop

- [ ] AI proposal interface (Grok API or local model)
- [ ] Proposal-validation-write pipeline
- [ ] Dual-wideband disagreement handling
- [ ] Dual-engine shared tuning service

## Phase 5 — Ahanu Integration

- [ ] EngineSourceKind 'standalone' path live
- [ ] Custom TypeScript tuner client (replaces TunerStudio)
- [ ] Ahanu as observer + manual override console
- [ ] Street-tune mode with multi-sensor redundancy
