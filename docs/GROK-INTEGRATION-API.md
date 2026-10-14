# Grok Integration API (v1 spec)

Status: draft spec with a reference implementation in `src/grok_pilot/grok.py`. The response contract is `src/grok_pilot/schemas/proposal-response.v1.schema.json` (JSON Schema 2020-12), and tests live in `tests/test_grok.py`. Model choice, quantization and hosting are **not decided**. Anything marked TBD is open.

## 1. Contract: co-pilot (v1) vs autopilot (future)

| | Co-pilot (v1, the only mode accepted) | Autopilot (future, not enabled) |
|---|---|---|
| Who proposes | Model (iPhone on-device or Mac Studio) | Model |
| Who disposes | **Teensy envelope**, deterministic and fixed | Teensy envelope (unchanged) |
| Operator role | Confirms stage advances. Sees every proposal and decision | Monitors. Can abort |
| Gateway behaviour | `mode` must be `"copilot"`. `"autopilot"` passes the schema but **the gateway rejects it** | Requires a separate safety case and sign-off. Tracked in #6 |

Invariants, true in every mode:
1. The model never writes a table directly. Each proposal goes into `Envelope.evaluate` and ends as accepted, clamped or rejected with a reason.
2. **Every** proposal is logged as a `cell_write` record (DATA-SCHEMA v0.2) with `request_id`, `decision`, `reject_reason`, `model_version`. Rejected ones are logged too.
3. The model can't change envelope limits, stage, the frozen flag or the hardware lean cut. It can only *recommend* a stage action.
4. A structurally invalid response (bad schema id, `request_id` or `engine_id` mismatch, non-finite numbers, non-copilot mode) rejects the **whole batch**. Nothing is applied and the failure is logged as an event.

## 2. Request flow

```
Teensy/Speeduino --serial/CAN--> gateway (Mac Studio or phone)
  gateway: window recent samples (both engines) + stage/status + envelope limits + table snapshot
        -> build_context()  -> render_prompt()  -> model
  model  -> JSON response (schema v1)
  gateway: check_response() + JSON Schema validation
        -> evaluate_response(): Envelope.evaluate() per proposal (reference model of the Teensy gate)
        -> forward to Teensy, which re-evaluates with its own fixed envelope (authoritative)
        -> log one cell_write per proposal
```
TBD: the transport to the Teensy (Speeduino serial commands vs CAN vs custom) and whether the Teensy gate is a port of `envelope.py` (needed for the "Teensy disposes" guarantee; tracked in a new issue).

## 3. Context payload (`build_context`)

```json
{
  "request_id": "req-1-42",
  "engine_id": 1,
  "stage": "cruise",
  "status": "green",
  "window_s": 60,
  "allowed_rpm_idx": [5, 6, 7, 8],
  "envelope": {"max_fuel_delta_pct": 5.0, "max_spark_delta_deg": 2.0, "spark_min_deg": 0.0, "spark_max_deg": 36.0,
               "afr_floor": 10.5, "afr_ceiling": 16.0, "ve_min": 10.0, "ve_max": 150.0,
               "min_evidence_samples": 50, "rate_limit": {"touches": 3, "window_s": 60.0}},
  "tables": {"ve": {"7,10": 80.0}},
  "samples": {"0": [{"timestamp_us": 0, "rpm": 2800, "map_kpa": 70.1, "afr_a": 14.6, "afr_b": 14.8, "afr_target": 14.7, "...": "..."}],
              "1": ["..."]}
}
```
- Both engines are always included. The other engine is context for comparison and anomaly detection, and proposals are only allowed for `engine_id`.
- Window: the last `window_s` seconds, downsampled to ≤ 1 Hz for the phone model. TBD: exact size versus the on-device context limit.
- The `spark_max_deg` default of 36 is a placeholder (TODO: confirm for the marinized 350 with HEI or Mallory).

## 4. Prompt template

> Versioned templates (system prompt, context assembly, budgets, examples) now live in `src/grok_pilot/prompts/v1/`. See [PROMPT-TEMPLATES.md](PROMPT-TEMPLATES.md). The inline `grok.PROMPT_TEMPLATE` below is the earlier minimal version and is kept for compatibility.

The prompt lives in `grok.PROMPT_TEMPLATE`. In summary, it covers:
- The role ("advisory only") and the statement that the envelope may clamp or reject.
- The stage, the status, and which `rpm_idx` cells are allowed.
- The envelope limits as JSON.
- A dual-bank note: A and B are separate banks, so a steady offset can be real. If they disagree by more than 1.5 AFR, the model proposes nothing and raises an anomaly.
- The instruction to return ONLY JSON matching `grok-pilot.proposal-response.v1`, `mode` `copilot`, at most 8 proposals, with `value_before` equal to the table value in the context.
- The context JSON.

## 5. Response schema (summary; the JSON Schema file is authoritative)

```json
{
  "schema": "grok-pilot.proposal-response.v1",
  "request_id": "req-1-42", "model_version": "grok-q4-2026-10", "engine_id": 1,
  "stage": "cruise", "mode": "copilot",
  "proposals": [{"table": "ve", "rpm_idx": 7, "map_idx": 10, "value_before": 80.0, "value_proposed": 82.0,
                 "evidence_samples": 120, "confidence": 0.8, "rationale": "Bank A/B both ~0.3 lean"}],
  "stage_recommendation": {"action": "hold", "reason": "need 300 more green cruise samples"},
  "explanation": "Plain-language summary for the helm.",
  "anomalies": [{"severity": "warn", "code": "bank_offset", "message": "Bank B reads 0.3 leaner than A"}]
}
```
The schema limits `rpm_idx`/`map_idx` to 0–15, `confidence` to 0–1, and allows at most 16 proposals and 16 anomalies, with no extra properties. **The schema does not encode safety.** A schema-valid proposal can still be clamped or rejected by the envelope (see `test_schema_valid_but_envelope_violating_proposals`).

## 6. On-device vs Mac Studio vs cloud split

| Task | iPhone (quantized, on-device) | Mac Studio (home port / dock) | Cloud |
|---|---|---|---|
| Per-cell proposals underway | ✅ primary: works offline at sea | ✅ when tethered | ❌ not needed in v1 |
| Stage recommendations, explanations, anomaly flags | ✅ | ✅ | optional |
| Training on longitudinal logs | ❌ | ✅ | optional, opt-in only |
| Envelope / disposal | ❌ never | ❌ reference copy only | ❌ never |

Connectivity at sea is unreliable, so nothing safety-relevant can depend on the cloud. TBD: the on-device model and its size, plus quantization quality tests against Mac Studio outputs.

## 7. Failure modes

| Failure | Detection | Behaviour |
|---|---|---|
| Model timeout / no response | gateway timer | No proposals; engine keeps running on the current map; logged event |
| Malformed JSON / schema fail | JSON Schema + `check_response` | Whole batch rejected and logged |
| Stale response (context older than `max_age_s` = 2 s) | `timestamp_s` = context snapshot time | `stale_timestamp` per proposal |
| Replayed / out-of-order response | `request_id` mismatch, per-cell monotonic timestamp | batch reject / `stale_timestamp` |
| Proposal based on an old map | `value_before` ≠ current cell | `stale_basis` |
| Wrong engine | `engine_id` mismatch | batch reject / `wrong_engine` |
| NaN / Inf / huge values | finite checks, absolute limits | `invalid_value` / `ve_limit` / `spark_limit` |
| Ratcheting (repeated max-delta asks) | per-cell rate limit (3 per 60 s) | `rate_limited`; cell moves at most 3 × 5 % per minute |
| Hallucinated cells | index bounds, stage lock | `off_table` / `stage_locked` |
| Wideband disagreement / sensor fault | curriculum red → envelope frozen | `learning_frozen` |
| Phone dies / gateway crash | Teensy heartbeat (watchdog spec #5) | Teensy keeps the current map; no writes |
| Model tries to talk the operator into unsafe action | — | The explanation is advisory text only, and stage advances need operator confirmation. TBD: UX review |
