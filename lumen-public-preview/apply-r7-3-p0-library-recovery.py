#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
pkg = root / "app/src/main/java/com/projectlumen/publicpreview"
main = pkg / "MainActivity.java"
gradle = root / "app/build.gradle"
support = Path(__file__).resolve().parent / "r7-3-p0-src" / "LibraryGenerationStore.java"
for path in (main, gradle, support):
    if not path.exists():
        raise SystemExit(f"P0 recovery input missing: {path}")
shutil.copy2(support, pkg / support.name)


def method_span(text: str, name: str) -> tuple[int, int]:
    pattern = re.compile(
        rf"(?m)^    (?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ?.]+\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*(?:throws\s+[\w., ]+)?\s*\{{")
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"method not found: {name}")
    opening = text.find("{", match.start(), match.end())
    depth = 0
    i = opening
    state = "code"
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if char == '"':
                state = "string"
            elif char == "'":
                state = "char"
            elif char == "/" and nxt == "/":
                state = "line"; i += 1
            elif char == "/" and nxt == "*":
                state = "block"; i += 1
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return match.start(), i + 1
        elif state == "string":
            if char == "\\": i += 1
            elif char == '"': state = "code"
        elif state == "char":
            if char == "\\": i += 1
            elif char == "'": state = "code"
        elif state == "line":
            if char == "\n": state = "code"
        elif state == "block":
            if char == "*" and nxt == "/": state = "code"; i += 1
        i += 1
    raise SystemExit(f"unterminated method: {name}")


def replace_method(text: str, name: str, replacement: str) -> str:
    start, end = method_span(text, name)
    return text[:start] + replacement.strip("\n") + text[end:]


g = gradle.read_text(encoding="utf-8")
g = re.sub(r"versionCode\s+\d+", "versionCode 134600", g, count=1)
g = re.sub(r"versionName\s+'[^']+'", "versionName '13.1.36-p0-crash-safe-library-pilot'", g, count=1)
gradle.write_text(g, encoding="utf-8")

s = main.read_text(encoding="utf-8")
if "import java.util.concurrent.atomic.AtomicBoolean;" not in s:
    s = s.replace("import java.util.concurrent.TimeUnit;", "import java.util.concurrent.TimeUnit;\nimport java.util.concurrent.atomic.AtomicBoolean;", 1)

field_marker = "    private volatile boolean restoringSource;\n"
if "restoreWorkerRunning" not in s:
    if field_marker not in s:
        raise SystemExit("restore field marker missing")
    s = s.replace(field_marker, field_marker
                  + "    private final AtomicBoolean restoreWorkerRunning = new AtomicBoolean(false);\n"
                  + "    private volatile LibraryGenerationStore.Generation activeLibraryGeneration;\n", 1)

s = s.replace('text("13.1.35"', 'text("13.1.36"')
s = s.replace('Project Lumen 13.1.35 · R7.2 Netzwerk & Diagnose',
              'Project Lumen 13.1.36 · P0 Bibliotheksschutz')

old_oncreate = '''        activeSourceName = getPreferences(MODE_PRIVATE).getString("active_name", "");
        activeSourceFile = getPreferences(MODE_PRIVATE).getString("active_file", "");
        loadFavoriteIds();
        restoringSource = !activeSourceFile.isBlank()
                && new File(getFilesDir(), activeSourceFile).isFile();'''
new_oncreate = '''        activeSourceName = getPreferences(MODE_PRIVATE).getString("active_name", "");
        activeSourceFile = getPreferences(MODE_PRIVATE).getString("active_file", "");
        activeLibraryGeneration = LibraryGenerationStore.active(this);
        if (activeLibraryGeneration != null) {
            activeSourceFile = activeLibraryGeneration.relativePlaylistPath(this);
        }
        loadFavoriteIds();
        restoringSource = activeLibraryGeneration != null
                || (!activeSourceFile.isBlank() && new File(getFilesDir(), activeSourceFile).isFile());'''
if old_oncreate not in s:
    raise SystemExit("onCreate restore marker missing")
s = s.replace(old_oncreate, new_oncreate, 1)

s = replace_method(s, "parseAndActivate", r'''
    private void parseAndActivate(String name, File plain, String origin) throws Exception {
        runOnUiThread(() -> showDiagnostic("Playlist wird geprüft", "Phase 2/4 · Inhalte werden lokal ausgewertet.", false));
        long parseStartedNs = System.nanoTime();
        List<Channel> parsed = parsePlaylist(plain);
        long parseDurationMs = (System.nanoTime() - parseStartedNs) / 1_000_000L;
        if (parsed.isEmpty()) throw new IllegalArgumentException("Keine unterstützten Einträge in der Playlist gefunden.");
        final boolean partialRecovery = lastDownloadPartialRecovery;
        appendDiagnosticLog("IMPORT", partialRecovery ? "Playlist-Teilstand ausgewertet" : "Playlist vollständig ausgewertet",
                "Einträge=" + parsed.size() + " · Bytes=" + plain.length() + " · ParserMs=" + parseDurationMs + " · Parser=FAST-1PASS", null);
        appendDiagnosticLog("CATALOG", "Länder- und Medienklassifikation abgeschlossen", classificationSummary(parsed), null);

        synchronized (channels) {
            previewChannels.clear();
            previewChannels.addAll(parsed);
            previewSnapshot = immutableSnapshot(parsed);
            previewSourceName = name;
            importPreviewActive = true;
        }
        livePage = 0;
        runOnUiThread(() -> {
            screen = Screen.START;
            render();
            showDiagnostic(partialRecovery ? "Bibliothek aus Teilstand sichtbar" : "Bibliothek ist sichtbar",
                    "Phase 3/4 · " + parsed.size() + " Einträge sind nutzbar.\nDie crash-sichere Speicherung läuft im Hintergrund.", true);
        });

        LibraryGenerationStore.Stage stage = null;
        try {
            stage = LibraryGenerationStore.begin(this);
            long catalogStartedNs = System.nanoTime();
            writeEncryptedCatalog(parsed, stage.catalog);
            long catalogDurationMs = (System.nanoTime() - catalogStartedNs) / 1_000_000L;
            encryptFileWithProgress(plain, stage.playlist, parsed.size());
            LibraryGenerationStore.Generation committed = LibraryGenerationStore.commit(this, stage, parsed.size());
            stage = null;

            boolean metadataSaved = getPreferences(MODE_PRIVATE).edit()
                    .putString("active_name", name)
                    .putString("active_file", committed.relativePlaylistPath(this))
                    .putString("active_origin", origin)
                    .putBoolean("active_catalog_ready", true)
                    .commit();
            if (!metadataSaved) throw new IllegalStateException("Metadaten der aktiven Liste konnten nicht dauerhaft gespeichert werden.");

            activeLibraryGeneration = committed;
            activeSourceName = name;
            activeSourceFile = committed.relativePlaylistPath(this);
            synchronized (channels) {
                channels.clear();
                channels.addAll(parsed);
                activeSnapshot = previewSnapshot.isEmpty() ? immutableSnapshot(parsed) : previewSnapshot;
                previewChannels.clear();
                previewSnapshot = Collections.emptyList();
                previewSourceName = "";
                importPreviewActive = false;
            }
            plain.delete();
            appendDiagnosticLog("STORAGE", "Crash-sichere Bibliotheksgeneration aktiviert",
                    "Code=LIBRARY-GENERATION-COMMIT-OK · Generation=" + committed.id
                            + " · Eintraege=" + parsed.size() + " · KatalogMs=" + catalogDurationMs
                            + " · KatalogBytes=" + committed.catalog.length() + " · QuelleBytes=" + committed.playlist.length(), null);
            runOnUiThread(() -> {
                screen = Screen.START;
                render();
                showDiagnostic(partialRecovery ? "Bibliothek aus Teilstand bereit" : "Bibliothek bereit",
                        "Phase 4/4 · Fertig\nCode " + (partialRecovery ? "IMPORT-PARTIAL-OK" : "IMPORT-OK")
                                + "\n" + parsed.size() + " Einträge wurden atomar gespeichert.\n"
                                + "Der vorherige gültige Stand bleibt als Wiederherstellung verfügbar.", true);
            });
        } catch (Throwable failure) {
            LibraryGenerationStore.abandon(stage);
            synchronized (channels) {
                previewChannels.clear();
                previewSnapshot = Collections.emptyList();
                previewSourceName = "";
                importPreviewActive = false;
            }
            runOnUiThread(this::render);
            if (failure instanceof Exception) throw (Exception) failure;
            throw new IllegalStateException("Bibliothek konnte nicht crash-sicher aktiviert werden.", failure);
        }
    }
''')

s = replace_method(s, "restoreActiveSource", r'''
    private void restoreActiveSource() {
        if (!restoreWorkerRunning.compareAndSet(false, true)) {
            appendDiagnosticLog("STORAGE", "Doppelter Wiederherstellungsversuch ignoriert",
                    "Code=RESTORE-DEBOUNCED", null);
            return;
        }
        activeSourceName = getPreferences(MODE_PRIVATE).getString("active_name", "");
        activeSourceFile = getPreferences(MODE_PRIVATE).getString("active_file", "");
        List<LibraryGenerationStore.Generation> candidates = LibraryGenerationStore.restoreCandidates(this, activeSourceFile);
        if (candidates.isEmpty()) {
            restoreWorkerRunning.set(false);
            LibraryGenerationStore.markRestoreFinished(this);
            restoringSource = false;
            restoreStage = activeSourceFile.isBlank() ? "idle" : "missing";
            if (!activeSourceFile.isBlank()) {
                appendDiagnosticLog("STORAGE", "Kein gültiger Bibliotheksstand gefunden",
                        "Code=RESTORE-CATALOG-MISSING", null);
            }
            render();
            return;
        }

        final long generation = ++restoreGeneration;
        final long restoreStartedNs = System.nanoTime();
        restoringSource = true;
        restoreStage = "manifest";
        appendDiagnosticLog("STORAGE", "Crash-sichere Bibliothek wird geöffnet",
                "Code=RESTORE-START · Kandidaten=" + candidates.size() + " · Strategie=aktive Generation, vorherige Generation, Legacy", null);
        render();
        scheduleRestoreWatchdog(generation, restoreStartedNs);

        storageWorker.execute(() -> {
            Throwable lastFailure = null;
            boolean restored = false;
            try {
                for (int index = 0; index < candidates.size() && generation == restoreGeneration; index++) {
                    LibraryGenerationStore.Generation candidate = candidates.get(index);
                    File plain = new File(getCacheDir(), "playlist-restore-" + generation + "-" + index + ".tmp");
                    try {
                        restoreStage = candidate.legacy ? "legacy" : "catalog";
                        if (candidate.catalog.isFile()) {
                            try {
                                long catalogStart = System.nanoTime();
                                List<Channel> parsed = readEncryptedCatalog(candidate.catalog);
                                if (parsed.isEmpty()) throw new IllegalStateException("Schnellstart-Katalog ist leer.");
                                if (!publishRestoredChannels(parsed, generation)) return;
                                activeLibraryGeneration = candidate.legacy ? null : candidate;
                                if (!candidate.legacy) LibraryGenerationStore.markActive(this, candidate);
                                persistRestoredMetadata(candidate);
                                restored = true;
                                long durationMs = (System.nanoTime() - catalogStart) / 1_000_000L;
                                appendDiagnosticLog("STORAGE", "Bibliothek aus Schnellstart-Katalog geöffnet",
                                        "Code=" + (index == 0 ? "RESTORE-CATALOG-OK" : "RESTORE-PREVIOUS-GENERATION-OK")
                                                + " · Generation=" + sanitizeLogText(candidate.id)
                                                + " · Eintraege=" + parsed.size() + " · DauerMs=" + durationMs, null);
                                finishRestoreUi(generation);
                                if (candidate.legacy) migrateLegacyAfterRestore(candidate, parsed.size());
                                return;
                            } catch (OutOfMemoryError memoryFailure) {
                                lastFailure = memoryFailure;
                                appendDiagnosticLog("ERROR", "Katalog überschreitet verfügbaren Speicher",
                                        "Code=RESTORE-OOM · Generation=" + sanitizeLogText(candidate.id), memoryFailure);
                                System.gc();
                            } catch (Throwable catalogFailure) {
                                lastFailure = catalogFailure;
                                appendDiagnosticLog("STORAGE", "Schnellstart-Katalog ungültig, Rohquelle wird geprüft",
                                        "Code=RESTORE-CATALOG-CORRUPT · Generation=" + sanitizeLogText(candidate.id)
                                                + " · Ursache=" + sanitizeLogText(catalogFailure.getClass().getSimpleName()), catalogFailure);
                            }
                        }

                        restoreStage = "fallback";
                        decryptFile(candidate.playlist, plain);
                        restoreStage = "parse";
                        List<Channel> parsed = parsePlaylist(plain);
                        if (parsed.isEmpty()) throw new IllegalStateException("Gespeicherte Liste enthält keine unterstützten Einträge.");
                        if (!publishRestoredChannels(parsed, generation)) return;
                        activeLibraryGeneration = recoverGenerationFromRaw(candidate, parsed);
                        persistRestoredMetadata(activeLibraryGeneration == null ? candidate : activeLibraryGeneration);
                        restored = true;
                        appendDiagnosticLog("STORAGE", "Bibliothek über gesicherte Rohquelle wiederhergestellt",
                                "Code=RESTORE-FALLBACK-OK · Ursprung=" + sanitizeLogText(candidate.id)
                                        + " · Eintraege=" + parsed.size(), null);
                        finishRestoreUi(generation);
                        return;
                    } catch (OutOfMemoryError memoryFailure) {
                        lastFailure = memoryFailure;
                        appendDiagnosticLog("ERROR", "Wiederherstellung wegen Speicherdruck gestoppt",
                                "Code=RESTORE-OOM · Generation=" + sanitizeLogText(candidate.id), memoryFailure);
                        System.gc();
                    } catch (Throwable candidateFailure) {
                        lastFailure = candidateFailure;
                        appendDiagnosticLog("STORAGE", "Bibliotheksgeneration nicht verwendbar",
                                "Code=RESTORE-GENERATION-MISMATCH · Generation=" + sanitizeLogText(candidate.id)
                                        + " · Ursache=" + sanitizeLogText(candidateFailure.getClass().getSimpleName()), candidateFailure);
                    } finally {
                        plain.delete();
                    }
                }

                if (generation != restoreGeneration) return;
                restoringSource = false;
                restoreStage = "failed";
                Throwable finalFailure = lastFailure == null
                        ? new IllegalStateException("Kein gültiger Bibliotheksstand vorhanden.") : lastFailure;
                appendDiagnosticLog("ERROR", "Bibliothek konnte nicht wiederhergestellt werden",
                        "Code=RESTORE-CRASH-GUARD · Kandidaten=" + candidates.size(), finalFailure);
                runOnUiThread(() -> {
                    if (generation != restoreGeneration) return;
                    render();
                    showDiagnostic("Bibliothek konnte nicht geöffnet werden",
                            "Code RESTORE-CRASH-GUARD\nDer letzte gültige Stand konnte nicht gelesen werden. "
                                    + "Die App bleibt stabil; vorhandene Dateien wurden nicht gelöscht.\n\n"
                                    + "Öffne Systemstatus für die bereinigte Diagnose.", false);
                });
            } catch (Throwable guardedFailure) {
                if (generation != restoreGeneration) return;
                restoringSource = false;
                restoreStage = "failed";
                appendDiagnosticLog("ERROR", "Crash-Guard hat einen unerwarteten Restorefehler abgefangen",
                        "Code=RESTORE-CRASH-GUARD", guardedFailure);
                runOnUiThread(() -> {
                    render();
                    showDiagnostic("Bibliothek geschützt", "Code RESTORE-CRASH-GUARD\nDie Wiederherstellung wurde sicher beendet. Kein Bibliotheksstand wurde gelöscht.", false);
                });
            } finally {
                if (!restored && generation == restoreGeneration) restoringSource = false;
                restoreWorkerRunning.set(false);
                LibraryGenerationStore.markRestoreFinished(this);
            }
        });
    }
''')

helpers = r'''
    private void persistRestoredMetadata(LibraryGenerationStore.Generation candidate) {
        if (candidate == null) return;
        activeSourceFile = candidate.relativePlaylistPath(this);
        getPreferences(MODE_PRIVATE).edit()
                .putString("active_file", activeSourceFile)
                .putBoolean("active_catalog_ready", candidate.catalog.isFile())
                .commit();
    }

    private LibraryGenerationStore.Generation recoverGenerationFromRaw(
            LibraryGenerationStore.Generation candidate, List<Channel> parsed) {
        LibraryGenerationStore.Stage stage = null;
        try {
            stage = LibraryGenerationStore.begin(this);
            LibraryGenerationStore.copyPlaylistToStage(candidate.playlist, stage);
            writeEncryptedCatalog(parsed, stage.catalog);
            LibraryGenerationStore.Generation recovered = LibraryGenerationStore.commit(this, stage, parsed.size());
            stage = null;
            appendDiagnosticLog("STORAGE", "Neue gültige Generation aus Rohquelle erzeugt",
                    "Code=RESTORE-RECOVERY-COMMIT-OK · Generation=" + recovered.id
                            + " · Eintraege=" + parsed.size(), null);
            return recovered;
        } catch (Throwable failure) {
            LibraryGenerationStore.abandon(stage);
            appendDiagnosticLog("STORAGE", "Recovery-Generation konnte nicht geschrieben werden",
                    "Code=RESTORE-RECOVERY-COMMIT-DEFERRED · Ursache="
                            + sanitizeLogText(failure.getClass().getSimpleName()), failure);
            return candidate.legacy ? null : candidate;
        }
    }

    private void migrateLegacyAfterRestore(LibraryGenerationStore.Generation candidate, int entryCount) {
        try {
            LibraryGenerationStore.Generation migrated = LibraryGenerationStore.migrateLegacy(
                    this, candidate.playlist, candidate.catalog, entryCount);
            if (migrated != null) {
                activeLibraryGeneration = migrated;
                persistRestoredMetadata(migrated);
                appendDiagnosticLog("STORAGE", "Legacy-Bibliothek crash-sicher migriert",
                        "Code=RESTORE-LEGACY-MIGRATION-OK · Generation=" + migrated.id
                                + " · Eintraege=" + entryCount, null);
            }
        } catch (Throwable failure) {
            appendDiagnosticLog("STORAGE", "Legacy-Migration wird später wiederholt",
                    "Code=RESTORE-LEGACY-MIGRATION-DEFERRED · Ursache="
                            + sanitizeLogText(failure.getClass().getSimpleName()), failure);
        }
    }
'''
if "private void persistRestoredMetadata(" not in s:
    insert_at = s.find("    private void migrateCatalogToCurrentVersion(")
    if insert_at < 0:
        raise SystemExit("helper insertion marker missing")
    s = s[:insert_at] + helpers.strip("\n") + "\n\n" + s[insert_at:]

s = replace_method(s, "restoreStageLabel", r'''
    private String restoreStageLabel() {
        return switch (restoreStage) {
            case "manifest" -> "Bibliotheksgeneration";
            case "catalog" -> "Schnellstart-Katalog";
            case "legacy" -> "älterer Bibliotheksstand";
            case "fallback" -> "verschlüsselte Rohquelle";
            case "parse" -> "Sender und Sprachbereiche";
            case "timeout" -> "Zeitlimit erreicht";
            case "failed" -> "Recovery beendet";
            default -> "wird vorbereitet";
        };
    }
''')

s = replace_method(s, "encryptedPlaylistFile", r'''
    private File encryptedPlaylistFile() {
        LibraryGenerationStore.Generation active = activeLibraryGeneration != null
                ? activeLibraryGeneration : LibraryGenerationStore.active(this);
        return active == null ? new File(getFilesDir(), "active-playlist.lumen") : active.playlist;
    }
''')
s = replace_method(s, "encryptedCatalogFile", r'''
    private File encryptedCatalogFile() {
        LibraryGenerationStore.Generation active = activeLibraryGeneration != null
                ? activeLibraryGeneration : LibraryGenerationStore.active(this);
        return active == null ? new File(getFilesDir(), "active-catalog.lumen") : active.catalog;
    }
''')

s = replace_method(s, "confirmClearData", r'''
    private void confirmClearData() {
        new AlertDialog.Builder(this).setTitle("Lokale Daten löschen?")
                .setMessage("Alle lokalen Bibliotheksgenerationen, Profileinträge und EPG-Daten werden von diesem Gerät entfernt.")
                .setPositiveButton("Löschen", (d, w) -> {
                    restoreGeneration++;
                    restoreWorkerRunning.set(false);
                    LibraryGenerationStore.clear(this);
                    File epg = encryptedEpgFile();
                    if (epg.exists()) epg.delete();
                    getPreferences(MODE_PRIVATE).edit().clear().commit();
                    favoriteIds.clear();
                    epgSnapshot = EpgStore.Snapshot.EMPTY;
                    synchronized (channels) { channels.clear(); previewChannels.clear(); importPreviewActive = false; }
                    activeSnapshot = Collections.emptyList();
                    previewSnapshot = Collections.emptyList();
                    activeLibraryGeneration = null;
                    activeSourceName = ""; activeSourceFile = ""; previewSourceName = "";
                    filter = ""; globalSearch = ""; livePage = 0; searchPage = 0; favoritePage = 0; epgPage = 0;
                    epgOffsetMinutes = 0L; restoringSource = false; restoreStage = "idle";
                    mediaSection = MediaSection.LIVE; languageHub = LanguageHub.ALL;
                    screen = Screen.START;
                    showDiagnostic("Lokale Daten gelöscht", "Code STORAGE-CLEAR-OK\nDie Bibliothek ist jetzt leer.", false);
                    render();
                }).setNegativeButton("Abbrechen", null).show();
    }
''')

main.write_text(s, encoding="utf-8")

checks = {
    "version": "versionCode 134600" in gradle.read_text(encoding="utf-8"),
    "store": (pkg / "LibraryGenerationStore.java").is_file(),
    "single_worker": "restoreWorkerRunning.compareAndSet(false, true)" in s,
    "generations": "LIBRARY-GENERATION-COMMIT-OK" in s,
    "fallback": "RESTORE-PREVIOUS-GENERATION-OK" in s,
    "oom": "RESTORE-OOM" in s,
    "guard": "RESTORE-CRASH-GUARD" in s,
    "clear": "LibraryGenerationStore.clear(this)" in s,
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("P0 recovery integration checks failed: " + ", ".join(missing))
print("P0 crash-safe library integration applied: " + ", ".join(checks))
