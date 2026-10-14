# Schema Stress Test (synthetic logs vs. schema v0.1)

**Date:** 2026-10-13. **Method:** software only, no hardware. **Reproduce:** `PYTHONPATH=src python -m grok_pilot.stress`

`grok_pilot.synth` simulates both Mercruiser 5.7s at 10 Hz for 6,000 samples per engine, running from a cold start (15 °C) through warm idle and cruise to load test. The **real** curriculum state machine (`curriculum.py`) and validation envelope (`envelope.py`) drive the run, so the stage, status and audit records are what that logic actually produces. An injected fault (bank-B wideband drifts +2.5 AFR for 5 s during cruise on engine 1) exercises regression. A deliberately misbehaving "AI" (10 % of proposals ask for +30 % VE) exercises clamping. The physics is crude on purpose: the run tests the **schema**, not the engine.

## Results (seed 1)

| Metric | Value |
|---|---|
| Records | 12,177 (12,000 samples, 162 cell_write, 15 events) |
| Invalid under **v0.2** | **0** |
| Invalid under **v0.1** (strict projection) | **7**: 6 × `status_change` event not in the enum, 1 × `learning_frozen` reject reason not in the enum |
| Samples with AFR available | 11,400 (widebands warming for the first 30 s) |
| Samples with warm-up enrichment > 0 while AFR is valid | **3,338 (29 %)** |
| Mean AFR bank B − bank A | engine 0: 0.00, engine 1: **+0.27** (simulated real bank difference) |
| Proposal decisions | 52 accepted, 13 clamped (fuel_delta_exceeded), 52 rate_limited, 44 insufficient_samples, 1 learning_frozen |
| Stage transitions | both engines: cold→warm→cruise. Engine 1: cruise→warm_idle (wideband_disagree), then back to cruise. Engine 0: cruise→load_test |

Validation is enforced by `grok_pilot.schema.validate_record` / `validate_stream`, which check type, range, enum, required/unknown fields, cross-field rules for cell_write, and per-(engine, boot) monotonicity of `seq`/`timestamp_us`. The tests cover all of this (`tests/test_schema_synth.py`).

## Can v0.1 support what the Mac Studio model needs?

| Model need | v0.1 coverage | Finding |
|---|---|---|
| AFR **error** per cell (measured − target) | ❌ No commanded AFR target in samples. Target differs by stage (14.7 cruise vs 12.8 load in the sim) | **Gap.** Without it the model has to guess intent. → v0.2 `afr_target` |
| Separate VE error from warm-up enrichment | ❌ 29 % of AFR-valid samples are enriched; the model would learn enrichment as a VE error | **Gap.** → v0.2 `warmup_enrich_pct` |
| Exclude transients | ❌ No accel-enrichment flag (TPS derivative is only a proxy) | **Gap.** → v0.2 `accel_enrich_active` |
| Know whether closed-loop EGO trim was already correcting | ❌ | **Gap.** Measured AFR is post-trim. → v0.2 `ego_correction_pct` |
| Trust trigger / RPM integrity | ❌ | **Gap.** → v0.2 `sync_loss_count` |
| Label samples by safety status | ❌ | **Gap.** Training filters on green-only. → v0.2 `status` |
| Represent the stage names the code uses | ⚠️ v0.1 uses `load`; the curriculum uses `load_test` and has an `aborted` state | **Fixed** in the v0.2 enum |
| Every envelope decision reason | ❌ No codes for invalid_value, off_table, wrong_engine, stale_timestamp, stale_basis, learning_frozen, spark_limit, ve_limit (all found by adversarial tests) | **Fixed** in the v0.2 enum |
| Status changes / freezes / resets as events | ❌ | **Fixed**: v0.2 events `status_change`, `learning_frozen`, `operator_reset` |
| Link an audit record to the model request/prompt | ❌ | **Fixed**: v0.2 cell_write `request_id` |
| Wideband B evidence behind a proposal | ❌ Only `afr_mean` | **Fixed**: v0.2 cell_write `afr_b_mean` |
| Safety interlock state always known | ⚠️ `oil_alarm`, `lean_cut_active` were optional | **Made required** in v0.2. EGT and oil pressure stay optional because those sensors may not be fitted |
| Dual-bank semantics | ⚠️ A and B are **separate banks** (AI_TUNING_SAFETY.md), so a steady offset (+0.27 in the sim) can be real | Open: a per-bank cross-check needs a learned offset, not a fixed threshold. Issue opened |

## Gaps found but NOT added to v0.2 (not yet justified, or need a design decision)

- **Map snapshots:** samples log the active cell but not its table value. The model can rebuild values from `cell_write` history, but only if it has the starting map. Proposed fix: a `map_snapshot` record at boot and after every burn. Needs a format decision.
- **Time-sync source and quality** (GPS from NMEA 2000 vs RTC): needed to line up the two engines. Still undecided.
- **Barometric pressure:** Dropbear has `pinBaro`. Baro shifts VE at altitude and with weather. Low priority for a boat at sea level.
- **Marine-specific:** raw-water flow and pressure, exhaust-riser temperature, bilge-blower runtime (interlock), trim/tab position, boat speed and sea state as load proxies. Hardware is TBD.
- **Knock:** no knock sensor is in the BOM. The spark-learning safety case depends on whether we add one.
- **Status-event flapping:** at the 11.0 AFR band edge, raw per-sample status flips yellow/green hundreds of times during warm-up. The generator debounces `status_change` events (1 s hold). The real firmware/gateway needs a defined debounce/hysteresis.

## Caveats
Synthetic data proves the schema is complete and **internally consistent**. It does **not** prove the sample rates are achievable or that the thresholds are right. See the TARGET/TODO notes in DATA-SCHEMA.md.
