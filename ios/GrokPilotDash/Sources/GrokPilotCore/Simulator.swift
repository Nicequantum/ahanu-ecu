import Foundation

/// Swift port of Ahanu PR #4 `src/lib/ahanu/engine/sim.ts` (`simPicture`).
/// Same banks, same wobble (sin(now/900)), same display units, so a phone and
/// Ahanu running the sim at the same timestamp show the same numbers.
public struct EngineSimulator: Sendable {
    struct Bank { let instance: Int; let rpm, coolant, oil, volts, hours, trim: Double }
    struct EfiBank {
        let mapKpa, tps, iat, afrA, afrBOffset, afrCommanded, sparkAdvance, egt, injectorPw: Double
        let cylinderSkew: [Double]
    }
    static let banks = [
        Bank(instance: 0, rpm: 1420, coolant: 168, oil: 46, volts: 13.8, hours: 1840, trim: 18),
        Bank(instance: 1, rpm: 1360, coolant: 176, oil: 40, volts: 13.4, hours: 1836, trim: 16),
    ]
    static let efiBanks = [
        EfiBank(mapKpa: 52, tps: 12, iat: 96, afrA: 14.1, afrBOffset: 0.05, afrCommanded: 14.2,
                sparkAdvance: 28, egt: 1040, injectorPw: 3.2, cylinderSkew: [0, 0.01, -0.01, 0.02, 0, -0.02, 0.01, 0]),
        EfiBank(mapKpa: 55, tps: 13, iat: 101, afrA: 14.3, afrBOffset: 0.3, afrCommanded: 14.2,
                sparkAdvance: 27, egt: 1075, injectorPw: 3.3, cylinderSkew: [0.02, 0, -0.01, 0, 0.03, -0.02, 0, -0.01]),
    ]

    /// Ahanu default instance map: 0 = port, 1 = starboard.
    public var instanceMap: [Int: String]
    public init(instanceMap: [Int: String] = [0: "port", 1: "starboard"]) { self.instanceMap = instanceMap }

    public static func isoTimestamp(_ ms: Double) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        f.timeZone = TimeZone(identifier: "UTC")
        return f.string(from: Date(timeIntervalSince1970: ms / 1000))
    }

    public func picture(nowMs: Double, mode: EngineRoomMode = .carb) -> [EngineReading] {
        let wobble = sin(nowMs / 900)
        let ts = Self.isoTimestamp(nowMs)
        var out: [EngineReading] = []
        for bank in Self.banks {
            let engineId = instanceMap[bank.instance] ?? "unmapped"
            let pulse = bank.instance == 0 ? wobble : -wobble
            var rows: [(String, Double, String, Int)] = [
                ("rpm", bank.rpm + pulse * 30, "rpm", 127488),
                ("coolantTemp", bank.coolant + pulse * 0.4, "°F", 127489),
                ("oilPressure", bank.oil + pulse * 0.3, "psi", 127489),
                ("voltage", bank.volts, "V", 127489),
                ("hours", bank.hours, "h", 127489),
                ("trim", bank.trim, "%", 127488),
            ]
            if mode == .efi {
                let e = Self.efiBanks[bank.instance]
                let pw = e.injectorPw + pulse * 0.04
                rows += [
                    ("mapKpa", e.mapKpa + pulse * 0.8, "kPa", 0),
                    ("tps", e.tps + pulse * 0.2, "%", 0),
                    ("iat", e.iat, "°F", 0),
                    ("afrA", e.afrA + pulse * 0.05, "AFR", 0),
                    ("afrB", e.afrA + e.afrBOffset + pulse * 0.05, "AFR", 0),
                    ("afrCommanded", e.afrCommanded, "AFR", 0),
                    ("sparkAdvance", e.sparkAdvance, "°BTDC", 0),
                    ("egt", e.egt + pulse * 4, "°F", 0),
                    ("injectorPw", pw, "ms", 0),
                ]
                for (i, skew) in e.cylinderSkew.enumerated() { rows.append(("injectorPw\(i + 1)", pw * (1 + skew), "ms", 0)) }
            }
            for (param, value, unit, pgn) in rows {
                out.append(EngineReading(engineId: engineId, param: param, value: value, unit: unit, ts: ts,
                                         source: .sim, quality: .ok, instance: bank.instance, pgn: pgn == 0 ? nil : pgn))
            }
        }
        return out
    }
}
