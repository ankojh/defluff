import SwiftUI

@main
struct DefluffApp: App {
    init() {
        AppDebugLog.reset()
        AppDebugLog.write("app.start", fields: ["debugLog": AppDebugLog.url.path])
    }

    var body: some Scene {
        WindowGroup {
            ContentView(client: BackendClient())
        }
    }
}
