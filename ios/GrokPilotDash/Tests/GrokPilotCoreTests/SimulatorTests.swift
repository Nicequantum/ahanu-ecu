import XCTest
@testable import GrokPilotCore

final class SimulatorTests: XCTestCase {
    /// Golden output from Ahanu PR #4 sim.ts, same timestamps.
    func testMatchesAhanuSimGolden() throws {
        struct Frame: Decodable { let t: Double; let readings: [EngineReading] }
        let frames = try JSONDecoder().decode([Frame].self, from: fixture("sim-golden.json"))
        XCTAssertEqual(frames.count, 4)
        let sim = EngineSimulator()
        for f in frames {
            let mine = sim.picture(nowMs: f.t, mode: .efi)
            XCTAssertEqual(mine.count, f.readings.count)
            for (a, b) in zip(mine, f.readings) {
                XCTAssertEqual(a.engineId, b.engineId); XCTAssertEqual(a.param, b.param)
                XCTAssertEqual(a.unit, b.unit); XCTAssertEqual(a.ts, b.ts)
                XCTAssertEqual(a.source, b.source); XCTAssertEqual(a.quality, b.quality)
                XCTAssertEqual(a.instance, b.instance); XCTAssertEqual(a.pgn, b.pgn)
                XCTAssertEqual(a.value, b.value, accuracy: 1e-9, "\(a.param) @\(f.t)")
            }
        }
    }
    func testCarbModeHasNoEfiFields() {
        let r = EngineSimulator().picture(nowMs: 0, mode: .carb)
        XCTAssertEqual(r.count, 12)
        XCTAssertFalse(r.contains { $0.param == "afrA" })
    }
    func testEfiModeFieldsPerEngine() {
        let r = EngineSimulator().picture(nowMs: 5000, mode: .efi)
        XCTAssertEqual(r.count, 2 * (6 + 9 + 8))
        let snaps = EngineSnapshot.group(r)
        XCTAssertEqual(snaps.map(\.engineId), ["port", "starboard"])
        for i in 1...8 { XCTAssertNotNil(snaps[1]["injectorPw\(i)"]) }
    }
    func testUnmappedInstance() {
        let r = EngineSimulator(instanceMap: [0: "port"]).picture(nowMs: 0)
        XCTAssertTrue(r.contains { $0.engineId == "unmapped" })
    }
    func testSchemaBridge() {
        let r = EngineSimulator().picture(nowMs: 0, mode: .efi)
        let s = try! XCTUnwrap(SchemaBridge.toSchemaSample(r, engineId: "port"))
        XCTAssertEqual(s["engine_id"], 0)
        XCTAssertEqual(s["coolant_c"]!, (168 - 32) * 5 / 9, accuracy: 1e-9)
        XCTAssertEqual(s["oil_press_kpa"]!, 46 * 6.894757293168361, accuracy: 1e-9)
        XCTAssertEqual(s["inj_pw_us[1]"]!, 3200, accuracy: 1e-6)
        XCTAssertNil(SchemaBridge.toSchemaSample(r, engineId: "unmapped"))
    }
    func testReadingRoundTripsJSON() throws {
        let r = EngineSimulator().picture(nowMs: 0, mode: .efi)
        let back = try JSONDecoder().decode([EngineReading].self, from: JSONEncoder().encode(r))
        XCTAssertEqual(back, r)
    }
}
