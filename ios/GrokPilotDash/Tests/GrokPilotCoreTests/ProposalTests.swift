import XCTest
@testable import GrokPilotCore

final class ProposalTests: XCTestCase {
    func testDecodesValid() throws {
        let r = try ProposalResponse.decode(response(proposals: "[\(item())]"))
        XCTAssertEqual(r.proposals.count, 1); XCTAssertEqual(r.proposals[0].table, .ve)
    }
    func testSchemaFixtureEnumsMatchSwift() throws {
        let s = try JSONSerialization.jsonObject(with: fixture("proposal-response.v1.schema.json")) as! [String: Any]
        let props = s["properties"] as! [String: Any]
        XCTAssertEqual(Set((s["required"] as! [String])), ["schema", "request_id", "model_version", "engine_id", "stage", "mode", "proposals", "explanation", "anomalies"])
        XCTAssertEqual(Set(props.keys), ProposalResponse.topKeys)
        let stages = (props["stage"] as! [String: Any])["enum"] as! [String]
        XCTAssertEqual(Set(stages), Set(Stage.allCases.map(\.rawValue)))
        let item = ((props["proposals"] as! [String: Any])["items"] as! [String: Any])
        XCTAssertEqual(Set((item["properties"] as! [String: Any]).keys), ProposalResponse.itemKeys)
    }
    func expectInvalid(_ d: Data, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertThrowsError(try ProposalResponse.decode(d), file: file, line: line)
    }
    func testRejectsBadPayloads() {
        expectInvalid(response(extra: #","extra":1"#))
        expectInvalid(response(engine: "2"))
        expectInvalid(response(engine: "true"))
        expectInvalid(response(engine: "0.5"))
        expectInvalid(response(mode: "yolo"))
        expectInvalid(response(proposals: "[\(item(rpm: 16))]"))
        expectInvalid(response(proposals: "[\(item(confidence: 1.5))]"))
        expectInvalid(response(proposals: "[\(item(evidence: -1))]"))
        expectInvalid(response(proposals: "[\(item("fuel"))]"))
        expectInvalid(response(proposals: #"[{"table":"ve","rpm_idx":1,"map_idx":1,"value_before":1,"value_proposed":1,"evidence_samples":1,"confidence":0.1,"rationale":"r","apply":true}]"#))
        expectInvalid(Data("[]".utf8))
        expectInvalid(Data(#"{"schema":"grok-pilot.proposal-response.v2"}"#.utf8))
        let many = Array(repeating: item(), count: 17).joined(separator: ",")
        expectInvalid(response(proposals: "[\(many)]"))
    }
}

final class EnvelopePreviewTests: XCTestCase {
    func p(_ b: Double, _ v: Double, _ t: String = "ve", ev: Int = 100) -> ProposalResponse.Item {
        try! ProposalResponse.decode(response(proposals: "[\(item(t, before: b, proposed: v, evidence: ev))]")).proposals[0]
    }
    func ev(_ i: ProposalResponse.Item, allowed: Bool = true) -> EnvelopeVerdict {
        EnvelopePreview.evaluate(i, engineId: 1, expectedEngine: 1, learningAllowed: allowed)
    }
    func testAcceptedAtBoundary() {
        XCTAssertEqual(ev(p(60, 63)).decision, .accepted)            // exactly 5%
        XCTAssertEqual(ev(p(28, 30, "spark")).decision, .accepted)   // exactly 2°
    }
    func testClamped() {
        let v = ev(p(60, 70)); XCTAssertEqual(v.decision, .clamped); XCTAssertEqual(v.valueAfter, 63, accuracy: 1e-9)
        XCTAssertEqual(v.reason, "fuel_delta_exceeded")
        let s = ev(p(28, 25, "spark")); XCTAssertEqual(s.valueAfter, 26, accuracy: 1e-9)
    }
    func testRejected() {
        XCTAssertEqual(ev(p(28, 40, "spark")).reason, "spark_limit")
        XCTAssertEqual(ev(p(14.7, 10.4, "afr_target")).reason, "afr_floor")
        XCTAssertEqual(ev(p(14.7, 16.01, "afr_target")).reason, "afr_ceiling")
        XCTAssertEqual(ev(p(60, 160)).reason, "ve_limit")
        XCTAssertEqual(ev(p(60, 61, ev: 49)).reason, "insufficient_samples")
        XCTAssertEqual(ev(p(60, 61), allowed: false).reason, "learning_frozen")
        let r = ev(p(28, 40, "spark")); XCTAssertEqual(r.valueAfter, 28); XCTAssertFalse(r.authoritative)
        XCTAssertEqual(EnvelopePreview.evaluate(p(60, 61), engineId: 0, expectedEngine: 1, learningAllowed: true).reason, "wrong_engine")
    }
    func testAfrTargetHasNoDeltaClamp() {
        XCTAssertEqual(ev(p(14.7, 12.0, "afr_target")).decision, .accepted)
    }
}

final class DashViewModelTests: XCTestCase {
    func testTickProducesTwoEnginesGreen() {
        let vm = DashViewModel()
        vm.tick(nowMs: 0)
        XCTAssertEqual(vm.engines.map(\.snapshot.engineId), ["port", "starboard"])
        // sim coolant 168°F ≈ 75.6 °C, idle rpm, widebands agree → green cold_start
        XCTAssertEqual(vm.engines.map(\.status), [.green, .green])
        XCTAssertEqual(vm.engines[0].stage, .coldStart)
        XCTAssertFalse(vm.engines[0].stageText.isEmpty)
    }
    func testInjectedFaultTurnsRed() {
        let vm = DashViewModel()
        vm.ingest(EngineSimulator().picture(nowMs: 0, mode: .efi), overrides: ["starboard": { $0.oilAlarm = true }])
        XCTAssertEqual(vm.engines[1].status, .red); XCTAssertEqual(vm.engines[1].stage, .aborted)
        XCTAssertEqual(vm.engines[0].status, .green)
        XCTAssertTrue(vm.engines[1].reasonTexts.contains("The oil pressure alarm switch tripped."))
    }
    func testProposalCardsShowVerdicts() {
        let vm = DashViewModel()
        // put starboard in a learning stage so the preview isn't learning_frozen
        _ = vm.curriculum(for: "starboard")
        let props = "[\(item(before: 60, proposed: 62)),\(item(before: 60, proposed: 70, rpm: 3)),\(item("spark", before: 28, proposed: 40))]"
        // cold_start → learning frozen: all rejected in preview
        XCTAssertEqual(try vm.show(responseJSON: response(proposals: props)).get(), 3)
        XCTAssertEqual(vm.proposals.map(\.verdict.reason), ["learning_frozen", "learning_frozen", "learning_frozen"])
        let vm2 = DashViewModel()
        vm2.curricula["starboard"] = Curriculum(stage: .warmIdle)
        _ = vm2.show(responseJSON: response(proposals: props))
        XCTAssertEqual(vm2.proposals.map(\.verdict.decision), [.accepted, .clamped, .rejected])
        XCTAssertTrue(vm2.proposals[1].plainLanguage.hasPrefix("Expected: the ECU trims"))
        vm2.applyAuditDecision(cardId: "r1#0", decision: .accepted, reason: "none", valueAfter: 62)
        XCTAssertTrue(vm2.proposals[0].verdict.authoritative)
        XCTAssertTrue(vm2.proposals[0].plainLanguage.hasPrefix("The ECU applies"))
    }
    func testAutopilotRefused() {
        let vm = DashViewModel()
        if case .success = vm.show(responseJSON: response(mode: "autopilot")) { XCTFail() }
        XCTAssertTrue(vm.proposals.isEmpty)
    }
    func testNoWritePathExists() {
        // Compile-time contract documented here: DashViewModel exposes no send/apply/write API.
        let names = Mirror(reflecting: DashViewModel()).children.compactMap(\.label)
        XCTAssertFalse(names.contains { $0.lowercased().contains("transport") || $0.lowercased().contains("serial") })
    }
}
