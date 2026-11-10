#if canImport(SwiftUI)
import SwiftUI
import Observation
import GrokPilotCore

/// SwiftUI-facing wrapper around the platform-neutral DashViewModel. Ticks the
/// sim at 4 Hz. UNCOMPILED on the Linux box — see docs/IOS-PROTOTYPE.md.
@MainActor @Observable
public final class DashStore {
    public private(set) var engines: [EngineCard] = []
    public private(set) var proposals: [ProposalCard] = []
    public private(set) var explanation = ""
    public private(set) var anomalies: [ProposalResponse.Anomaly] = []
    let vm = DashViewModel(mode: .efi)
    private var timer: Timer?

    public init() {}

    public func start() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
        loadSample()
    }
    public func stop() { timer?.invalidate(); timer = nil }

    func refresh() {
        vm.tick(nowMs: Date().timeIntervalSince1970 * 1000)
        engines = vm.engines
    }

    /// Prototype: load the bundled sample response. A real build receives it
    /// from the on-device model or the Mac Studio gateway.
    func loadSample() {
        vm.show(responseJSON: Data(SampleData.proposalResponse.utf8))
        proposals = vm.proposals; explanation = vm.modelExplanation; anomalies = vm.anomalies
    }
}

enum SampleData {
    static let proposalResponse = """
    {"schema":"grok-pilot.proposal-response.v1","request_id":"demo-1","model_version":"proto",
     "engine_id":1,"stage":"warm_idle","mode":"copilot",
     "proposals":[
      {"table":"ve","rpm_idx":2,"map_idx":4,"value_before":60,"value_proposed":62,"evidence_samples":180,"confidence":0.8,"rationale":"Bank B reads 0.3 lean of target across 180 idle samples."},
      {"table":"ve","rpm_idx":3,"map_idx":4,"value_before":60,"value_proposed":70,"evidence_samples":120,"confidence":0.6,"rationale":"Consistently lean."},
      {"table":"spark","rpm_idx":2,"map_idx":4,"value_before":28,"value_proposed":40,"evidence_samples":200,"confidence":0.4,"rationale":"More advance."}],
     "explanation":"Starboard idle is running slightly lean. I suggest a little more fuel in two idle cells.",
     "anomalies":[{"severity":"info","code":"wideband_offset","message":"Starboard widebands read 0.3 AFR apart; within limits."}]}
    """
}
#endif
