# Grok Prompt Templates (v1)

Code: `src/grok_pilot/prompts/`. Tests: `tests/test_prompts.py`. Implements the prompt and context parts of [GROK-INTEGRATION-API.md](GROK-INTEGRATION-API.md).

## Versioning
- Templates live in `src/grok_pilot/prompts/<version>/`. The current version is **`v1`** (`PROMPT_VERSION`).
- Any wording or section change that could change model behaviour gets a new directory (`v2/`). Old versions stay, so logged proposals can be traced to the exact prompt. Log `prompt_version` next to `model_version` (TBD schema field; see the follow-up issue).
- **Response schema:** unchanged. Still `grok-pilot.proposal-response.v1` (`src/grok_pilot/schemas/proposal-response.v1.schema.json`). No bump was needed, because v1 prompts ask for exactly that contract.

| File | Content |
|---|---|
| `v1/system.md` | System prompt: role (advisory/copilot), envelope rules, reasoning rules (dual-bank, evidence, value_before, audit-trail learning, marine context), output rules |
| `v1/user.md` | User template with fixed sections: REQUEST, ENVELOPE LIMITS, ENGINE STATE, TABLE CELLS, RECENT AUDIT TRAIL, RECENT HISTORY, RESPONSE |
| `v1/examples/*.json` | 3 good and 7 bad responses, each with machine-checkable `expect` |
| `assemble.py` | `assemble_context()`, `render()`, `estimate_tokens()`, `load_examples()` |

## Context assembly (`assemble_context`)
Inputs are DATA-SCHEMA v0.2 records (`sample`, `cell_write`), coming from the Teensy, the synthetic generator, or the ingest store's query API.

| Section | Source | Rules |
|---|---|---|
| REQUEST | caller | request_id, engine_id plus label, stage, status, allowed_rpm_idx, max_proposals, wideband fault threshold |
| ENVELOPE LIMITS | `EnvelopeConfig` | All limits, including rate limit and max_age |
| ENGINE STATE | latest sample per engine within the window | **Both engines.** 25 fields (`STATE_FIELDS`); `null` if an engine has no data |
| TABLE CELLS | caller (`{table: {(r,m): value}}`) | Current values that `value_before` must match |
| RECENT AUDIT TRAIL | `cell_write` for the target engine, ≤ now | Newest last, at most 20, with decision and reject_reason |
| RECENT HISTORY | samples for both engines in `[now − window_s, now]` | Downsampled to `history_every_s` (default 1 s), compact `{"cols":[…],"rows":[[…]]}`, `t_s` relative to now |

**Determinism:** keys are sorted, separators are compact, floats are rounded to 2 decimals (`t_s` to 1), records are sorted by `(timestamp_us, seq)`, and there are no clocks or randomness. NaN/inf become `null` (`allow_nan=False`). The tests check that shuffled input gives byte-identical output.

## Budget and truncation (`render(ctx, budget_tokens=6000)`)
`budget_tokens` covers the **prompt only** (system plus user); reserve the response separately (≈ 1,000–1,500 tokens for 8 proposals with rationale). When the prompt is over budget, items are dropped in this order:
1. **History rows**, oldest first, from whichever engine has more rows.
2. **Audit trail**, oldest first.
3. **Table cells**, those outside the allowed rpm band first.

REQUEST, ENVELOPE LIMITS and ENGINE STATE are **never** cut. If those alone exceed the budget, the call raises `BudgetError` (about 1,560 estimated tokens). `PromptBundle.truncated` reports what was dropped.

## Token estimates
**Method:** the production model's tokenizer isn't available offline. `estimate_tokens()` is a **labeled heuristic**:

`tokens = ceil(letters/4 + digits×0.5 + punctuation×1.0 + non-ASCII×1.0)`, with whitespace free.

I calibrated it against **tiktoken `o200k_base`** (installed in the box venv; used only for calibration, and **only a proxy** for the real tokenizer). Across the rendered v1 prompts and all examples, the heuristic over-estimates o200k by **1.07–1.53×**, which is the safe direction for budgeting. A plain bytes/4 rule undercounts JSON-heavy prompts by about 2× (measured: about 1.7–2.1 bytes per token), which is why it isn't used. **Re-calibrate this when the target tokenizer is known.**

Measured on synthetic data (seed 5, cruise, both engines, 1 s history):

| History window | Budget | System (est) | User (est) | Total (est) | o200k actual | est/actual | Truncated |
|---|---|---|---|---|---|---|---|
| 60 s | none | 545 | 8,718 | 9,263 | 7,908 | 1.17 | – |
| 120 s | none | 545 | 13,808 | 14,353 | 12,904 | 1.11 | – |
| 300 s | none | 545 | 29,053 | 29,598 | 27,757 | 1.07 | – |
| 120 s | 8,000 | 545 | 7,350 | 7,895 | 6,564 | 1.20 | 152 history rows |
| 120 s | 6,000 | 545 | 5,384 | 5,929 | 4,632 | 1.28 | 198 history rows |
| 120 s | 4,000 | 545 | 3,397 | 3,942 | 2,710 | 1.45 | 242 history rows, 1 audit |

**Rules of thumb:**
- The system prompt is about 0.5k tokens.
- Fixed sections are about 1.5k.
- Each history row (both engines) costs about 55 estimated tokens, roughly 3.3k per engine-minute at 1 Hz.

**Phone tier:** with a 6k prompt budget, history covers roughly the last 25 s per engine at 1 Hz, or about 50 s at 2 s spacing (`history_every_s=2`). The Mac Studio tier can afford 300 s or more. The on-device context limit is TBD (#6).

## Examples
| Example | Kind | Expected |
|---|---|---|
| good_ve_small_lean_fix | good | schema ✓, gateway ✓, accepted |
| good_no_change_wideband_disagree | good | empty proposals plus a critical anomaly and a hold recommendation |
| good_spark_and_ve | good | two accepted |
| bad_markdown_wrapped | bad | not parseable JSON |
| bad_missing_explanation | bad | schema ✗ |
| bad_off_table_cell | bad | schema ✗ (rpm_idx 16) |
| bad_autopilot_mode | bad | schema ✓, gateway ✗ (copilot only in v1) |
| bad_wrong_request_id | bad | schema ✓, gateway ✗ |
| bad_envelope_violations | bad | rejected: spark_limit, afr_floor, stale_basis, insufficient_samples |
| bad_greedy_fuel_jump | bad | clamped: fuel_delta_exceeded |

Each test evaluates the example against an envelope with a stage lock on rpm_idx 5–9 (`tests/test_prompts.py::test_example_behaves_as_documented`). Bad examples must fail parsing, the schema, the gateway, or get an envelope intervention. Good examples must be fully accepted.

## Usage
```python
from grok_pilot.prompts import assemble_context, render
ctx = assemble_context(request_id="req-1", engine_id=1, stage="cruise", status="green", allowed_rpm_idx=range(5, 9),
                       envelope_cfg=cfg, samples=samples, cell_writes=cws, tables={"ve": {(7, 10): 80.0}},
                       now_us=now_us, window_s=60)
bundle = render(ctx, budget_tokens=6000)   # bundle.system, bundle.user, bundle.tokens_total, bundle.truncated
```

## v2 (carb jetting, branch feature/carb-jetting-mode)

The v2 templates are in `src/grok_pilot/prompts/v2/` (system.md, user.md and 8 examples), with code in `prompts/carb_prompts.py` (`carb_block`, `render_v2`). The response schema is `grok-pilot.proposal-response.v2`.

What v2 adds over v1:
- `engine_room_mode`
- `allowed_tables` (`["spark"]` in carb mode)
- a mandatory, never-truncated **CARB / JETTING** section: installed jets, rod, spring, the jet ladder, the target band, per-bank load-AFR analysis with the deterministic recommendation, an open-experiment flag, and recent `jet_change` experiments

**v1 is unchanged.** `render()` with default arguments produces byte-identical output, which was checked against the main-branch hash.

Measured on synthetic seed 5, engine 0, with a 120 s window:

| Mode | Budget | Est | o200k | Truncation |
|---|---|---|---|---|
| carb | none | 15,779 | 14,016 | – |
| carb | 6,000 | 5,991 | 4,400 | 230 history rows dropped |
| efi | 6,000 | 5,981 | 4,650 | 212 history rows dropped |

The v2 system prompt is about 1,139 estimated tokens, and the carb block about 788. See [CARB_JETTING_MODE.md](CARB_JETTING_MODE.md).
