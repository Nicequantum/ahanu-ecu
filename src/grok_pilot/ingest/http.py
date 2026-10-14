"""Tiny read-only local HTTP endpoint over a Store (stdlib only). Binds 127.0.0.1 by default.

GET /range?engine=0
GET /samples?engine=0&start_us=..&end_us=..&fields=rpm,afr_a&bucket_s=1&agg=avg&limit=1000
GET /state?engine=0&t_us=..
GET /cell_writes?engine=0&start_us=..&end_us=..&decision=rejected
GET /events?engine=0&start_us=..&end_us=..&event=stage_transition
GET /dashboard
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import Store


def _int(q, k, default=None):
    v = q.get(k, [None])[0]
    return default if v in (None, "") else int(v)


def make_handler(db_path: str):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quiet
            pass

        def _send(self, code, obj):
            body = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            st = Store(db_path)  # one connection per request (sqlite objects aren't thread-safe)
            try:
                eng = _int(q, "engine")
                if u.path == "/range":
                    return self._send(200, st.time_range(eng))
                if u.path == "/samples":
                    fields = q.get("fields", [""])[0]
                    bucket = q.get("bucket_s", [None])[0]
                    return self._send(200, st.query_samples(eng, _int(q, "start_us"), _int(q, "end_us"),
                                                            fields.split(",") if fields else None,
                                                            float(bucket) if bucket else None,
                                                            q.get("agg", ["avg"])[0], _int(q, "limit", 10000)))
                if u.path == "/state":
                    return self._send(200, st.state_at(eng, _int(q, "t_us")))
                if u.path == "/cell_writes":
                    return self._send(200, st.query_cell_writes(eng, _int(q, "start_us"), _int(q, "end_us"),
                                                                q.get("decision", [None])[0]))
                if u.path == "/events":
                    return self._send(200, st.query_events(eng, _int(q, "start_us"), _int(q, "end_us"),
                                                           q.get("event", [None])[0]))
                if u.path == "/dashboard":
                    return self._send(200, st.dashboard())
                return self._send(404, {"error": "not found"})
            except (ValueError, TypeError) as e:
                return self._send(400, {"error": str(e)})
            finally:
                st.close()
    return H


def serve(db_path: str, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(db_path))
