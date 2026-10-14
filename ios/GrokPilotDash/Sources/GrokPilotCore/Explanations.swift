import Foundation

/// Plain-language strings for the operator. Deterministic templates — the
/// model's own `explanation` text is shown alongside, never instead of these.
public enum Explain {
    public static func stage(_ s: Stage) -> String {
        switch s {
        case .coldStart: return "Cold start: engine warming up. The AI is watching only; no tuning changes yet."
        case .warmIdle: return "Warm idle: learning idle fuel cells. Changes are small and checked by the ECU."
        case .cruise: return "Cruise: learning the cruise range (about 2000–3500 rpm)."
        case .loadTest: return "Load test: learning heavy-load cells (about 3500–5000 rpm). Watch temps."
        case .street: return "Street mode is disabled in v1."
        case .aborted: return "Learning stopped for safety. An operator must check the engine and reset."
        }
    }
    public static func status(_ s: StageStatus) -> String {
        switch s {
        case .green: return "All checks pass."
        case .yellow: return "Something needs attention; learning is paused until it clears."
        case .red: return "Fault detected; the curriculum stepped back or stopped."
        }
    }
    static let reasons: [String: String] = [
        "lean_cut": "The hardware lean cutoff fired.",
        "oil_alarm": "The oil pressure alarm switch tripped.",
        "overheat": "Coolant is too hot.",
        "egt_high": "Exhaust gas temperature is too high.",
        "low_oil_pressure": "Oil pressure is low for this rpm.",
        "sensor_fault": "A sensor is reporting a fault.",
        "invalid_core_sensor": "RPM, coolant or battery reading is missing or invalid.",
        "wideband_not_ready": "The oxygen sensors aren't ready yet.",
        "wideband_disagree": "The two oxygen sensors disagree a lot — one may be faulty.",
        "wideband_mismatch": "The two oxygen sensors disagree slightly.",
        "afr_out_of_band": "Air-fuel ratio is outside the normal range.",
        "coolant_warm": "Coolant is running warm.",
        "battery_low": "Battery voltage is low.",
        "aborted_await_reset": "Waiting for an operator reset.",
        // envelope reasons
        "none": "Within limits.",
        "fuel_delta_exceeded": "Fuel change was larger than 5% per step, so it was trimmed.",
        "spark_delta_exceeded": "Timing change was larger than 2° per step, so it was trimmed.",
        "spark_limit": "Timing would be outside the safe 0–36° range.",
        "afr_floor": "Target would be richer than the 10.5 floor.",
        "afr_ceiling": "Target would be leaner than the 16.0 ceiling.",
        "ve_limit": "Fuel value would be outside the table's safe range.",
        "rate_limited": "This cell was changed too often recently.",
        "insufficient_samples": "Not enough data behind this suggestion yet.",
        "stage_locked": "This cell isn't open in the current stage.",
        "learning_frozen": "Learning is not allowed in the current stage.",
        "wrong_engine": "Proposal was for the other engine.",
        "off_table": "Proposal pointed outside the table.",
        "invalid_value": "Proposal contained an invalid number.",
        "stale_timestamp": "Proposal was too old or out of order.",
        "stale_basis": "Proposal was based on an older map.",
    ]
    public static func reason(_ code: String) -> String { reasons[code] ?? "Reason: \(code)" }

    public static func verdict(_ table: ProposalResponse.Table, _ v: EnvelopeVerdict) -> String {
        let what: String
        switch table { case .ve: what = "fuel"; case .spark: what = "timing"; case .afrTarget: what = "AFR target" }
        let fmt = { (x: Double) in String(format: "%.1f", x) }
        let src = v.authoritative ? "The ECU" : "Expected: the ECU"
        switch v.decision {
        case .accepted: return "\(src) applies the \(what) change \(fmt(v.valueBefore)) → \(fmt(v.valueAfter))."
        case .clamped: return "\(src) trims the \(what) change to \(fmt(v.valueBefore)) → \(fmt(v.valueAfter)). \(reason(v.reason))"
        case .rejected: return "\(src) rejects this \(what) change; the cell stays \(fmt(v.valueBefore)). \(reason(v.reason))"
        }
    }
}
