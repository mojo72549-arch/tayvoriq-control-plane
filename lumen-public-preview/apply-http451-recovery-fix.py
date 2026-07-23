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
        raise SystemExit("usage: apply-http451-recovery-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "        boolean protocolRecoveryUsed = false;\n        long requestedResumeFrom = target.isFile() ? target.length() : 0L;\n",
        "        boolean protocolRecoveryUsed = false;\n"
        "        boolean browserCompatibilityProfile = false;\n"
        "        long requestedResumeFrom = target.isFile() ? target.length() : 0L;\n",
        "HTTP 451 recovery state",
    )

    text = replace_once(
        text,
        '''            connection.setRequestProperty("Accept", "application/x-mpegURL, application/vnd.apple.mpegurl, text/plain, */*");
            connection.setRequestProperty("Accept-Encoding", "identity");
            connection.setRequestProperty("Cache-Control", "no-cache");
            connection.setRequestProperty("Connection", "close");
            connection.setRequestProperty("User-Agent", "VLC/3.0.20 LibVLC/3.0.20");
            if (requestedResumeFrom > 0) connection.setRequestProperty("Range", "bytes=" + requestedResumeFrom + "-");
''',
        '''            connection.setRequestProperty("Accept-Encoding", "identity");
            connection.setRequestProperty("Cache-Control", "no-cache");
            connection.setRequestProperty("Connection", "close");
            if (browserCompatibilityProfile) {
                connection.setRequestProperty("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,application/x-mpegURL,application/vnd.apple.mpegurl,text/plain;q=0.8,*/*;q=0.7");
                connection.setRequestProperty("Accept-Language", "de-DE,de;q=0.9,en;q=0.8");
                connection.setRequestProperty("Pragma", "no-cache");
                connection.setRequestProperty("Upgrade-Insecure-Requests", "1");
                connection.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36");
            } else {
                connection.setRequestProperty("Accept", "application/x-mpegURL, application/vnd.apple.mpegurl, text/plain, */*");
                connection.setRequestProperty("User-Agent", "VLC/3.0.20 LibVLC/3.0.20");
            }
            if (requestedResumeFrom > 0) connection.setRequestProperty("Range", "bytes=" + requestedResumeFrom + "-");
''',
        "browser-compatible request profile",
    )

    status_marker = '''                if (status == 416 && requestedResumeFrom > 0
                        && countRecoverablePlaylistEntries(target, MIN_RECOVERABLE_PLAYLIST_ENTRIES) >= MIN_RECOVERABLE_PLAYLIST_ENTRIES) {
'''
    status_recovery = r'''                if (status == 451) {
                    String responseServer = connection.getHeaderField("Server");
                    String responseType = connection.getContentType();
                    appendDiagnosticLog(
                            "NETWORK",
                            "HTTP 451 erkannt",
                            "Anfrageprofil=" + (browserCompatibilityProfile ? "Android-Browser" : "VLC")
                                    + " · Server=" + sanitizeLogText(responseServer == null ? "unbekannt" : responseServer)
                                    + " · Content-Type=" + sanitizeLogText(responseType == null ? "unbekannt" : responseType),
                            null);
                    if (!browserCompatibilityProfile) {
                        browserCompatibilityProfile = true;
                        requestedResumeFrom = 0L;
                        runOnUiThread(() -> showDiagnostic(
                                "Serverzugriff wird kompatibel wiederholt",
                                "Code IMPORT-HTTP-451-RECOVERY\n"
                                        + "Der Server hat das bisherige Player-Anfrageprofil abgelehnt.\n"
                                        + "Lumen wiederholt den Abruf einmalig mit einem normalen Android-Browser-Profil.\n\n"
                                        + "Adresse und Zugangsdaten bleiben ausgeblendet.",
                                false));
                        continue;
                    }
                    throw new ImportFailure(
                            "IMPORT-ACCESS-DENIED",
                            "Der Server oder ein vorgeschalteter Filter verweigert den Playlist-Abruf weiterhin (HTTP 451). Die Adresse ist erreichbar, aber dieser Zugriff wird vom Anbieter oder verwendeten Netz nicht freigegeben.",
                            false);
                }

''' + status_marker
    text = replace_once(text, status_marker, status_recovery, "HTTP 451 status recovery")

    text = text.replace('text("v13.1.16"', 'text("v13.1.17"')
    text = text.replace('value.append("App=").append("13.1.16")', 'value.append("App=").append("13.1.17")')
    text = text.replace("ProjectLumen/13.1.16 Android", "ProjectLumen/13.1.17 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132600", "versionCode 132700", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.16-resilient-download-preview'",
        "versionName '13.1.17-http451-recovery-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.16 Preview", "Project Lumen 13.1.17 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.16", "Project Lumen 13.1.17")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "HTTP 451 detected": "status == 451" in text,
        "single browser compatibility retry": "IMPORT-HTTP-451-RECOVERY" in text and "browserCompatibilityProfile" in text,
        "clear final access error": "IMPORT-ACCESS-DENIED" in text,
        "no proxy or TLS bypass": "Proxy(" not in text and "HostnameVerifier" not in text,
        "version 13.1.17": 'text("v13.1.17"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.17 HTTP 451 recovery patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
