import Foundation

/// Decodes `grok-pilot.proposal-response.v1` (src/grok_pilot/schemas/proposal-response.v1.schema.json).
/// The Codable types plus `validate()` enforce the schema's required fields,
/// enums, ranges and length caps. Unknown keys are rejected (additionalProperties: false).
public struct ProposalResponse: Codable, Equatable, Sendable {
    public enum Mode: String, Codable, Sendable { case copilot, autopilot }
    public enum Table: String, Codable, Sendable { case ve, spark, afrTarget = "afr_target" }
    public struct Item: Codable, Equatable, Sendable {
        public let table: Table
        public let rpm_idx: Int, map_idx: Int
        public let value_before: Double, value_proposed: Double
        public let evidence_samples: Int
        public let confidence: Double
        public let rationale: String
    }
    public struct StageRecommendation: Codable, Equatable, Sendable {
        public enum Action: String, Codable, Sendable { case hold, advance, regress, abort }
        public let action: Action, reason: String
    }
    public struct Anomaly: Codable, Equatable, Sendable {
        public enum Severity: String, Codable, Sendable { case info, warn, critical }
        public let severity: Severity, code: String, message: String
    }
    public let schema: String
    public let request_id: String
    public let model_version: String
    public let engine_id: Int
    public let stage: Stage
    public let mode: Mode
    public let proposals: [Item]
    public let stage_recommendation: StageRecommendation?
    public let explanation: String
    public let anomalies: [Anomaly]

    public static let schemaId = "grok-pilot.proposal-response.v1"
    static let topKeys: Set<String> = ["schema", "request_id", "model_version", "engine_id", "stage", "mode",
                                        "proposals", "stage_recommendation", "explanation", "anomalies"]
    static let itemKeys: Set<String> = ["table", "rpm_idx", "map_idx", "value_before", "value_proposed",
                                         "evidence_samples", "confidence", "rationale"]

    public enum SchemaError: Error, Equatable { case invalid(String) }

    /// Decode and validate. Throws on any schema violation.
    public static func decode(_ data: Data) throws -> ProposalResponse {
        guard let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw SchemaError.invalid("not an object") }
        if let extra = Set(obj.keys).subtracting(topKeys).first { throw SchemaError.invalid("unknown key \(extra)") }
        if let items = obj["proposals"] as? [[String: Any]] {
            for it in items { if let extra = Set(it.keys).subtracting(itemKeys).first { throw SchemaError.invalid("unknown proposal key \(extra)") } }
        }
        if let sr = obj["stage_recommendation"] as? [String: Any], let extra = Set(sr.keys).subtracting(["action", "reason"]).first {
            throw SchemaError.invalid("unknown stage_recommendation key \(extra)")
        }
        for a in (obj["anomalies"] as? [[String: Any]]) ?? [] {
            if let extra = Set(a.keys).subtracting(["severity", "code", "message"]).first { throw SchemaError.invalid("unknown anomaly key \(extra)") }
        }
        // JSONDecoder already refuses booleans and non-integral numbers for Int fields.
        let r: ProposalResponse
        do { r = try JSONDecoder().decode(ProposalResponse.self, from: data) } catch { throw SchemaError.invalid("decode: \(error)") }
        try r.validate()
        return r
    }

    public func validate() throws {
        func req(_ ok: Bool, _ m: String) throws { if !ok { throw SchemaError.invalid(m) } }
        try req(schema == Self.schemaId, "schema const")
        try req((1...64).contains(request_id.count), "request_id length")
        try req((1...64).contains(model_version.count), "model_version length")
        try req(engine_id == 0 || engine_id == 1, "engine_id enum")
        try req(proposals.count <= 16, "proposals maxItems")
        try req(anomalies.count <= 16, "anomalies maxItems")
        try req(explanation.count <= 2000, "explanation maxLength")
        for p in proposals {
            try req((0...15).contains(p.rpm_idx) && (0...15).contains(p.map_idx), "cell index range")
            try req(p.evidence_samples >= 0, "evidence_samples minimum")
            try req((0...1).contains(p.confidence), "confidence range")
            try req(p.rationale.count <= 500, "rationale maxLength")
            try req(p.value_before.isFinite && p.value_proposed.isFinite, "non-finite value")
        }
        if let s = stage_recommendation { try req(s.reason.count <= 500, "stage reason maxLength") }
        for a in anomalies { try req(a.code.count <= 64 && a.message.count <= 500, "anomaly length") }
    }
}

