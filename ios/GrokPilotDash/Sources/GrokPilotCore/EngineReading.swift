import Foundation

/// Mirrors Ahanu `src/lib/ahanu/types.ts` `EngineReading` (Ahanu PR #4, branch engine-dashboard).
public enum EngineSourceKind: String, Codable, Sendable {
    case analogN2k = "analog-n2k", smartcraft, mefi, standalone, sim
}
public enum ReadingQuality: String, Codable, Sendable { case ok, stale, missing }
public enum EngineRoomMode: String, Codable, Sendable { case carb, efi }

public struct EngineReading: Codable, Equatable, Sendable {
    public var engineId: String
    public var param: String
    public var value: Double
    public var unit: String
    public var ts: String
    public var source: EngineSourceKind
    public var quality: ReadingQuality
    public var instance: Int?
    public var pgn: Int?

    public init(engineId: String, param: String, value: Double, unit: String, ts: String,
                source: EngineSourceKind, quality: ReadingQuality, instance: Int? = nil, pgn: Int? = nil) {
        self.engineId = engineId; self.param = param; self.value = value; self.unit = unit
        self.ts = ts; self.source = source; self.quality = quality; self.instance = instance; self.pgn = pgn
    }
}

/// Display param -> ahanu-ecu docs/DATA-SCHEMA.md field name, after the same
/// mapping as Ahanu `engine/schema.ts`. Display units are imperial (°F, psi);
/// schema units are metric (°C, kPa).
public enum SchemaBridge {
    public struct Field: Sendable { public let field: String; public let unit: String; public let toSchema: @Sendable (Double) -> Double }
    public static func fToC(_ f: Double) -> Double { (f - 32) * 5 / 9 }
    public static func psiToKpa(_ p: Double) -> Double { p * 6.894757293168361 }
    static func inj(_ ch: Int) -> Field { Field(field: "inj_pw_us[\(ch)]", unit: "µs", toSchema: { $0 * 1000 }) }
    public static let fields: [String: Field] = {
        let same: @Sendable (Double) -> Double = { $0 }
        var m: [String: Field] = [
            "rpm": Field(field: "rpm", unit: "rev/min", toSchema: same),
            "mapKpa": Field(field: "map_kpa", unit: "kPa", toSchema: same),
            "tps": Field(field: "tps_pct", unit: "%", toSchema: same),
            "coolantTemp": Field(field: "coolant_c", unit: "°C", toSchema: { fToC($0) }),
            "iat": Field(field: "iat_c", unit: "°C", toSchema: { fToC($0) }),
            "afrA": Field(field: "afr_a", unit: "AFR", toSchema: same),
            "afrB": Field(field: "afr_b", unit: "AFR", toSchema: same),
            "voltage": Field(field: "battery_v", unit: "V", toSchema: same),
            "sparkAdvance": Field(field: "spark_adv_deg", unit: "° BTDC", toSchema: same),
            "egt": Field(field: "egt_c", unit: "°C", toSchema: { fToC($0) }),
            "oilPressure": Field(field: "oil_press_kpa", unit: "kPa", toSchema: { psiToKpa($0) }),
        ]
        for ch in 1...8 { m["injectorPw\(ch)"] = inj(ch) }
        return m
    }()
    /// Port of `schemaEngineId`: port -> 0, starboard -> 1.
    public static func schemaEngineId(_ id: String) -> Int? { id == "port" ? 0 : id == "starboard" ? 1 : nil }
    /// Port of `toSchemaSample`.
    public static func toSchemaSample(_ readings: [EngineReading], engineId: String) -> [String: Double]? {
        guard let id = schemaEngineId(engineId) else { return nil }
        var out: [String: Double] = ["engine_id": Double(id)]
        for r in readings where r.engineId == engineId && r.quality != .missing && r.value.isFinite {
            if let f = fields[r.param] { out[f.field] = f.toSchema(r.value) }
        }
        return out
    }
}

/// One engine's latest values, keyed by display param.
public struct EngineSnapshot: Equatable, Sendable {
    public var engineId: String
    public var instance: Int
    public var values: [String: Double]
    public var units: [String: String]
    public var ts: String
    public init(engineId: String, instance: Int, values: [String: Double] = [:], units: [String: String] = [:], ts: String = "") {
        self.engineId = engineId; self.instance = instance; self.values = values; self.units = units; self.ts = ts
    }
    public subscript(_ p: String) -> Double? { values[p] }

    public static func group(_ readings: [EngineReading]) -> [EngineSnapshot] {
        var by: [String: EngineSnapshot] = [:]
        for r in readings {
            var s = by[r.engineId] ?? EngineSnapshot(engineId: r.engineId, instance: r.instance ?? -1)
            if r.quality == .ok { s.values[r.param] = r.value }
            s.units[r.param] = r.unit; s.ts = r.ts
            by[r.engineId] = s
        }
        return by.values.sorted { $0.instance < $1.instance }
    }
}
