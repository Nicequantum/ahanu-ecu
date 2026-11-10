# iPhone consumer dash — prototype (branch `prototype/ios-dash`)

Status: **prototype, not for main yet.** Advisory only: the phone proposes, the Teensy disposes.

## Layout

```
ios/GrokPilotDash/                  Swift package (swift-tools 5.9, iOS 17 / macOS 14)
  Sources/GrokPilotCore/            platform-neutral, builds + tests on Linux
    EngineReading.swift             EngineReading / quality / source enums (Ahanu types.ts),
                                    EngineSnapshot, SchemaBridge (port of Ahanu engine/schema.ts)
    Simulator.swift                 port of Ahanu PR #4 engine/sim.ts simPicture()
    Curriculum.swift                port of src/grok_pilot/curriculum.py
    Proposal.swift                  proposal-response.v1 decoder + validator
    EnvelopePreview.swift           stateless DISPLAY preview of src/grok_pilot/envelope.py
    Explanations.swift              plain-language strings for stages, statuses, reasons, verdicts
    DashViewModel.swift             sim tick -> snapshots -> curriculum -> cards; proposal cards
  Sources/GrokPilotDashUI/          SwiftUI (every file under #if canImport(SwiftUI))
    DashStore.swift                 @Observable wrapper, 4 Hz sim timer, bundled sample response
    Views.swift                     DashRootView, gauges, stage badge, injector bars, proposal cards
  App/GrokPilotDashApp.swift.txt    @main for an Xcode app target (kept .txt so SwiftPM ignores it)
  Tests/GrokPilotCoreTests/         XCTest + generated fixtures
  tools/                            fixture generators / provenance
```

## Data binding

`EngineSimulator.picture(nowMs:mode:.efi)` → `[EngineReading]` (identical shape and values to Ahanu PR #4:
port/starboard, rpm, coolant, oil, battery, hours, trim, MAP, TPS, IAT, AFR A/B, commanded AFR, spark,
EGT, injector PW + 8 per-cylinder) → `EngineSnapshot.group` → per engine `Observation(snapshot:)`
(°F/psi → °C/kPa via the same conversions as Ahanu `schema.ts`) → `Curriculum.step` → `EngineCard`
(stage, green/yellow/red, reason codes, plain-language text). `DashStore` republishes `EngineCard`s to
SwiftUI. A real build would replace the sim with the Teensy/Ahanu feed producing the same `EngineReading`s.

Proposals: model JSON → `ProposalResponse.decode` (required fields, enums, ranges, length caps,
`additionalProperties:false`, integer strictness) → `mode == autopilot` refused (v1) → per item an
`EnvelopePreview` verdict (accepted / clamped / rejected + `envelope.py` reason code, value after) →
`ProposalCard`. When the Teensy's `cell_write` audit record arrives, `applyAuditDecision` replaces the
preview with the authoritative decision (UI drops the "preview" tag, text changes from "Expected: the
ECU…" to "The ECU…").

## Advisory-only contract

- No apply / send / write API exists in `DashViewModel` or the views. The proposal card has no button.
- The envelope preview omits stateful rules (rate limit, freshness, replay, stale basis); it is a hint.
  The C++ envelope on the Teensy (`firmware/envelope/`, fork `grok-pilot` proposal command) is the only
  authority.
- `learning_frozen` is previewed when the engine's displayed curriculum stage is cold_start/aborted.

## Verified vs not

| Part | Status |
|---|---|
| GrokPilotCore build | **compiled** on Linux, Swift 6.0.3 (Debian 13 box), no warnings |
| `swift test` | **24/24 pass** (6 sim, 6 curriculum, 3 proposal decode, 4 envelope preview, 5 view-model) |
| Sim parity | golden from Ahanu PR #4 `sim.ts` at 4 timestamps: every reading equal (values to 1e-9, ts, units, pgn) |
| Curriculum parity | 40 random streams, ~19,950 steps from `curriculum.py`: stage, status, reasons, transition identical; all of cold_start/warm_idle/cruise/load_test/aborted reached |
| Schema | Swift key sets and stage enum checked against the copied `proposal-response.v1.schema.json` |
| SwiftUI views / DashStore / App | **NOT compiled** — no SwiftUI on Linux; files are excluded by `#if canImport(SwiftUI)`. Needs Xcode 15+/macOS. |
| On-device run, layout, accessibility | not done |
| CI | `.github/workflows/ios-core.yml` runs `swift test` in `swift:6.0.3-noble` |

## Fixture provenance

See `ios/GrokPilotDash/tools/README.md`. The schema fixture is a copy; if
`src/grok_pilot/schemas/proposal-response.v1.schema.json` changes, recopy it (the schema test will catch
key/enum drift only after the copy is refreshed — TODO: a drift check like the envelope one).

## Next

1. Open in Xcode on a Mac, build `GrokPilotDashUI`, fix whatever the type-checker finds, run in simulator.
2. Real transport: subscribe to Ahanu/Teensy `EngineReading`s and the `cell_write` audit stream.
3. Wire the on-device model (prompt templates) to produce `proposal-response.v1`.
4. Schema-copy drift check in CI.
