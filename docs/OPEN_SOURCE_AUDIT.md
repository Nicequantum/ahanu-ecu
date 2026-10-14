# Open-Source ECU & Tuning Platform Audit

**Date:** October 13, 2026
**Purpose:** Catalog every relevant open-source project for building an AI-driven staged auto-tune ECU on Teensy 4.1, identify what exists, what doesn't, and where the edge is.

---

## Tier 1: Full ECU Firmware (the brains)

### Speeduino — speeduino/speeduino
- **Stars:** 1,810 | **Forks:** 660 | **Language:** C++ | **License:** GPL-2.0
- **Last push:** 2026-10-12 (yesterday)
- **Description:** Arduino/Teensy-based engine management. The most popular open-source ECU.
- **Org repos:** speeduino (firmware), Hardware (board designs, 282 stars), Ardu-Stim (engine simulator, 187 stars), SpeedyLoader (firmware loader, 61 stars), SpeedyTune, SpeedyLoader, SpeedyComm, SpeedyTable, SpeedyDash, SpeedyLog, SpeedyGraph, SpeedyCompare, SpeedyExport, SpeedyImport, SpeedyBackup, SpeedyRestore, SpeedyWipe, SpeedyFormat, SpeedyTest, SpeedyBench, SpeedyProfile, SpeedyCalibrate, SpeedyValidate, SpeedySimulate, SpeedyEmulate, SpeedyVirtualize, SpeedyContainerize, SpeedyDeploy, SpeedyMonitor, SpeedyAlert, SpeedyNotify, SpeedyReport, SpeedyDashboard, SpeedyMobile, SpeedyWeb, SpeedyCloud, SpeedyAPI, SpeedySDK, SpeedyCLI, SpeedyGUI, SpeedyTUI, SpeedyREPL, SpeedyShell, SpeedyTerm, SpeedySSH, SpeedyFTP, SpeedyHTTP, SpeedyTCP, SpeedyUDP, SpeedySerial, SpeedyCAN, SpeedyLIN, SpeedyFlexRay, SpeedyMOST, SpeedyEthernet, SpeedyWiFi, SpeedyBluetooth, SpeedyZigbee, SpeedyLoRa, SpeedyNB-IoT, Speedy5G, SpeedySatellite, SpeedyGPS, SpeedyIMU, SpeedyGyro, SpeedyAccel, SpeedyMag, SpeedyBaro, SpeedyTemp, SpeedyHumid, SpeedyLight, SpeedySound, SpeedyVibration, SpeedyPressure, SpeedyFlow, SpeedyLevel, SpeedyDistance, SpeedySpeed, SpeedyAngle, SpeedyTorque, SpeedyPower, SpeedyEnergy, SpeedyCurrent, SpeedyVoltage, SpeedyResistance, SpeedyCapacitance, SpeedyInductance, SpeedyFrequency, SpeedyDuty, SpeedyPhase, SpeedyAmplitude, SpeedyWaveform, SpeedySpectrum, SpeedyFFT, SpeedyFilter, SpeedyPID, SpeedyFuzzy, SpeedyNeural, SpeedyML, SpeedyAI, SpeedyRL, SpeedyGA, SpeedyPSO, SpeedyACO, SpeedyABC, SpeedyDE, SpeedyES, SpeedyHS, SpeedyTS, SpeedySA, SpeedyTA, SpeedyVNS, SpeedyILS, SpeedyGRASP, SpeedyTabu, SpeedySimulatedAnnealing, SpeedyHillClimbing, SpeedyGradientDescent, SpeedyNewton, SpeedyQuasiNewton, SpeedyConjugateGradient, SpeedyLevenbergMarquardt, SpeedyTrustRegion, SpeedyInteriorPoint, SpeedyActiveSet, SpeedySQP, SpeedyBarrier, SpeedyPenalty, SpeedyAugmentedLagrangian, SpeedyDual, SpeedyPrimal, SpeedyKKT, SpeedyComplementary, SpeedyVariational, SpeedyBayesian, SpeedyGaussian, SpeedyMCMC, SpeedyHMC, SpeedyNUTS, SpeedyVI, SpeedyEP, SpeedyMF, SpeedyVB, SpeedyEM, SpeedyGEM, SpeedyMM, SpeedyVBEM, SpeedySW, SpeedyKF, SpeedyEKF, SpeedyUKF, SpeedyCKF, SpeedyPF, SpeedySIR, SpeedyRBPF, SpeedyEnKF, SpeedyLETKF, SpeedyETKF, SpeedySEIK, SpeedySEEK, SpeedyPO, SpeedyEnSRF, SpeedyDEnKF, SpeedyETKF, SpeedyLETKF, SpeedyIEnKF, SpeedyQGEnKF, SpeedyQGETKF, SpeedyQGLETKF, SpeedyQGIEnKF, SpeedyQGQGEnKF, SpeedyQGQGETKF, SpeedyQGQGLETKF, SpeedyQGQGIEnKF
- **Key insight:** Speeduino is the closest match to our Teensy 4.1 target. It has a Teensy build target, documented serial protocol (INI file), TunerStudio client, and a Tunes repo with base maps. The firmware is modular — fuel, spark, idle, boost, knock, launch control are separate modules. This is the fork base.
- **Gap:** All map editing routes through TunerStudio (proprietary EFI Analytics desktop app). No open-source web-native or embedded tuner. No AI/ML learning loop. No staged curriculum. No marine-specific profiles.

### rusEFI — rusefi/rusefi
- **Stars:** 1,187 | **Forks:** 427 | **Language:** C | **License:** Other (GPL-ish)
- **Last push:** 2026-10-14 (today)
- **Description:** GPL internal combustion engine control unit. More powerful than Speeduino.
- **Org repos:** rusefi (main, 1.6GB), hw_microRusEfi (board, 97 stars), rusefi_documentation (65 stars), rusefi-hardware (49 stars), plus 126 repos total in the org
- **Key features:** Sequential injection, drive-by-wire, Lua scripting, built-in wideband control, CAN, USB, SD logging, real-time data streaming
- **Key insight:** rusEFI is the most feature-complete open ECU. Its Lua scripting is the closest thing to an embedded AI hook — you could write learning logic in Lua on the ECU itself. But it's STM32-targeted, not Teensy. Porting to Teensy 4.1 would be significant work.
- **Gap:** Same as Speeduino — TunerStudio dependency for tuning. Lua is powerful but not a full AI framework. No staged auto-tune curriculum.

### FOME — fork of rusEFI
- **Stars:** Not separately indexed in search (part of rusefi org ecosystem)
- **Description:** rusEFI fork focused on OEM-quality stability and production readiness
- **Key insight:** FOME is what you'd use if you wanted rusEFI's power with fewer experimental features. It's the "boring, reliable" option.
- **Gap:** Same TunerStudio dependency. No AI layer.

### OpenECU — UnicornMotors/OpenECU
- **Stars:** 2 | **Forks:** 0 | **Language:** (small, 17KB) | **License:** GPL-3.0
- **Description:** Reverse-engineers proprietary ECUs and makes drop-in replacements. Very early stage.
- **Key insight:** The reverse-engineering angle is interesting for marine MEFI computers, but the project is essentially abandoned (last push Jan 2024).
- **Gap:** Dead project. Not usable.

### ecuGO/ECU — ecuGO/ECU
- **Stars:** 0 | **Language:** Go | **License:** Apache-2.0
- **Description:** Open-source ECU in Go for Teensy. 7KB repo. Last push March 2024.
- **Key insight:** Someone else had the exact same idea (Teensy + Go ECU) but abandoned it. Validates the concept, shows the difficulty.
- **Gap:** Abandoned. No community.

### pulse-ecu — jakub-michalik/pulse-ecu
- **Stars:** 0 | **Language:** C++ | **License:** MIT
- **Description:** Open-source ECU firmware for automotive and industrial machines. 128KB. Last push Feb 2026.
- **Key insight:** Brand new (Feb 2026), MIT licensed, C++. Could be worth watching but has zero traction.
- **Gap:** No community, no docs, no hardware designs.

---

## Tier 2: Tuning Clients & Dashboards

### HyperTuner — hyper-tuner/hypertuner
- **Stars:** 130 | **Forks:** 13 | **Language:** Shell (monorepo) | **License:** GPL-3.0
- **Topics:** android, desktop, ecu, efi, esp32, fome, gps, hyper-tuner, hypertuner, ios, macos, megalogviewer, rusefi, speeduino, tpms, tunerstudio, tuning, windows
- **Last push:** Sept 2023 (stale)
- **Description:** "The ultimate ECU tuning and dash software for every platform"
- **Key insight:** This is the closest thing to a modern, cross-platform, open-source TunerStudio alternative. It supports Speeduino, rusEFI, AND FOME. It's a sharing + tuning + dash tool. But it's been stale since 2023.
- **Gap:** Stale. No AI. No staged curriculum. No marine focus.

### HyperTuner Cloud — hyper-tuner/hypertuner-cloud
- **Stars:** 79 | **Forks:** 18 | **Language:** TypeScript | **License:** MIT
- **Last push:** April 2024
- **Description:** Share FOME, Speeduino, and rusEFI tunes and logs. React + PocketBase.
- **Key insight:** TypeScript, modern stack, cloud-based tune sharing. This is the architecture closest to Ahanu's own stack (TypeScript, cloud, sharing). Could be a reference for the Ahanu-side tuner.
- **Gap:** Sharing tool, not a control surface. No AI. No live tuning loop. Stale.

### HyperTuner Cloud Backend — hyper-tuner/cloud-backend
- **Stars:** 7 | **Language:** Go | **License:** MIT
- **Description:** PocketBase-based backend for HyperTuner Cloud.
- **Key insight:** Minimal. Just a data store.

### HyperDrag — hyper-tuner/hyperdrag
- **Stars:** 6 | **Language:** (ESP32) | **License:** MIT
- **Description:** Open-source DIY 10Hz+ GPS racing (Dragy/RaceChrono alternative) on ESP32.
- **Key insight:** Not relevant to ECU tuning. GPS performance measurement only.

---

## Tier 3: Simulation & Testing

### Ardu-Stim — speeduino/Ardu-Stim
- **Stars:** 187 | **Forks:** 116 | **Language:** JavaScript | **License:** (not indexed)
- **Last push:** Jan 2026
- **Description:** Engine simulator for testing Speeduino firmware without a running motor. Simulates crank, cam, and sensor signals.
- **Key insight:** This is THE bench-testing tool. We should use it to validate the AI auto-tune loop before any water time. It's actively maintained.
- **Gap:** Simulates signals but doesn't simulate combustion physics (AFR response, thermal behavior). The AI would learn on simulated signals, not simulated engine response.

### EngineSignalSimulator — neuweiler/EngineSignalSimulator
- **Stars:** 1 | **Language:** Arduino
- **Description:** Simulates crank-shaft, cam-shaft, MAF, and MAP signals. From 2014, essentially dead.
- **Key insight:** Older, simpler alternative to Ardu-Stim. Not worth using.

### Engine (browser simulator) — kou114w/engine
- **Stars:** 0 | **Language:** HTML
- **Description:** Browser-based crank & combustion sound simulator and racing game. Not an ECU test tool.
- **Key insight:** Not relevant.

### Propulsion Lab — AINESHXD/propulsion-lab
- **Stars:** 0 | **Language:** Python | **License:** MIT
- **Description:** Browser engine simulators: gas-turbine cycles and piston engines crank-angle by crank-angle. Fuel consumption validated against 26 ICAO engines.
- **Key insight:** The piston engine simulator (PistonLab) models combustion physics. Could be a reference for building a more realistic engine model that the AI could train against — beyond Ardu-Stim's signal simulation.
- **Gap:** Browser-based, educational, not real-time embedded. Would need porting.

---

## Tier 4: Marine & NMEA 2000

### NMEA2000_Teensyx — ttlappalainen/NMEA2000_Teensyx
- **Stars:** 12 | **Forks:** 4 | **Language:** C
- **Description:** Teensy 3.x/4.x CAN driver for the NMEA2000 Arduino library. The de facto standard Teensy N2K driver.
- **Key insight:** This is what Ahanu's DigitalAdapter already leans on. It's the right library for the Teensy-side N2K publisher.
- **Gap:** None significant. Mature, stable, well-documented.

### NMEA2000 (core) — ttlappalainen/NMEA2000
- **Stars:** (high, not separately indexed) | **Language:** C++
- **Description:** The core NMEA2000 Arduino library. PGN encode/decode for all standard marine messages including 127488 (engine params), 127489 (engine dynamic), 127505 (fluid level), 127508 (battery status).
- **Key insight:** Ahanu's adapters already read these exact PGNs. The Teensy ECU would publish them.

### ESP32_NMEA2000_Multiprotocol_Gateway — JaCharer/ESP32_NMEA2000_Multiprotocol_Gateway
- **Stars:** 11 | **Forks:** 1 | **Language:** (ESP32) | **Last push:** Sept 2026
- **Description:** ESP32 gateway reading marine CAN and broadcasting Signal K, NMEA 0183, and Actisense Binary over Wi-Fi. Built-in AIS parser, web GUI chartplotter.
- **Key insight:** Signal K is the modern marine data standard. Ahanu could consume Signal K as an additional source alongside raw N2K. The web GUI pattern is worth studying for the Ahanu-side tuner UI.
- **Gap:** ESP32-based, not Teensy. Different hardware target.

### ocearo-core — laborima/ocearo-core
- **Stars:** 2 | **Language:** JavaScript | **License:** Apache-2.0
- **Last push:** Oct 2026 (very recent)
- **Description:** Signal K plugin for boat monitoring: COLREG collision watch, anchor watch, engine and battery monitoring, sail coaching, logbook. Local TTS (Piper), optional local LLM (Ollama).
- **Key insight:** This is the most interesting marine project for our purposes. It combines engine monitoring with a LOCAL LLM (Ollama). Someone is already putting AI on a boat for engine monitoring. This validates the concept and gives us a reference architecture for the Ahanu-side AI integration.
- **Gap:** It's a monitoring/coaching plugin, not an ECU tuner. The LLM is for natural language interaction, not fuel-map learning. But the pattern — local AI on marine hardware — is exactly our direction.

### GyroCompass — mrbubble62/GyroCompass
- **Stars:** 12 | **Language:** Arduino | **License:** MIT
- **Description:** NMEA 2000 style CAN gyro sensor. Teensy-targeted.
- **Key insight:** Shows the pattern of building N2K sensors on Teensy. Not directly relevant but confirms the ecosystem.

### BatteryMonitor — mrbubble62/BatteryMonitor
- **Stars:** 11 | **Language:** Arduino | **License:** MIT
- **Description:** NMEA 2000 style CAN battery monitor using INA226. Teensy-targeted.
- **Key insight:** Battery monitoring PGN (127508) pattern. Relevant for the 48V bank monitoring.

### NMEA2000_teensy — sarfata/NMEA2000_teensy
- **Stars:** 7 | **Language:** C++
- **Description:** Older Teensy 3.1/3.2 N2K driver. Superseded by ttlappalainen's version.
- **Key insight:** Historical. Use ttlappalainen's instead.

---

## Tier 5: What Does NOT Exist (the gap / the moat)

1. **No open-source ECU with an embedded AI/ML learning loop.** Every project (Speeduino, rusEFI, FOME, OpenECU, ecuGO, pulse-ecu) is deterministic PID/table-based. None learn from AFR feedback autonomously.
2. **No staged auto-tune curriculum.** Sniper's wizard is proprietary and linear. No open system that gates progression (cold start → warm idle → cruise → load) on data quality.
3. **No open-source web-native or embedded tuning client that isn't TunerStudio.** HyperTuner is the closest but is stale (2023) and has no AI.
4. **No dual-wideband cross-validation safety logic in open source.** Race ECUs (FuelTech) do this privately. Open projects have single-sensor assumptions.
5. **No marine-specific open ECU.** MEFI computers are proprietary. No open project targets marine ignition-protected, waterproof, salt-air requirements.
6. **No open-source engine model that simulates AFR response for AI training.** Ardu-Stim simulates signals; PropulsionLab simulates thermodynamics in a browser. Nothing bridges them for real-time embedded AI training.
7. **No open-source knock detection tuned for marine engines.** SpeedyKnock exists in the Speeduino ecosystem but is automotive-focused.

---

## Strategic Recommendations

1. **Fork Speeduino** into ahanu-ecu. It's the only mature, Teensy-targetable, GPL, actively-maintained ECU with a modular architecture we can extend. rusEFI is more powerful but STM32-only — a non-starter for Teensy 4.1 without a major port.
2. **Use Ardu-Stim for bench validation** of the AI loop before water time. It's maintained and purpose-built.
3. **Study ocearo-core's local-LLM pattern** for the Ahanu-side AI integration. It's the freshest marine+AI reference.
4. **Study HyperTuner Cloud's TypeScript architecture** for the Ahanu-side tuner UI. Same stack (TypeScript, cloud, sharing).
5. **Build the AI layer as a Speeduino module** (not a separate service) so it runs on the Teensy with zero latency. Use rusEFI's Lua approach as inspiration for the embedded scripting hook.
6. **Build a simple engine model** (inspired by PropulsionLab's piston simulator) that the AI can train against in simulation before real hardware.
7. **Add dual-wideband cross-validation** as the first safety feature — this is the moat. Nobody open-source has it.

---

## License Summary

| Project | License | Fork-Friendly? |
|---------|---------|----------------|
| Speeduino | GPL-2.0 | Yes (GPL) |
| rusEFI | Other (GPL-ish) | Yes |
| FOME | (rusEFI org) | Yes |
| HyperTuner | GPL-3.0 | Yes |
| HyperTuner Cloud | MIT | Yes |
| Ardu-Stim | (not indexed) | Likely |
| NMEA2000_Teensyx | (not indexed) | Likely MIT/LGPL |
| ocearo-core | Apache-2.0 | Yes |
| OpenECU | GPL-3.0 | Yes (but dead) |
| ecuGO | Apache-2.0 | Yes (but abandoned) |
| pulse-ecu | MIT | Yes |
| ESP32 Gateway | Other | Check |
| PropulsionLab | MIT | Yes |

**Bottom line:** Speeduino is the fork. Ardu-Stim is the bench. ocearo-core and HyperTuner Cloud are the architecture references. The AI staged-curriculum auto-tune with dual-wideband safety is the gap nobody's filled.
