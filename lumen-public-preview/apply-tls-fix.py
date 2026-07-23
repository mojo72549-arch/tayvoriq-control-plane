#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply_tls_fix_v11.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")
    start = text.index("    private void downloadAttempt(String sourceUrl, File target, int connectTimeout, int attempt) throws Exception {")
    end = text.index("    private void parseAndActivate(String name, File plain, String origin) throws Exception {", start)

    replacement = r'''    private void downloadAttempt(String sourceUrl, File target, int connectTimeout, int attempt) throws Exception {
        URL original = new URL(sourceUrl);
        URL current = original;
        boolean httpOrigin = "http".equalsIgnoreCase(original.getProtocol());
        boolean protocolRecoveryUsed = false;

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
                                "Code IMPORT-HTTP-RECOVERY\n"
                                        + "Die Quelle wurde ausdrücklich mit HTTP eingegeben. Der Server hat zwischendurch fälschlich HTTPS verwendet.\n"
                                        + "Lumen setzt den Abruf automatisch über HTTP fort.\n\n"
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

                try (InputStream in = connection.getInputStream(); FileOutputStream out = new FileOutputStream(target)) {
                    byte[] buffer = new byte[64 * 1024];
                    long total = 0;
                    long nextReport = 256 * 1024;
                    while (true) {
                        final int read;
                        try {
                            read = in.read(buffer);
                        } catch (SocketTimeoutException timeout) {
                            throw new ImportFailure(
                                    "IMPORT-READ-TIMEOUT",
                                    "Der Server hat den begonnenen Download länger als " + (READ_TIMEOUT_MS / 1000) + " Sekunden nicht fortgesetzt.",
                                    true, timeout);
                        } catch (IOException network) {
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
                            nextReport = total + 256 * 1024;
                            runOnUiThread(() -> showDiagnostic(
                                    "Quelle wird geladen",
                                    "Phase 1/4 · Download läuft\nEmpfangen: " + humanBytes(report)
                                            + "\nVerbindung bleibt bis zu 180 Sekunden ohne neue Daten offen.",
                                    false));
                        }
                    }
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

    private static URL buildBrokenHttpsRedirectRecoveryUrl(
            URL original,
            URL redirected,
            boolean recoveryAlreadyUsed) throws Exception {
        if (recoveryAlreadyUsed) return null;
        if (!"http".equalsIgnoreCase(original.getProtocol())) return null;
        if (!"https".equalsIgnoreCase(redirected.getProtocol())) return null;

        int recoveryPort = redirected.getPort();
        if (recoveryPort == -1 && sameHost(original, redirected) && original.getPort() != -1) {
            recoveryPort = original.getPort();
        }
        if (recoveryPort <= 0 || recoveryPort == 443) return null;

        return withHttpScheme(redirected, recoveryPort);
    }

    private static URL buildHttpOriginRecoveryUrl(
            URL original,
            URL current,
            boolean recoveryAlreadyUsed,
            IOException failure) throws Exception {
        if (recoveryAlreadyUsed || !isTlsPlaintextMismatch(failure)) return null;
        if (!"http".equalsIgnoreCase(original.getProtocol())) return null;
        if (!"https".equalsIgnoreCase(current.getProtocol())) return null;

        int recoveryPort = current.getPort();
        if (recoveryPort == -1 && sameHost(original, current) && original.getPort() != -1) {
            recoveryPort = original.getPort();
        }
        if (recoveryPort <= 0 || recoveryPort == 443) return null;

        return withHttpScheme(current, recoveryPort);
    }

    private static URL withHttpScheme(URL source, int port) throws Exception {
        URI uri = source.toURI();
        return new URI(
                "http",
                uri.getUserInfo(),
                uri.getHost(),
                port,
                uri.getPath(),
                uri.getQuery(),
                uri.getFragment()).toURL();
    }

    private static boolean isTlsPlaintextMismatch(Throwable failure) {
        Throwable current = failure;
        for (int depth = 0; current != null && depth < 8; depth++, current = current.getCause()) {
            String message = current.getMessage();
            String normalized = message == null ? "" : message.toLowerCase(Locale.ROOT);
            if (normalized.contains("unable to parse tls packet header")
                    || normalized.contains("not an ssl/tls record")
                    || normalized.contains("unrecognized ssl message")
                    || normalized.contains("plaintext connection")
                    || normalized.contains("wrong version number")) {
                return true;
            }
        }
        return false;
    }

    private static boolean sameHost(URL left, URL right) {
        return left.getHost() != null
                && right.getHost() != null
                && left.getHost().equalsIgnoreCase(right.getHost());
    }

'''

    text = text[:start] + replacement + text[end:]
    text = text.replace('text("v13.1.9"', 'text("v13.1.11"')
    text = text.replace('ProjectLumen/13.1.9 Android', 'ProjectLumen/13.1.11 Android')
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 131900", "versionCode 132100", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.9-network-recovery-preview'",
        "versionName '13.1.11-http-origin-recovery-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.8 Preview", "Project Lumen 13.1.11 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.9", "Project Lumen 13.1.11")
        readme_text = readme_text.replace("## v13.1.9", "## v13.1.11")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "HTTP redirect recovery": "IMPORT-HTTP-REDIRECT-RECOVERY" in text,
        "HTTP TLS recovery": "IMPORT-HTTP-RECOVERY" in text,
        "VLC media user-agent": 'VLC/3.0.20 LibVLC/3.0.20' in text,
        "direct HTTPS protected": '!\"http\".equalsIgnoreCase(original.getProtocol())' in text,
        "port 443 protected": "recoveryPort == 443" in text,
        "version 13.1.11": 'text("v13.1.11"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.11 HTTP origin recovery patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
