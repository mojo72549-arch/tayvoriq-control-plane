import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var importer: BedrockImportCoordinator
    @State private var showFileImporter = false
    @State private var showSpaceflightFolderImporter = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    Image(systemName: "shippingbox.and.arrow.backward.fill")
                        .font(.system(size: 62))
                        .foregroundStyle(.cyan)
                        .padding(.top, 24)

                    Text("TAYVORIQ Universal Import")
                        .font(.title2.bold())
                        .multilineTextAlignment(.center)

                    Text("Minecraft Bedrock + Spaceflight Simulator")
                        .font(.headline)
                        .foregroundStyle(.secondary)

                    Text("Unterstützt .mcaddon, .mcpack, .mcworld und .zip. ZIP-Dateien werden lokal geprüft und automatisch dem passenden Spiel zugeordnet.")
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal)

                    HStack(spacing: 8) {
                        formatChip(".mcaddon")
                        formatChip(".mcpack")
                        formatChip(".mcworld")
                        formatChip(".zip")
                    }
                    .font(.caption.bold())

                    if let fileName = importer.selectedFileName, let target = importer.target {
                        VStack(spacing: 10) {
                            Text(target.rawValue)
                                .font(.headline)
                            Text(fileName)
                                .font(.subheadline)
                                .lineLimit(2)
                                .multilineTextAlignment(.center)

                            if target == .minecraft {
                                Button("In Minecraft Bedrock öffnen") {
                                    importer.openInMinecraft()
                                }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.large)
                            } else {
                                Button("Spaceflight-Blueprint installieren") {
                                    showSpaceflightFolderImporter = true
                                }
                                .buttonStyle(.borderedProminent)
                                .controlSize(.large)

                                Text("Wähle den in der Dateien-App sichtbaren Blueprints-Ordner von Spaceflight Simulator. iOS erlaubt TAYVORIQ keinen direkten Zugriff auf den privaten App-Sandbox-Ordner ohne diese Auswahl.")
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .multilineTextAlignment(.center)
                            }
                        }
                        .padding()
                        .frame(maxWidth: .infinity)
                        .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
                    }

                    Button("DATEI AUSWÄHLEN") {
                        showFileImporter = true
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.large)

                    Text(importer.statusMessage)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal)

                    Divider().padding(.vertical, 4)

                    Text("Unabhängiges Produkt. Nicht von Mojang, Microsoft oder Spaceflight Simulator UK Ltd genehmigt oder mit diesen verbunden.")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding()
            }
            .navigationTitle("Universal Import")
        }
        .fileImporter(
            isPresented: $showFileImporter,
            allowedContentTypes: [.item, .zip],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first {
                    importer.receive(url: url)
                }
            case .failure(let error):
                importer.report(error: error)
            }
        }
        .fileImporter(
            isPresented: $showSpaceflightFolderImporter,
            allowedContentTypes: [.folder],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                if let url = urls.first {
                    importer.installSpaceflight(into: url)
                }
            case .failure(let error):
                importer.report(error: error)
            }
        }
    }

    private func formatChip(_ text: String) -> some View {
        Text(text)
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(.thinMaterial, in: Capsule())
    }
}
