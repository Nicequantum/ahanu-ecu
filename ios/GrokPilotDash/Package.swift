// swift-tools-version:5.9
// Grok Pilot iPhone consumer dash — PROTOTYPE. Advisory only: the phone
// proposes, the Teensy disposes. See docs/IOS-PROTOTYPE.md.
import PackageDescription

let package = Package(
    name: "GrokPilotDash",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [
        .library(name: "GrokPilotCore", targets: ["GrokPilotCore"]),
        .library(name: "GrokPilotDashUI", targets: ["GrokPilotDashUI"]),
    ],
    targets: [
        // Platform-neutral: models, sim, curriculum, proposal decoding, view-models.
        // Builds and tests on Linux.
        .target(name: "GrokPilotCore"),
        // SwiftUI views. Every file is wrapped in `#if canImport(SwiftUI)`, so on
        // Linux this target compiles to nothing. Only an Apple toolchain checks it.
        .target(name: "GrokPilotDashUI", dependencies: ["GrokPilotCore"]),
        .testTarget(name: "GrokPilotCoreTests", dependencies: ["GrokPilotCore"],
                    resources: [.copy("Fixtures")]),
    ]
)
