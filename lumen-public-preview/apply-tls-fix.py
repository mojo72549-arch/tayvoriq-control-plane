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
        raise SystemExit("usage: apply_tls_fix.py <project-root>")

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
        boolean recoverableHttpToHttpsRedirectSeen = false;
        boolean tlsRecoveryUsed = false;

        for (int redirect = 0; redirect <= MAX_REDIRECTS; redirect++) {
            HttpURLConnection connection = (HttpURLConnection) current.openConnection();
            connection.setConnectTimeout(connectTimeout);
            connection.setReadTimeout(READ_TIMEOUT_MS);
            connection.setInstanceFollowRedirects(false);
            connection.setUseCaches(false);
            connection.setRequestProperty("Accept", "*/*");
            connection.setRequestProperty("Accept-Encoding", "identity");
            connection.setRequestProperty("Cache-Control", "no-cache");
            connection.setRequestProperty("Connection", "close");
            connection.setRequestProperty("User-Agent", attempt == 1
                    ? "ProjectLumen/13.1.10 Android"
                    : "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/126 Mobile Safari/537.36");
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
                    URL recovery = buildTlsMismatchRecoveryUrl(
                            original,
                            current,
                            recoverableHttpToHttpsRedirectSeen,
                            tlsRecoveryUsed,
                            network);
                    if (recovery != null) {
                        tlsRecoveryUsed = true;
                        current = recovery;
                        runOnUiThread(() -> showDiagnostic(
                                "Serverprotokoll wird korrigiert",
                                "Code IMPORT-TLS-RECOVERY\n"
                                        + "Der Server hat HTTPS angekündigt, liefert auf diesem Port aber unverschlüsseltes HTTP.\n"
                                        + "Lumen verwendet einmalig wieder die ursprünglich eingegebene HTTP-Verbindung.\n\n"
                                        + "Adresse und Zugangsdaten bleiben ausgeblendet.",
                                false));
                        continue;
                    }
                    if (isTlsPlaintextMismatch(network)) {
                        throw new ImportFailure(
                                "IMPORT-TLS-MISMATCH",
                                "Der Server meldet HTTPS, liefert auf dem angesprochenen Port jedoch kein TLS. Bitte die ursprüngliche HTTP-Adresse verwenden.",
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
                    if (redirect == MAX_REDIRECTS) {
                        throw new ImportFailure("IMPORT-REDIRECT", "Zu viele Serverumleitungen.", false);
                    }
                    URL next = new URL(current, location);
                    if (isRecoverableHttpToHttpsRedirect(original, current, next)) {
                        recoverableHttpToHttpsRedirectSeen = true;
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

    private static boolean isRecoverableHttpToHttpsRedirect(URL original, URL from, URL to) {
        if (!"http".equalsIgnoreCase(original.getProtocol())) return false;
        if (!"http".equalsIgnoreCase(from.getProtocol())) return false;
        if (!"https".equalsIgnoreCase(to.getProtocol())) return false;
        if (!sameHost(original, from) || !sameHost(original, to)) return false;

        int originalPort = effectivePort(original);
        int targetPort = effectivePort(to);
        return originalPort > 0
                && targetPort == originalPort
                && targetPort != 443
                && to.getPort() != -1;
    }

    private static URL buildTlsMismatchRecoveryUrl(
            URL original,
            URL current,
            boolean recoverableRedirectSeen,
            boolean recoveryAlreadyUsed,
            IOException failure) throws Exception {
        if (!recoverableRedirectSeen || recoveryAlreadyUsed || !isTlsPlaintextMismatch(failure)) return null;
        if (!"http".equalsIgnoreCase(original.getProtocol())) return null;
        if (!"https".equalsIgnoreCase(current.getProtocol())) return null;
        if (!sameHost(original, current)) return null;

        int originalPort = effectivePort(original);
        int currentPort = effectivePort(current);
        if (originalPort <= 0 || currentPort != originalPort || currentPort == 443 || current.getPort() == -1) return null;

        URI uri = current.toURI();
        return new URI(
                "http",
                uri.getUserInfo(),
                uri.getHost(),
                uri.getPort(),
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

    private static int effectivePort(URL url) {
        return url.getPort() == -1 ? url.getDefaultPort() : url.getPort();
    }

'''

    text = text[:start] + replacement + text[end:]
    text = text.replace('text("v13.1.9"', 'text("v13.1.10"')
    text = text.replace('ProjectLumen/13.1.9 Android', 'ProjectLumen/13.1.10 Android')
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 131900", "versionCode 132000", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.9-network-recovery-preview'",
        "versionName '13.1.10-tls-transport-recovery-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.8 Preview", "Project Lumen 13.1.10 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.9", "Project Lumen 13.1.10")
        readme_text = readme_text.replace("## v13.1.9", "## v13.1.10")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "IMPORT-TLS-RECOVERY": "IMPORT-TLS-RECOVERY" in text,
        "IMPORT-TLS-MISMATCH": "IMPORT-TLS-MISMATCH" in text,
        "version 13.1.10": 'text("v13.1.10"' in text,
        "safe port guard": "currentPort == 443" in text,
        "single recovery guard": "recoveryAlreadyUsed" in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.10 TLS transport patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
