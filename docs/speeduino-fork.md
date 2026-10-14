# Speeduino Fork (Nicequantum/speeduino)

| | |
|---|---|
| Fork | https://github.com/Nicequantum/speeduino (GitHub fork of `speeduino/speeduino`; default branch `master`, the same as upstream) |
| Submodule | `third_party/speeduino`; `.gitmodules` sets `url = https://github.com/Nicequantum/speeduino.git`, `branch = grok-pilot` |
| Pinned commit | `29bdaa32fc35764094e281f169754714100ce1f0`, upstream release tag **`202501`** (2025-01-07) |
| Branches | `master` = an untouched upstream mirror. [`grok-pilot`](https://github.com/Nicequantum/speeduino/tree/grok-pilot) was created from tag `202501` (`29bdaa3`) and has no commits of its own yet. [`feat/proposal-command`](https://github.com/Nicequantum/speeduino/tree/feat/proposal-command) holds the #11 work, in draft fork PR [#1](https://github.com/Nicequantum/speeduino/pull/1) → `grok-pilot` |
| Pinned commit = `grok-pilot` HEAD | `29bdaa3` (identical to upstream 202501 until fork PR #1 merges) |

**Why the pin didn't move:** the tag-202501 commit exists on the fork, so repointing the URL changed *where* the code comes from but not *which* firmware gets built. The fork's `master` HEAD (`c965de4`, 2026-10-12) is untagged upstream development, and we only build release tags (FORK-NOTES upstream-tracking plan). Verified after the repoint: `pio run -e teensy41` still succeeds, and the image size is identical (FLASH code 232,256 B).

`branch = grok-pilot` in `.gitmodules` only affects `git submodule update --remote`. Pins are still explicit SHAs. **Pin bump rule:** when work lands on `grok-pilot`, bump the ahanu-ecu pin to `grok-pilot` HEAD, but only after `pio run -e teensy41` passes, and record the RAM/flash delta here.

**Workflow choice:** changes reach `grok-pilot` through **PRs from feature branches inside the fork** (e.g. `feat/proposal-command` → `grok-pilot`), not direct commits. That gives a reviewable diff against the 202501 baseline and a place to record build deltas. Fork PR #1 stays a draft until ahanu-ecu PR #12 (the envelope source of truth) is merged, and the vendored copy is re-checked against it.

## Why fork
1. **Marine proposal command:** a dedicated serial command for AI map-write proposals, kept separate from TunerStudio's `'M'` write path (#11).
2. **Envelope integration:** link `firmware/envelope/envelope.h` (C++ port, draft PR #12) into the firmware so the Teensy disposes, not the phone.
3. **Marine pin map and inputs:** Spartan 3 Lite UART wideband(s), MAX31855 EGT, VDO 360-004 oil sender and 87-805605A1 alarm, bilge-blower interlock, hardware lean-cut hook. Plus extra log fields (DATA-SCHEMA v0.2) such as per-channel PW and cell_write records.

None of this can live in this repo alone, because every option touches upstream `comms.cpp` / `pages.cpp` / `init.cpp`. Licence: GPL-3.0. Fork changes are published in the public fork.

## Branch layout (planned)
- `master`: an untouched mirror of upstream `master`. We never commit to it.
- `grok-pilot`: our marine changes, branched from tag `202501`. This is the branch the submodule pins once changes exist.
- Generic fixes go upstream as PRs from topic branches.

## Merging upstream into grok-pilot (notes)
- Merge **release tags only**, never `master`: `git merge --no-ff <tag>` on a `sync/<tag>` branch, then PR into `grok-pilot`.
- Hot spots for conflicts are `speeduino/comms.cpp` (the `'Y'` case and one include) and `.github/workflows/`. Everything else is new files (`speeduino/grok_pilot/`, `grok_pilot_glue.*`, `test/grok_pilot_native/`).
- After each merge:
  1. **Re-check that `'Y'` is still unused** in `comms.cpp`, `comms_legacy.cpp` and `reference/speeduino.ini`.
  2. Re-check page numbers (`pages.h`: VE 2, ign 3, AFR 5), table encodings in `speeduino.ini`, `OFFSET_IGNITION`, and the `setPageValue`/`getPageValue`/`isEepromWritePending` signatures.
  3. Run the native tests and `pio run -e teensy41`, and compare RAM/flash.

## Upstream sync procedure

Run in a clone of the fork:
```bash
git clone https://github.com/Nicequantum/speeduino.git && cd speeduino
git remote add upstream https://github.com/speeduino/speeduino.git
git fetch upstream --tags

# 1. keep the mirror current (fast-forward only; never commit on master)
git checkout master
git merge --ff-only upstream/master
git push origin master
git push origin --tags

# 2. on a new upstream RELEASE tag (e.g. 2026xx), bring it into grok-pilot by MERGE
git checkout grok-pilot
git checkout -b sync/2026xx
git merge --no-ff 2026xx          # resolve conflicts here
pio run -e teensy41               # must build
git push origin sync/2026xx       # open PR sync/2026xx -> grok-pilot, run bench loop, then merge
```

Then bump the pin in ahanu-ecu on a branch:
```bash
cd third_party/speeduino && git fetch origin --tags && git checkout <grok-pilot or tag commit SHA> && cd ../..
git add third_party/speeduino && git commit -m "Bump speeduino to <tag/SHA>: <reason>"
```
After the bump: update the pin table in FORK-NOTES, run the Ardu-Stim bench loop, and diff `reference/speeduino.ini` for changes to logging, table encoding or pages that affect DATA-SCHEMA or the envelope byte encoding.

**Cadence:** upstream publishes dated release tags (`YYYYMM`, e.g. `202501`). Sync **per upstream release tag** only, not continuously. Review upstream activity monthly.

**Merge vs rebase:** **merge.** `grok-pilot` is published and pinned by SHA from ahanu-ecu, so rebasing would rewrite pinned commits and need force-pushes, which we don't do. Rebase only local, unpushed topic branches. Keep the marine patch set small and isolated (new files plus thin hooks) to keep merges cheap.

## #11 plan: AI proposal command

Flow inside the fork (`grok-pilot` branch):
1. **Command:** a new framed command on the new-protocol serial path (`comms.cpp` command switch). The letter or ID still has to be chosen; it must be unused in `202501`'s `comms.cpp` and in `reference/speeduino.ini`. Optionally a CAN equivalent later.
2. **Decode and type-check:** fixed binary layout (engine_id u8, table_code u8, rpm_idx u8, map_idx u8, value_before and value_proposed as int16 in engineering units ×10 or float32 — TBD, timestamp, evidence u16, proposal_id u32) plus a CRC32, the same as the existing new-protocol framing. A wrong length, bad CRC, or out-of-range enum is rejected *before* a `grok_pilot::Proposal` is built. This replaces the Python-side type checks the typed C++ API can't express.
3. **Validate:** `grok_pilot::Envelope::evaluate()` from `firmware/envelope/envelope.h` (PR #12). The envelope's table copy is loaded from EEPROM at boot and updated on **every** write path (the TunerStudio `'M'`/`'W'` writes included), so `stale_basis` reflects the real map.
4. **Write if accepted or clamped:** convert to the table byte encoding (VE U08 1 %/bit; spark U08 1°/bit, −40 offset; AFR U08 0.1/bit), **rounding toward the old value**, so the quantized change never exceeds the envelope limit. Rounding to no change at all is logged as accepted with no write (exact semantics TBD in #11 vectors). Then write via `setPageValue()` → `set_table_value()` for pages 2, 3 and 5. Set `deferEEPROMWritesUntil` the way `updatePageValues()` does.
5. **Log:** reply with decision, reason and value_accepted, and append a `cell_write` record (DATA-SCHEMA v0.2) to SD for every proposal, rejected ones included.
6. **Burn policy:** AI writes go to **RAM only**. They're never auto-burned to EEPROM in v1. Burning needs an explicit operator command (the existing `'b'`), after reviewing the session's accepted cells. A power cycle reverts unburned AI changes, which is the safe default. TBD: whether a per-session "AI write count" gates the burn.

**Status:** implemented on `feat/proposal-command` (fork PR #1). The wire protocol is in [PROPOSAL-WIRE-PROTOCOL.md](PROPOSAL-WIRE-PROTOCOL.md): command `'Y'`, a 26-byte request with inner CRC32, a 14-byte response, a RAM ring log instead of SD for now, and `BUSY_EEPROM` while a burn is pending. Remaining work is tracked in #11, #13 and #14.
