import Foundation

/// What the phone shows next to a proposal: the envelope's expected verdict.
///
/// IMPORTANT: this is a DISPLAY PREVIEW of the stateless rules from
/// `src/grok_pilot/envelope.py` (absolute limits + delta clamp, same default
/// thresholds). It has no rate-limit, freshness, replay or stale-basis state,
/// and it never writes anything. The Teensy's C++ envelope is the only
/// authority. When a real Teensy decision (cell_write audit record) arrives,
/// the UI shows that instead and marks the preview superseded.
public enum EnvelopeDecision: String, Codable, Sendable { case accepted, clamped, rejected }

public struct EnvelopeVerdict: Equatable, Sendable {
    public let decision: EnvelopeDecision
    public let reason: String          // envelope.py Reason value, "none" when accepted
    public let valueBefore: Double
    public let valueAfter: Double      // what the cell would hold; == before when rejected
    public let authoritative: Bool     // true only when it came from the Teensy audit trail
}

public struct EnvelopeLimits: Sendable {
    public var maxFuelDeltaPct = 5.0, maxSparkDeltaDeg = 2.0
    public var sparkMinDeg = 0.0, sparkMaxDeg = 36.0
    public var afrFloor = 10.5, afrCeiling = 16.0
    public var veMin = 10.0, veMax = 150.0
    public var minEvidenceSamples = 50
    public var clampDeltas = true
    public init() {}
}

public enum EnvelopePreview {
    public static func evaluate(_ p: ProposalResponse.Item, engineId: Int, expectedEngine: Int,
                                learningAllowed: Bool, limits L: EnvelopeLimits = .init()) -> EnvelopeVerdict {
        let vb = p.value_before, v = p.value_proposed
        func reject(_ r: String) -> EnvelopeVerdict {
            EnvelopeVerdict(decision: .rejected, reason: r, valueBefore: vb, valueAfter: vb, authoritative: false)
        }
        if engineId != expectedEngine { return reject("wrong_engine") }
        if !(0..<16).contains(p.rpm_idx) || !(0..<16).contains(p.map_idx) { return reject("off_table") }
        if !vb.isFinite || !v.isFinite || p.evidence_samples < 0 { return reject("invalid_value") }
        if !learningAllowed { return reject("learning_frozen") }
        if p.evidence_samples < L.minEvidenceSamples { return reject("insufficient_samples") }
        switch p.table {
        case .afrTarget:
            if v < L.afrFloor { return reject("afr_floor") }
            if v > L.afrCeiling { return reject("afr_ceiling") }
        case .spark:
            if !(L.sparkMinDeg <= v && v <= L.sparkMaxDeg) { return reject("spark_limit") }
        case .ve:
            if !(L.veMin <= v && v <= L.veMax) || vb <= 0 { return reject("ve_limit") }
        }
        let lim: Double?, reason: String
        switch p.table {
        case .spark: lim = L.maxSparkDeltaDeg; reason = "spark_delta_exceeded"
        case .ve: lim = abs(vb) * L.maxFuelDeltaPct / 100; reason = "fuel_delta_exceeded"
        case .afrTarget: lim = nil; reason = "none"
        }
        if let lim, abs(v - vb) > lim + 1e-9 {
            if !L.clampDeltas { return reject(reason) }
            let out = vb + (v - vb > 0 ? lim : -lim)
            return EnvelopeVerdict(decision: .clamped, reason: reason, valueBefore: vb, valueAfter: out, authoritative: false)
        }
        return EnvelopeVerdict(decision: .accepted, reason: "none", valueBefore: vb, valueAfter: v, authoritative: false)
    }
}
