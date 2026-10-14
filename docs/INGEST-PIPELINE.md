# Mac Studio ingest pipeline

Package: `src/grok_pilot/ingest/`. Stdlib only (sqlite3, gzip, http.server), so there are no extra dependencies.
Status: **software-only**. It is tested against synthetic data and has never been run on real Teensy logs.

## 1. On-disk log format (interim): GPLOG-JSONL

The format is interim until #8 settles the Teensy SD/stream format. It stays consistent with DATA-SCHEMA v0.2 by design.

- UTF-8 [JSON Lines](https://jsonlines.org/). Each line holds one DATA-SCHEMA record (`sample`, `cell_write` or `event`), with fields named exactly as in `schema.py` and `docs/DATA-SCHEMA.md`.
- Optional gzip (`.jsonl.gz`).
- Blank lines and lines starting with `#` are ignored (use them for a free-form header).
- Recommended filename: `e<engine_id>_b<boot_id>_<first_timestamp_us>.jsonl[.gz]`. The reader does not depend on the name.
- Synthetic generator output (`grok_pilot.synth.generate`) uses the same record dicts, so it ingests directly, with no file needed.
- If #8 adopts a binary format, add a decoder that yields the same dicts. Everything downstream stays unchanged.

## 2. Validation and quarantine

Every record goes through `schema.validate_record`, which checks the version, types, ranges, enums and required fields. Invalid input is not dropped. It goes to the `quarantine` table along with the raw line, source, line number, reason and errors. Reasons:

| reason | meaning |
|---|---|
| `parse_error` | the line is not JSON, or not a JSON object |
| `schema_invalid` | the record fails DATA-SCHEMA validation |
| `duplicate_conflict` | the natural key is already stored, but the content differs. The stored row is kept |

## 3. Idempotency

- The natural key is `(engine_id, boot_id, seq)`. It is unique across all record types and enforced by the `record_keys` table. `seq` is monotonic per boot.
- Each record is fingerprinted with the SHA-256 of its canonical JSON.
- Re-importing the same record only counts it as a duplicate. Re-importing a whole file is therefore a no-op.
- Each file or batch runs as one transaction and is logged in `imports`.

## 4. SQLite store

- WAL journal mode for file databases, with `synchronous=NORMAL`.
- `samples`: typed columns for every v0.2 sample field (`inj_pw_us` is stored as JSON text). PK is `(engine_id, boot_id, seq)`, WITHOUT ROWID. Index on `(engine_id, timestamp_us)`.
- `cell_writes` and `events`: key, time and decision/event columns, plus the full record as `payload` JSON.
- Also `quarantine`, `imports`, and `meta` (`store_schema_version=1`).

## 5. Query API (Python)

```python
from grok_pilot.ingest import Store
st = Store("pilot.db")
st.ingest_file("e0_b771356991_1791000000100000.jsonl.gz")
rows = st.query_samples(engine_id=0, start_us=a, end_us=b, fields=["rpm", "afr_a", "afr_b"])          # raw
agg  = st.query_samples(engine_id=None, start_us=a, end_us=b, fields=["rpm"], bucket_s=10, agg="max") # downsampled
st.state_at(0, t_us); st.query_cell_writes(0, a, b, decision="rejected"); st.query_events(None, a, b)
st.dashboard()   # per engine/stage summary, decision counts, last rejects, quarantine counts
```

Query semantics:

- The window is half-open: `[start_us, end_us)`. `start == end` returns nothing, and `end < start` raises `ValueError`.
- Fields are checked against the column whitelist, so unknown names raise `ValueError` and no SQL can be injected through them.
- Buckets are aligned to `start_us`. Each row carries `bucket_start_us` and `n`. `agg` is one of `avg`, `min` or `max`, and booleans average to a fraction.

## 6. CLI

```
python -m grok_pilot.ingest import-synthetic --db pilot.db --samples 6000 --seed 1
python -m grok_pilot.ingest import --db pilot.db logs/*.jsonl.gz
python -m grok_pilot.ingest query --db pilot.db --engine 0 --start 2026-10-14T03:00:00Z --end 2026-10-14T03:10:00Z --fields rpm,afr_a,afr_b --bucket 10
python -m grok_pilot.ingest state --db pilot.db --engine 1 --at 1791000300000000
python -m grok_pilot.ingest dashboard --db pilot.db
python -m grok_pilot.ingest quarantine --db pilot.db
python -m grok_pilot.ingest serve --db pilot.db --port 8765
```

Times can be given as epoch microseconds or as ISO-8601 with an explicit zone. Zone-less ISO times are refused.

### Example: basic dashboard query

This uses synthetic seed 1 with 6,000 samples per engine. Re-running the import gives `inserted: 0, duplicates: 12177`.

```
$ python -m grok_pilot.ingest query --db pilot.db --engine 0 --start 1791000000000000 --end 1791000060000000 --fields rpm,coolant_c,afr_a --bucket 20
[{"engine_id":0,"bucket_start_us":1791000000000000,"n":199,"rpm":749.3,"coolant_c":19.3,"afr_a":null}, ...]
```

`afr_a` is null in the first bucket because the wideband is still warming up.

## 7. Local HTTP endpoint (read-only)

The endpoint binds to `127.0.0.1` by default and returns JSON. It has no authentication, so do not expose it beyond localhost.

Endpoints: `/range`, `/samples?engine=&start_us=&end_us=&fields=&bucket_s=&agg=&limit=`, `/state?engine=&t_us=`, `/cell_writes`, `/events`, `/dashboard`. Bad parameters return 400.

## 8. Tests and known gaps

`tests/test_ingest.py` (21 tests) covers:

- validation and quarantine (6 kinds of invalid input, plus parse errors in a gz file)
- WAL mode
- duplicates, conflicts, cross-type key collisions, and idempotent re-import
- correctness against the source records
- window edges, buckets and `state_at`
- the CLI and the HTTP endpoint

Known gaps:

- The format is not final (#8).
- No retention or compaction yet.
- No performance figures on real multi-hour logs. A 12k-record synthetic import takes about 1 s on the box.
- Finding: `synth.generate(version="0.1")` emits a v0.2-only `status_change` event, which v0.1 validation rejects. Ingest quarantines it correctly. The generator itself has not been changed.
