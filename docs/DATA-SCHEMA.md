# Teensy Log Schema (v0.1 draft)

This is the foundation the Mac Studio model trains on. If we log the wrong fields, the model learns garbage. Version this file and bump `schema_version` on every change.

> **⚠️ All sample rates and resolutions in this document are TARGETS, not measurements.** TODO(hardware): measure actual achievable rates/resolutions on the Dropbear (SD logging throughput, UART wideband update rate, MAX31855 conversion time) once hardware talks, and replace targets with measured values.

**Status:** draft. Sample rates and resolutions are design targets, **not yet measured** on Dropbear hardware. Some fields (per-channel PW, AI proposal records, wideband B, EGT) are **not in stock Speeduino logs** and need firmware or gateway changes. That's the main reason we'd fork (see `FORK-NOTES.md`).

## Record types

1. **`sample`**: high-rate engine state stream.
2. **`cell_write`**: one row per AI proposal, whether it was accepted or rejected (the audit trail).
3. **`event`**: stage transitions, faults, lean cutoffs, interlocks.

Every record carries the common header: `schema_version`, `engine_id`, `boot_id`, `seq`, `timestamp_us`.

## `sample` fields

| Field | Type | Units | Resolution (TARGET) | Sample rate (TARGET — TODO measure) | Retention | Rationale |
|---|---|---|---|---|---|---|
| timestamp_us | uint64 | µs since epoch (GPS/RTC-synced) | 1 µs | every record | permanent | Aligns both engines and AFR lag; time ordering for training |
| engine_id | uint8 enum | — | port=0, stbd=1 | every record | permanent | Two engines, one dataset. Assigned at first run |
| boot_id | uint32 | — | — | every record | permanent | Detects resets/brownouts; segments sessions |
| stage | uint8 enum | cold_start, warm_idle, cruise, load, street | — | every record | permanent | Model must condition on curriculum stage |
| rpm | uint16 | rev/min | 1 rpm | 50 Hz (target 100 Hz) | raw 90 d, 1 Hz downsample permanent | Table axis; core load variable |
| map_kpa | uint16 | kPa abs | 0.1 kPa | 50 Hz | same as rpm | Table axis (speed-density). GM 3-bar 12569240 |
| tps_pct | uint16 | % | 0.1 % | 50 Hz | same | Transients / accel enrichment learning |
| coolant_c | int16 | °C | 0.1 °C | 10 Hz | same | Warm-up enrichment; cold-start stage gating |
| iat_c | int16 | °C | 0.1 °C | 10 Hz | same | Air density correction; heat-soak in closed engine box |
| afr_a | uint16 | AFR (gasoline) and lambda | 0.01 AFR | 50 Hz | same | Primary feedback for fuel learning (Spartan 3 Lite v2 + LSU 4.9) |
| afr_b | uint16 | AFR / lambda | 0.01 AFR | 50 Hz | same | Second wideband for cross-check; disagreement means the data can't be trusted |
| afr_a_status / afr_b_status | uint8 | enum (ok, warming, fault, stale) | — | per reading | same | Never train on a wideband that isn't ready |
| battery_v | uint16 | V | 0.01 V | 10 Hz | same | Injector dead-time depends on voltage; detects charging faults |
| spark_adv_deg | int16 | ° BTDC | 0.1 ° | 50 Hz | same | Commanded timing; spark-delta envelope |
| inj_pw_us[ch] (ch 1–8) | uint16 ×8 | µs | 1 µs | 50 Hz | same | Per-channel fueling; trim/imbalance detection (Dropbear has 8 channels) |
| ve_cell_rpm_idx / ve_cell_map_idx | uint8 | table index | — | 50 Hz | same | Which cell is active, so learning maps to exact cells |

### Recommended additions (not in original field list)

| Field | Type | Units | Resolution (TARGET) | Rate (TARGET) | Retention | Rationale |
|---|---|---|---|---|---|---|
| egt_c | int16 | °C | 0.25 °C (MAX31855 native) | 10 Hz | same | Lean/timing danger signal; probe upstream of water injection |
| egt_fault | uint8 | bitfield (open/short-GND/short-VCC) | — | 10 Hz | same | MAX31855 reports these fault bits |
| oil_press_kpa | uint16 | kPa | 1 kPa | 10 Hz | same | Engine protection (VDO 360-004, 10–180 Ω) |
| oil_alarm | bool | — | — | on change + 1 Hz | same | 87-805605A1 switch; independent of the sender |
| ecu_temp_c | int16 | °C | 1 °C | 1 Hz | same | Detects electronics heat-soak |
| lean_cut_active | bool | — | — | on change | permanent | Hardware lean cutoff state |

## `cell_write` fields (audit trail: every AI proposal)

| Field | Type | Units | Notes |
|---|---|---|---|
| timestamp_us, engine_id, boot_id, stage | — | — | common header |
| proposal_id | uint32 | — | unique, monotonic per engine |
| source | enum | mac_studio / iphone / manual | which tier proposed it |
| model_version | string(16) | — | model hash/version |
| table | enum | ve / spark / afr_target | |
| cell_rpm_idx, cell_map_idx | uint8 | index | cell coordinates |
| value_before | int16 | table units | |
| value_proposed | int16 | table units | |
| value_accepted | int16 | table units | equals before when the proposal is rejected; clamped value when partially accepted |
| decision | enum | accepted / clamped / rejected | |
| reject_reason | enum | none, fuel_delta_exceeded, spark_delta_exceeded, afr_floor, afr_ceiling, rate_limited, wideband_disagree, insufficient_samples, stage_locked, sensor_fault | |
| evidence_samples | uint16 | count | samples behind the proposal |
| afr_mean / afr_target | uint16 | AFR | context |

Retention: **permanent, never deleted** (safety audit trail).

## `event` records
stage_transition (from/to/reason), lean_cut, fault (code), boot, interlock (bilge blower), watchdog_trip. Retention: permanent.

## Retention policy summary

- **On Teensy SD:** ring buffer of raw logs. Oldest session gets overwritten only once it's confirmed ingested (ack from Mac Studio). `cell_write` and `event` records are never overwritten until they've been ingested.
- **Mac Studio TSDB:** raw high-rate data for 90 days, 1 Hz downsamples kept permanently, `cell_write` and `event` kept permanently. These numbers are initial targets and still **TBD**.
- **Storage format:** binary on SD (CSV is too slow at 50–100 Hz), converted to Parquet on ingest. The exact on-SD format is **TBD**.

## Open questions
- Stock Speeduino SD logging rate on Teensy 4.1. Unmeasured.
- Whether wideband B goes into the Teensy (second UART) or into the gateway.
- Time sync source (GPS from NMEA 2000 vs RTC).
