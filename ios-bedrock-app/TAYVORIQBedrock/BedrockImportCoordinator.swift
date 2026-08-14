import Foundation
import UIKit
import Combine
import ZIPFoundation

@MainActor
final class BedrockImportCoordinator: NSObject, ObservableObject, UIDocumentInteractionControllerDelegate {
    enum ImportTarget: String {
        case minecraft = "Minecraft Bedrock"
        case spaceflight = "Spaceflight Simulator"
    }

    @Published private(set) var selectedFileName: String?
    @Published private(set) var target: ImportTarget?
    @Published private(set) var statusMessage = "Wähle .mcaddon, .mcpack, .mcworld oder .zip aus. TAYVORIQ erkennt Minecraft Bedrock und Spaceflight Simulator automatisch."

    private var stagedURL: URL?
    private var documentController: UIDocumentInteractionController?
    private var spaceflightBlueprintURL: URL?
    private var spaceflightVersionURL: URL?
    private var spaceflightFolderName: String?

    private let supportedMinecraftExtensions: Set<String> = ["mcaddon", "mcpack", "mcworld"]
    private let maxUnpackedBytes: UInt64 = 750 * 1024 * 1024
    private let maxEntries = 10_000

    func receive(url: URL) {
        do {
            resetPreparedState()
            let accessed = url.startAccessingSecurityScopedResource()
            defer { if accessed { url.stopAccessingSecurityScopedResource() } }

            let ext = url.pathExtension.lowercased()
            guard supportedMinecraftExtensions.contains(ext) || ext == "zip" else {
                throw ImportError.unsupportedFile
            }

            let local = try stageInput(url: url)
            if supportedMinecraftExtensions.contains(ext) {
                stagedURL = local
                selectedFileName = url.lastPathComponent
                target = .minecraft
                statusMessage = "Minecraft-Bedrock-Datei geprüft. Tippe auf „In Minecraft Bedrock öffnen“."
                return
            }

            try analyzeZip(localURL: local, originalName: url.lastPathComponent)
        } catch {
            report(error: error)
        }
    }

    func openInMinecraft() {
        guard target == .minecraft, let url = stagedURL else {
            statusMessage = "Bitte zuerst eine Minecraft-Bedrock-Datei auswählen."
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
            statusMessage = "iOS zeigt jetzt kompatible Apps. Wähle Minecraft, damit Bedrock den Import übernimmt."
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

    func installSpaceflight(into folderURL: URL) {
        do {
            guard target == .spaceflight,
                  let blueprint = spaceflightBlueprintURL,
                  let folderName = spaceflightFolderName else {
                throw ImportError.noSpaceflightBlueprint
            }

            let accessed = folderURL.startAccessingSecurityScopedResource()
            defer { if accessed { folderURL.stopAccessingSecurityScopedResource() } }

            let destinationFolder = folderURL.appendingPathComponent(folderName, isDirectory: true)
            try FileManager.default.createDirectory(at: destinationFolder, withIntermediateDirectories: true)

            try replaceCopy(from: blueprint, to: destinationFolder.appendingPathComponent("Blueprint.txt"))
            if let version = spaceflightVersionURL {
                try replaceCopy(from: version, to: destinationFolder.appendingPathComponent("Version.txt"))
            }

            statusMessage = "Spaceflight-Blueprint wurde in den gewählten Blueprints-Ordner installiert. Öffne jetzt Spaceflight Simulator; der neue Blueprint sollte dort verfügbar sein."
        } catch {
            report(error: error)
        }
    }

    func report(error: Error) {
        if let importError = error as? ImportError {
            statusMessage = importError.localizedDescription
        } else {
            statusMessage = "Datei konnte nicht vorbereitet werden: \(error.localizedDescription)"
        }
    }

    private func analyzeZip(localURL: URL, originalName: String) throws {
        let archive = try Archive(url: localURL, accessMode: .read)
        var entryCount = 0
        var unpacked: UInt64 = 0
        var nestedMinecraftPath: String?
        var manifestCount = 0
        var hasLevelDat = false
        var blueprintPath: String?
        var versionPath: String?
        var blueprintParent: String?

        for entry in archive {
            entryCount += 1
            if entryCount > maxEntries { throw ImportError.archiveTooLarge }
            unpacked += UInt64(entry.uncompressedSize)
            if unpacked > maxUnpackedBytes { throw ImportError.archiveTooLarge }

            let path = try safeArchivePath(entry.path)
            let lower = path.lowercased()
            if isBlockedExecutable(lower) { throw ImportError.unsafeArchive }

            if supportedMinecraftExtensions.contains(URL(fileURLWithPath: path).pathExtension.lowercased()), nestedMinecraftPath == nil {
                nestedMinecraftPath = path
            }
            if lower == "manifest.json" || lower.hasSuffix("/manifest.json") { manifestCount += 1 }
            if lower == "level.dat" || lower.hasSuffix("/level.dat") { hasLevelDat = true }
            if (lower == "blueprint.txt" || lower.hasSuffix("/blueprint.txt")), blueprintPath == nil {
                blueprintPath = path
                blueprintParent = URL(fileURLWithPath: path).deletingLastPathComponent().path
            }
            if lower == "version.txt" || lower.hasSuffix("/version.txt") {
                if versionPath == nil { versionPath = path }
                if let parent = blueprintParent,
                   URL(fileURLWithPath: path).deletingLastPathComponent().path == parent {
                    versionPath = path
                }
            }
        }

        if let nestedMinecraftPath,
           let entry = archive[nestedMinecraftPath] {
            let destination = importsDirectory().appendingPathComponent(URL(fileURLWithPath: nestedMinecraftPath).lastPathComponent)
            try removeIfExists(destination)
            try archive.extract(entry, to: destination)
            stagedURL = destination
            selectedFileName = destination.lastPathComponent
            target = .minecraft
            statusMessage = "Minecraft Bedrock wurde im ZIP erkannt. Das enthaltene Paket ist bereit für die Übergabe."
            return
        }

        if manifestCount > 0 || hasLevelDat {
            let ext = hasLevelDat ? "mcworld" : (manifestCount > 1 ? "mcaddon" : "mcpack")
            let destination = importsDirectory()
                .appendingPathComponent(stripExtension(originalName))
                .appendingPathExtension(ext)
            try removeIfExists(destination)
            try FileManager.default.copyItem(at: localURL, to: destination)
            stagedURL = destination
            selectedFileName = destination.lastPathComponent
            target = .minecraft
            statusMessage = "Minecraft-Bedrock-ZIP erkannt. Das Archiv wurde lokal als .\(ext) vorbereitet."
            return
        }

        if let blueprintPath,
           let blueprintEntry = archive[blueprintPath] {
            let folderName = sanitizeFolderName(stripExtension(originalName))
            let working = importsDirectory().appendingPathComponent("Spaceflight", isDirectory: true)
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
            try FileManager.default.createDirectory(at: working, withIntermediateDirectories: true)

            let blueprintDestination = working.appendingPathComponent("Blueprint.txt")
            try archive.extract(blueprintEntry, to: blueprintDestination)
            spaceflightBlueprintURL = blueprintDestination

            if let versionPath, let versionEntry = archive[versionPath] {
                let versionDestination = working.appendingPathComponent("Version.txt")
                try archive.extract(versionEntry, to: versionDestination)
                spaceflightVersionURL = versionDestination
            }

            spaceflightFolderName = folderName
            selectedFileName = originalName
            target = .spaceflight
            statusMessage = "Spaceflight-Simulator-Blueprint erkannt. Wähle einmal den Blueprints-Ordner von Spaceflight Simulator und TAYVORIQ legt Blueprint.txt/Version.txt dort ab."
            return
        }

        throw ImportError.unknownZip
    }

    private func stageInput(url: URL) throws -> URL {
        let destination = importsDirectory()
            .appendingPathComponent(UUID().uuidString + "-" + sanitizeFileName(url.lastPathComponent))
        try FileManager.default.copyItem(at: url, to: destination)
        return destination
    }

    private func importsDirectory() -> URL {
        let folder = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("UniversalImports", isDirectory: true)
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder
    }

    private func replaceCopy(from source: URL, to destination: URL) throws {
        try removeIfExists(destination)
        try FileManager.default.copyItem(at: source, to: destination)
    }

    private func removeIfExists(_ url: URL) throws {
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
    }

    private func safeArchivePath(_ raw: String) throws -> String {
        let normalized = raw.replacingOccurrences(of: "\\", with: "/")
        if normalized.hasPrefix("/") || normalized.contains("../") || normalized == ".." {
            throw ImportError.unsafeArchive
        }
        return normalized
    }

    private func isBlockedExecutable(_ lower: String) -> Bool {
        [".apk", ".exe", ".dex", ".so", ".jar", ".msi", ".bat", ".cmd", ".ps1", ".sh"].contains { lower.hasSuffix($0) }
    }

    private func stripExtension(_ value: String) -> String {
        let ns = value as NSString
        let stem = ns.deletingPathExtension
        return stem.isEmpty ? value : stem
    }

    private func sanitizeFileName(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "._ -"))
        let mapped = value.unicodeScalars.map { allowed.contains($0) ? Character(String($0)) : "_" }
        let result = String(mapped).trimmingCharacters(in: .whitespacesAndNewlines)
        return result.isEmpty ? "import.bin" : result
    }

    private func sanitizeFolderName(_ value: String) -> String {
        let safe = sanitizeFileName(value).replacingOccurrences(of: ".zip", with: "", options: .caseInsensitive)
        return safe.isEmpty ? "TAYVORIQ Blueprint" : safe
    }

    private func resetPreparedState() {
        stagedURL = nil
        target = nil
        selectedFileName = nil
        spaceflightBlueprintURL = nil
        spaceflightVersionURL = nil
        spaceflightFolderName = nil
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
        case unknownZip
        case archiveTooLarge
        case unsafeArchive
        case noSpaceflightBlueprint

        var errorDescription: String? {
            switch self {
            case .unsupportedFile:
                return "Nicht unterstützt. Erlaubt sind .mcaddon, .mcpack, .mcworld und .zip."
            case .unknownZip:
                return "ZIP-Inhalt nicht erkannt. Erwartet wird ein Minecraft-Bedrock-Paket oder ein Spaceflight-Blueprint mit Blueprint.txt."
            case .archiveTooLarge:
                return "ZIP wurde aus Sicherheitsgründen blockiert: zu viele Dateien oder mehr als 750 MB entpackter Inhalt."
            case .unsafeArchive:
                return "ZIP wurde wegen eines unsicheren Pfads oder einer ausführbaren Datei blockiert."
            case .noSpaceflightBlueprint:
                return "Kein vorbereiteter Spaceflight-Blueprint vorhanden."
            }
        }
    }
}
