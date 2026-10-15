import SwiftUI

struct Sandbox: Decodable, Identifiable {
    let sandboxID: String
    let templateID: String?
    let startedAt: String?
    var id: String { sandboxID }
}

@MainActor
final class Fleet: ObservableObject {
    @Published var sandboxes: [Sandbox] = []
    @Published var status = "loading"

    private let api = URL(string: ProcessInfo.processInfo.environment["E2B_API_URL"]
        ?? "https://sandbox.agent-next.com")!

    private var key: String? {
        let path = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent(".config/sbx/key")
        return (try? String(contentsOf: path, encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    init() {
        Task {
            while !Task.isCancelled {
                await refresh()
                try? await Task.sleep(for: .seconds(15))
            }
        }
    }

    func refresh() async {
        guard let key, !key.isEmpty else { status = "no key in ~/.config/sbx/key"; return }
        var req = URLRequest(url: api.appendingPathComponent("sandboxes"))
        req.setValue(key, forHTTPHeaderField: "X-API-Key")
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
            guard code == 200 else { status = "HTTP \(code)"; return }
            sandboxes = try JSONDecoder().decode([Sandbox].self, from: data)
            status = "updated \(Date().formatted(date: .omitted, time: .standard))"
        } catch {
            status = "error: \(error.localizedDescription)"
        }
    }
}

@main
struct SbxBarApp: App {
    @StateObject private var fleet = Fleet()

    var body: some Scene {
        MenuBarExtra("sbx \(fleet.sandboxes.count)", systemImage: "shippingbox") {
            Text("\(fleet.sandboxes.count) live sandboxes")
            ForEach(fleet.sandboxes) { s in
                Text("\(s.templateID ?? "?")  \(s.sandboxID.prefix(8))")
            }
            Divider()
            Text(fleet.status)
            Button("Refresh") { Task { await fleet.refresh() } }
            Button("Quit") { NSApplication.shared.terminate(nil) }
        }
    }
}
