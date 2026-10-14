"""Generate shared envelope test vectors from the Python reference.

    PYTHONPATH=src python tests/vectors/gen_envelope_vectors.py > tests/vectors/envelope_vectors.txt

The C++ port (firmware/envelope) replays this file and must give identical
decisions, reasons and values, bit for bit. CI regenerates the file and fails
if it differs from the committed copy.

Line format (whitespace-separated; doubles use Python repr, so nan/inf/-inf
round-trip through strtod):
  S <name> <engine_id> <clamp_deltas 0|1>     start scenario (default config otherwise)
  F <ve> <spark> <afr>                        fill every cell of the 16x16 tables
  C <table_code> <r> <m> <value>              set one cell
  Z <0|1>                                     frozen flag
  P <engine> <table_code> <r> <m> <before> <proposed> <ts> <evidence> <now> <allow_lo> <allow_hi> <commit>
    = <decision> <reason> <value_before> <value_accepted>
    allow_lo = -1 means no stage-lock callback; otherwise allowed iff allow_lo <= r <= allow_hi
  E                                           end scenario
"""
from __future__ import annotations

import math
import random
import sys

from grok_pilot.envelope import Envelope, EnvelopeConfig, Proposal

TABLES = ["ve", "spark", "afr_target", "boost"]  # index 3 = unknown table → off_table


def fmt(x) -> str:
    return repr(float(x))


class Gen:
    def __init__(self, out):
        self.out = out
        self.n = 0

    def scenario(self, name, engine_id=0, clamp=True, fill=(100.0, 20.0, 14.7)):
        self.env = Envelope(EnvelopeConfig(engine_id=engine_id, clamp_deltas=clamp))
        self.out.write(f"S {name} {engine_id} {int(clamp)}\n")
        if fill is not None:
            for t, v in zip(TABLES, fill):
                for r in range(16):
                    for m in range(16):
                        self.env.tables[t][(r, m)] = v
            self.out.write(f"F {fmt(fill[0])} {fmt(fill[1])} {fmt(fill[2])}\n")

    def cell(self, tc, r, m, v):
        self.env.tables[TABLES[tc]][(r, m)] = v
        self.out.write(f"C {tc} {r} {m} {fmt(v)}\n")

    def frozen(self, f):
        self.env.frozen = f
        self.out.write(f"Z {int(f)}\n")

    def prop(self, tc, r, m, before, proposed, ts, n=100, eng=0, now=None, allow=None, commit=True):
        now = ts if now is None else now
        cb = None if allow is None else (lambda t, rr, mm, a=allow: a[0] <= rr <= a[1])
        p = Proposal(eng, TABLES[tc], r, m, before, proposed, ts, n)
        res = self.env.evaluate(p, now, cell_allowed=cb, commit=commit)
        lo, hi = allow if allow else (-1, -1)
        self.out.write(f"P {eng} {tc} {r} {m} {fmt(before)} {fmt(proposed)} {fmt(ts)} {n} {fmt(now)} {lo} {hi} {int(commit)}"
                       f" = {res.decision.value} {res.reason.value} {fmt(res.value_before)} {fmt(res.value_accepted)}\n")
        self.n += 1
        return res

    def end(self):
        self.out.write("E\n")


NOW = 1000.0
INF, NAN = math.inf, math.nan


def handwritten(g: Gen):
    """Mirrors tests/test_envelope.py case by case (typed cases only)."""
    g.scenario("accept_within_limits"); g.prop(0, 5, 5, 100.0, 103.0, NOW); g.end()
    for v in (105.0, 95.0, 105.0001, 94.9, 140.0):
        g.scenario(f"fuel_delta_{v}"); g.prop(0, 5, 5, 100.0, v, NOW); g.end()
    g.scenario("fuel_delta_reject_mode", clamp=False); g.prop(0, 5, 5, 100.0, 106.0, NOW); g.end()
    for v in (22.0, 18.0, 22.01, 17.0):
        g.scenario(f"spark_delta_{v}"); g.prop(1, 5, 5, 20.0, v, NOW); g.end()
    g.scenario("spark_abs_low"); g.cell(1, 5, 5, 1.0); g.prop(1, 5, 5, 1.0, -0.1, NOW); g.end()
    g.scenario("spark_abs_high"); g.cell(1, 5, 5, 35.0); g.prop(1, 5, 5, 35.0, 36.01, NOW); g.end()
    g.scenario("spark_abs_exact"); g.cell(1, 5, 5, 35.0); g.prop(1, 5, 5, 35.0, 36.0, NOW); g.end()
    for v in (10.5, 16.0, 10.49, 16.01, 0.0, -14.7):
        g.scenario(f"afr_{v}"); g.prop(2, 5, 5, 14.7, v, NOW); g.end()
    for v in (9.99, 150.01, -5.0, 0.0):
        g.scenario(f"ve_abs_{v}"); g.prop(0, 5, 5, 100.0, v, NOW); g.end()
    for name, b, v, ts in [("prop_nan", 100.0, NAN, NOW), ("prop_inf", 100.0, INF, NOW), ("prop_ninf", 100.0, -INF, NOW),
                           ("before_nan", NAN, 101.0, NOW), ("ts_nan", 100.0, 101.0, NAN), ("ts_inf", 100.0, 101.0, INF)]:
        g.scenario(f"invalid_{name}"); g.prop(0, 5, 5, b, v, ts, now=NOW); g.end()
    g.scenario("huge_values")
    for v in (1e308, -1e308, float(2**63)):
        g.prop(0, 5, 5, 100.0, v, NOW)
    g.prop(0, 5, 5, 100.0, 101.0, NOW + 1)  # table untouched → basis still 100
    g.end()
    g.scenario("now_nan"); g.prop(0, 5, 5, 100.0, 101.0, NOW, now=NAN); g.end()
    for r, m in [(-1, 0), (0, -1), (16, 0), (0, 16), (10**9, 0)]:
        g.scenario(f"off_table_{r}_{m}"); g.prop(0, r, m, 100.0, 101.0, NOW); g.end()
    g.scenario("unknown_table"); g.prop(3, 1, 1, 1.0, 1.0, NOW); g.end()
    for e in (1, -1, 2):
        g.scenario(f"wrong_engine_{e}"); g.prop(0, 5, 5, 100.0, 101.0, NOW, eng=e); g.end()
    for ts in (NOW - 2.0001, NOW - 3600, 0.0, NOW + 0.5001, NOW + 1e9, NOW - 2.0, NOW + 0.5):
        g.scenario(f"ts_{ts!r}"); g.prop(0, 5, 5, 100.0, 101.0, ts, now=NOW); g.end()
    g.scenario("replay"); g.prop(0, 5, 5, 100.0, 101.0, NOW); g.prop(0, 5, 5, 101.0, 102.0, NOW); g.end()
    g.scenario("stale_basis"); g.prop(0, 5, 5, 90.0, 92.0, NOW); g.end()
    for n in (49, 50, -1):
        g.scenario(f"evidence_{n}"); g.prop(0, 5, 5, 100.0, 101.0, NOW, n=n); g.end()
    g.scenario("frozen"); g.frozen(True); g.prop(0, 5, 5, 100.0, 101.0, NOW); g.end()
    g.scenario("stage_lock"); g.prop(0, 5, 5, 100.0, 101.0, NOW, allow=(0, 4)); g.end()
    g.scenario("rate_limit_window")
    v = 100.0
    for k in range(3):
        v = g.prop(0, 5, 5, v, v + 1, NOW + k).value_accepted
    g.prop(0, 5, 5, v, v + 1, NOW + 3)
    g.prop(0, 5, 5, v, v + 1, NOW + 60)
    g.end()
    g.scenario("rate_limit_per_cell")
    for k in range(3):
        g.prop(0, 5, 5, 100.0 + k, 101.0 + k, NOW + k)
    g.prop(0, 6, 5, 100.0, 101.0, NOW + 3)
    g.end()
    g.scenario("rejections_dont_consume_budget")
    for k in range(10):
        g.prop(0, 5, 5, 100.0, NAN, NOW + k)
    g.prop(0, 5, 5, 100.0, 101.0, NOW + 10)
    g.end()
    g.scenario("ratchet")
    v = 100.0
    for k in range(100):
        r = g.prop(0, 5, 5, v, v * 10, NOW + k * 0.5)
        if r.applied:
            v = r.value_accepted
    g.end()
    g.scenario("dry_run"); g.prop(0, 5, 5, 100.0, 104.0, NOW, commit=False); g.prop(0, 5, 5, 100.0, 104.0, NOW + 1); g.end()
    g.scenario("empty_tables_no_basis_check", fill=None); g.prop(0, 5, 5, 77.0, 78.0, NOW); g.prop(2, 1, 1, 14.0, 13.5, NOW); g.end()


SPECIAL = [NAN, INF, -INF, 1e308, -1e308, 0.0, -0.0, 1e-300]


def fuzz(g: Gen, seed: int, scenarios: int, steps: int):
    rng = random.Random(seed)
    for s in range(scenarios):
        eng = rng.choice([0, 1])
        g.scenario(f"fuzz_{seed}_{s}", engine_id=eng, clamp=rng.random() < 0.8,
                   fill=(rng.uniform(20, 140), rng.uniform(5, 34), rng.uniform(11, 15.5)))
        t = 5000.0 + rng.uniform(0, 1000)
        for _ in range(steps):
            if rng.random() < 0.03:
                g.frozen(rng.random() < 0.25)
            tc = rng.choices([0, 1, 2, 3], weights=[50, 25, 23, 2])[0]
            hot = rng.random() < 0.5  # hammer a few cells so rate limiting / replay get exercised
            r = rng.randrange(2) if hot else rng.choices([rng.randrange(16), -1, 16], weights=[96, 2, 2])[0]
            m = rng.randrange(2) if hot else rng.choices([rng.randrange(16), -1, 16], weights=[96, 2, 2])[0]
            tname = TABLES[tc] if tc < 3 else "ve"
            cur = g.env.tables[tname].get((r, m)) if 0 <= r < 16 and 0 <= m < 16 else None
            before = cur if (cur is not None and rng.random() < 0.92) else rng.choice([rng.uniform(-10, 200)] + SPECIAL)
            base = before if math.isfinite(before) else 50.0
            kind = rng.random()
            if kind < 0.1:
                proposed = rng.choice(SPECIAL)
            elif kind < 0.6:
                proposed = base * (1 + rng.uniform(-0.08, 0.08))
            elif kind < 0.7:
                proposed = base + rng.uniform(-3, 3)
            else:
                proposed = rng.uniform(-50, 300)
            t += rng.choice([0.0, 0.1, 0.1, 0.5, 1.0, 5.0, 20.0, 61.0])
            ts = t + (rng.choice([0.0] * 12 + [-0.3, -1.99, -2.0, -2.5, 0.5, 0.6]) if rng.random() < 0.97 else rng.choice(SPECIAL))
            n = rng.choice([100] * 10 + [50, 49, 0, -1, 10**6])
            e = eng if rng.random() < 0.97 else rng.choice([1 - eng, -1, 7])
            allow = None if rng.random() < 0.85 else (rng.randrange(16), rng.randrange(16))
            g.prop(tc, r, m, before, proposed, ts, n=n, eng=e, now=t, allow=allow, commit=rng.random() < 0.95)
        g.end()


def hammer(g: Gen, seed: int, scenarios: int, steps: int):
    """One cell, current basis, jittered sub-window spacing: rate-limit edges."""
    rng = random.Random(seed)
    for s in range(scenarios):
        g.scenario(f"hammer_{seed}_{s}", fill=(100.0, 20.0, 14.7))
        tc = s % 3
        t = 100.0
        for _ in range(steps):
            t += rng.choice([0.25, 1.0, 5.0, 10.0, 19.75, 20.0, 30.0, 60.0])
            cur = g.env.tables[TABLES[tc]][(3, 3)]
            proposed = cur + rng.uniform(-3, 3) if tc else cur * (1 + rng.uniform(-0.1, 0.1))
            g.prop(tc, 3, 3, cur, proposed, t)
        g.end()


def main():
    out = sys.stdout
    out.write("# Generated by tests/vectors/gen_envelope_vectors.py. Do not edit.\n")
    g = Gen(out)
    handwritten(g)
    fuzz(g, seed=20261013, scenarios=40, steps=150)
    hammer(g, seed=7, scenarios=6, steps=60)
    out.write(f"# steps: {g.n}\n")


if __name__ == "__main__":
    main()
