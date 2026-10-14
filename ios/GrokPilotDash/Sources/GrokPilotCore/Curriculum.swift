import Foundation

/// Port of ahanu-ecu `src/grok_pilot/curriculum.py` (main). Same stages,
/// thresholds and green/yellow/red semantics. Display-only on the phone: the
/// authoritative curriculum runs off the Teensy log stream, not here.
public enum Stage: String, Codable, CaseIterable, Sendable {
    case coldStart = "cold_start", warmIdle = "warm_idle", cruise, loadTest = "load_test", street, aborted
}
public enum StageStatus: String, Codable, Sendable { case green, yellow, red }

public struct CurriculumConfig: Sendable {
    public var warmCoolantC = 60.0, cruiseCoolantC = 70.0, overheatC = 95.0, warnCoolantC = 88.0
    public var idleRpm = (500.0, 1200.0), cruiseRpm = (2000.0, 3500.0), loadRpm = (3500.0, 5000.0)
    public var afrBand = (11.0, 15.5)
    public var widebandWarnAfr = 0.7, widebandFaultAfr = 1.5
    public var minOilKpaRunning = 70.0, oilCheckRpm = 1000.0, maxEgtC = 760.0, minBatteryV = 11.5
    public var samplesToAdvance: [Stage: Int] = [.coldStart: 300, .warmIdle: 600, .cruise: 900, .loadTest: 1200]
    public var requireOperatorConfirm: Set<Stage> = [.warmIdle, .cruise, .loadTest]
    public var enableStreet = false
    public init() {}
}

public struct Observation: Sendable {
    public var rpm: Double, coolantC: Double
    public var afrA: Double?, afrB: Double?
    public var afrAOk = true, afrBOk = true
    public var batteryV = 13.8
    public var oilPressKpa: Double? = nil
    public var oilAlarm = false
    public var egtC: Double? = nil
    public var leanCutActive = false, sensorFault = false, operatorConfirm = false
    public init(rpm: Double, coolantC: Double, afrA: Double?, afrB: Double?) {
        self.rpm = rpm; self.coolantC = coolantC; self.afrA = afrA; self.afrB = afrB
    }
}

public struct Transition: Equatable, Sendable { public let from: Stage, to: Stage, cause: String }
public struct StepResult: Equatable, Sendable {
    public let stage: Stage, status: StageStatus, reasons: [String], transition: Transition?
}

public final class Curriculum {
    static let order: [Stage] = [.coldStart, .warmIdle, .cruise, .loadTest, .street]
    public let cfg: CurriculumConfig
    public private(set) var stage: Stage
    public private(set) var good = 0
    private var regressLatched = false

    public init(config: CurriculumConfig = .init(), stage: Stage = .coldStart) { cfg = config; self.stage = stage }

    func rpmBand(_ s: Stage) -> (Double, Double) {
        switch s {
        case .coldStart, .warmIdle: return cfg.idleRpm
        case .cruise: return cfg.cruiseRpm
        case .loadTest: return cfg.loadRpm
        default: return (cfg.idleRpm.0, cfg.loadRpm.1)
        }
    }
    public var learningAllowed: Bool { stage != .aborted && stage != .coldStart }

    @discardableResult public func reset(operatorAck: Bool) -> Bool {
        guard stage == .aborted, operatorAck else { return false }
        stage = .coldStart; good = 0; return true
    }
    private func move(_ to: Stage, _ cause: String) -> Transition {
        let t = Transition(from: stage, to: to, cause: cause); stage = to; good = 0; return t
    }
    private static func bad(_ x: Double?) -> Bool { guard let x else { return true }; return !x.isFinite }

    public func step(_ o: Observation) -> StepResult {
        let c = cfg
        if stage == .aborted { return StepResult(stage: .aborted, status: .red, reasons: ["aborted_await_reset"], transition: nil) }
        var severe: [String] = [], moderate: [String] = [], warn: [String] = []
        if Self.bad(o.rpm) || Self.bad(o.coolantC) || Self.bad(o.batteryV) { moderate.append("invalid_core_sensor") }
        if o.leanCutActive { severe.append("lean_cut") }
        if o.oilAlarm { severe.append("oil_alarm") }
        if !Self.bad(o.coolantC) && o.coolantC >= c.overheatC { severe.append("overheat") }
        if let e = o.egtC, !Self.bad(e), e >= c.maxEgtC { severe.append("egt_high") }
        if let p = o.oilPressKpa, !Self.bad(p), !Self.bad(o.rpm), o.rpm >= c.oilCheckRpm, p < c.minOilKpaRunning {
            severe.append("low_oil_pressure")
        }
        if o.sensorFault { moderate.append("sensor_fault") }
        let aOk = o.afrAOk && !Self.bad(o.afrA), bOk = o.afrBOk && !Self.bad(o.afrB)
        if !(aOk && bOk) {
            if stage == .coldStart { warn.append("wideband_not_ready") } else { moderate.append("wideband_not_ready") }
        } else if let a = o.afrA, let b = o.afrB {
            let d = abs(a - b)
            if d >= c.widebandFaultAfr { moderate.append("wideband_disagree") }
            else if d >= c.widebandWarnAfr { warn.append("wideband_mismatch") }
            let (lo, hi) = c.afrBand
            if !(lo <= a && a <= hi && lo <= b && b <= hi) { warn.append("afr_out_of_band") }
        }
        if !Self.bad(o.coolantC) && c.warnCoolantC <= o.coolantC && o.coolantC < c.overheatC { warn.append("coolant_warm") }
        if !Self.bad(o.batteryV) && o.batteryV < c.minBatteryV { warn.append("battery_low") }

        if !severe.isEmpty {
            let t = move(.aborted, severe.joined(separator: ","))
            return StepResult(stage: stage, status: .red, reasons: severe + moderate + warn, transition: t)
        }
        if !moderate.isEmpty {
            var t: Transition? = nil
            if let idx = Self.order.firstIndex(of: stage), idx > 0, !regressLatched {
                t = move(Self.order[idx - 1], moderate.joined(separator: ","))
            } else { good = 0 }
            regressLatched = true
            return StepResult(stage: stage, status: .red, reasons: moderate + warn, transition: t)
        }
        regressLatched = false
        if !warn.isEmpty { return StepResult(stage: stage, status: .yellow, reasons: warn, transition: nil) }
        let (lo, hi) = rpmBand(stage)
        if lo <= o.rpm && o.rpm <= hi { good += 1 }
        let t = maybeAdvance(o)
        return StepResult(stage: stage, status: .green, reasons: [], transition: t)
    }

    private func maybeAdvance(_ o: Observation) -> Transition? {
        let c = cfg, s = stage
        guard s != .street, let need = c.samplesToAdvance[s], good >= need,
              let i = Self.order.firstIndex(of: s) else { return nil }
        let nxt = Self.order[i + 1]
        if nxt == .street && !c.enableStreet { return nil }
        if s == .coldStart && o.coolantC < c.warmCoolantC { return nil }
        if s == .warmIdle && o.coolantC < c.cruiseCoolantC { return nil }
        if c.requireOperatorConfirm.contains(s) && !o.operatorConfirm { return nil }
        return move(nxt, "criteria_met")
    }
}

extension Observation {
    /// Build an observation from a sim/display snapshot (°F/psi -> °C/kPa).
    public init?(snapshot s: EngineSnapshot) {
        guard let rpm = s["rpm"], let ct = s["coolantTemp"] else { return nil }
        self.init(rpm: rpm, coolantC: SchemaBridge.fToC(ct), afrA: s["afrA"], afrB: s["afrB"])
        if let v = s["voltage"] { batteryV = v }
        if let p = s["oilPressure"] { oilPressKpa = SchemaBridge.psiToKpa(p) }
        if let e = s["egt"] { egtC = SchemaBridge.fToC(e) }
    }
}
