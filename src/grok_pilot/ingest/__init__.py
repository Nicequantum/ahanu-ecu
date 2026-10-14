"""Mac Studio ingest pipeline: Teensy log files -> validated SQLite time-series store.

See docs/INGEST-PIPELINE.md.
"""
from .reader import read_records
from .store import IngestReport, Store

__all__ = ["Store", "IngestReport", "read_records"]
