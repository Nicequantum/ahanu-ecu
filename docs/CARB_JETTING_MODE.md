# Carb jetting mode

Status: **software-only**, on branch `feature/carb-jetting-mode`. Tested on synthetic data only, never on a boat.

## 1. What it is

Each engine room runs in one engine-room mode, `efi` or `carb` (`carb.EngineRoomMode`, mirroring Ahanu's `EngineRoomMode`). **EFI is the default, and EFI behaviour is unchanged.** Every new code path is gated on `EngineRoomMode.CARB`.

In **carb mode**:

| Function | Who controls it | What the system does |
|---|---|---|
| Fuel | The carburetor (Edelbrock 1410) | Analyses logged load AFR and **recommends** a jet change |
| Spark | Speeduino, through a GM 7/8-pin HEI module | Auto-tune may propose **spark cells only**, through the unchanged envelope |
| Jet swap | **A person** (physical job) | Logs the AFR window before and after the swap as an experiment |

**The AI never writes anything to the carb.** Jet changes are advice. A person does the swap and then declares it (`jet_swap_declared` event). The system logs the before and after windows as a `jet_change` experiment record.

## 2. Code map

| Piece | File |
|---|---|
| Mode, jet ladder, load-AFR analysis, recommendation, one-step rule, record builder | `src/grok_pilot/carb.py` |
| Mode-aware gateway, proposal-response **v2** | `src/grok_pilot/gateway_v2.py`, `schemas/proposal-response.v2.schema.json` |
| Curriculum mode wrapper and `carb_jetting` branch | `src/grok_pilot/carb_curriculum.py` (plus `Stage.CARB_JETTING`, which is not in the EFI `ORDER`) |
| Log schema v0.3 (`jet_change`, `carb_jetting`, new reasons and events) | `src/grok_pilot/schema.py`, [DATA-SCHEMA.md](DATA-SCHEMA.md) |
| Ingest `jet_changes` table, query, dashboard, HTTP `/jet_changes` | `src/grok_pilot/ingest/` (store schema 2) |
| Prompt templates **v2** (v1 untouched, output byte-identical) | `src/grok_pilot/prompts/v2/`, `prompts/carb_prompts.py` |
| Tests | `tests/test_carb.py`, `test_carb_curriculum.py`, `test_schema_v03.py`, `test_ingest_carb.py`, the v2 section of `test_prompts.py` |

## 3. Rules (deterministic layer)

**Fuel is locked in carb mode.**
- A VE or AFR-target proposal is rejected as `carb_fuel_locked` before it reaches the envelope, so the envelope state never changes.
- The cell gate is also restricted to `spark` (`carb_cell_allowed`), as defence in depth.

**Jetting evidence (`analyze_afr`)** comes only from load samples, never idle.
- **secondary** circuit: WOT samples (`tps ≥ 85 %`, `rpm ≥ 3000`).
- **primary** circuit: on-plane samples (`25 ≤ tps < 70 %`, `2500–4200 rpm`, `MAP ≥ 55 kPa`). The secondaries are assumed closed here. This is an assumption, see §7.
- Samples are excluded if either wideband status isn't `ok`, if accel enrichment or lean cut is active, or if any value is missing or non-finite.
- A sample's AFR is the mean of AFR A and AFR B, since one carb feeds both banks.
- Per-cell stats use the active `ve_cell` indices. A cell with fewer than `min_samples_per_cell` samples is excluded (`thin_cells`).

**Gates applied to the evidence cells.** Each one blocks the recommendation and is reported as the reason:

| Gate | Default | Reason |
|---|---|---|
| Total qualifying samples | ≥ 100, and at least 1 cell with ≥ 20 | `insufficient_samples` |
| Per-cell \|mean A − mean B\| | ≤ 0.3 AFR | `wideband_disagree` |
| Every cell mean | ≥ 10.5 | `afr_floor` (inspect, don't jet) |
| Every cell mean | ≤ 16.0 | `afr_ceiling` (dangerously lean: stop and inspect) |
| Std of load AFR | ≤ 0.6 | `afr_variance` |

**Recommendation (`recommend`).** The target band is **11.0–12.0**, biased rich.
- Above the band: one ladder step richer.
- Below the band: one step leaner.
- In the band: hold.
- At the end of the ladder: hold, with reason `off_ladder` ("check rods, float, fuel supply").

**Model jetting proposal (`evaluate_jet`).** Checks run in this order:
1. Mode is carb and stage is `carb_jetting`, else `stage_locked`.
2. Table is `jet` and the bank is valid, else `off_table`.
3. Sizes are finite, else `invalid_value`.
4. `current_size` equals the declared installed jet, else `stale_basis`.
5. Both sizes are on the ladder, else `off_ladder`.
6. No experiment is still open, else `experiment_open` (one jet change per cycle).
7. The evidence gates above.
8. The proposal isn't a no-op, else `invalid_value`.
9. The direction matches the deterministic recommendation, else `wrong_direction`.
10. **At most 1 ladder step.** A bigger jump is **clamped** to one step with reason `jet_step_exceeded`. With `clamp_jet_steps=False` it's rejected instead.

**Experiment lifecycle.**
1. The proposal is decided. A `jet_change` record with `phase=proposed` stores the prior AFR window.
2. The person swaps the jet and declares it.
3. New load data is collected and analysed the same way.
4. A `jet_change` record with `phase=evaluated` stores the new window, `afr_delta` and `moved_toward_target`, then the experiment closes.

## 4. Curriculum

`ModeCurriculum` wraps the unchanged `Curriculum`:
- **EFI:** a pure pass-through. Tested to give identical step results.
- **Carb:** the same stages and safety checks, with spark-only cells.
- **Entering `carb_jetting`:** only from `load_test`, with operator confirmation, and only if the load-AFR gates pass. It refuses on high variance under load, a low sample count, wideband disagreement, or AFR outside the floor/ceiling.
- **Leaving `carb_jetting`:** any red step (regress or abort) exits the branch.
- **Switching mode** needs an operator ack and restarts at `cold_start`.

## 5. Edelbrock 1410 calibration reference (verified 2026-10-14)

The 1410 is Edelbrock's **Marine Series 750 CFM**, square-flange, electric choke, non-EGR carburetor [1][2]. The user reports it on a **5.7 Vortec**. That's user-provided, not something Edelbrock states: the 1410 page lists the application as "Universal" [1], and the reseller text says it suits "small-block and big-block V8 engines" [2]. A Vortec head needs a Vortec-pattern intake, which is outside this doc's scope.

**Out-of-box calibration** [1][2]: primary jet **.113**, secondary jet **.107**, metering rods **.071 × .047**, step-up spring **orange (5 in Hg)**.

**Main jets** (Edelbrock p/n, verified [3][5][6][7]):

| p/n | 1427 | 1429 | 1430 | 1431 | 1432 | 1433 | 1434 |
|---|---|---|---|---|---|---|---|
| size (in) | .098 | .101 | .104 | .107 | .110 | .113 | .116 |

These seven make the .003 in staging ladder used by the code. **#1428 exists but is .100 in** [7], so it's off-ladder and not used for steps. Jet ID check from the owner's manual: the stamped code is "120-" plus three digits, and those digits minus 300 give the size, e.g. 120-413 = .113 = #1433 [3].

**Secondary staging, #1407/#1410 chart** [3]. This matches the user's lean-12/-8/-4/stock/+4/+8/+12 exactly:

| Lean 12 % | Lean 8 % | Lean 4 % | **Stock** | Rich 4 % | Rich 8 % | Rich 12 % |
|---|---|---|---|---|---|---|
| #1427 .098 | #1429 .101 | #1430 .104 | **#1431 .107** | #1432 .110 | #1433 .113 | #1434 .116 |

**Primary.** The published #1407/#1410 chart has 27 rod/jet combinations, not a seven-jet staging list [3]. Primary jets used in it: .107, .110, .113 (stock), .116.

**Metering rods in that chart** range from **.062 × .052 (#1441)** to **.073 × .052 (#1457)**. Stock is .071 × .047 (#1453) [3]. The #1480 calibration kit adds rods .065×.037, .065×.047, .068×.047, .073×.047 and .073×.052, and jets .101–.116 [4].

**Step-up springs (five)** [4]:

| Colour | Blue | Yellow | Orange (stock) | Pink | Silver |
|---|---|---|---|---|---|
| in Hg | 3 | 4 | 5 | 7 | 8 |

Rods and springs are **context only**. The system never proposes changing them.

### Discrepancies with the brief

- **Jet part numbers.** The real p/ns are **1427–1434** (four digits), with **1428 = .100 off-ladder**. "14227–14234" is not supported by any source found and appears to be a typo.
- **"Seven primary sizes."** Not published as a staging list for the primary on #1407/#1410. Primary tuning is mainly done with rods. The code uses the same physical seven-jet ladder for both circuits; the user should confirm this.
- **Rod range** .062×.052 to .073×.052: matches the published chart.
- **Five spring colours:** match.
- **Secondary staging:** matches.

### Sources

1. Edelbrock, Marine Carb #1410: https://www.edelbrock.com/marine-series-750-cfm-carburetor-with-electric-choke-non-egr-1410.html
2. Tunersports, 1410 listing (quotes Edelbrock's calibration text): https://www.tunersports.com/edelbrock-1410-marine-carb-p96302.html
3. Edelbrock Performer Series Carburetor Owner's Manual (#1403–#1413), p. 25, "Model #1407 & #1410 Rod/Jet Reference Chart": https://auto.manualsonline.com/manuals/mfg/edelbrock_corporation/14031413.html?p=25
4. Edelbrock calibration kit #1480 (for #1407/#1410/#1412/#1413): https://www.edelbrock.com/performer-series-calibration-kit-for-1407-1410-1412-1413-carburetors-1480.html
5. Edelbrock jet #1430 (.104): https://www.edelbrock.com/edelbrock-primary-metering-jet-104-qty-2-1430.html
6. Edelbrock jet #1431 (.107): https://www.edelbrock.com/edelbrock-primary-metering-jet-107-qty-2-1431.html
7. Edelbrock jet #1428 (.100): https://www.edelbrock.com/edelbrock-primary-metering-jet-100-qty-2-1428.html

## 6. Marine note: bias rich

The WOT target is **11.0–12.0 AFR by default**. Marine engines run at sustained high load (planing against a prop, with no road-load relief), so they need **detonation margin**. A slightly rich mixture also cools the chambers and the exhaust. Recommendations aim for that band and never lean out for power. The band lives in `JetConfig.afr_target_lo/hi`.

## 7. Open items for the user to decide

| Item | User value (jetting config) | Repo EFI default (unchanged) | Note |
|---|---|---|---|
| Min samples per cell | 20 | `EnvelopeConfig.min_evidence_samples = 50` | Jetting uses 20. EFI is unchanged |
| Wideband disagreement | 0.3 AFR | Curriculum warns at 0.7 and faults at 1.5. Prompt `wideband_fault_afr = 1.5` | Jetting uses 0.3 per cell (strict). Real bank offsets may trip it, as the synthetic engine 1 has a 0.25 offset |
| VE delta | ±2.5 % | `max_fuel_delta_pct = 5.0` | **Not changed.** It's irrelevant in carb mode, where VE is locked |
| AFR floor / ceiling | 10.5 / 16.0 | 10.5 / 16.0 | Same |
| WOT target band | 11.0–12.0 | Curriculum "sane" band 11.0–15.5 | Separate concept, unchanged |

Other assumptions and ambiguities:
- **Evidence windows per circuit:** primary uses on-plane cells and secondary uses WOT cells. At WOT the primaries also flow, so a WOT-lean reading could partly be primary-side. The code moves only the bank that was proposed.
- **Load filter thresholds** (TPS, RPM, MAP) and `max_afr_std = 0.6` are placeholders until there's boat data.
- **HEI wiring:** Speeduino driving a 7/8-pin HEI's EST input (with bypass and reference) is assumed. It hasn't been bench-tested here; see the Ardu-Stim bench and #11.
- **Carb-mode `sample` records** keep `inj_pw_us` (all zeros). A carb-specific profile could drop it later.
