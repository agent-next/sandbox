import SwiftUI

@main
struct TallyApp: App {
    var body: some Scene {
        WindowGroup { ContentView() }
    }
}

struct ContentView: View {
    @State private var count = 0

    var body: some View {
        VStack(spacing: 32) {
            Text("Built on Linux in an agent-next sandbox")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Text("\(count)")
                .font(.system(size: 120, weight: .bold, design: .rounded))
                .contentTransition(.numericText())
                .accessibilityIdentifier("count")
            HStack(spacing: 24) {
                Button("Reset") { withAnimation { count = 0 } }
                    .buttonStyle(.bordered)
                    .accessibilityIdentifier("reset")
                Button("+1") { withAnimation(.spring) { count += 1 } }
                    .buttonStyle(.borderedProminent)
                    .font(.title)
                    .accessibilityIdentifier("increment")
            }
        }
        .padding()
    }
}
