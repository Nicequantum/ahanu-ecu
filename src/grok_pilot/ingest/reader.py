"""On-disk log format reader ("GPLOG-JSONL", interim format until #8 picks a binary one).

A log file is UTF-8 JSON Lines: one DATA-SCHEMA record (v0.1 or v0.2) per line.
It may be gzip-compressed (``.gz``). Blank lines and lines starting with ``#``
are ignored. Recommended file name: ``e<engine_id>_b<boot_id>_<first_timestamp_us>.jsonl[.gz]``.
The name is informational only; every record carries its own header.
"""
from __future__ import annotations

import gzip
import io
import json
from typing import Iterator, Tuple, Union

ParsedLine = Tuple[int, Union[dict, None], str, Union[str, None]]  # (line_no, record|None, raw, parse_error|None)


def _open(path: str):
    if str(path).endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8")
    return open(path, "r", encoding="utf-8")


def read_lines(lines) -> Iterator[ParsedLine]:
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        try:
            rec = json.loads(s)  # NaN/Infinity literals parse; the validator rejects them
        except json.JSONDecodeError as e:
            yield i, None, s, f"json: {e.msg}"
            continue
        if not isinstance(rec, dict):
            yield i, None, s, "json: not an object"
            continue
        yield i, rec, s, None


def read_records(path: str) -> Iterator[ParsedLine]:
    with _open(path) as f:
        yield from read_lines(f)
