import SwiftUI

@main
struct TAYVORIQBedrockApp: App {
    @StateObject private var importer = BedrockImportCoordinator()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(importer)
                .onOpenURL { url in
                    importer.receive(url: url)
                }
        }
    }
}
