#if canImport(SwiftUI)
import SwiftUI
import GrokPilotCore

/// UNCOMPILED on the Linux box. Type-checks only with an Apple toolchain.
public struct DashRootView: View {
    @State private var store = DashStore()
    public init() {}
    public var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    AdvisoryBanner()
                    HStack(alignment: .top, spacing: 12) {
                        ForEach(store.engines, id: \.snapshot.engineId) { EngineColumn(card: $0) }
                    }
                    if !store.explanation.isEmpty {
                        GroupBox("AI says") { Text(store.explanation).frame(maxWidth: .infinity, alignment: .leading) }
                    }
                    ForEach(store.anomalies, id: \.code) { a in
                        Label(a.message, systemImage: a.severity == .critical ? "exclamationmark.octagon" : "info.circle")
                            .foregroundStyle(a.severity == .critical ? .red : a.severity == .warn ? .orange : .secondary)
                    }
                    Text("Proposals").font(.headline)
                    ForEach(store.proposals) { ProposalCardView(card: $0) }
                }.padding()
            }
            .navigationTitle("Grok Pilot")
        }
        .onAppear { store.start() }
        .onDisappear { store.stop() }
    }
}

struct AdvisoryBanner: View {
    var body: some View {
        Label("Advisory only — the phone proposes, the ECU decides.", systemImage: "lock.shield")
            .font(.footnote).padding(8).frame(maxWidth: .infinity, alignment: .leading)
            .background(.blue.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
    }
}

extension StageStatus {
    var color: Color { switch self { case .green: .green; case .yellow: .yellow; case .red: .red } }
}

struct StageBadge: View {
    let card: EngineCard
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Circle().fill(card.status.color).frame(width: 12, height: 12)
                Text(card.stage.rawValue.replacingOccurrences(of: "_", with: " ").capitalized).font(.subheadline.bold())
            }
            Text(card.stageText).font(.caption).foregroundStyle(.secondary)
            ForEach(card.reasonTexts, id: \.self) { Text("• \($0)").font(.caption2) }
        }
    }
}

struct EngineColumn: View {
    let card: EngineCard
    static let gauges: [(String, String, ClosedRange<Double>)] = [
        ("rpm", "RPM", 0...6000), ("coolantTemp", "Coolant", 100...230), ("oilPressure", "Oil", 0...80),
        ("voltage", "Battery", 10...16), ("mapKpa", "MAP", 0...300), ("tps", "TPS", 0...100),
        ("iat", "IAT", 0...200), ("afrA", "AFR A", 10...18), ("afrB", "AFR B", 10...18),
        ("afrCommanded", "AFR cmd", 10...18), ("sparkAdvance", "Spark", 0...40), ("egt", "EGT", 300...1600),
    ]
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(card.snapshot.engineId.capitalized).font(.title3.bold())
            StageBadge(card: card)
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 72))], spacing: 8) {
                ForEach(Self.gauges, id: \.0) { g in
                    GaugeTile(label: g.1, value: card.snapshot[g.0], unit: card.snapshot.units[g.0] ?? "", range: g.2)
                }
            }
            InjectorBars(snapshot: card.snapshot)
        }.frame(maxWidth: .infinity)
    }
}

struct GaugeTile: View {
    let label: String; let value: Double?; let unit: String; let range: ClosedRange<Double>
    var body: some View {
        if let value {
            Gauge(value: min(max(value, range.lowerBound), range.upperBound), in: range) {
                Text(label).font(.caption2)
            } currentValueLabel: { Text(value, format: .number.precision(.fractionLength(value < 100 ? 1 : 0))) }
            .gaugeStyle(.accessoryCircular)
        } else {
            VStack { Text(label).font(.caption2); Text("—") }   // no data shows a dash, like Ahanu
        }
    }
}

struct InjectorBars: View {
    let snapshot: EngineSnapshot
    var body: some View {
        HStack(alignment: .bottom, spacing: 3) {
            ForEach(1...8, id: \.self) { i in
                let v = snapshot["injectorPw\(i)"] ?? 0
                VStack { Capsule().fill(.teal).frame(width: 8, height: CGFloat(v) * 12); Text("\(i)").font(.system(size: 8)) }
            }
        }
    }
}

struct ProposalCardView: View {
    let card: ProposalCard
    var tint: Color {
        switch card.verdict.decision { case .accepted: .green; case .clamped: .orange; case .rejected: .red }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text("\(card.item.table.rawValue.uppercased()) [rpm \(card.item.rpm_idx), map \(card.item.map_idx)]").font(.subheadline.bold())
                Spacer()
                Text(card.verdict.decision.rawValue.uppercased()).font(.caption.bold()).foregroundStyle(tint)
                if !card.verdict.authoritative { Text("preview").font(.caption2).foregroundStyle(.secondary) }
            }
            Text("Proposed \(card.item.value_before, specifier: "%.1f") → \(card.item.value_proposed, specifier: "%.1f")  ·  envelope → \(card.verdict.valueAfter, specifier: "%.1f")")
                .font(.caption.monospacedDigit())
            Text(card.plainLanguage).font(.caption)
            Text(card.item.rationale).font(.caption2).foregroundStyle(.secondary)
            // Deliberately no Apply/Send button: the phone never writes the map.
        }
        .padding(10).background(tint.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
    }
}
#endif
