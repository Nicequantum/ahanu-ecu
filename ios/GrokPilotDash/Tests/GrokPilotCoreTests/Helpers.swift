import Foundation
import XCTest

func fixture(_ name: String) throws -> Data {
    let url = try XCTUnwrap(Bundle.module.url(forResource: name, withExtension: nil, subdirectory: "Fixtures"))
    return try Data(contentsOf: url)
}

func response(proposals: String = "[]", mode: String = "copilot", engine: String = "1", extra: String = "") -> Data {
    Data("""
    {"schema":"grok-pilot.proposal-response.v1","request_id":"r1","model_version":"m","engine_id":\(engine),
     "stage":"warm_idle","mode":"\(mode)","proposals":\(proposals),"explanation":"x","anomalies":[]\(extra)}
    """.utf8)
}

func item(_ table: String = "ve", before: Double = 60, proposed: Double = 62, evidence: Int = 100,
          rpm: Int = 2, map: Int = 4, confidence: Double = 0.5) -> String {
    #"{"table":"\#(table)","rpm_idx":\#(rpm),"map_idx":\#(map),"value_before":\#(before),"value_proposed":\#(proposed),"evidence_samples":\#(evidence),"confidence":\#(confidence),"rationale":"r"}"#
}
