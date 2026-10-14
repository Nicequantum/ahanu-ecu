# AI Proposal Command: Wire Protocol (v1)

Implementation: `Nicequantum/speeduino`, branch `feat/proposal-command` (fork PR [#1](https://github.com/Nicequantum/speeduino/pull/1), targeting `grok-pilot`).
- Pure logic: `speeduino/src/grok_pilot/proposal.{h,cpp}`
- Glue: `speeduino/grok_pilot_glue.cpp`
- Command: `comms.cpp` `case 'Y'`
- Tests: `test/grok_pilot_native/`

Status: desktop-tested, compiles for teensy41. **Not run on hardware.**

## Transport
The command uses Speeduino's existing **new (TunerStudio) serial protocol** framing on the primary serial port:

```
[len: u16 big-endian] [payload: len bytes] [crc32(payload): u32 big-endian]
```
The outer framing and CRC come from Speeduino (`serialReceive()` / `sendSerialPayloadNonBlocking()`). A bad outer CRC gets Speeduino's own `SERIAL_RC_CRC_ERR` (0x82). The command is only reachable once the link is in new-protocol mode: a legacy single-byte `'Y'` falls into the legacy handler, which doesn't implement it.

## Command byte: `'Y'` (0x59)
I checked the Speeduino `202501` sources and `speeduino.ini`, and `'Y'` isn't used by any of these:
- the new-protocol `processSerialCommand()` switch in `comms.cpp` (in use: `A B C E F H I J M O Q S T U X b d f h j k o p r t w x`)
- the legacy `comms_legacy.cpp` switch (in use: `? A B C E F G H J L M N O P Q S T U V W X Z \` a b c d g h j m o p r t w x z`)
- the TunerStudio ini command strings (`B H J O Q T X b d h j k o p r t x C E`)

**Future upstream merges must re-check this** (see speeduino-fork.md). The command only exists on Teensy 4.1 builds. Other targets reply `SERIAL_RC_UKWN_ERR` (0x83).

## Request payload (26 bytes; multi-byte fields little-endian)

| Offset | Size | Field | Notes |
|---|---|---|---|
| 0 | 1 | command | `'Y'` (0x59) |
| 1 | 1 | version | `0x01` |
| 2 | 1 | engine_id | 0 = port, 1 = starboard. Must equal the ECU's `GROK_PILOT_ENGINE_ID` build flag |
| 3 | 1 | table_code | 0 = VE (page 2), 1 = spark (page 3), 2 = AFR target (page 5) |
| 4 | 1 | rpm_idx | 0–15 (X / column) |
| 5 | 1 | map_idx | 0–15 (Y / load row) |
| 6 | 1 | before_raw | The cell's **raw table byte** the proposal was based on. Compared exactly against the live table |
| 7 | 1 | flags | Reserved, must be 0 |
| 8 | 4 | value_proposed | IEEE-754 float32, engineering units (VE %, spark ° BTDC, AFR) |
| 12 | 4 | ts_ms | Proposal time in the **ECU `millis()` time base** (the gateway learns it from `ecu_ms` in each response) |
| 16 | 2 | evidence | Sample count behind the proposal (u16) |
| 18 | 4 | proposal_id | Echoed in the response and log |
| 22 | 4 | crc32 | IEEE CRC-32 (zlib) over bytes 0–21 |

**Why there's an inner CRC on top of the frame CRC:** it gives end-to-end integrity from the proposal's author, so it survives transports without Speeduino's framing (a future CAN or secondary-serial path) and catches gateway bugs that re-frame data.

**Why before_raw is a byte rather than a float:** comparing float32 against byte×0.1 isn't exact (14.7f ≠ 147 × 0.1). Comparing raw bytes makes the stale-basis check exact.

## Processing order
1. Structural decode: length is 26, `command` is `'Y'`, version is 1, inner CRC matches, flags is 0. Any failure gives an `rc` error, and nothing reaches the envelope.
2. If an EEPROM burn is in progress (`isEepromWritePending()`), reply `BUSY_EEPROM`. This stops Speeduino's background `writeAllConfig()` from persisting the AI write (see the burn policy below).
3. **Sync:** read the live cell byte via `getPageValue()` and load it into the envelope as units. Any other write path (TunerStudio `'M'`/`'W'`, EEPROM load at boot) is therefore picked up automatically, and `stale_basis` is exact.
4. `Envelope::evaluate()`: the vendored C++ port of `grok_pilot.envelope` (ahanu-ecu PR #12), with the same limits, reasons and check order.
5. If the result is accepted or clamped, convert to a byte **rounded toward the old value**: VE `raw = %`, spark `raw = deg + 40`, AFR `raw = AFR × 10`. The rounding uses ε = 1e-6 to absorb floating-point error. If the rounded byte equals the old byte, the result is reported accepted with `wrote = 0` and no table write.
6. Write via `setPageValue(page, map_idx*16 + rpm_idx, raw)`, the same call TunerStudio's `'M'` path uses. It's **RAM only**, and `deferEEPROMWritesUntil` is refreshed.
7. Append a log record to the RAM ring (64 entries).

## Response payload (14 bytes, little-endian)

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | rc (table below) |
| 1 | 1 | decision: 0 accepted, 1 clamped, 2 rejected. Valid only when rc = 0x00 |
| 2 | 1 | reason (codes below). Valid only when rc = 0x00 |
| 3 | 1 | wrote: 1 if the table byte changed |
| 4 | 1 | old_raw |
| 5 | 1 | new_raw (equals old_raw unless wrote) |
| 6 | 4 | proposal_id (echo; 0 if decode failed) |
| 10 | 4 | ecu_ms: ECU `millis()` when processed (the gateway time base) |

### rc codes
| rc | Meaning |
|---|---|
| 0x00 | PROCESSED: decision and reason are valid |
| 0xA1 | BAD_LENGTH (payload isn't 26 bytes) |
| 0xA2 | BAD_VERSION |
| 0xA3 | BAD_CRC (inner CRC) |
| 0xA4 | BAD_RESERVED (flags ≠ 0) |
| 0xA5 | BUSY_EEPROM: retry after the burn completes |
| 0xA6 | BAD_COMMAND (internal; shouldn't occur via `'Y'`) |
| 0x82 / 0x83 | Speeduino's frame CRC error / unknown command (non-Teensy-4.1 build) |

### reason codes (same order as `grok_pilot::Reason` and DATA-SCHEMA v0.2 strings)
0 none, 1 fuel_delta_exceeded, 2 spark_delta_exceeded, 3 spark_limit, 4 afr_floor, 5 afr_ceiling, 6 ve_limit, 7 rate_limited, 8 wideband_disagree (reserved), 9 insufficient_samples, 10 stage_locked (reserved, no on-ECU stage lock yet), 11 sensor_fault (reserved), 12 invalid_value, 13 off_table, 14 wrong_engine, 15 stale_timestamp, 16 stale_basis, 17 learning_frozen.

## Burn policy
- AI writes **never** trigger an EEPROM write. They persist only when the operator sends Speeduino's normal burn (`'b'`/`'B'` for the page, e.g. from TunerStudio). A power cycle reverts unburned AI changes.
- **Known interaction:** if an operator burn is still pending (`isEepromWritePending()`), Speeduino's loop calls `writeAllConfig()`, which would also persist any AI write made meanwhile. That's why the command returns `BUSY_EEPROM` while a burn is pending.
- **TunerStudio:** AI writes change the page contents, so TunerStudio's page-CRC check will report that the ECU differs from the project. That's expected; the operator reviews and either burns or reloads.

## Logging
Each proposal, decode failures included, is appended to a **RAM ring buffer** of 64 `LogRecord`s (`proposal_id`, `ecu_ms`, rc, engine, table, cell, decision, reason, wrote, old/new raw, value_proposed). It isn't persisted yet.
- **Why not SD now:** Speeduino's SD logger writes its own fixed-format CSV of live data from `logger.cpp`. Adding a second `cell_write` stream (DATA-SCHEMA v0.2) needs new file handling and a format decision (#8), which is a bigger change.
- **Until then:** the gateway must log every response as the authoritative `cell_write`. Reading the ring over serial and SD persistence are follow-ups (#14).

## Gaps / TODO
- Cell orientation (`offset = map_idx*16 + rpm_idx`, following the TunerStudio ini `[16x16]` convention) is **unverified**. Confirm it on the bench by proposing a write and checking the cell in TunerStudio.
- `ts_ms` is a u32 that wraps after about 49.7 days of uptime. Fine for v1; document it in gateway code.
- No on-ECU stage lock or freeze input yet. `frozen` defaults to false and the curriculum runs off-ECU.
- Rate-limit touches count even when rounding leaves the byte unchanged (conservative).
- **RAM cost (teensy41 vs 202501):** +44,672 B RAM1 variables, +2,436 B flash code. Free RAM1 for locals drops from 226,048 B to 181,376 B.
