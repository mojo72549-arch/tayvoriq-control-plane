import Foundation
import UIKit
import Combine

@MainActor
final class BedrockImportCoordinator: NSObject, ObservableObject, UIDocumentInteractionControllerDelegate {
    @Published private(set) var selectedFileName: String?
    @Published private(set) var statusMessage = "Wähle eine Bedrock-Datei aus oder öffne sie aus der Dateien-App mit TAYVORIQ."

    private var stagedURL: URL?
    private var documentController: UIDocumentInteractionController?
    private let supportedExtensions: Set<String> = ["mcaddon", "mcpack", "mcworld"]

    func receive(url: URL) {
        do {
            let ext = url.pathExtension.lowercased()
            guard supportedExtensions.contains(ext) else {
                throw ImportError.unsupportedFile
            }

            let accessed = url.startAccessingSecurityScopedResource()
            defer {
                if accessed { url.stopAccessingSecurityScopedResource() }
            }

            let folder = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
                .appendingPathComponent("BedrockImports", isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)

            let safeName = url.lastPathComponent.isEmpty ? "bedrock.\(ext)" : url.lastPathComponent
            let destination = folder.appendingPathComponent(safeName)

            if FileManager.default.fileExists(atPath: destination.path) {
                try FileManager.default.removeItem(at: destination)
            }
            try FileManager.default.copyItem(at: url, to: destination)

            stagedURL = destination
            selectedFileName = destination.lastPathComponent
            statusMessage = "Datei geprüft. Tippe auf „In Minecraft Bedrock öffnen“ und wähle Minecraft in der iOS-Übergabe."
        } catch {
            report(error: error)
        }
    }

    func openInMinecraft() {
        guard let url = stagedURL else {
            statusMessage = "Bitte zuerst eine .mcaddon-, .mcpack- oder .mcworld-Datei auswählen."
            return
        }
        guard let presenter = topViewController(), let view = presenter.view else {
            statusMessage = "Der iOS-Übergabedialog konnte nicht geöffnet werden."
            return
        }

        let controller = UIDocumentInteractionController(url: url)
        controller.delegate = self
        controller.name = url.lastPathComponent
        documentController = controller

        let anchor = CGRect(x: view.bounds.midX, y: view.bounds.maxY - 40, width: 1, height: 1)
        if controller.presentOptionsMenu(from: anchor, in: view, animated: true) {
            statusMessage = "iOS zeigt jetzt die kompatiblen Apps. Wähle Minecraft, damit Bedrock den Import übernimmt."
        } else {
            let activity = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            if let popover = activity.popoverPresentationController {
                popover.sourceView = view
                popover.sourceRect = anchor
            }
            presenter.present(activity, animated: true)
            statusMessage = "Die Datei wurde an den iOS-Teilen-Dialog übergeben. Wähle Minecraft."
        }
    }

    func report(error: Error) {
        if let importError = error as? ImportError {
            statusMessage = importError.localizedDescription
        } else {
            statusMessage = "Datei konnte nicht vorbereitet werden: \(error.localizedDescription)"
        }
    }

    func documentInteractionController(_ controller: UIDocumentInteractionController, willBeginSendingToApplication application: String?) {
        if let application, !application.isEmpty {
            statusMessage = "Bedrock-Datei wird an \(application) übergeben."
        } else {
            statusMessage = "Bedrock-Datei wird an die ausgewählte App übergeben."
        }
    }

    func documentInteractionController(_ controller: UIDocumentInteractionController, didEndSendingToApplication application: String?) {
        statusMessage = "Übergabe abgeschlossen. Minecraft Bedrock sollte den Import jetzt verarbeiten."
    }

    private func topViewController(base: UIViewController? = nil) -> UIViewController? {
        let root: UIViewController?
        if let base {
            root = base
        } else {
            root = UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .flatMap { $0.windows }
                .first(where: { $0.isKeyWindow })?
                .rootViewController
        }

        if let navigation = root as? UINavigationController {
            return topViewController(base: navigation.visibleViewController)
        }
        if let tab = root as? UITabBarController, let selected = tab.selectedViewController {
            return topViewController(base: selected)
        }
        if let presented = root?.presentedViewController {
            return topViewController(base: presented)
        }
        return root
    }

    enum ImportError: LocalizedError {
        case unsupportedFile

        var errorDescription: String? {
            switch self {
            case .unsupportedFile:
                return "Nicht unterstützt. Erlaubt sind Minecraft-Bedrock-Dateien: .mcaddon, .mcpack und .mcworld."
            }
        }
    }
}
