# ahanu-ecu Roadmap

## Phase 0: Foundation (current)

- [x] Repo created with README and source stub
- [x] EngineReading type mirror from Nicequantum/Ahanu
- [x] Open source platform audit committed
- [x] AI tuning safety architecture documented
- [ ] Fork Speeduino into this repo
- [ ] Ardu-Stim bench loop: minimal fuel+spark on simulator

## Phase 1: Marine Layer

- [ ] Teensy 4.1 + Dropbear V2 pin map
- [ ] NMEA 2000 PGN publisher (Lappalainen library): 127488 RPM, 127489 engine params, 127505 fluid level, 127508 battery
- [ ] Spartan 3 Lite UART reader (9600 baud, 5V logic, divider) → AFR PGN
- [ ] SMX oil pressure sender via ADS1115
- [ ] EGT via MAX31855
- [ ] Dual-engine support: two Speeduino instances, shared AI brain

## Phase 2: Watchdog Teensy

- [ ] Heartbeat monitor on Speeduino serial
- [ ] Fuel pump relay kill on timeout
- [ ] Independent lean cutoff via second Spartan 3
- [ ] NMEA 2000 passthrough when Speeduino is dead

## Phase 3: AI Auto-Tune

- [ ] Deterministic validation envelope (fuel/spark/AFR limits)
- [ ] Rate limiter and burst protection
- [ ] Audit trail (append-only, replayable)
- [ ] Staged curriculum: cold start → warm idle → cruise → load → street
- [ ] Green/yellow/red phase status → Ahanu dashboard
- [ ] Dual-wideband divergence detection
- [ ] Grok reasoning layer: plain-language proposals + logged rationale

## Phase 4: Ahanu Integration

- [ ] Gateway service: Speeduino serial ↔ Ahanu UDP JSON / TCP 39150
- [ ] Two-way map writes through Ahanu UI
- [ ] AI phase status as live gauge binding
- [ ] Manual override console in Ahanu
