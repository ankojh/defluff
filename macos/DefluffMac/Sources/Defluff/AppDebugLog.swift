import Foundation

enum AppDebugLog {
    static let url = FileManager.default.temporaryDirectory
        .appendingPathComponent("Defluff")
        .appendingPathComponent("debug-session.log")

    static func reset() {
        do {
            try FileManager.default.createDirectory(
                at: url.deletingLastPathComponent(),
                withIntermediateDirectories: true
            )
            try "".write(to: url, atomically: true, encoding: .utf8)
        } catch {
            NSLog("Could not reset Defluff debug log: \(error.localizedDescription)")
        }
    }

    static func write(_ event: String, fields: [String: String] = [:]) {
        var payload = fields
        payload["time"] = ISO8601DateFormatter().string(from: Date())
        payload["event"] = event

        guard
            let data = try? JSONSerialization.data(withJSONObject: payload),
            let line = String(data: data, encoding: .utf8)
        else {
            return
        }

        do {
            let handle = try FileHandle(forWritingTo: url)
            try handle.seekToEnd()
            try handle.write(contentsOf: Data((line + "\n").utf8))
            try handle.close()
        } catch {
            try? (line + "\n").write(to: url, atomically: true, encoding: .utf8)
        }
    }
}
