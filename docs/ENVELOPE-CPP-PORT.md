# Validation Envelope: C++ Port (issue #7)

Status: **desktop-verified, not integrated into Speeduino yet.** The module lives on branch `feat/envelope-cpp`.

## Module

| File | Purpose |
|---|---|
| `firmware/envelope/envelope.h` | Header-only port of `src/grok_pilot/envelope.py` |
| `firmware/envelope/test/test_envelope.cpp` | GoogleTest unit tests that mirror `tests/test_envelope.py` |
| `firmware/envelope/test/test_vectors.cpp` | Cross-check: replays the Python-generated vectors |
| `firmware/envelope/test/firmware_flags_check.cpp` | Compiles the header with `-fno-exceptions -fno-rtti` |
| `firmware/envelope/pio/` | Teensy 4.1 PlatformIO smoke build (compile only) |
| `tests/vectors/gen_envelope_vectors.py` → `envelope_vectors.txt` | Shared vectors: 6,543 steps (hand-written cases, seeded fuzz with NaN/±inf/huge/negative/off-table/wrong-engine/stale/future/frozen/stage-lock, and a rate-limit hammer) |

**Teensy constraints:**
- No heap, exceptions or RTTI, and no STL containers.
- All state is fixed-size inside `Envelope`: 3 tables × 16 × 16 cells, each holding the value, the last timestamp, and a ring of up to `kMaxRateTouches` = 4 touch timestamps.
- Behaviour is deterministic.
- **RAM: about 43 KB** of static storage, measured by the PlatformIO teensy41 build (RAM1 variables 46,944 B including the core). For comparison, the stock Speeduino teensy41 build uses 36 KB of RAM1 variables and leaves 226 KB free, so it fits. If space gets tight, it could be shrunk with `float` timestamps relative to boot, or with U08 cell values. That would need new vectors.

**Numerics:** the header uses IEEE-754 `double`, like Python, so results are bit-exact. The Teensy 4.1's Cortex-M7 has a double-precision FPU. Build with `-ffp-contract=off` so the compiler can't fuse multiply-adds, which would change rounding.

## API

```cpp
#include "envelope.h"
using namespace grok_pilot;
EnvelopeConfig cfg;            // defaults == Python EnvelopeConfig
cfg.engine_id = 0;
static Envelope env(cfg);      // static storage; check env.config_ok()
env.set_cell(Table::VE, r, m, ve);           // load the current map
Proposal p = {engine_id, table_code, rpm_idx, map_idx, value_before, value_proposed, timestamp_s, evidence_samples, proposal_id};
Result res = env.evaluate(p, now_s, allowed_fn /*stage lock, may be nullptr*/, ctx, /*commit=*/true);
// res.decision ∈ {ACCEPTED, CLAMPED, REJECTED}, res.reason (reason_name() == schema string), res.value_accepted
env.frozen = true;             // wideband cross-check / curriculum abort
```
In this API "propose" is building a `Proposal` and "accept/reject" is the `Result`. `commit=false` gives a dry run.

## Python ↔ C++ mapping

| Python (`envelope.py`) | C++ (`envelope.h`) | Notes |
|---|---|---|
| `EnvelopeConfig` (frozen dataclass) | `struct EnvelopeConfig` | Same fields and defaults (5 %, 2°, 0–36°, AFR 10.5–16.0, VE 10–150, 50 samples, 3 per 60 s, 2 s age, 0.5 s skew, clamp) |
| `Table` str enum | `enum class Table` + `int32_t table_code` | An unknown table name maps to a code outside 0–2, giving `OFF_TABLE` |
| `Reason` / `Decision` | `enum class Reason/Decision` + `reason_name()` | Strings are identical to DATA-SCHEMA v0.2 |
| `Proposal` / `Result` | `struct Proposal` / `struct Result` | `Result::applied()` |
| `tables` dict (missing cell = no basis check) | `Cell::has_value` | Same behaviour |
| `_touches` deque per cell | fixed ring buffer of 4 per cell | The Python deque never holds more than `rate_limit_touches` entries, so the behaviour is the same |
| `_last_ts` dict | `Cell::last_ts` + `has_last_ts` | Replay check |
| `cell_allowed` callable | `CellAllowedFn` + `void* ctx` | Stage lock |
| `math.isfinite`, `copysign`, `abs` | `isfinite`, `copysign`, `fabs` | Bit-exact under `-ffp-contract=off` |
| Type checks (bool/str/None, non-int indices) | n/a: typed API | The gateway or protocol decoder must reject these before building a `Proposal`. Covered in Python tests only |
| Check order 1–6 | identical | Order decides *which* reason is reported when several apply, and the vectors pin it |

## Test results (2026-10-13, box)
- C++: **28 GoogleTest tests pass** (27 unit tests + 1 vector replay). Built with `-Wall -Wextra -Werror -ffp-contract=off`.
- Cross-check: **6,543 vector steps, 0 mismatches.** A deliberate one-line corruption of the vectors is caught.
- Python: 139 pytest tests pass, including a check that the committed vectors are current.
- Teensy 4.1 (`pio run -d firmware/envelope/pio -e teensy41`): **compiles.** It hasn't run on hardware.

## Where it goes in Speeduino's map-write path

This section comes from reading `third_party/speeduino` at tag `202501`:
- **New protocol:** `comms.cpp`, `case 'M'` ("New write command": page, offset, length, values) calls `updatePageValues()`. That loops `setPageValue(pageNum, offset+i, byte)` from `pages.cpp`, then `map_page_offset_to_entity()` and `set_table_value()`, which writes the table cell in RAM.
- **Legacy protocol:** `comms_legacy.cpp` writes through the same `setPageValue()` (`case 'W'`, plus the chunked write path).
- **Burn:** `case 'b'` / `'B'` calls `writeConfig(page)` and persists RAM to EEPROM.
- **Pages:** `veMapPage 2`, `ignMapPage 3`, `afrMapPage 5` (`pages.h`).
- **Encodings** from `reference/speeduino.ini`:
  - `veTable` is U08, 1 %/bit, 0–255.
  - `advTable1` is U08, 1°/bit, offset −40 (`OFFSET_IGNITION 40`).
  - `afrTable` is U08, 0.1 AFR/bit.
  - All are 16 × 16.

### Open question: where to intercept
1. **Inside `setPageValue()` for table pages 2/3/5.** This catches every writer, TunerStudio included. The catch is that the call is byte-at-a-time with no proposal context (engine id, evidence, timestamp), and it would block normal TunerStudio tuning unless there's a "manual/operator" bypass mode, which needs its own safety story.
2. **A new dedicated serial command** (for example an unused command letter, framed with proposal fields and CRC) that runs `Envelope::evaluate`, then on accept writes via `setPageValue()` and logs a `cell_write` to SD. The existing `'M'` path stays for TunerStudio under operator control. **This is the recommended starting point:** it's the smallest diff and makes the AI path explicit.
3. **A CAN-based proposal channel** (FlexCAN_T4 is already in the teensy41 deps), which would suit the phone/gateway path.

Further points:
- **Quantization:** the envelope works in engineering units (double). The integration layer has to convert the U08 table bytes to units for `value_before`, and quantize `value_accepted` back to a byte **toward `value_before`**, so the quantized change never exceeds the limit. For example, 5 % of VE 30 is 1.5, which becomes 1. This needs specifying plus vectors. Tracked in the integration issue.
- **Map-version mismatch:** `STALE_BASIS` compares against the cell value the envelope holds. The envelope's table copy has to be updated on *every* write path, including TunerStudio `'M'`/`'W'` writes and EEPROM load at boot. Otherwise every AI proposal after a manual edit gets rejected, which is the safe failure mode.
- **Time base:** Python uses epoch seconds. On the Teensy, `timestamp_s` and `now_s` need a shared clock with the gateway (see #8, time sync).

## Fork implications
Every option above modifies upstream `comms.cpp` and/or `pages.cpp`, so integration **requires forking** Speeduino to `Nicequantum/speeduino` (see FORK-NOTES "Fork to Nicequantum later?"). The envelope itself stays in this repo as a header with no Speeduino dependencies, and the fork includes it. Licensing: the combined firmware is GPL-3.0.
