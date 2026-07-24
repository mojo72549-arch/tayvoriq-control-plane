#!/usr/bin/env python3
from __future__ import annotations
import pathlib
import sys


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def block(text: str, start: str, end: str, new: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"{label}: start not found")
    b = text.find(end, a)
    if b < 0:
        raise SystemExit(f"{label}: end not found")
    return text[:a] + new + text[b:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-poc-home-persistence-fix.py <project-root>")
    root = pathlib.Path(sys.argv[1])
    java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"
    text = java.read_text(encoding="utf-8")

    text = once(text,
        "    private volatile boolean lastDownloadPartialRecovery;\n    private int livePage;\n\n    private enum Screen { START, LIVE, LIBRARY, SETTINGS }\n",
        "    private volatile boolean lastDownloadPartialRecovery;\n    private volatile boolean restoringSource;\n    private int livePage;\n    private MediaSection mediaSection = MediaSection.LIVE;\n\n    private enum Screen { START, MEDIA, EPG, SOURCE, SETTINGS }\n    private enum MediaSection { LIVE, VOD, SERIES }\n",
        "screen state")

    text = once(text,
        "        root = new FrameLayout(this);\n        buildMainUi();\n",
        "        activeSourceName = getPreferences(MODE_PRIVATE).getString(\"active_name\", \"\");\n        activeSourceFile = getPreferences(MODE_PRIVATE).getString(\"active_file\", \"\");\n        restoringSource = !activeSourceFile.isBlank()\n                && new File(getFilesDir(), activeSourceFile).isFile();\n        root = new FrameLayout(this);\n        buildMainUi();\n",
        "preload source")

    text = once(text,
        "        addNav(\"Start\", Screen.START);\n        addNav(\"Live\", Screen.LIVE);\n        addNav(television ? \"Bibliothek\" : \"Bibli.\", Screen.LIBRARY);\n        addNav(television ? \"Einstellungen\" : \"Einst.\", Screen.SETTINGS);\n",
        "        addNav(\"Start\", Screen.START);\n        addNav(television ? \"Einstellungen\" : \"Einst.\", Screen.SETTINGS);\n",
        "minimal nav")

    text = once(text,
        "            boolean selected = b.getTag() == screen;\n",
        "            boolean selected = b.getTag() == screen\n                    || (b.getTag() == Screen.START && screen != Screen.SETTINGS);\n",
        "nav selection")

    text = once(text,
        "        switch (screen) {\n            case START -> renderStart();\n            case LIVE -> renderLive();\n            case LIBRARY -> renderLibrary();\n            case SETTINGS -> renderSettings();\n        }\n",
        "        switch (screen) {\n            case START -> renderStart();\n            case MEDIA -> renderMedia();\n            case EPG -> renderEpg();\n            case SOURCE -> renderSource();\n            case SETTINGS -> renderSettings();\n        }\n",
        "render switch")

    home = r'''    private void renderStart() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText("Start");
        if (restoringSource) {
            pageSubtitle.setText("Gespeicherte Liste wird wiederhergestellt");
            cardInfo("Liste wird geladen", "Die bereits verschlüsselt gespeicherte Quelle wird lokal geöffnet. Ein erneuter Download ist nicht erforderlich.");
            return;
        }
        if (display.isEmpty()) {
            pageSubtitle.setText("Noch keine Liste eingerichtet");
            cardAction("Liste hinzufügen", "Server + Login, Playlist-Link oder lokale M3U/M3U8-Datei", () -> { screen = Screen.SOURCE; render(); });
            cardAction("Lokales Video öffnen", "Eine Videodatei ohne Upload direkt abspielen", this::openVideoPicker);
            cardInfo("Local First", "Playlist und Metadaten werden auf diesem Gerät verschlüsselt gespeichert. Project Lumen hostet oder vermittelt keine Inhalte.");
            return;
        }
        String sourceLabel = activeSourceName == null || activeSourceName.isBlank() ? "Gespeicherte Liste" : activeSourceName;
        pageSubtitle.setText(sourceLabel + " · " + display.size() + " Einträge bereit");
        int liveCount = countMediaSection(display, MediaSection.LIVE);
        int vodCount = countMediaSection(display, MediaSection.VOD);
        int seriesCount = countMediaSection(display, MediaSection.SERIES);
        cardAction("Live-Fernsehen", liveCount + " erkannte Live-Einträge öffnen", () -> openMedia(MediaSection.LIVE));
        cardAction("Programm (EPG)", "Elektronischen Programmführer öffnen", () -> { screen = Screen.EPG; render(); });
        cardAction("Filme & Mediathek", vodCount > 0 ? vodCount + " erkannte Film- und Mediathek-Einträge öffnen" : "Bereich vorbereitet; passende Einträge werden anhand der Listengruppen erkannt", () -> openMedia(MediaSection.VOD));
        cardAction("Serien", seriesCount > 0 ? seriesCount + " erkannte Serien-Einträge öffnen" : "Bereich vorbereitet; passende Einträge werden anhand der Listengruppen erkannt", () -> openMedia(MediaSection.SERIES));
        cardAction("Liste verwalten", "Aktive Quelle ansehen, ersetzen oder eine weitere Liste importieren", () -> { screen = Screen.SOURCE; render(); });
        if (importPreviewActive) {
            cardInfo("Speicherung läuft weiter", "Die Inhalte sind bereits sichtbar. Die verschlüsselte lokale Speicherung wird im Hintergrund abgeschlossen.");
        } else {
            cardInfo("Automatisch gespeichert", "Diese Liste wird beim nächsten Start lokal wiederhergestellt und muss nicht erneut heruntergeladen werden.");
        }
    }

    private void renderSource() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText("Liste verwalten");
        if (importPreviewActive) {
            pageSubtitle.setText(previewSourceName + " · " + display.size() + " Einträge werden gespeichert");
        } else {
            pageSubtitle.setText(display.isEmpty() ? "Liste einrichten" : activeSourceName + " · " + display.size() + " Einträge aktiv");
        }
        cardAction("Server + Login", "Serveradresse, Benutzername und Passwort eingeben; Lumen erzeugt die Abrufadresse.", this::promptServerLogin);
        cardAction("Playlist-Link", "Vollständigen HTTP- oder HTTPS-Link zu M3U/M3U8 eingeben.", this::promptPlaylistLink);
        cardAction("Datei auswählen", "Lokale M3U/M3U8-Datei öffnen, prüfen und verschlüsselt speichern.", this::openPlaylistPicker);
        if (!display.isEmpty()) {
            String state = importPreviewActive ? "Vorschau verfügbar · Speicherung läuft im Hintergrund" : "lokal verschlüsselt und beim Neustart verfügbar";
            cardInfo(importPreviewActive ? "Liste bereits sichtbar" : "Aktive Liste", (importPreviewActive ? previewSourceName : activeSourceName) + "\n" + display.size() + " Einträge · " + state);
            cardAction("Zur Startseite", "Live-Fernsehen, Programm, Filme und Serien öffnen", () -> { screen = Screen.START; render(); });
        }
    }

'''
    text = block(text, "    private void renderStart() {\n", "    private void renderLive() {\n", home, "home/source")

    media = r'''    private void openMedia(MediaSection section) {
        mediaSection = section;
        filter = "";
        livePage = 0;
        screen = Screen.MEDIA;
        render();
    }

    private void renderMedia() {
        List<Channel> snapshot = displayChannelsSnapshot();
        pageTitle.setText(mediaSectionTitle());
        if (snapshot.isEmpty()) {
            pageSubtitle.setText("Keine Liste geladen");
            cardAction("Liste hinzufügen", "Eine rechtmäßig nutzbare Quelle einrichten.", () -> { screen = Screen.SOURCE; render(); });
            return;
        }
        ChannelPage channelPage = channelPage(snapshot);
        int from = channelPage.total == 0 ? 0 : channelPage.start + 1;
        int to = channelPage.start + channelPage.items.size();
        pageSubtitle.setText(from + "–" + to + " von " + channelPage.total + " passenden Einträgen");
        if (channelPage.total == 0) {
            cardInfo("Noch keine passenden Einträge erkannt", "Project Lumen ordnet den Bereich im POC anhand von Streampfad und Gruppenname zu. Die Liste bleibt unverändert gespeichert.");
            cardAction("Liste verwalten", "Quelle prüfen oder eine andere Liste importieren", () -> { screen = Screen.SOURCE; render(); });
            return;
        }
        if (importPreviewActive) cardInfo("Import läuft weiter", "Die Liste ist bereits nutzbar. Die verschlüsselte Speicherung wird im Hintergrund abgeschlossen.");
        EditText search = input("Sender, Titel oder Gruppe suchen", false);
        search.setText(filter);
        Button apply = button("Suchen", true);
        apply.setOnClickListener(v -> { filter = search.getText().toString().trim(); livePage = 0; render(); });
        LinearLayout searchRow = new LinearLayout(this);
        searchRow.setOrientation(LinearLayout.HORIZONTAL);
        searchRow.addView(search, new LinearLayout.LayoutParams(0, dp(television ? 56 : 48), 1f));
        LinearLayout.LayoutParams ap = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 56 : 48));
        ap.setMargins(dp(7), 0, 0, 0);
        searchRow.addView(apply, ap);
        content.addView(searchRow, marginBottom(10));
        ListView list = new ListView(this);
        list.setDividerHeight(dp(5));
        list.setBackgroundColor(Color.TRANSPARENT);
        list.setNestedScrollingEnabled(true);
        ChannelAdapter adapter = new ChannelAdapter(this, channelPage.items);
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> play(channelPage.items.get(position)));
        content.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(television ? 620 : 480)));
        LinearLayout pager = new LinearLayout(this);
        pager.setOrientation(LinearLayout.HORIZONTAL);
        Button previous = button("Zurück", false);
        previous.setEnabled(livePage > 0);
        previous.setOnClickListener(v -> { if (livePage > 0) livePage--; render(); });
        Button next = button("Weiter", false);
        next.setEnabled(channelPage.start + channelPage.items.size() < channelPage.total);
        next.setOnClickListener(v -> { if (channelPage.start + channelPage.items.size() < channelPage.total) livePage++; render(); });
        pager.addView(previous, new LinearLayout.LayoutParams(0, dp(48), 1f));
        LinearLayout.LayoutParams nextParams = new LinearLayout.LayoutParams(0, dp(48), 1f);
        nextParams.setMargins(dp(8), 0, 0, 0);
        pager.addView(next, nextParams);
        content.addView(pager, marginBottom(10));
    }

    private void renderEpg() {
        pageTitle.setText("Programm");
        pageSubtitle.setText("Elektronischer Programmführer (EPG)");
        if (displayChannelsSnapshot().isEmpty()) {
            cardAction("Liste hinzufügen", "Zuerst eine Quelle einrichten.", () -> { screen = Screen.SOURCE; render(); });
            return;
        }
        cardInfo("EPG im POC vorbereitet", "Die Startseite und Navigation sind eingerichtet. Für echte Sendungsdaten benötigt die Quelle zusätzlich eine EPG-Adresse beziehungsweise XMLTV-Daten. Diese Zuordnung folgt im nächsten Ausbauschritt.");
        cardAction("Live-Fernsehen öffnen", "Zur aktuell geladenen Senderliste wechseln", () -> openMedia(MediaSection.LIVE));
    }

    private String mediaSectionTitle() {
        return switch (mediaSection) {
            case LIVE -> "Live-Fernsehen";
            case VOD -> "Filme & Mediathek";
            case SERIES -> "Serien";
        };
    }

    private int countMediaSection(List<Channel> source, MediaSection section) {
        int count = 0;
        for (Channel channel : source) if (matchesMediaSection(channel, section)) count++;
        return count;
    }

    private boolean matchesMediaSection(Channel channel, MediaSection section) {
        String group = channel.group == null ? "" : channel.group.toLowerCase(Locale.ROOT);
        String url = channel.url == null ? "" : channel.url.toLowerCase(Locale.ROOT);
        boolean series = url.contains("/series/") || containsAny(group, "serie", "series", "tv show", "staffel", "episode");
        boolean vod = !series && (url.contains("/movie/") || containsAny(group, " vod", "vod ", "filme", "film ", "movie", "kino", "mediathek"));
        return switch (section) {
            case LIVE -> !series && !vod;
            case VOD -> vod;
            case SERIES -> series;
        };
    }

    private static boolean containsAny(String value, String... needles) {
        for (String needle : needles) if (value.contains(needle)) return true;
        return false;
    }

'''
    text = block(text, "    private void renderLive() {\n", "    private List<Channel> displayChannelsSnapshot() {\n", media, "media/epg")

    text = once(text,
        "            boolean matches = needle.isBlank()\n                    || channel.name.toLowerCase(Locale.ROOT).contains(needle)\n                    || channel.group.toLowerCase(Locale.ROOT).contains(needle);\n            if (!matches) continue;\n",
        "            if (!matchesMediaSection(channel, mediaSection)) continue;\n            boolean matches = needle.isBlank()\n                    || channel.name.toLowerCase(Locale.ROOT).contains(needle)\n                    || channel.group.toLowerCase(Locale.ROOT).contains(needle);\n            if (!matches) continue;\n",
        "section paging")

    text = text.replace("screen = Screen.LIVE;", "screen = Screen.START;")
    text = text.replace("screen = Screen.LIBRARY;", "screen = Screen.SOURCE;")

    text = once(text,
        "        diagnosticOpenList.setOnClickListener(v -> { hideDiagnostics(); screen = Screen.START; render(); });\n",
        "        diagnosticOpenList.setOnClickListener(v -> { hideDiagnostics(); mediaSection = MediaSection.LIVE; filter = \"\"; livePage = 0; screen = Screen.MEDIA; render(); });\n",
        "diagnostic target")

    text = once(text,
        "            getPreferences(MODE_PRIVATE).edit()\n                    .putString(\"active_name\", name)\n                    .putString(\"active_file\", encrypted.getName())\n                    .putString(\"active_origin\", origin)\n                    .apply();\n",
        "            boolean metadataSaved = getPreferences(MODE_PRIVATE).edit()\n                    .putString(\"active_name\", name)\n                    .putString(\"active_file\", encrypted.getName())\n                    .putString(\"active_origin\", origin)\n                    .commit();\n            if (!metadataSaved) throw new IllegalStateException(\"Metadaten der aktiven Liste konnten nicht dauerhaft gespeichert werden.\");\n",
        "durable prefs")

    restore = r'''    private void restoreActiveSource() {
        activeSourceName = getPreferences(MODE_PRIVATE).getString("active_name", "");
        activeSourceFile = getPreferences(MODE_PRIVATE).getString("active_file", "");
        if (activeSourceFile.isBlank()) { restoringSource = false; render(); return; }
        File encrypted = new File(getFilesDir(), activeSourceFile);
        if (!encrypted.isFile()) {
            appendDiagnosticLog("STORAGE", "Gespeicherte Liste fehlt", "Code=RESTORE-FILE-MISSING", null);
            getPreferences(MODE_PRIVATE).edit().remove("active_name").remove("active_file").remove("active_origin").commit();
            activeSourceName = "";
            activeSourceFile = "";
            restoringSource = false;
            render();
            return;
        }
        restoringSource = true;
        appendDiagnosticLog("STORAGE", "Gespeicherte Liste wird wiederhergestellt", "Datei=interne verschluesselte App-Datei", null);
        render();
        storageWorker.execute(() -> {
            File plain = new File(getCacheDir(), "playlist-restore.tmp");
            try {
                decryptFile(encrypted, plain);
                List<Channel> parsed = parsePlaylist(plain);
                plain.delete();
                if (parsed.isEmpty()) throw new IllegalStateException("Gespeicherte Liste enthält keine unterstützten Einträge.");
                synchronized (channels) { channels.clear(); channels.addAll(parsed); }
                restoringSource = false;
                appendDiagnosticLog("STORAGE", "Gespeicherte Liste wiederhergestellt", "Code=RESTORE-OK · Eintraege=" + parsed.size(), null);
                runOnUiThread(() -> { screen = Screen.START; hideDiagnostics(); render(); });
            } catch (Exception e) {
                plain.delete();
                restoringSource = false;
                appendDiagnosticLog("ERROR", "Gespeicherte Liste konnte nicht geladen werden", "Code=STORAGE-DECRYPT", e);
                runOnUiThread(() -> { render(); showDiagnostic("Liste konnte nicht geladen werden", "Code STORAGE-DECRYPT\n" + safeMessage(e) + "\n\nDie gespeicherte Datei wurde nicht automatisch gelöscht.", false); });
            }
        });
    }

'''
    text = block(text, "    private void restoreActiveSource() {\n", "    private File encryptedPlaylistFile() {", restore, "restore")

    text = once(text,
        "                    activeSourceName = \"\"; activeSourceFile = \"\"; previewSourceName = \"\"; filter = \"\"; livePage = 0;\n",
        "                    activeSourceName = \"\"; activeSourceFile = \"\"; previewSourceName = \"\";\n                    filter = \"\"; livePage = 0; restoringSource = false; mediaSection = MediaSection.LIVE;\n                    screen = Screen.START;\n",
        "clear state")

    text = text.replace('text("v13.1.21"', 'text("v13.1.22"')
    text = text.replace('value.append("App=").append("13.1.21")', 'value.append("App=").append("13.1.22")')
    text = text.replace("ProjectLumen/13.1.21 Android", "ProjectLumen/13.1.22 Android")
    java.write_text(text, encoding="utf-8")

    g = gradle.read_text(encoding="utf-8")
    g = once(g, "versionCode 133100", "versionCode 133200", "versionCode")
    g = once(g, "versionName '13.1.21-import-start-watchdog-preview'", "versionName '13.1.22-poc-home-persistence-preview'", "versionName")
    gradle.write_text(g, encoding="utf-8")
    strings.write_text(strings.read_text(encoding="utf-8").replace("Project Lumen 13.1.21 Preview", "Project Lumen 13.1.22 Preview"), encoding="utf-8")
    if readme.exists():
        readme.write_text(readme.read_text(encoding="utf-8").replace("Project Lumen 13.1.21", "Project Lumen 13.1.22"), encoding="utf-8")

    checks = {
        "minimal navigation": 'addNav("Live"' not in text and "Screen.LIBRARY" not in text,
        "four German areas": all(x in text for x in ["Live-Fernsehen", "Programm (EPG)", "Filme & Mediathek", "Serien"]),
        "empty state": "Noch keine Liste eingerichtet" in text,
        "section filtering": "matchesMediaSection" in text,
        "restore success": "Code=RESTORE-OK" in text,
        "durable preferences": "metadataSaved" in text and ".commit();" in text,
        "version": 'text("v13.1.22"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("verification failed: " + ", ".join(failed))
    print("Project Lumen 13.1.22 POC home and persistence patch applied")
    for name in checks:
        print("OK:", name)


if __name__ == "__main__":
    main()
