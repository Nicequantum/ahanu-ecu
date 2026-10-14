import Foundation

/// Platform-neutral view-model. SwiftUI binds to it via an @Observable wrapper
/// in GrokPilotDashUI. There is deliberately NO method that sends or applies a
/// proposal: the phone displays; the Teensy decides.
public struct ProposalCard: Equatable, Sendable, Identifiable {
    public let id: String
    public let item: ProposalResponse.Item
    public let verdict: EnvelopeVerdict
    public let plainLanguage: String
}

public struct EngineCard: Equatable, Sendable {
    public let snapshot: EngineSnapshot
    public let stage: Stage
    public let status: StageStatus
    public let reasons: [String]
    public let stageText: String
    public let reasonTexts: [String]
}

public final class DashViewModel {
    public private(set) var engines: [EngineCard] = []
    public private(set) var proposals: [ProposalCard] = []
    public private(set) var modelExplanation = ""
    public private(set) var anomalies: [ProposalResponse.Anomaly] = []
    public private(set) var advisoryBanner = "Advisory only — the ECU decides every change."
    public var mode: EngineRoomMode
    let sim: EngineSimulator
    var curricula: [String: Curriculum] = [:]

    public init(sim: EngineSimulator = .init(), mode: EngineRoomMode = .efi) { self.sim = sim; self.mode = mode }

    public func curriculum(for engineId: String) -> Curriculum {
        if let c = curricula[engineId] { return c }
        let c = Curriculum(); curricula[engineId] = c; return c
    }

    /// One tick of the sim → snapshots → curriculum step per engine.
    public func tick(nowMs: Double) {
        ingest(sim.picture(nowMs: nowMs, mode: mode))
    }

    public func ingest(_ readings: [EngineReading], overrides: [String: (inout Observation) -> Void] = [:]) {
        engines = EngineSnapshot.group(readings).map { snap in
            let cur = curriculum(for: snap.engineId)
            guard var obs = Observation(snapshot: snap) else {
                return EngineCard(snapshot: snap, stage: cur.stage, status: .red, reasons: ["invalid_core_sensor"],
                                  stageText: Explain.stage(cur.stage), reasonTexts: [Explain.reason("invalid_core_sensor")])
            }
            overrides[snap.engineId]?(&obs)
            let r = cur.step(obs)
            return EngineCard(snapshot: snap, stage: r.stage, status: r.status, reasons: r.reasons,
                              stageText: Explain.stage(r.stage), reasonTexts: r.reasons.map(Explain.reason))
        }
    }

    /// Show a model response. Autopilot responses are refused for display in v1.
    @discardableResult public func show(responseJSON data: Data) -> Result<Int, ProposalResponse.SchemaError> {
        let r: ProposalResponse
        do { r = try ProposalResponse.decode(data) } catch let e as ProposalResponse.SchemaError { return .failure(e) }
        catch { return .failure(.invalid("\(error)")) }
        if r.mode == .autopilot { return .failure(.invalid("autopilot not accepted in v1")) }
        let engineName = r.engine_id == 0 ? "port" : "starboard"
        let allowed = curriculum(for: engineName).learningAllowed
        modelExplanation = r.explanation
        anomalies = r.anomalies
        proposals = r.proposals.enumerated().map { i, p in
            let v = EnvelopePreview.evaluate(p, engineId: r.engine_id, expectedEngine: r.engine_id, learningAllowed: allowed)
            return ProposalCard(id: "\(r.request_id)#\(i)", item: p, verdict: v, plainLanguage: Explain.verdict(p.table, v))
        }
        return .success(proposals.count)
    }

    /// Replace a preview with the Teensy's real decision (from a cell_write audit record).
    public func applyAuditDecision(cardId: String, decision: EnvelopeDecision, reason: String, valueAfter: Double) {
        guard let i = proposals.firstIndex(where: { $0.id == cardId }) else { return }
        let old = proposals[i]
        let v = EnvelopeVerdict(decision: decision, reason: reason, valueBefore: old.verdict.valueBefore,
                                valueAfter: decision == .rejected ? old.verdict.valueBefore : valueAfter, authoritative: true)
        proposals[i] = ProposalCard(id: old.id, item: old.item, verdict: v, plainLanguage: Explain.verdict(old.item.table, v))
    }
}
