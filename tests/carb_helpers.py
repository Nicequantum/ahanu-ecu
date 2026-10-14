"""Synthetic load samples for carb-mode tests (deterministic)."""
T0 = 1791000000000000


def load_samples(afr=12.6, n=200, bank="secondary", spread=0.1, b_offset=0.0, cells=((14, 13), (15, 14)),
                 t0=T0, engine_id=0, idle_afr=None):
    out = []
    tps, rpm, mp = (95.0, 4400, 98.0) if bank == "secondary" else (45.0, 3200, 70.0)
    for i in range(n):
        r, m = cells[i % len(cells)]
        a = afr + spread * ((i % 5) - 2) / 2
        out.append({"record_type": "sample", "engine_id": engine_id, "timestamp_us": t0 + i * 100_000, "seq": i,
                    "rpm": rpm, "tps_pct": tps, "map_kpa": mp, "afr_a": round(a, 3), "afr_b": round(a + b_offset, 3),
                    "afr_a_status": "ok", "afr_b_status": "ok", "accel_enrich_active": False,
                    "lean_cut_active": False, "ve_cell_rpm_idx": r, "ve_cell_map_idx": m})
    if idle_afr is not None:  # idle data must never count as evidence
        for i in range(n):
            out.append({**out[0], "timestamp_us": t0 + (n + i) * 100_000, "seq": n + i, "rpm": 700, "tps_pct": 2.0,
                        "map_kpa": 35.0, "afr_a": idle_afr, "afr_b": idle_afr, "ve_cell_rpm_idx": 1,
                        "ve_cell_map_idx": 2})
    return out
