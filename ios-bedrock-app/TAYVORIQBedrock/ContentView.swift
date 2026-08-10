import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @EnvironmentObject private var importer: BedrockImportCoordinator
    @State private var showFileImporter = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                Spacer()

                Image(systemName: "shippingbox.fill")
                    .font(.system(size: 64))

                Text("TAYVORIQ Bedrock Add-ons")
                    .font(.title2.bold())
                    .multilineTextAlignment(.center)

                Text("Importiert .mcaddon, .mcpack und .mcworld für Minecraft Bedrock auf iPhone und iPad.")
                    .multilineTextAlignment(.center)
                    .foregroundStyle(.secondary)
                    .padding(.horizontal)

                if let fileName = importer.selectedFileName {
                    VStack(spacing: 8) {
                        Text("Bereit")
                            .font(.headline)
                        Text(fileName)
                            .font(.subheadline)
                            .lineLimit(2)
                            .multilineTextAlignment(.center)

                        Button("In Minecraft Bedrock öffnen") {
                            importer.openInMinecraft()
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.large)
                        .padding(.top, 4)
                    }
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 18))
                }

                Button("Bedrock-Datei auswählen") {
                    showFileImporter = true
                }
                .buttonStyle(.bordered)
                .controlSize(.large)

                Text(importer.statusMessage)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                Spacer()
            }
            .padding()
            .navigationTitle("Bedrock Import")
        }
        .fileImporter(
            isPresented: $showFileImporter,
            allowedContentTypes: [.item],
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
    }
}
