# Speeduino Fork Notes

## Pinned firmware

| Item | Value |
|---|---|
| Submodule URL | https://github.com/Nicequantum/speeduino (fork of upstream, created 2026-10-14 UTC; `.gitmodules` branch = `grok-pilot`) |
| Upstream | https://github.com/speeduino/Speeduino |
| Fork contents vs upstream | `grok-pilot` is still identical to 202501. The marine `'Y'` proposal command is in review in fork PR #1 (see [speeduino-fork.md](speeduino-fork.md)) |
| Path in this repo | `third_party/speeduino` (git submodule) |
| Pinned tag | `202501` (latest upstream release tag at time of pinning, 2026-10-13; the same commit exists on the fork) |
| Pinned commit | `29bdaa32fc35764094e281f169754714100ce1f0` (2025-01-07) |
| Upstream master HEAD seen at pin time | `c965de489bb2153e7f1c6bd2e90103dc2a501a3b` (2026-10-12) — **not** used; untagged |
| PlatformIO env for our target | `teensy41` (verified in `third_party/speeduino/platformio.ini`; upstream `default_envs` is `megaatmega2560`, so always pass `-e teensy41`) |

Clone with: `git clone --recurse-submodules https://github.com/Nicequantum/ahanu-ecu.git`
or after cloning: `git submodule update --init --recursive`.

## Why Speeduino (vs rusEFI / FOME)

- **Hardware fit:** the chosen board, Speeduino Dropbear V2, is a Teensy 4.1 Speeduino board; `teensy41` is a first-class upstream build target. rusEFI/FOME target STM32-based boards (Proteus, uaEFI, etc.) and would mean different hardware.
- **Simplicity of the safety floor:** Speeduino's codebase is small and table-driven, which makes it easier to audit as the "Teensy disposes" layer and to reason about fixed envelopes.
- **Bench tooling:** Ardu-Stim is maintained by the same project and documented against Speeduino.
- **Trade-offs acknowledged:** rusEFI/FOME have more advanced features (e.g. richer logging, Lua scripting, closed-loop features) and an open tuning client (rusEFI console). Speeduino tuning normally uses TunerStudio (proprietary). Grok Pilot's own tuning/AI client is the intended differentiator. See `docs/OPEN_SOURCE_AUDIT.md`.
- **License:** Speeduino is GPL-3.0 (see `third_party/speeduino/LICENSE`). Any modified firmware we distribute must be released under GPL-3.0 with source.

## Upstream-tracking plan

1. Pin to upstream **release tags** only (or our `grok-pilot` commits built on them) (e.g. `202501`), never untagged master, for anything flashed to an engine.
2. On each new upstream release: bump submodule on a branch, run the Ardu-Stim bench loop (`docs/ARDU-STIM-BENCH.md`), diff `reference/speeduino.ini` for log/field changes affecting `docs/DATA-SCHEMA.md`, then merge.
3. Record each bump in the table above (tag, SHA, date, bench result).

## Fork status

**Forked** (2026-10-13 ET). The submodule now points at `Nicequantum/speeduino`, still pinned to the upstream `202501` commit `29bdaa3`, so the firmware version hasn't changed. The fork's `master` mirrors upstream. Marine work goes on the `grok-pilot` branch, created from `202501`, through in-fork PRs. The first is the AI proposal command (fork PR #1, draft). None has merged yet. The rationale, sync procedure and #11 plan are in [speeduino-fork.md](speeduino-fork.md).

## Marine notes (open engineering questions — not yet validated)

- **Salt / corrosion:** conformal-coat the ECU, sealed connectors (Deutsch DT / DTM), tinned marine wire, dielectric grease, enclosure mounted high and away from bilge water. Check grounds regularly; voltage-drop errors will show up in sensor readings.
- **No-airflow engine bay:** an enclosed engine box runs hot. Mount the ECU outside the hatch or in a ventilated spot; log IAT and ECU internal temperature (upstream `teensy41` env pulls `InternalTemperature`). IAT readings will run high at idle with the hatch closed. Expect heat soak.
- **Flame arrestor:** a USCG-required backfire flame arrestor replaces the air filter. It adds restriction and affects the MAP/VE relationship. Tune with it fitted. Never run without it.
- **Water-injected exhaust / EGT placement:** put the EGT probe (Omega KMQSS-125G-6 with MAX31855) in the exhaust riser/manifold **upstream of the water injection point**. Downstream readings get quenched and mean nothing. Do the same for the wideband O2 sensor (Bosch LSU 4.9) and keep it clear of water reversion, because water droplets crack the heated sensor. Exact bung location per riser is **TBD**.
- **Ignition protection (USCG 33 CFR 183.410, SAE J1171):** any electrical part in a gasoline engine compartment has to be ignition-protected. A Dropbear, Teensy, Arduino or wideband controller is **not certified** as ignition-protected. Mount it outside the engine compartment, or in a J1171-compliant enclosure. Compliance of the Holley Sniper 550-871K for marine use is **unverified**; check with Holley.
- **Wideband UART level shifting:** the Spartan 3 Lite v2 TX (5 V, unverified) feeding a 3.3 V Teensy RX needs a **10k top / 20k bottom** divider (≈ 3.33 V). The earlier 10k/2k spec gave ≈ 0.83 V and wouldn't work. This is a **pending hardware change**; see [WIRING-NOTES](WIRING-NOTES.md).
- **Dual-engine sync:** each Mercruiser 5.7 runs its own ECU and its own log stream (`engine_id`). Cross-engine RPM sync is an Ahanu/iPhone-tier advisory feature, not a Teensy function.
- **Bilge blower interlock:** the engine shouldn't crank or fuel until the bilge blower has run (USCG guidance is 4 minutes before starting). Implement it as a hardware interlock or an ECU input gating the fuel pump/injectors. Design is **TBD**, tracked under the watchdog spec.
- **Engines:** port/starboard assignment happens at first run. Engine A is the carbureted one with the seized Edelbrock 650 and is the Holley Sniper candidate. Engine B has the new Edelbrock 650 and the Mallory distributor.
