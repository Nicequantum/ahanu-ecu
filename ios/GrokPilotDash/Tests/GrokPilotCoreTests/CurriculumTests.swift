import XCTest
@testable import GrokPilotCore

final class CurriculumTests: XCTestCase {
    /// Replays random streams generated from src/grok_pilot/curriculum.py; every step must match.
    func testParityWithPythonReference() throws {
        let raw = try JSONSerialization.jsonObject(with: fixture("curriculum-vectors.json")) as! [[[String: Any]]]
        var cfg = CurriculumConfig()
        cfg.samplesToAdvance = [.coldStart: 20, .warmIdle: 30, .cruise: 30, .loadTest: 30]
        var steps = 0, seen = Set<Stage>()
        for steps0 in raw {
            let c = Curriculum(config: cfg)
            for s in steps0 {
                if s["reset"] != nil { XCTAssertTrue(c.reset(operatorAck: true)); continue }
                let o = s["obs"] as! [String: Any]
                var ob = Observation(rpm: o["rpm"] as! Double, coolantC: o["coolant_c"] as! Double,
                                     afrA: o["afr_a"] as? Double, afrB: o["afr_b"] as? Double)
                ob.batteryV = o["battery_v"] as! Double
                ob.oilPressKpa = o["oil_press_kpa"] as? Double
                ob.egtC = o["egt_c"] as? Double
                ob.sensorFault = o["sensor_fault"] as! Bool
                ob.operatorConfirm = o["operator_confirm"] as! Bool
                let r = c.step(ob)
                XCTAssertEqual(r.stage.rawValue, s["stage"] as? String)
                XCTAssertEqual(r.status.rawValue, s["status"] as? String)
                XCTAssertEqual(r.reasons, s["reasons"] as? [String])
                let t = s["transition"] as? [String]
                XCTAssertEqual(r.transition.map { [$0.from.rawValue, $0.to.rawValue, $0.cause] }, t)
                seen.insert(r.stage); steps += 1
            }
        }
        XCTAssertGreaterThan(steps, 19_000)
        XCTAssertEqual(seen, [.coldStart, .warmIdle, .cruise, .loadTest, .aborted])
    }

    func obs(_ rpm: Double, _ c: Double, a: Double? = 14.2, b: Double? = 14.2) -> Observation {
        Observation(rpm: rpm, coolantC: c, afrA: a, afrB: b)
    }
    func testGreenProgressionNeedsOperatorConfirm() {
        var cfg = CurriculumConfig(); cfg.samplesToAdvance = [.coldStart: 3, .warmIdle: 3, .cruise: 3, .loadTest: 3]
        let c = Curriculum(config: cfg)
        for _ in 0..<3 { XCTAssertEqual(c.step(obs(800, 65)).status, .green) }
        XCTAssertEqual(c.stage, .warmIdle)
        for _ in 0..<5 { _ = c.step(obs(800, 75)) }
        XCTAssertEqual(c.stage, .warmIdle, "needs operator confirm")
        var o = obs(800, 75); o.operatorConfirm = true
        XCTAssertEqual(c.step(o).transition?.to, .cruise)
    }
    func testYellowHolds() {
        let c = Curriculum()
        let r = c.step(obs(800, 40, a: 14.0, b: 14.9))
        XCTAssertEqual(r.status, .yellow); XCTAssertEqual(r.reasons, ["wideband_mismatch"]); XCTAssertEqual(c.good, 0)
    }
    func testSevereAbortsAndNeedsReset() {
        let c = Curriculum(stage: .cruise)
        var o = obs(2500, 80); o.leanCutActive = true
        XCTAssertEqual(c.step(o).stage, .aborted)
        XCTAssertEqual(c.step(obs(2500, 80)).reasons, ["aborted_await_reset"])
        XCTAssertFalse(c.reset(operatorAck: false))
        XCTAssertTrue(c.reset(operatorAck: true)); XCTAssertEqual(c.stage, .coldStart)
    }
    func testModerateRegressesOncePerEpisode() {
        let c = Curriculum(stage: .loadTest)
        XCTAssertEqual(c.step(obs(4000, 80, a: 13, b: 15)).transition?.to, .cruise)
        XCTAssertNil(c.step(obs(4000, 80, a: 13, b: 15)).transition)
        XCTAssertEqual(c.stage, .cruise)
    }
    func testObservationFromSimSnapshot() throws {
        let snap = EngineSnapshot.group(EngineSimulator().picture(nowMs: 0, mode: .efi))[0]
        let o = try XCTUnwrap(Observation(snapshot: snap))
        XCTAssertEqual(o.coolantC, (168 - 32) * 5 / 9, accuracy: 1e-9)
        XCTAssertEqual(o.oilPressKpa!, 46 * 6.894757293168361, accuracy: 1e-9)
    }
}
