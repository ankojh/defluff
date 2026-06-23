import SwiftUI

/// Gates the main UI behind a backend health check. On first launch (or if the
/// backend is missing) it runs the bundled `bootstrap.sh` in Terminal so the
/// user can see Homebrew/sudo prompts and the model download, then polls
/// `/health` until the backend is up. Once everything is installed and the
/// LaunchAgent keeps the backend running, this resolves to the UI immediately.
struct SetupGate: View {
    private enum Phase: Equatable {
        case connecting
        case installing
        case ready
        case failed(String)
    }

    @State private var phase: Phase = .connecting

    private let healthURL = URL(string: "http://127.0.0.1:8000/health")!

    var body: some View {
        switch phase {
        case .ready:
            ContentView(client: BackendClient())
        case .connecting, .installing:
            SetupStatusView(installing: phase == .installing)
                .task { await run() }
        case .failed(let message):
            SetupFailedView(message: message) { phase = .connecting }
        }
    }

    private func run() async {
        // A fresh, never-installed Mac goes straight to setup. An installed Mac
        // gets a grace period for its LaunchAgents to come up after login.
        if isInstalled {
            for _ in 0..<20 {
                if await isHealthy() { phase = .ready; return }
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
        } else if await isHealthy() {
            phase = .ready
            return
        }

        phase = .installing
        launchBootstrap()

        // Allow up to ~40 min for the first-run model pull on a slow network.
        for _ in 0..<2400 {
            try? await Task.sleep(nanoseconds: 1_000_000_000)
            if await isHealthy() { phase = .ready; return }
        }
        phase = .failed(
            "Setup hasn't finished. Check the Terminal window for progress, or the "
            + "logs in ~/Library/Application Support/Defluff/.logs."
        )
    }

    private var isInstalled: Bool {
        let marker = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Defluff/.installed")
        return FileManager.default.fileExists(atPath: marker.path)
    }

    private func isHealthy() async -> Bool {
        var request = URLRequest(url: healthURL)
        request.timeoutInterval = 3
        guard
            let (_, response) = try? await URLSession.shared.data(for: request),
            (response as? HTTPURLResponse)?.statusCode == 200
        else { return false }
        return true
    }

    private func launchBootstrap() {
        guard let script = Bundle.main.url(forResource: "bootstrap", withExtension: "sh") else {
            AppDebugLog.write("setup.bootstrap_missing")
            phase = .failed("Installer wasn't found inside the app bundle.")
            return
        }
        AppDebugLog.write("setup.bootstrap_launch", fields: ["path": script.path])
        let appleScript = """
        tell application "Terminal"
            activate
            do script "/bin/bash '\(script.path)'; echo; echo '[Defluff setup finished — you can close this window.]'"
        end tell
        """
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", appleScript]
        do {
            try process.run()
        } catch {
            AppDebugLog.write("setup.bootstrap_failed", fields: ["error": error.localizedDescription])
            phase = .failed("Couldn't start the installer: \(error.localizedDescription)")
        }
    }
}

// MARK: - Status views

private enum SetupTheme {
    static let paper = Color(red: 0.09, green: 0.08, blue: 0.07)
    static let ink = Color(red: 0.93, green: 0.89, blue: 0.81)
    static let inkSoft = Color(red: 0.70, green: 0.66, blue: 0.58)
    static let accent = Color(red: 0.82, green: 0.64, blue: 0.34)
}

private struct SetupStatusView: View {
    let installing: Bool

    var body: some View {
        VStack(spacing: 18) {
            ProgressView()
                .controlSize(.large)
                .tint(SetupTheme.accent)
            Text(installing ? "Setting up Defluff…" : "Connecting to Defluff…")
                .font(.system(size: 20, weight: .semibold, design: .serif))
                .foregroundStyle(SetupTheme.ink)
            if installing {
                Text(
                    "First run installs the local services and downloads the model. "
                    + "Follow the Terminal window — it may ask for your password and can "
                    + "take a while on the first download."
                )
                .font(.system(size: 13))
                .multilineTextAlignment(.center)
                .foregroundStyle(SetupTheme.inkSoft)
                .frame(maxWidth: 360)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(SetupTheme.paper)
    }
}

private struct SetupFailedView: View {
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 18) {
            Text("Setup didn't finish")
                .font(.system(size: 20, weight: .semibold, design: .serif))
                .foregroundStyle(SetupTheme.ink)
            Text(message)
                .font(.system(size: 13))
                .multilineTextAlignment(.center)
                .foregroundStyle(SetupTheme.inkSoft)
                .frame(maxWidth: 360)
            Button("Try again", action: retry)
                .tint(SetupTheme.accent)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(SetupTheme.paper)
    }
}
