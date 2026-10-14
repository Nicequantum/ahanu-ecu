"""SQLite time-series store for DATA-SCHEMA records.

- Natural keys: (engine_id, boot_id, seq) for every record type, which makes ingest idempotent.
- An identical duplicate is counted and skipped. A same-key record with different
  content is quarantined as ``duplicate_conflict`` and the stored row is left alone.
- Invalid records (schema validation, JSON errors) go to ``quarantine`` with errors and raw text.
- WAL journal mode; indexes on (engine_id, timestamp_us).
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from ..schema import SCHEMAS, validate_record
from .reader import read_lines, read_records

SAMPLE_COLS = [k for k in SCHEMAS["0.2"]["sample"] if k not in ("record_type",)]
NUMERIC_SAMPLE_COLS = [k for k, f in SCHEMAS["0.2"]["sample"].items() if f.type in ("int", "float", "bool")
                       and k not in ("engine_id", "boot_id", "seq", "timestamp_us")]
STORE_SCHEMA_VERSION = 1

DDL = f"""
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS samples (
  {", ".join(
      (f"{c} TEXT" if c == "inj_pw_us" or SCHEMAS["0.2"]["sample"][c].type in ("str", "enum") else
       f"{c} INTEGER" if SCHEMAS["0.2"]["sample"][c].type in ("int", "bool") else f"{c} REAL")
      for c in SAMPLE_COLS)},
  record_sha TEXT NOT NULL,
  source TEXT,
  PRIMARY KEY (engine_id, boot_id, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS samples_engine_time ON samples (engine_id, timestamp_us);
CREATE TABLE IF NOT EXISTS cell_writes (
  engine_id INTEGER NOT NULL, boot_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  timestamp_us INTEGER NOT NULL, schema_version TEXT NOT NULL, stage TEXT,
  proposal_id INTEGER, tbl TEXT, cell_rpm_idx INTEGER, cell_map_idx INTEGER,
  value_before REAL, value_proposed REAL, value_accepted REAL, decision TEXT, reject_reason TEXT,
  payload TEXT NOT NULL, record_sha TEXT NOT NULL, source TEXT,
  PRIMARY KEY (engine_id, boot_id, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS cell_writes_engine_time ON cell_writes (engine_id, timestamp_us);
CREATE TABLE IF NOT EXISTS events (
  engine_id INTEGER NOT NULL, boot_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  timestamp_us INTEGER NOT NULL, schema_version TEXT NOT NULL, stage TEXT, event TEXT,
  payload TEXT NOT NULL, record_sha TEXT NOT NULL, source TEXT,
  PRIMARY KEY (engine_id, boot_id, seq)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS events_engine_time ON events (engine_id, timestamp_us);
CREATE TABLE IF NOT EXISTS record_keys (
  engine_id INTEGER NOT NULL, boot_id INTEGER NOT NULL, seq INTEGER NOT NULL,
  record_type TEXT NOT NULL, record_sha TEXT NOT NULL,
  PRIMARY KEY (engine_id, boot_id, seq)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS quarantine (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, line_no INTEGER, reason TEXT NOT NULL,
  errors TEXT NOT NULL, raw TEXT NOT NULL, ingested_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS imports (
  id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, started_at REAL, finished_at REAL,
  read INTEGER, inserted INTEGER, duplicates INTEGER, quarantined INTEGER
);
"""


def record_sha(rec: dict) -> str:
    return hashlib.sha256(json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass
class IngestReport:
    source: str
    read: int = 0
    inserted: int = 0
    duplicates: int = 0
    quarantined: int = 0
    by_type: dict = field(default_factory=dict)
    quarantine_reasons: dict = field(default_factory=dict)

    def as_dict(self):
        return self.__dict__.copy()


class Store:
    def __init__(self, path: str = ":memory:"):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        if path != ":memory:":
            self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(DDL)
        self.db.execute("INSERT OR IGNORE INTO meta VALUES ('store_schema_version', ?)", (str(STORE_SCHEMA_VERSION),))
        self.db.commit()

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------ ingest
    def _quarantine(self, rep, source, line_no, reason, errors, raw):
        self.db.execute("INSERT INTO quarantine (source, line_no, reason, errors, raw, ingested_at) VALUES (?,?,?,?,?,?)",
                        (source, line_no, reason, json.dumps(errors), raw, time.time()))
        rep.quarantined += 1
        rep.quarantine_reasons[reason] = rep.quarantine_reasons.get(reason, 0) + 1

    def _insert(self, rec: dict, sha: str, source: str) -> bool:
        rt = rec["record_type"]
        if rt == "sample":
            row = {c: rec.get(c) for c in SAMPLE_COLS}
            row["inj_pw_us"] = json.dumps(rec.get("inj_pw_us"))
            for c, f in SCHEMAS["0.2"]["sample"].items():
                if f.type == "bool" and row.get(c) is not None:
                    row[c] = int(row[c])
            cols = SAMPLE_COLS + ["record_sha", "source"]
            vals = [row[c] for c in SAMPLE_COLS] + [sha, source]
            cur = self.db.execute(f"INSERT OR IGNORE INTO samples ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", vals)
        elif rt == "cell_write":
            cur = self.db.execute(
                "INSERT OR IGNORE INTO cell_writes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (rec["engine_id"], rec["boot_id"], rec["seq"], rec["timestamp_us"], rec["schema_version"], rec["stage"],
                 rec["proposal_id"], rec["table"], rec["cell_rpm_idx"], rec["cell_map_idx"], rec["value_before"],
                 rec["value_proposed"], rec["value_accepted"], rec["decision"], rec["reject_reason"],
                 json.dumps(rec, sort_keys=True), sha, source))
        else:
            cur = self.db.execute("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (rec["engine_id"], rec["boot_id"], rec["seq"], rec["timestamp_us"],
                                   rec["schema_version"], rec["stage"], rec["event"], json.dumps(rec, sort_keys=True),
                                   sha, source))
        return cur.rowcount == 1

    def _claim_key(self, rec, sha) -> Optional[str]:
        """Claim the natural key across all record types. Returns None if newly
        claimed, else the sha of the record that already owns it."""
        k = (rec["engine_id"], rec["boot_id"], rec["seq"])
        cur = self.db.execute("INSERT OR IGNORE INTO record_keys VALUES (?,?,?,?,?)", k + (rec["record_type"], sha))
        if cur.rowcount == 1:
            return None
        return self.db.execute("SELECT record_sha FROM record_keys WHERE engine_id=? AND boot_id=? AND seq=?", k).fetchone()[0]

    def ingest_records(self, parsed: Iterable, source: str = "<memory>") -> IngestReport:
        """parsed: iterable of dicts, or of (line_no, record|None, raw, parse_error|None) tuples."""
        rep = IngestReport(source)
        started = time.time()
        with self.db:  # one transaction per import
            for item in parsed:
                if isinstance(item, dict):
                    line_no, rec, raw, perr = rep.read + 1, item, None, None
                else:
                    line_no, rec, raw, perr = item
                rep.read += 1
                if raw is None:
                    raw = json.dumps(rec, sort_keys=True, default=str) if rec is not None else ""
                if perr:
                    self._quarantine(rep, source, line_no, "parse_error", [perr], raw)
                    continue
                errs = validate_record(rec)
                if errs:
                    self._quarantine(rep, source, line_no, "schema_invalid", errs, raw)
                    continue
                sha = record_sha(rec)
                owner = self._claim_key(rec, sha)
                if owner is None:
                    self._insert(rec, sha, source)
                    rep.inserted += 1
                    rep.by_type[rec["record_type"]] = rep.by_type.get(rec["record_type"], 0) + 1
                elif owner == sha:
                    rep.duplicates += 1
                else:
                    self._quarantine(rep, source, line_no, "duplicate_conflict",
                                     ["natural key (engine_id, boot_id, seq) exists with different content"], raw)
            self.db.execute("INSERT INTO imports (source, started_at, finished_at, read, inserted, duplicates, quarantined) "
                            "VALUES (?,?,?,?,?,?,?)", (source, started, time.time(), rep.read, rep.inserted,
                                                       rep.duplicates, rep.quarantined))
        return rep

    def ingest_file(self, path: str) -> IngestReport:
        return self.ingest_records(read_records(path), source=str(path))

    def ingest_lines(self, lines, source="<lines>") -> IngestReport:
        return self.ingest_records(read_lines(lines), source=source)

    # ------------------------------------------------------------------ query
    def query_samples(self, engine_id: Optional[int], start_us: int, end_us: int,
                      fields: Optional[Sequence[str]] = None, bucket_s: Optional[float] = None,
                      agg: str = "avg", limit: Optional[int] = None) -> list:
        """Samples with start_us <= timestamp_us < end_us (half-open), ordered by time.

        engine_id=None means both engines. ``fields`` defaults to all numeric fields.
        With ``bucket_s``, rows are aggregated per engine into buckets aligned to
        start_us: ``bucket_start_us``, ``n``, and ``agg`` (avg|min|max) of each numeric field.
        """
        if end_us < start_us:
            raise ValueError("end_us < start_us")
        allowed = set(SAMPLE_COLS)
        fields = list(fields) if fields else list(NUMERIC_SAMPLE_COLS)
        bad = [f for f in fields if f not in allowed]
        if bad:
            raise ValueError(f"unknown fields: {bad}")
        where = "timestamp_us >= ? AND timestamp_us < ?"
        args: list = [start_us, end_us]
        if engine_id is not None:
            where = "engine_id = ? AND " + where
            args.insert(0, engine_id)
        lim = f" LIMIT {int(limit)}" if limit else ""
        if not bucket_s:
            cols = ["engine_id", "timestamp_us"] + [f for f in fields if f not in ("engine_id", "timestamp_us")]
            sql = f"SELECT {','.join(cols)} FROM samples WHERE {where} ORDER BY timestamp_us, engine_id, boot_id, seq{lim}"
            out = [dict(r) for r in self.db.execute(sql, args)]
            if "inj_pw_us" in cols:
                for r in out:
                    r["inj_pw_us"] = json.loads(r["inj_pw_us"]) if r["inj_pw_us"] else None
            return out
        if agg not in ("avg", "min", "max"):
            raise ValueError("agg must be avg|min|max")
        num = [f for f in fields if f in NUMERIC_SAMPLE_COLS]
        if not num:
            raise ValueError("bucketed queries need numeric fields")
        b = int(bucket_s * 1e6)
        if b <= 0:
            raise ValueError("bucket_s must be > 0")
        sel = ", ".join(f"{agg.upper()}({f}) AS {f}" for f in num)
        sql = (f"SELECT engine_id, (? + ((timestamp_us - ?) / {b}) * {b}) AS bucket_start_us, COUNT(*) AS n, {sel} "
               f"FROM samples WHERE {where} GROUP BY engine_id, bucket_start_us ORDER BY bucket_start_us, engine_id{lim}")
        return [dict(r) for r in self.db.execute(sql, [start_us, start_us] + args)]

    def state_at(self, engine_id: int, t_us: int) -> Optional[dict]:
        """Latest sample for the engine with timestamp_us <= t_us."""
        r = self.db.execute("SELECT * FROM samples WHERE engine_id=? AND timestamp_us<=? "
                            "ORDER BY timestamp_us DESC, boot_id DESC, seq DESC LIMIT 1", (engine_id, t_us)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["inj_pw_us"] = json.loads(d["inj_pw_us"]) if d["inj_pw_us"] else None
        return d

    def query_cell_writes(self, engine_id: Optional[int], start_us: int, end_us: int, decision: Optional[str] = None) -> list:
        sql, args = "SELECT payload FROM cell_writes WHERE timestamp_us >= ? AND timestamp_us < ?", [start_us, end_us]
        if engine_id is not None:
            sql += " AND engine_id = ?"; args.append(engine_id)
        if decision:
            sql += " AND decision = ?"; args.append(decision)
        return [json.loads(r[0]) for r in self.db.execute(sql + " ORDER BY timestamp_us, engine_id, seq", args)]

    def query_events(self, engine_id: Optional[int], start_us: int, end_us: int, event: Optional[str] = None) -> list:
        sql, args = "SELECT payload FROM events WHERE timestamp_us >= ? AND timestamp_us < ?", [start_us, end_us]
        if engine_id is not None:
            sql += " AND engine_id = ?"; args.append(engine_id)
        if event:
            sql += " AND event = ?"; args.append(event)
        return [json.loads(r[0]) for r in self.db.execute(sql + " ORDER BY timestamp_us, engine_id, seq", args)]

    def time_range(self, engine_id: Optional[int] = None):
        sql, args = "SELECT MIN(timestamp_us), MAX(timestamp_us), COUNT(*) FROM samples", []
        if engine_id is not None:
            sql += " WHERE engine_id=?"; args.append(engine_id)
        lo, hi, n = self.db.execute(sql, args).fetchone()
        return {"start_us": lo, "end_us": hi, "samples": n}

    def quarantine(self, limit: int = 100) -> list:
        return [dict(r) for r in self.db.execute("SELECT * FROM quarantine ORDER BY id LIMIT ?", (limit,))]

    def dashboard(self, start_us: Optional[int] = None, end_us: Optional[int] = None) -> dict:
        """Example dashboard query: per-engine/per-stage summary + decisions + last rejects."""
        tr = self.time_range()
        start_us = tr["start_us"] if start_us is None else start_us
        end_us = (tr["end_us"] + 1 if tr["end_us"] is not None else 0) if end_us is None else end_us
        stages = [dict(r) for r in self.db.execute(
            "SELECT engine_id, stage, COUNT(*) AS samples, ROUND(AVG(rpm),0) AS rpm_avg, ROUND(AVG(coolant_c),1) AS coolant_avg, "
            "ROUND(AVG(afr_a),2) AS afr_a_avg, ROUND(AVG(afr_b),2) AS afr_b_avg, ROUND(MAX(egt_c),1) AS egt_max, "
            "MIN(timestamp_us) AS first_us, MAX(timestamp_us) AS last_us "
            "FROM samples WHERE timestamp_us>=? AND timestamp_us<? GROUP BY engine_id, stage ORDER BY engine_id, first_us",
            (start_us, end_us))]
        decisions = [dict(r) for r in self.db.execute(
            "SELECT engine_id, decision, reject_reason, COUNT(*) AS n FROM cell_writes WHERE timestamp_us>=? AND timestamp_us<? "
            "GROUP BY engine_id, decision, reject_reason ORDER BY engine_id, n DESC", (start_us, end_us))]
        rejects = [dict(r) for r in self.db.execute(
            "SELECT engine_id, timestamp_us, proposal_id, tbl, cell_rpm_idx, cell_map_idx, value_before, value_proposed, reject_reason "
            "FROM cell_writes WHERE decision='rejected' AND timestamp_us>=? AND timestamp_us<? ORDER BY timestamp_us DESC LIMIT 10",
            (start_us, end_us))]
        q = self.db.execute("SELECT reason, COUNT(*) FROM quarantine GROUP BY reason").fetchall()
        return {"window": {"start_us": start_us, "end_us": end_us}, "stages": stages, "decisions": decisions,
                "last_rejects": rejects, "quarantine": {r[0]: r[1] for r in q}}
