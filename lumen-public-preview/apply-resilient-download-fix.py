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
        raise SystemExit("usage: apply-resilient-download-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "    private static final int READ_TIMEOUT_MS = 180_000;\n",
        "    private static final int READ_TIMEOUT_MS = 45_000;\n"
        "    private static final long DOWNLOAD_PROGRESS_STEP_BYTES = 4L * 1024L * 1024L;\n"
        "    private static final long MIN_RECOVERABLE_PLAYLIST_BYTES = 1024L * 1024L;\n"
        "    private static final int MIN_RECOVERABLE_PLAYLIST_ENTRIES = 250;\n",
        "download resilience constants",
    )

    text = replace_once(
        text,
        "    private volatile boolean importPreviewActive;\n",
        "    private volatile boolean importPreviewActive;\n"
        "    private volatile boolean lastDownloadPartialRecovery;\n",
        "partial recovery field",
    )

    download_block = r'''    private void downloadToFile(String sourceUrl, File target) throws Exception {
        lastDownloadPartialRecovery = false;
        File bestPartial = new File(target.getParentFile(), target.getName() + ".best");
        if (target.exists()) target.delete();
        if (bestPartial.exists()) bestPartial.delete();

        ImportFailure lastFailure = null;
        for (int attempt = 1; attempt <= CONNECT_TIMEOUTS_MS.length; attempt++) {
            File attemptFile = new File(target.getParentFile(), target.getName() + ".attempt-" + attempt);
            if (attemptFile.exists()) attemptFile.delete();
            if (bestPartial.isFile() && bestPartial.length() > 0) copyFile(bestPartial, attemptFile);

            int connectTimeout = CONNECT_TIMEOUTS_MS[attempt - 1];
            int currentAttempt = attempt;
            long resumeBytes = attemptFile.isFile() ? attemptFile.length() : 0L;
            runOnUiThread(() -> showDiagnostic(
                    "Quelle wird geladen",
                    "Phase 1/4 · Verbindungsversuch " + currentAttempt + "/" + CONNECT_TIMEOUTS_MS.length
                            + "\nVerbindungsfenster: " + (connectTimeout / 1000) + " Sekunden"
                            + (resumeBytes > 0 ? "\nWiederaufnahme ab: " + humanBytes(resumeBytes) : "")
                            + "\nAdresse und Zugangsdaten sind ausgeblendet.",
                    false));
            try {
                downloadAttempt(sourceUrl, attemptFile, connectTimeout, attempt);
                replaceFile(attemptFile, target);
                if (bestPartial.exists()) bestPartial.delete();
                appendDiagnosticLog("NETWORK", "Download vollständig", "Bytes=" + target.length() + " · Versuch=" + attempt, null);
                return;
            } catch (ImportFailure failure) {
                lastFailure = failure;
                int recoverableEntries = countRecoverablePlaylistEntries(attemptFile, MIN_RECOVERABLE_PLAYLIST_ENTRIES);
                long savedBytes = attemptFile.isFile() ? attemptFile.length() : 0L;
                appendDiagnosticLog(
                        "NETWORK",
                        "Downloadversuch beendet",
                        "Code=" + failure.code + " · Versuch=" + attempt + " · Bytes=" + savedBytes
                                + " · VerwertbareEinträge=" + recoverableEntries,
                        failure);

                if (recoverableEntries >= MIN_RECOVERABLE_PLAYLIST_ENTRIES
                        && savedBytes >= MIN_RECOVERABLE_PLAYLIST_BYTES
                        && savedBytes > bestPartial.length()) {
                    replaceFile(attemptFile, bestPartial);
                    appendDiagnosticLog(
                            "RECOVERY",
                            "Bester Playlist-Teilstand gesichert",
                            "Bytes=" + bestPartial.length() + " · Einträge>=" + recoverableEntries,
                            null);
                } else if (attemptFile.exists()) {
                    attemptFile.delete();
                }

                if (!failure.retryable || attempt == CONNECT_TIMEOUTS_MS.length) break;
                int nextAttempt = attempt + 1;
                String code = failure.code;
                runOnUiThread(() -> showDiagnostic(
                        "Verbindung wird erneut versucht",
                        "Code " + code + "\n" + failure.getMessage()
                                + "\n\nAutomatischer Versuch " + nextAttempt + "/" + CONNECT_TIMEOUTS_MS.length + " folgt."
                                + (bestPartial.isFile() ? "\nDer bisher beste Teilstand bleibt erhalten." : ""),
                        false));
                try {
                    Thread.sleep(1_000L * attempt);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                    throw new ImportFailure("IMPORT-CANCELLED", "Import wurde unterbrochen.", false, interrupted);
                }
            }
        }

        int bestEntries = countRecoverablePlaylistEntries(bestPartial, MIN_RECOVERABLE_PLAYLIST_ENTRIES);
        if (bestPartial.isFile()
                && bestPartial.length() >= MIN_RECOVERABLE_PLAYLIST_BYTES
                && bestEntries >= MIN_RECOVERABLE_PLAYLIST_ENTRIES) {
            replaceFile(bestPartial, target);
            lastDownloadPartialRecovery = true;
            appendDiagnosticLog(
                    "RECOVERY",
                    "Verwertbarer Playlist-Teilstand wird verwendet",
                    "Bytes=" + target.length() + " · Einträge>=" + bestEntries
                            + " · LetzterCode=" + (lastFailure == null ? "unbekannt" : lastFailure.code),
                    lastFailure);
            runOnUiThread(() -> showDiagnostic(
                    "Senderliste wird aus Teilstand aufgebaut",
                    "Code IMPORT-PARTIAL-RECOVERY\n"
                            + "Der Server oder das Mobilfunknetz hat den Download wiederholt unterbrochen.\n"
                            + "Lumen verwirft die bereits empfangenen Daten nicht mehr und wertet den besten gültigen Teilstand aus.",
                    false));
            return;
        }

        if (lastFailure != null) throw lastFailure;
        throw new ImportFailure("IMPORT-NETWORK", "Verbindung konnte nicht hergestellt werden.", false);
    }

    private void downloadAttempt(String sourceUrl, File target, int connectTimeout, int attempt) throws Exception {
        URL original = new URL(sourceUrl);
        URL current = original;
        boolean httpOrigin = "http".equalsIgnoreCase(original.getProtocol());
        boolean protocolRecoveryUsed = false;
        long requestedResumeFrom = target.isFile() ? target.length() : 0L;

        for (int redirect = 0; redirect <= MAX_REDIRECTS + 2; redirect++) {
            HttpURLConnection connection = (HttpURLConnection) current.openConnection();
            connection.setConnectTimeout(connectTimeout);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setInstanceFollowRedirects(false);
            connection.setUseCaches(false);
            connection.setRequestProperty("Accept", "application/x-mpegURL, application/vnd.apple.mpegurl, text/plain, */*");
            connection.setRequestProperty("Accept-Encoding", "identity");
            connection.setRequestProperty("Cache-Control", "no-cache");
            connection.setRequestProperty("Connection", "close");
            connection.setRequestProperty("User-Agent", "VLC/3.0.20 LibVLC/3.0.20");
            if (requestedResumeFrom > 0) connection.setRequestProperty("Range", "bytes=" + requestedResumeFrom + "-");
            try {
                final int status;
                try {
                    status = connection.getResponseCode();
                } catch (SocketTimeoutException timeout) {
                    throw new ImportFailure(
                            "IMPORT-CONNECT-TIMEOUT",
                            "Der Server hat innerhalb von " + (connectTimeout / 1000) + " Sekunden nicht geantwortet.",
                            true, timeout);
                } catch (IOException network) {
                    URL recovery = buildHttpOriginRecoveryUrl(original, current, protocolRecoveryUsed, network);
                    if (recovery != null) {
                        protocolRecoveryUsed = true;
                        current = recovery;
                        runOnUiThread(() -> showDiagnostic(
                                "Serverprotokoll wird korrigiert",
                                "Code IMPORT-PROTOCOL-RECOVERY\n"
                                        + "Der angesprochene Nichtstandard-Port liefert kein TLS.\n"
                                        + "Lumen setzt den Abruf einmalig über HTTP fort.\n\n"
                                        + "Adresse und Zugangsdaten bleiben ausgeblendet.",
                                false));
                        continue;
                    }
                    if (isTlsPlaintextMismatch(network)) {
                        throw new ImportFailure(
                                "IMPORT-TLS-MISMATCH",
                                httpOrigin
                                        ? "Der Server liefert auf seinem HTTPS-Ziel kein TLS. Der automatische HTTP-Rückweg konnte nicht verwendet werden."
                                        : "Der HTTPS-Server liefert auf dem angesprochenen Port kein TLS.",
                                false,
                                network);
                    }
                    throw new ImportFailure("IMPORT-CONNECT", "Serververbindung fehlgeschlagen: " + compactNetworkMessage(network), true, network);
                }

                if (status >= 300 && status < 400) {
                    String location = connection.getHeaderField("Location");
                    if (location == null || location.isBlank()) {
                        throw new ImportFailure("IMPORT-REDIRECT", "Serverumleitung enthält kein Ziel.", false);
                    }
                    if (redirect >= MAX_REDIRECTS + 1) {
                        throw new ImportFailure("IMPORT-REDIRECT", "Zu viele Serverumleitungen.", false);
                    }
                    URL next = new URL(current, location);
                    URL recoveredRedirect = buildBrokenHttpsRedirectRecoveryUrl(original, next, protocolRecoveryUsed);
                    if (recoveredRedirect != null) {
                        protocolRecoveryUsed = true;
                        current = recoveredRedirect;
                        runOnUiThread(() -> showDiagnostic(
                                "Serverumleitung wird korrigiert",
                                "Code IMPORT-HTTP-REDIRECT-RECOVERY\n"
                                        + "Die HTTP-Quelle wurde auf ein nicht funktionierendes HTTPS-Ziel umgeleitet.\n"
                                        + "Lumen behält automatisch das funktionierende HTTP-Protokoll bei.\n\n"
                                        + "Adresse und Zugangsdaten bleiben ausgeblendet.",
                                false));
                        continue;
                    }
                    current = next;
                    continue;
                }

                if (status == 416 && requestedResumeFrom > 0
                        && countRecoverablePlaylistEntries(target, MIN_RECOVERABLE_PLAYLIST_ENTRIES) >= MIN_RECOVERABLE_PLAYLIST_ENTRIES) {
                    appendDiagnosticLog("RECOVERY", "Server bestätigt vorhandenen Teilstand", "HTTP=416 · Bytes=" + requestedResumeFrom, null);
                    return;
                }
                if (status == 401 || status == 403) {
                    throw new ImportFailure("IMPORT-AUTH", "Server lehnt die Anmeldung ab (HTTP " + status + ").", false);
                }
                if (status == 404) {
                    throw new ImportFailure("IMPORT-NOT-FOUND", "Playlist-Endpunkt wurde nicht gefunden (HTTP 404).", false);
                }
                if (status >= 500) {
                    throw new ImportFailure("IMPORT-SERVER", "Server ist vorübergehend nicht verfügbar (HTTP " + status + ").", true);
                }
                if (status < 200 || status >= 300) {
                    throw new ImportFailure("IMPORT-HTTP", "Server antwortet mit HTTP " + status + ".", false);
                }

                boolean append = status == 206 && requestedResumeFrom > 0;
                long responseLength = connection.getContentLengthLong();
                long expectedTotal = responseLength < 0 ? -1L : (append ? requestedResumeFrom + responseLength : responseLength);
                String transferEncoding = connection.getHeaderField("Transfer-Encoding");
                String contentType = connection.getContentType();
                appendDiagnosticLog(
                        "NETWORK",
                        "HTTP-Antwort",
                        "Status=" + status
                                + " · Wiederaufnahme=" + append
                                + " · Content-Length=" + responseLength
                                + " · Transfer-Encoding=" + sanitizeLogText(transferEncoding == null ? "keins" : transferEncoding)
                                + " · Content-Type=" + sanitizeLogText(contentType == null ? "unbekannt" : contentType),
                        null);

                try (InputStream in = connection.getInputStream(); FileOutputStream out = new FileOutputStream(target, append)) {
                    byte[] buffer = new byte[64 * 1024];
                    long total = append ? requestedResumeFrom : 0L;
                    long nextReport = total + DOWNLOAD_PROGRESS_STEP_BYTES;
                    while (true) {
                        final int read;
                        try {
                            read = in.read(buffer);
                        } catch (SocketTimeoutException timeout) {
                            out.flush();
                            out.getFD().sync();
                            if (expectedTotal > 0 && total >= expectedTotal) break;
                            throw new ImportFailure(
                                    "IMPORT-READ-TIMEOUT",
                                    "Der Server hat den begonnenen Download länger als " + (READ_TIMEOUT_MS / 1000) + " Sekunden nicht fortgesetzt.",
                                    true, timeout);
                        } catch (IOException network) {
                            out.flush();
                            out.getFD().sync();
                            if (expectedTotal > 0 && total >= expectedTotal) break;
                            throw new ImportFailure("IMPORT-DOWNLOAD", "Download wurde unterbrochen: " + compactNetworkMessage(network), true, network);
                        }
                        if (read < 0) break;
                        if (read == 0) continue;
                        total += read;
                        if (total > MAX_PLAYLIST_BYTES) {
                            throw new ImportFailure("IMPORT-SIZE", "Tatsächlich empfangene Playlist überschreitet 256 MB.", false);
                        }
                        out.write(buffer, 0, read);
                        if (total >= nextReport) {
                            long report = total;
                            nextReport = total + DOWNLOAD_PROGRESS_STEP_BYTES;
                            runOnUiThread(() -> showDiagnostic(
                                    "Quelle wird geladen",
                                    "Phase 1/4 · Download läuft\nEmpfangen: " + humanBytes(report)
                                            + "\nStillstand wird nach 45 Sekunden erkannt. Teilstände bleiben erhalten.",
                                    false));
                        }
                    }
                    out.flush();
                    out.getFD().sync();
                    if (total == 0) throw new ImportFailure("IMPORT-EMPTY", "Server hat eine leere Antwort geliefert.", false);
                } catch (ImportFailure failure) {
                    throw failure;
                } catch (IOException storageOrNetwork) {
                    throw new ImportFailure("IMPORT-DOWNLOAD", "Antwort konnte nicht vollständig gespeichert werden: " + compactNetworkMessage(storageOrNetwork), true, storageOrNetwork);
                }
                return;
            } finally {
                connection.disconnect();
            }
        }
        throw new ImportFailure("IMPORT-REDIRECT", "Zu viele Serverumleitungen.", false);
    }

    private int countRecoverablePlaylistEntries(File file, int stopAt) {
        if (file == null || !file.isFile() || file.length() < MIN_RECOVERABLE_PLAYLIST_BYTES) return 0;
        int entries = 0;
        int lines = 0;
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(new FileInputStream(file), StandardCharsets.UTF_8), 64 * 1024)) {
            String line;
            while ((line = reader.readLine()) != null && lines < 300_000 && entries < stopAt) {
                lines++;
                String normalized = line.trim().toLowerCase(Locale.ROOT);
                if (normalized.startsWith("http://")
                        || normalized.startsWith("https://")
                        || normalized.startsWith("rtsp://")
                        || normalized.startsWith("udp://")) {
                    entries++;
                }
            }
        } catch (Exception ignored) {
            return 0;
        }
        return entries;
    }

    private static void copyFile(File source, File destination) throws IOException {
        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IOException("Zielordner konnte nicht erstellt werden.");
        }
        try (FileInputStream in = new FileInputStream(source); FileOutputStream out = new FileOutputStream(destination, false)) {
            byte[] buffer = new byte[256 * 1024];
            int read;
            while ((read = in.read(buffer)) >= 0) {
                if (read > 0) out.write(buffer, 0, read);
            }
            out.flush();
            out.getFD().sync();
        }
    }

    private static void replaceFile(File source, File destination) throws IOException {
        if (destination.exists() && !destination.delete()) {
            throw new IOException("Alte temporäre Datei konnte nicht ersetzt werden.");
        }
        if (!source.renameTo(destination)) {
            copyFile(source, destination);
            if (!source.delete()) source.deleteOnExit();
        }
    }

'''

    text = replace_between(
        text,
        "    private void downloadToFile(String sourceUrl, File target) throws Exception {",
        "    private static URL buildBrokenHttpsRedirectRecoveryUrl(",
        download_block + "    private static URL buildBrokenHttpsRedirectRecoveryUrl(",
        "resilient download block",
    )

    text = replace_once(
        text,
        "        if (parsed.isEmpty()) throw new IllegalArgumentException(\"Keine unterstützten Einträge in der Playlist gefunden.\");\n",
        "        if (parsed.isEmpty()) throw new IllegalArgumentException(\"Keine unterstützten Einträge in der Playlist gefunden.\");\n"
        "        final boolean partialRecovery = lastDownloadPartialRecovery;\n"
        "        appendDiagnosticLog(\"IMPORT\", partialRecovery ? \"Playlist-Teilstand ausgewertet\" : \"Playlist vollständig ausgewertet\",\n"
        "                \"Einträge=\" + parsed.size() + \" · Bytes=\" + plain.length(), null);\n",
        "partial parse state",
    )

    text = replace_once(
        text,
        '''            showDiagnostic(
                    "Senderliste ist sichtbar",
                    "Phase 3/4 · " + parsed.size() + " Einträge wurden ausgewertet.\n"
                            + "Die Liste kann jetzt bereits geöffnet und durchsucht werden.\n\n"
                            + "Die lokale Verschlüsselung läuft weiter.",
                    true);''',
        '''            showDiagnostic(
                    partialRecovery ? "Senderliste aus Teilstand sichtbar" : "Senderliste ist sichtbar",
                    "Phase 3/4 · " + parsed.size() + " Einträge wurden ausgewertet.\n"
                            + (partialRecovery
                            ? "Code IMPORT-PARTIAL-RECOVERY\nDer Serverdownload war unvollständig; der größte gültige Teilstand wird genutzt.\n"
                            : "Die Liste kann jetzt bereits geöffnet und durchsucht werden.\n")
                            + "\nDie lokale Verschlüsselung läuft weiter.",
                    true);''',
        "partial preview diagnostic",
    )

    text = replace_once(
        text,
        '''                showDiagnostic("Senderliste bereit", "Phase 4/4 · Fertig\nCode IMPORT-OK\n" + parsed.size() + " Einträge wurden erkannt und aktiviert.\n\nDie Liste wird seitenweise angezeigt, damit auch sehr große Playlists flüssig bleiben.", true);''',
        '''                showDiagnostic(partialRecovery ? "Senderliste aus Teilstand bereit" : "Senderliste bereit",
                        "Phase 4/4 · Fertig\nCode " + (partialRecovery ? "IMPORT-PARTIAL-OK" : "IMPORT-OK")
                                + "\n" + parsed.size() + " Einträge wurden erkannt und aktiviert."
                                + (partialRecovery ? "\nDer Server hat den vollständigen Abruf nicht zuverlässig beendet; ein späterer Neuimport kann weitere Einträge ergänzen." : "")
                                + "\n\nDie Liste wird seitenweise angezeigt, damit auch sehr große Playlists flüssig bleiben.", true);''',
        "partial final diagnostic",
    )

    share_block = r'''    private String resolveSharedSessionId(String logBody) {
        String resolved = diagnosticSessionId;
        if (logBody != null) {
            for (String line : logBody.split("\\r?\\n")) {
                String[] parts = line.split("\\|", 4);
                if (parts.length < 2) continue;
                String candidate = parts[1].trim();
                if (!candidate.equalsIgnoreCase("not-started")
                        && candidate.matches("[A-Z0-9-]{6,40}")) {
                    resolved = candidate;
                }
            }
        }
        return resolved == null || resolved.isBlank() ? "unbekannt" : resolved;
    }

    private void shareDiagnosticLog() {
        appendDiagnosticLog("USER", "Logdatei angefordert", "Log-ID=" + diagnosticSessionId, null);
        new Thread(() -> {
            try {
                String logBody = readDiagnosticLogText();
                String sharedSessionId = resolveSharedSessionId(logBody);
                String shareBody = "Project Lumen Diagnose · Log-ID " + sharedSessionId
                        + "\nZugangsdaten und vollständige Adressen wurden ausgeblendet.\n\n"
                        + logBody;
                if (Build.VERSION.SDK_INT >= 29) {
                    String fileName = "Lumen_Diagnose_" + sharedSessionId + ".txt";
                    ContentValues values = new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
                    values.put(MediaStore.MediaColumns.MIME_TYPE, "text/plain");
                    values.put(MediaStore.MediaColumns.RELATIVE_PATH, "Download/Lumen Flow");
                    values.put(MediaStore.MediaColumns.IS_PENDING, 1);
                    Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
                    if (uri == null) throw new IOException("Logdatei konnte nicht im Download-Ordner erstellt werden.");
                    try (OutputStream out = getContentResolver().openOutputStream(uri, "w")) {
                        if (out == null) throw new IOException("Logdatei konnte nicht geschrieben werden.");
                        out.write(logBody.getBytes(StandardCharsets.UTF_8));
                        out.flush();
                    }
                    values.clear();
                    values.put(MediaStore.MediaColumns.IS_PENDING, 0);
                    getContentResolver().update(uri, values, null, null);
                    runOnUiThread(() -> {
                        Intent share = new Intent(Intent.ACTION_SEND);
                        share.setType("text/plain");
                        share.putExtra(Intent.EXTRA_SUBJECT, "Lumen Flow Diagnose " + sharedSessionId);
                        share.putExtra(Intent.EXTRA_TEXT, shareBody);
                        share.putExtra(Intent.EXTRA_STREAM, uri);
                        share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(share, "Logdatei senden"));
                    });
                } else {
                    runOnUiThread(() -> {
                        Intent share = new Intent(Intent.ACTION_SEND);
                        share.setType("text/plain");
                        share.putExtra(Intent.EXTRA_SUBJECT, "Lumen Flow Diagnose " + sharedSessionId);
                        share.putExtra(Intent.EXTRA_TEXT, shareBody);
                        startActivity(Intent.createChooser(share, "Diagnose senden"));
                    });
                }
            } catch (Exception failure) {
                appendDiagnosticLog("ERROR", "Logdatei konnte nicht geteilt werden", null, failure);
                runOnUiThread(() -> showDiagnostic("Logdatei nicht erstellt", "Code LOG-EXPORT\n" + safeMessage(failure), !channels.isEmpty()));
            }
        }, "lumen-log-export").start();
    }

'''

    text = replace_between(
        text,
        "    private void shareDiagnosticLog() {",
        "    private void clearDiagnosticLog() {",
        share_block + "    private void clearDiagnosticLog() {",
        "share session id recovery",
    )

    text = text.replace('text("v13.1.15"', 'text("v13.1.16"')
    text = text.replace('value.append("App=").append("13.1.15")', 'value.append("App=").append("13.1.16")')
    text = text.replace("ProjectLumen/13.1.15 Android", "ProjectLumen/13.1.16 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132500", "versionCode 132600", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.15-direct-log-share-preview'",
        "versionName '13.1.16-resilient-download-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.15 Preview", "Project Lumen 13.1.16 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.15", "Project Lumen 13.1.16")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "45 second stall detection": "READ_TIMEOUT_MS = 45_000" in text,
        "range resume": 'setRequestProperty("Range"' in text and "status == 206" in text,
        "partial file preserved": "bestPartial" in text and "IMPORT-PARTIAL-RECOVERY" in text,
        "valid partial threshold": "MIN_RECOVERABLE_PLAYLIST_ENTRIES = 250" in text,
        "progress throttled": "DOWNLOAD_PROGRESS_STEP_BYTES" in text,
        "response metadata logged": '"HTTP-Antwort"' in text,
        "shared session id recovered": "resolveSharedSessionId" in text,
        "version 13.1.16": 'text("v13.1.16"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.16 resilient download patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
