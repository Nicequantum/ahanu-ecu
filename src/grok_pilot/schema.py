"""Machine-readable Teensy log schema (mirrors docs/DATA-SCHEMA.md).

``SCHEMAS["0.1"]`` is the original draft; ``SCHEMAS["0.2"]`` adds only the
fields justified in docs/SCHEMA-STRESS-TEST.md. Records are dicts with a
``record_type`` of ``sample`` | ``cell_write`` | ``event``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

STAGES_V01 = ["cold_start", "warm_idle", "cruise", "load", "street"]
STAGES_V02 = ["cold_start", "warm_idle", "cruise", "load_test", "street", "aborted"]
WB_STATUS = ["ok", "warming", "fault", "stale"]
SOURCES = ["mac_studio", "iphone", "manual"]
TABLES = ["ve", "spark", "afr_target"]
DECISIONS = ["accepted", "clamped", "rejected"]
REASONS_V01 = ["none", "fuel_delta_exceeded", "spark_delta_exceeded", "afr_floor", "afr_ceiling",
               "rate_limited", "wideband_disagree", "insufficient_samples", "stage_locked", "sensor_fault"]
REASONS_V02 = REASONS_V01 + ["spark_limit", "ve_limit", "invalid_value", "off_table", "wrong_engine",
                             "stale_timestamp", "stale_basis", "learning_frozen"]
EVENTS_V01 = ["stage_transition", "lean_cut", "fault", "boot", "interlock", "watchdog_trip"]
EVENTS_V02 = EVENTS_V01 + ["status_change", "learning_frozen", "operator_reset"]
# v0.3 (carb jetting mode, docs/CARB_JETTING_MODE.md). Additive only: every valid v0.2 record
# is valid v0.3 once its schema_version is changed.
STAGES_V03 = STAGES_V02 + ["carb_jetting"]
REASONS_V03 = REASONS_V02 + ["carb_fuel_locked", "jet_step_exceeded", "off_ladder", "wrong_direction",
                             "afr_variance", "experiment_open"]
EVENTS_V03 = EVENTS_V02 + ["engine_room_mode", "jet_swap_declared"]
JET_BANKS = ["primary", "secondary"]
SPRING_COLORS = ["blue", "yellow", "orange", "pink", "silver"]
ENGINE_ROOM_MODES = ["efi", "carb"]
JET_PHASES = ["proposed", "evaluated"]


@dataclass(frozen=True)
class F:
    type: str                      # int | float | bool | str | enum | list_int
    lo: Optional[float] = None
    hi: Optional[float] = None
    enum: Optional[list] = None
    required: bool = True
    length: Optional[int] = None


def _header(stages):
    return {
        "schema_version": F("str"),
        "record_type": F("enum", enum=["sample", "cell_write", "event"]),
        "engine_id": F("int", 0, 1),
        "boot_id": F("int", 0, 2**32 - 1),
        "seq": F("int", 0, 2**63 - 1),
        "timestamp_us": F("int", 0, 2**64 - 1),
        "stage": F("enum", enum=stages),
    }


def _v01():
    h = _header(STAGES_V01)
    sample = {**h,
        "rpm": F("int", 0, 65535), "map_kpa": F("float", 0, 6553.5), "tps_pct": F("float", 0, 100),
        "coolant_c": F("float", -40, 150), "iat_c": F("float", -40, 150),
        "afr_a": F("float", 0, 655.35, required=False), "afr_b": F("float", 0, 655.35, required=False),
        "afr_a_status": F("enum", enum=WB_STATUS), "afr_b_status": F("enum", enum=WB_STATUS),
        "battery_v": F("float", 0, 655.35), "spark_adv_deg": F("float", -3276.8, 3276.7),
        "inj_pw_us": F("list_int", 0, 65535, length=8),
        "ve_cell_rpm_idx": F("int", 0, 255), "ve_cell_map_idx": F("int", 0, 255),
        # recommended additions in v0.1 (optional)
        "egt_c": F("float", -270, 1372, required=False), "egt_fault": F("int", 0, 7, required=False),
        "oil_press_kpa": F("float", 0, 65535, required=False), "oil_alarm": F("bool", required=False),
        "ecu_temp_c": F("float", -40, 150, required=False), "lean_cut_active": F("bool", required=False),
    }
    cw = {**h,
        "proposal_id": F("int", 0, 2**32 - 1), "source": F("enum", enum=SOURCES), "model_version": F("str"),
        "table": F("enum", enum=TABLES), "cell_rpm_idx": F("int", 0, 255), "cell_map_idx": F("int", 0, 255),
        "value_before": F("float"), "value_proposed": F("float"), "value_accepted": F("float"),
        "decision": F("enum", enum=DECISIONS), "reject_reason": F("enum", enum=REASONS_V01),
        "evidence_samples": F("int", 0, 65535), "afr_mean": F("float", 0, 655.35), "afr_target": F("float", 0, 655.35),
    }
    ev = {**h, "event": F("enum", enum=EVENTS_V01), "detail": F("str", required=False),
          "from_stage": F("enum", enum=STAGES_V01, required=False), "to_stage": F("enum", enum=STAGES_V01, required=False),
          "code": F("int", 0, 65535, required=False)}
    return {"sample": sample, "cell_write": cw, "event": ev}


def _v02():
    s = _v01()
    h = _header(STAGES_V02)
    for rt in s:
        s[rt].update(h)
    s["sample"].update({
        "afr_target": F("float", 0, 655.35),        # commanded AFR: needed for error signal
        "ego_correction_pct": F("float", -100, 100),  # closed-loop trim active at the time
        "warmup_enrich_pct": F("float", 0, 255),    # confounds cold-start fuel learning
        "accel_enrich_active": F("bool"),           # transient samples must be excluded
        "sync_loss_count": F("int", 0, 65535),      # trigger integrity
        "status": F("enum", enum=["green", "yellow", "red"]),
        "egt_c": F("float", -270, 1372, required=False),
        "oil_press_kpa": F("float", 0, 65535, required=False),
        "oil_alarm": F("bool"), "lean_cut_active": F("bool"),
    })
    s["cell_write"]["reject_reason"] = F("enum", enum=REASONS_V02)
    s["cell_write"].update({"request_id": F("str"), "afr_b_mean": F("float", 0, 655.35)})
    s["event"]["event"] = F("enum", enum=EVENTS_V02)
    s["event"]["from_stage"] = F("enum", enum=STAGES_V02, required=False)
    s["event"]["to_stage"] = F("enum", enum=STAGES_V02, required=False)
    return s


def _v03():
    s = _v02()
    h = _header(STAGES_V03)
    h["record_type"] = F("enum", enum=["sample", "cell_write", "event", "jet_change"])
    for rt in s:
        s[rt].update(h)
    s["cell_write"]["reject_reason"] = F("enum", enum=REASONS_V03)
    s["event"]["event"] = F("enum", enum=EVENTS_V03)
    s["event"]["from_stage"] = F("enum", enum=STAGES_V03, required=False)
    s["event"]["to_stage"] = F("enum", enum=STAGES_V03, required=False)
    s["event"]["engine_room_mode"] = F("enum", enum=ENGINE_ROOM_MODES, required=False)
    afr = lambda req=True: F("float", 0, 655.35, required=req)
    s["jet_change"] = {**h,
        # identity / audit (same pattern as cell_write)
        "proposal_id": F("int", 0, 2**32 - 1), "request_id": F("str"), "source": F("enum", enum=SOURCES),
        "model_version": F("str"), "phase": F("enum", enum=JET_PHASES),
        "engine_room_mode": F("enum", enum=["carb"]),
        "bank": F("enum", enum=JET_BANKS),
        "jet_before": F("float", 0.05, 0.2), "jet_proposed": F("float", 0.05, 0.2), "jet_accepted": F("float", 0.05, 0.2),
        "rod": F("str", required=False), "spring": F("enum", enum=SPRING_COLORS, required=False),
        "decision": F("enum", enum=DECISIONS), "reject_reason": F("enum", enum=REASONS_V03),
        "rationale": F("str", required=False),
        "afr_target_lo": afr(), "afr_target_hi": afr(),
        # prior AFR window (the evidence the recommendation is based on)
        "before_start_us": F("int", 0, 2**64 - 1), "before_end_us": F("int", 0, 2**64 - 1),
        "afr_before_mean": afr(), "afr_before_std": F("float", 0, 100), "afr_before_n": F("int", 0, 2**32 - 1),
        # human-declared physical swap + new AFR window (phase=evaluated only)
        "swap_declared_us": F("int", 0, 2**64 - 1, required=False),
        "after_start_us": F("int", 0, 2**64 - 1, required=False), "after_end_us": F("int", 0, 2**64 - 1, required=False),
        "afr_after_mean": afr(False), "afr_after_std": F("float", 0, 100, required=False),
        "afr_after_n": F("int", 0, 2**32 - 1, required=False),
        "afr_delta": F("float", -100, 100, required=False), "moved_toward_target": F("bool", required=False),
    }
    return s


SCHEMAS = {"0.1": _v01(), "0.2": _v02(), "0.3": _v03()}
CURRENT = "0.2"


def _check(name: str, f: F, v: Any) -> Optional[str]:
    if f.type == "bool":
        return None if isinstance(v, bool) else f"{name}: expected bool"
    if f.type == "str":
        return None if isinstance(v, str) and v else f"{name}: expected non-empty str"
    if f.type == "enum":
        return None if v in f.enum else f"{name}: {v!r} not in {f.enum}"
    if f.type == "list_int":
        if not isinstance(v, list) or (f.length and len(v) != f.length):
            return f"{name}: expected list of {f.length}"
        for i, x in enumerate(v):
            e = _check(f"{name}[{i}]", F("int", f.lo, f.hi), x)
            if e:
                return e
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return f"{name}: expected number"
    if f.type == "int" and not isinstance(v, int):
        return f"{name}: expected int"
    if not math.isfinite(v):
        return f"{name}: non-finite"
    if f.lo is not None and v < f.lo or f.hi is not None and v > f.hi:
        return f"{name}: {v} out of range [{f.lo}, {f.hi}]"
    return None


def validate_record(rec: dict, version: Optional[str] = None) -> list[str]:
    """Return a list of error strings (empty = valid)."""
    if not isinstance(rec, dict):
        return ["record is not an object"]
    version = version or rec.get("schema_version")
    if version not in SCHEMAS:
        return [f"unknown schema_version {version!r}"]
    spec = SCHEMAS[version].get(rec.get("record_type"))
    if spec is None:
        return [f"unknown record_type {rec.get('record_type')!r}"]
    errs = []
    for k, f in spec.items():
        if k not in rec or rec[k] is None:
            if f.required:
                errs.append(f"{k}: missing")
            continue
        e = _check(k, f, rec[k])
        if e:
            errs.append(e)
    for k in rec:
        if k not in spec:
            errs.append(f"{k}: unknown field")
    if rec.get("record_type") == "cell_write" and not errs:
        if rec["decision"] == "rejected" and rec["reject_reason"] == "none":
            errs.append("reject_reason: rejected record needs a reason")
        if rec["decision"] == "accepted" and rec["reject_reason"] != "none":
            errs.append("reject_reason: accepted record must have reason none")
        if rec["decision"] == "rejected" and rec["value_accepted"] != rec["value_before"]:
            errs.append("value_accepted: must equal value_before when rejected")
    if rec.get("record_type") == "jet_change" and not errs:
        errs += _jet_change_rules(rec)
    return errs


_AFTER = ("swap_declared_us", "after_start_us", "after_end_us", "afr_after_mean", "afr_after_n", "afr_delta",
          "moved_toward_target")


def _jet_change_rules(r: dict) -> list:
    e = []
    if r["decision"] == "rejected" and r["reject_reason"] == "none":
        e.append("reject_reason: rejected record needs a reason")
    if r["decision"] == "accepted" and r["reject_reason"] != "none":
        e.append("reject_reason: accepted record must have reason none")
    if r["decision"] == "rejected" and r["jet_accepted"] != r["jet_before"]:
        e.append("jet_accepted: must equal jet_before when rejected")
    if r["before_end_us"] < r["before_start_us"]:
        e.append("before_end_us: before window ends before it starts")
    if r["afr_target_hi"] < r["afr_target_lo"]:
        e.append("afr_target_hi: below afr_target_lo")
    present = [k for k in _AFTER if r.get(k) is not None]
    if r["phase"] == "proposed" and present:
        e.append(f"phase: proposed record must not carry after-swap fields ({present[0]})")
    if r["phase"] == "evaluated":
        missing = [k for k in _AFTER if r.get(k) is None]
        if missing:
            e.append(f"{missing[0]}: required when phase=evaluated")
        elif r["decision"] == "rejected":
            e.append("phase: a rejected proposal cannot be evaluated (no swap was advised)")
        else:
            if not (r["before_end_us"] <= r["swap_declared_us"] <= r["after_start_us"] <= r["after_end_us"]):
                e.append("after_start_us: windows must be ordered before < swap <= after")
            if abs(r["afr_delta"] - (r["afr_after_mean"] - r["afr_before_mean"])) > 0.011:
                e.append("afr_delta: must equal afr_after_mean - afr_before_mean")
    return e


def validate_stream(records) -> dict:
    """Validate a sequence; also checks per-(engine, boot) seq/timestamp monotonicity."""
    from collections import Counter
    total, bad, errors, counts = 0, 0, [], Counter()
    last: dict = {}
    for i, r in enumerate(records):
        total += 1
        e = validate_record(r)
        if not e:
            k = (r["engine_id"], r["boot_id"])
            if k in last:
                ps, pt = last[k]
                if r["seq"] <= ps:
                    e.append("seq: not strictly increasing")
                if r["timestamp_us"] < pt:
                    e.append("timestamp_us: went backwards")
            last[k] = (r["seq"], r["timestamp_us"])
        if e:
            bad += 1
            counts.update(x.split(":")[0] + ":" + (x.split(":", 1)[1][:60] if ":" in x else "") for x in e)
            if len(errors) < 50:
                errors.append((i, e))
    return {"total": total, "invalid": bad, "errors": errors, "error_counts": dict(counts)}
