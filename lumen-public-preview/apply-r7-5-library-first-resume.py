#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
main = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
gradle = root / "app/build.gradle"
if not main.exists() or not gradle.exists():
    raise SystemExit("13.1.38 input source missing")


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
g = re.sub(r"versionCode\s+\d+", "versionCode 134800", g, count=1)
g = re.sub(r"versionName\s+'[^']+'", "versionName '13.1.38-library-first-resume-pilot'", g, count=1)
gradle.write_text(g, encoding="utf-8")

s = main.read_text(encoding="utf-8")
s = s.replace('text("13.1.37"', 'text("13.1.38"')
s = s.replace('Project Lumen 13.1.37 · P0 Schnelle Listen',
              'Project Lumen 13.1.38 · Bibliothek direkt öffnen')

field_marker = "    private volatile long lastMediaNavigationAtMs;\n"
if "libraryResumeLoaded" not in s:
    if field_marker not in s:
        raise SystemExit("13.1.37 navigation field marker missing")
    s = s.replace(field_marker, field_marker + '''    private boolean libraryResumeLoaded;
    private static final String NAV_SECTION = "library_resume_section";
    private static final String NAV_LANGUAGE = "library_resume_language";
    private static final String NAV_FILTER = "library_resume_filter";
    private static final String NAV_PAGE = "library_resume_page";
''', 1)

oncreate_marker = '''        restoringSource = activeLibraryGeneration != null
                || (!activeSourceFile.isBlank() && new File(getFilesDir(), activeSourceFile).isFile());
        root = new FrameLayout(this);'''
oncreate_replacement = '''        restoringSource = activeLibraryGeneration != null
                || (!activeSourceFile.isBlank() && new File(getFilesDir(), activeSourceFile).isFile());
        restoreLibraryNavigationState();
        root = new FrameLayout(this);'''
if oncreate_marker not in s:
    raise SystemExit("onCreate library resume marker missing")
s = s.replace(oncreate_marker, oncreate_replacement, 1)

s = replace_method(s, "render", r'''
    private void render() {
        if (content == null) return;
        refreshProfileStateIfNeeded();
        content.removeAllViews();
        if (contentScroll != null) contentScroll.post(() -> contentScroll.scrollTo(0, 0));
        rebuildNav();
        switch (screen) {
            case START -> renderStart();
            case MEDIA -> renderMedia();
            case EPG -> renderEpg();
            case SEARCH -> renderSearch();
            case FAVORITES -> renderFavorites();
            case SOURCE -> renderSource();
            case SETTINGS -> renderSettings();
        }
        if (pageSubtitle != null) {
            CharSequence value = pageSubtitle.getText();
            pageSubtitle.setVisibility(value == null || value.toString().isBlank() ? View.GONE : View.VISIBLE);
        }
        if (!restoringSource && screen == Screen.MEDIA && hasDisplayChannels()) {
            persistLibraryNavigationState();
        }
    }
''')

s = replace_method(s, "renderStart", r'''
    private void renderStart() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText(timeGreeting());
        pageSubtitle.setText("Profil " + ProfileStore.activeName(this));
        if (restoringSource) {
            premiumHero("Bibliothek wird geöffnet", restoreStageLabel(), null, null);
            cardInfo("Letzte Bibliothek", "Wird lokal und ohne neuen Netzwerkdownload wiederhergestellt.");
            return;
        }
        if (display.isEmpty()) {
            premiumHero("Deine Medien", "Quelle hinzufügen und loslegen.",
                    "Quelle hinzufügen", () -> { screen = Screen.SOURCE; render(); });
            sectionTitle("Schnell starten", "");
            cardAction("Lokales Video", "Direkt vom Gerät abspielen", this::openVideoPicker);
            cardInfo("Lokal & privat", "Nur eigene Quellen verwenden.");
            return;
        }

        HomeSnapshot home = buildHomeSnapshot(display);
        pageSubtitle.setText(ProfileStore.activeName(this) + " · " + display.size() + " Inhalte");
        premiumHero("Bereit", home.liveCount + " Live · " + home.vodCount + " Filme · "
                + home.seriesCount + " Serien", "Bibliothek öffnen", this::openRememberedLibrary);
        premiumMediaRow("Weiterschauen", "", continueWatchingChannels(display));
        List<Channel> favoritePreview = new ArrayList<>();
        for (Channel channel : display) {
            if (isFavorite(channel)) favoritePreview.add(channel);
            if (favoritePreview.size() >= 14) break;
        }
        premiumMediaRow("Favoriten", "", favoritePreview);
        sectionTitle("Sprachen & Länder", "");
        languageHubRow(home);
        premiumMediaRow("Jetzt live", "", home.livePreview);
        premiumMediaRow("Filme", "", home.vodPreview);
        premiumMediaRow("Serien", "", home.seriesPreview);
    }
''')

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
        mediaSection = MediaSection.LIVE;
        languageHub = LanguageHub.ALL;
        filter = "";
        runOnUiThread(() -> {
            screen = Screen.MEDIA;
            hideDiagnostics();
            invalidateMediaUi();
            render();
            Toast.makeText(this, "Bibliothek ist bereits nutzbar. Speicherung läuft weiter.", Toast.LENGTH_SHORT).show();
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
                screen = Screen.MEDIA;
                persistLibraryNavigationState();
                hideDiagnostics();
                invalidateMediaUi();
                render();
                Toast.makeText(this, partialRecovery ? "Bibliothek aus Teilstand bereit" : "Bibliothek bereit",
                        Toast.LENGTH_SHORT).show();
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

s = replace_method(s, "finishRestoreUi", r'''
    private void finishRestoreUi(long generation) {
        runOnUiThread(() -> {
            if (generation != restoreGeneration) return;
            screen = Screen.MEDIA;
            hideDiagnostics();
            invalidateMediaUi();
            render();
            appendDiagnosticLog("UI", "Letzte Bibliothek automatisch geöffnet",
                    "Code=LIBRARY-RESUME-OK · Bereich=" + mediaSection
                            + " · Sprache=" + languageHub + " · Seite=" + livePage, null);
        });
    }
''')

helper_marker = "    private void openMedia(MediaSection section) {"
helpers = r'''
    private void restoreLibraryNavigationState() {
        if (libraryResumeLoaded) return;
        libraryResumeLoaded = true;
        SharedPreferences preferences = getPreferences(MODE_PRIVATE);
        mediaSection = parseEnum(preferences.getString(NAV_SECTION, MediaSection.LIVE.name()),
                MediaSection.class, MediaSection.LIVE);
        languageHub = parseEnum(preferences.getString(NAV_LANGUAGE, LanguageHub.ALL.name()),
                LanguageHub.class, LanguageHub.ALL);
        filter = preferences.getString(NAV_FILTER, "");
        livePage = Math.max(0, Math.min(1_666, preferences.getInt(NAV_PAGE, 0)));
    }

    private void persistLibraryNavigationState() {
        if (!hasDisplayChannels()) return;
        getPreferences(MODE_PRIVATE).edit()
                .putString(NAV_SECTION, mediaSection.name())
                .putString(NAV_LANGUAGE, languageHub.name())
                .putString(NAV_FILTER, filter == null ? "" : filter)
                .putInt(NAV_PAGE, Math.max(0, livePage))
                .apply();
    }

    private void openRememberedLibrary() {
        if (!acceptMediaNavigation()) return;
        screen = Screen.MEDIA;
        invalidateMediaUi();
        render();
    }

    private static <E extends Enum<E>> E parseEnum(String value, Class<E> type, E fallback) {
        try {
            return Enum.valueOf(type, value == null ? "" : value);
        } catch (Exception ignored) {
            return fallback;
        }
    }

'''
if helper_marker not in s:
    raise SystemExit("library navigation helper marker missing")
s = s.replace(helper_marker, helpers.strip("\n") + "\n\n" + helper_marker, 1)

on_destroy_marker = "    @Override\n    protected void onDestroy() {"
if "protected void onStop()" not in s:
    if on_destroy_marker not in s:
        raise SystemExit("onDestroy insertion marker missing")
    s = s.replace(on_destroy_marker, '''    @Override
    protected void onStop() {
        if (!restoringSource && screen == Screen.MEDIA && hasDisplayChannels()) {
            persistLibraryNavigationState();
        }
        super.onStop();
    }

''' + on_destroy_marker, 1)

main.write_text(s, encoding="utf-8")

for strings in root.glob("app/src/main/res/values*/strings.xml"):
    text = strings.read_text(encoding="utf-8")
    if 'name="app_name"' in text:
        text = re.sub(r'(<string\s+name="app_name"[^>]*>).*?(</string>)',
                      r'\1Project Lumen 13.1.38\2', text, count=1, flags=re.S)
        strings.write_text(text, encoding="utf-8")

checks = {
    "version": "versionCode 134800" in gradle.read_text(encoding="utf-8"),
    "resume_load": "restoreLibraryNavigationState();" in s,
    "resume_finish": "Code=LIBRARY-RESUME-OK" in s,
    "content_default": "screen = Screen.MEDIA;" in s,
    "nonblocking_import": "Bibliothek ist bereits nutzbar. Speicherung läuft weiter." in s,
    "no_restore_cta": 'premiumHero("Bibliothek wird geöffnet", restoreStageLabel(), null, null)' in s,
    "persist": "persistLibraryNavigationState()" in s,
    "anr_worker": "libraryUiWorker.execute" in s,
    "p0_store": "LibraryGenerationStore.commit" in s,
    "dns": "IMPORT-DNS" in s,
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("13.1.38 integration checks failed: " + ", ".join(missing))
print("13.1.38 library-first integration applied: " + ", ".join(checks))
