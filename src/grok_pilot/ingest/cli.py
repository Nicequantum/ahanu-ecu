"""CLI: python -m grok_pilot.ingest <command> ...

  import-synthetic --db store.db [--samples 6000 --seed 1 --version 0.2]
  import --db store.db FILE [FILE ...]          (JSONL or .jsonl.gz)
  query --db store.db --engine 0 --start 2026-10-14T03:00:00Z --end ... [--fields rpm,afr_a] [--bucket 10]
  state --db store.db --engine 0 --at <time>
  dashboard --db store.db
  quarantine --db store.db
  serve --db store.db [--port 8765]

Times are accepted as integer microseconds since the epoch, or as ISO-8601 (Z or with an offset).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from ..synth import generate
from .store import Store


def parse_time(s: str) -> int:
    if s.lstrip("-").isdigit():
        return int(s)
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("ISO times need an explicit zone (Z or +hh:mm)")
    return int(dt.timestamp() * 1_000_000)


def _out(obj):
    json.dump(obj, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m grok_pilot.ingest", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    def add(name):
        p = sub.add_parser(name)
        p.add_argument("--db", required=True)
        return p
    p = add("import-synthetic"); p.add_argument("--samples", type=int, default=6000); p.add_argument("--seed", type=int, default=1)
    p.add_argument("--version", default="0.2")
    p = add("import"); p.add_argument("files", nargs="+")
    p = add("query"); p.add_argument("--engine", type=int); p.add_argument("--start", required=True)
    p.add_argument("--end", required=True); p.add_argument("--fields"); p.add_argument("--bucket", type=float)
    p.add_argument("--agg", default="avg"); p.add_argument("--limit", type=int)
    p = add("state"); p.add_argument("--engine", type=int, required=True); p.add_argument("--at", required=True)
    add("dashboard"); add("quarantine")
    p = add("serve"); p.add_argument("--host", default="127.0.0.1"); p.add_argument("--port", type=int, default=8765)
    a = ap.parse_args(argv)

    st = Store(a.db)
    try:
        if a.cmd == "import-synthetic":
            _out(st.ingest_records(generate(seed=a.seed, max_samples=a.samples, version=a.version),
                                   source=f"synthetic:seed={a.seed}:samples={a.samples}:v{a.version}").as_dict())
        elif a.cmd == "import":
            _out([st.ingest_file(f).as_dict() for f in a.files])
        elif a.cmd == "query":
            _out(st.query_samples(a.engine, parse_time(a.start), parse_time(a.end),
                                  a.fields.split(",") if a.fields else None, a.bucket, a.agg, a.limit))
        elif a.cmd == "state":
            _out(st.state_at(a.engine, parse_time(a.at)))
        elif a.cmd == "dashboard":
            _out(st.dashboard())
        elif a.cmd == "quarantine":
            _out(st.quarantine())
        elif a.cmd == "serve":
            from .http import serve
            srv = serve(a.db, a.host, a.port)
            print(f"serving {a.db} on http://{a.host}:{a.port} (Ctrl-C to stop)", file=sys.stderr)
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
    finally:
        st.close()


if __name__ == "__main__":
    main()
