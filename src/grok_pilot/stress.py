"""Schema stress test: generate synthetic logs, validate them under v0.1 and
v0.2, and print the coverage numbers used in docs/SCHEMA-STRESS-TEST.md.

    python -m grok_pilot.stress [--samples 6000] [--seed 1]
"""
from __future__ import annotations

import argparse
from collections import Counter

from .schema import SCHEMAS, validate_stream
from .synth import generate


def run(samples: int = 6000, seed: int = 1) -> dict:
    rich = list(generate(seed=seed, max_samples=samples, version="0.2"))
    v01 = list(generate(seed=seed, max_samples=samples, version="0.1"))
    r02, r01 = validate_stream(rich), validate_stream(v01)
    smp = [r for r in rich if r["record_type"] == "sample"]
    cw = [r for r in rich if r["record_type"] == "cell_write"]
    warm = sum(1 for r in smp if r["warmup_enrich_pct"] > 0 and r["afr_a"] is not None)
    target_varies = len({r["afr_target"] for r in smp}) > 1
    bank = {}
    for e in (0, 1):
        d = [r["afr_b"] - r["afr_a"] for r in smp if r["engine_id"] == e and r["afr_a"] is not None]
        bank[e] = round(sum(d) / len(d), 3) if d else None
    return {
        "records": len(rich),
        "by_type": dict(Counter(r["record_type"] for r in rich)),
        "v02_invalid": r02["invalid"],
        "v01_invalid": r01["invalid"],
        "v01_error_counts": r01["error_counts"],
        "samples_with_warmup_enrich": warm,
        "samples_with_afr": sum(1 for r in smp if r["afr_a"] is not None),
        "afr_target_varies_by_stage": target_varies,
        "mean_bank_b_minus_a": bank,
        "decisions": dict(Counter(f'{r["decision"]}/{r["reject_reason"]}' for r in cw)),
        "stage_transitions": [(r["engine_id"], r["from_stage"], r["to_stage"], r["detail"])
                              for r in rich if r.get("event") == "stage_transition"],
        "fields_added_v02": {k: sorted(set(SCHEMAS["0.2"][k]) - set(SCHEMAS["0.1"][k])) for k in SCHEMAS["0.2"]},
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    for k, v in run(a.samples, a.seed).items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
