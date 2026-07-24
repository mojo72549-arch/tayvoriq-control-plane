#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str, label: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        raise SystemExit(f"{label}: start marker not found")
    end = text.find(end_marker, start)
    if end < 0:
        raise SystemExit(f"{label}: end marker not found")
    return text[:start] + replacement + text[end:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-list-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    private static final int MAX_CHANNELS = 100_000;\n",
        "    private static final int MAX_CHANNELS = 100_000;\n"
        "    private static final int LIVE_PAGE_SIZE = 200;\n",
        "LIVE_PAGE_SIZE",
    )

    text = replace_once(
        text,
        "    private final List<Channel> channels = new ArrayList<>();\n",
        "    private final List<Channel> channels = new ArrayList<>();\n"
        "    private final List<Channel> previewChannels = new ArrayList<>();\n",
        "previewChannels field",
    )

    text = replace_once(
        text,
        "    private String filter = \"\";\n",
        "    private String filter = \"\";\n"
        "    private String previewSourceName = \"\";\n"
        "    private volatile boolean importPreviewActive;\n"
        "    private int livePage;\n",
        "preview state fields",
    )

    render_block = r'''    private void renderStart() {
        List<Channel> display = displayChannelsSnapshot();
        boolean empty = display.isEmpty();
        pageTitle.setText("Start");
        if (importPreviewActive) {
            pageSubtitle.setText(display.size() + " Einträge werden gespeichert");
        } else {
            pageSubtitle.setText(empty ? "Noch keine Quelle eingerichtet" : display.size() + " Einträge bereit");
        }
        cardAction(empty ? "Quelle hinzufügen" : "Live ansehen",
                empty ? "Server + Login, Playlist-Link oder lokale Datei" : "Senderliste öffnen und direkt streamen",
                () -> { screen = empty ? Screen.LIBRARY : Screen.LIVE; render(); });
        cardAction("Lokales Video öffnen", "Videodatei ohne Upload direkt abspielen", this::openVideoPicker);
        cardInfo("Local First", "Playlist und Metadaten werden auf diesem Gerät verschlüsselt gespeichert. Project Lumen hostet oder vermittelt keine Inhalte.");
    }

    private void renderLibrary() {
        List<Channel> display = displayChannelsSnapshot();
        pageTitle.setText("Bibliothek");
        if (importPreviewActive) {
            pageSubtitle.setText(previewSourceName + " · " + display.size() + " Einträge werden gespeichert");
        } else {
            pageSubtitle.setText(display.isEmpty() ? "Quelle einrichten" : activeSourceName + " · " + display.size() + " Einträge aktiv");
        }
        cardAction("1. Server + Login", "Serveradresse, Benutzername und Passwort eingeben; Lumen erzeugt die Abrufadresse.", this::promptServerLogin);
        cardAction("2. Playlist-Link", "Vollständigen HTTP- oder HTTPS-Link zu M3U/M3U8 eingeben.", this::promptPlaylistLink);
        cardAction("3. Datei auswählen", "Lokale M3U/M3U8-Datei öffnen, prüfen und verschlüsselt speichern.", this::openPlaylistPicker);
        if (!display.isEmpty()) {
            String state = importPreviewActive
                    ? "Vorschau verfügbar · Speicherung läuft im Hintergrund"
                    : "lokal verschlüsselt";
            cardInfo(importPreviewActive ? "Senderliste bereits sichtbar" : "Aktive Quelle",
                    (importPreviewActive ? previewSourceName : activeSourceName) + "\n" + display.size() + " Einträge · " + state);
            cardAction("Senderliste öffnen", "Direkt zu Live wechseln", () -> { screen = Screen.LIVE; render(); });
        }
    }

    private void renderLive() {
        List<Channel> snapshot = displayChannelsSnapshot();
        pageTitle.setText("Live");
        if (snapshot.isEmpty()) {
            pageSubtitle.setText("Keine Senderliste geladen");
            cardAction("Quelle hinzufügen", "Bibliothek öffnen und eine rechtmäßig nutzbare Quelle einrichten.", () -> { screen = Screen.LIBRARY; render(); });
            return;
        }

        ChannelPage channelPage = channelPage(snapshot);
        int from = channelPage.total == 0 ? 0 : channelPage.start + 1;
        int to = channelPage.start + channelPage.items.size();
        pageSubtitle.setText(from + "–" + to + " von " + channelPage.total + " Einträgen");

        if (importPreviewActive) {
            cardInfo("Import läuft weiter", "Die Senderliste ist bereits nutzbar. Die verschlüsselte Speicherung wird im Hintergrund abgeschlossen.");
        }

        EditText search = input("Sender oder Gruppe suchen", false);
        search.setText(filter);
        Button apply = button("Suchen", true);
        apply.setOnClickListener(v -> {
            filter = search.getText().toString().trim();
            livePage = 0;
            render();
        });
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
        content.addView(list, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(television ? 620 : 480)));

        LinearLayout pager = new LinearLayout(this);
        pager.setOrientation(LinearLayout.HORIZONTAL);
        Button previous = button("Zurück", false);
        previous.setEnabled(livePage > 0);
        previous.setOnClickListener(v -> {
            if (livePage > 0) livePage--;
            render();
        });
        Button next = button("Weiter", false);
        next.setEnabled(channelPage.start + channelPage.items.size() < channelPage.total);
        next.setOnClickListener(v -> {
            if (channelPage.start + channelPage.items.size() < channelPage.total) livePage++;
            render();
        });
        pager.addView(previous, new LinearLayout.LayoutParams(0, dp(48), 1f));
        LinearLayout.LayoutParams nextParams = new LinearLayout.LayoutParams(0, dp(48), 1f);
        nextParams.setMargins(dp(8), 0, 0, 0);
        pager.addView(next, nextParams);
        content.addView(pager, marginBottom(10));
    }

    private List<Channel> displayChannelsSnapshot() {
        synchronized (channels) {
            return new ArrayList<>(importPreviewActive ? previewChannels : channels);
        }
    }

    private ChannelPage channelPage(List<Channel> source) {
        String needle = filter == null ? "" : filter.trim().toLowerCase(Locale.ROOT);
        int requestedStart = Math.max(0, livePage) * LIVE_PAGE_SIZE;
        List<Channel> items = new ArrayList<>(LIVE_PAGE_SIZE);
        int total = 0;
        for (Channel channel : source) {
            boolean matches = needle.isBlank()
                    || channel.name.toLowerCase(Locale.ROOT).contains(needle)
                    || channel.group.toLowerCase(Locale.ROOT).contains(needle);
            if (!matches) continue;
            if (total >= requestedStart && items.size() < LIVE_PAGE_SIZE) items.add(channel);
            total++;
        }
        if (requestedStart >= total && total > 0) {
            livePage = Math.max(0, (total - 1) / LIVE_PAGE_SIZE);
            return channelPage(source);
        }
        return new ChannelPage(items, total, requestedStart);
    }

'''

    text = replace_between(
        text,
        "    private void renderStart() {",
        "    private void renderSettings() {",
        render_block,
        "render list block",
    )

    parse_block = r'''    private void parseAndActivate(String name, File plain, String origin) throws Exception {
        runOnUiThread(() -> showDiagnostic("Playlist wird geprüft", "Phase 2/4 · Sender, Gruppen und Streamadressen werden ausgewertet.", false));
        List<Channel> parsed = parsePlaylist(plain);
        if (parsed.isEmpty()) throw new IllegalArgumentException("Keine unterstützten Einträge in der Playlist gefunden.");

        synchronized (channels) {
            previewChannels.clear();
            previewChannels.addAll(parsed);
            previewSourceName = name;
            importPreviewActive = true;
        }
        livePage = 0;
        runOnUiThread(() -> {
            screen = Screen.LIVE;
            render();
            showDiagnostic(
                    "Senderliste ist sichtbar",
                    "Phase 3/4 · " + parsed.size() + " Einträge wurden ausgewertet.\n"
                            + "Die Liste kann jetzt bereits geöffnet und durchsucht werden.\n\n"
                            + "Die lokale Verschlüsselung läuft weiter.",
                    true);
        });

        try {
            File encrypted = encryptedPlaylistFile();
            File tempEncrypted = new File(encrypted.getParentFile(), encrypted.getName() + ".tmp");
            encryptFileWithProgress(plain, tempEncrypted, parsed.size());
            if (encrypted.exists() && !encrypted.delete()) throw new IllegalStateException("Alte verschlüsselte Quelle konnte nicht ersetzt werden.");
            if (!tempEncrypted.renameTo(encrypted)) throw new IllegalStateException("Verschlüsselte Quelle konnte nicht aktiviert werden.");
            plain.delete();
            getPreferences(MODE_PRIVATE).edit()
                    .putString("active_name", name)
                    .putString("active_file", encrypted.getName())
                    .putString("active_origin", origin)
                    .apply();
            synchronized (channels) {
                channels.clear();
                channels.addAll(parsed);
                previewChannels.clear();
                previewSourceName = "";
                importPreviewActive = false;
            }
            activeSourceName = name;
            activeSourceFile = encrypted.getName();
            runOnUiThread(() -> {
                screen = Screen.LIVE;
                render();
                showDiagnostic("Senderliste bereit", "Phase 4/4 · Fertig\nCode IMPORT-OK\n" + parsed.size() + " Einträge wurden erkannt und aktiviert.\n\nDie Liste wird seitenweise angezeigt, damit auch sehr große Playlists flüssig bleiben.", true);
            });
        } catch (Exception failure) {
            synchronized (channels) {
                previewChannels.clear();
                previewSourceName = "";
                importPreviewActive = false;
            }
            runOnUiThread(this::render);
            throw failure;
        }
    }

'''

    text = replace_between(
        text,
        "    private void parseAndActivate(String name, File plain, String origin) throws Exception {",
        "    private List<Channel> parsePlaylist(File file) throws Exception {",
        parse_block,
        "parseAndActivate",
    )

    encrypt_block = r'''    private void encryptFileWithProgress(File input, File output, int entryCount) throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
        long expected = Math.max(1L, input.length());
        long nextReport = 512L * 1024L;
        long total = 0L;
        try (FileOutputStream fileOut = new FileOutputStream(output)) {
            byte[] iv = cipher.getIV();
            fileOut.write(iv.length);
            fileOut.write(iv);
            try (CipherOutputStream encrypted = new CipherOutputStream(fileOut, cipher); FileInputStream in = new FileInputStream(input)) {
                byte[] buffer = new byte[64 * 1024];
                int read;
                while ((read = in.read(buffer)) >= 0) {
                    if (read == 0) continue;
                    encrypted.write(buffer, 0, read);
                    total += read;
                    if (total >= nextReport) {
                        long report = total;
                        int percent = (int) Math.min(99L, (report * 100L) / expected);
                        nextReport = total + 512L * 1024L;
                        runOnUiThread(() -> showDiagnostic(
                                "Quelle wird gespeichert",
                                "Phase 3/4 · " + entryCount + " Einträge werden lokal verschlüsselt gespeichert.\n"
                                        + "Fortschritt: " + percent + "%\n\n"
                                        + "Die Senderliste kann bereits geöffnet werden.",
                                true));
                    }
                }
            }
        }
    }

'''

    text = replace_between(
        text,
        "    private void encryptFile(File input, File output) throws Exception {",
        "    private void decryptFile(File input, File output) throws Exception {",
        encrypt_block,
        "encryptFileWithProgress",
    )

    text = replace_once(
        text,
        "    private void openDiagnostics() { showDiagnostic(lastDiagnosticTitle, lastDiagnosticBody, !channels.isEmpty()); }",
        "    private void openDiagnostics() { showDiagnostic(lastDiagnosticTitle, lastDiagnosticBody, !displayChannelsSnapshot().isEmpty()); }",
        "openDiagnostics",
    )

    text = replace_once(
        text,
        "                    channels.clear(); activeSourceName = \"\"; activeSourceFile = \"\"; filter = \"\";",
        "                    synchronized (channels) { channels.clear(); previewChannels.clear(); importPreviewActive = false; }\n"
        "                    activeSourceName = \"\"; activeSourceFile = \"\"; previewSourceName = \"\"; filter = \"\"; livePage = 0;",
        "clear data preview state",
    )

    channel_page_class = r'''    private static final class ChannelPage {
        final List<Channel> items;
        final int total;
        final int start;

        ChannelPage(List<Channel> items, int total, int start) {
            this.items = items;
            this.total = total;
            this.start = start;
        }
    }

'''
    text = replace_once(
        text,
        "    private static final class Channel {\n",
        channel_page_class + "    private static final class Channel {\n",
        "ChannelPage class",
    )

    text = text.replace('text("v13.1.11"', 'text("v13.1.12"')
    text = text.replace('ProjectLumen/13.1.11 Android', 'ProjectLumen/13.1.12 Android')
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132100", "versionCode 132200", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.11-http-origin-recovery-preview'",
        "versionName '13.1.12-large-library-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.11 Preview", "Project Lumen 13.1.12 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.11", "Project Lumen 13.1.12")
        readme_text = readme_text.replace("## v13.1.11", "## v13.1.12")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "preview list before encryption": "Senderliste ist sichtbar" in text,
        "paged live list": "LIVE_PAGE_SIZE = 200" in text and "ChannelPage" in text,
        "no full-list copy per render": "visibleChannels()" not in text,
        "encryption progress": "encryptFileWithProgress" in text and "Fortschritt:" in text,
        "preview rollback": "previewChannels.clear()" in text and "importPreviewActive = false" in text,
        "version 13.1.12": 'text("v13.1.12"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.12 large-library patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
