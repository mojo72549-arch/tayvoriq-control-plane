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
        raise SystemExit("usage: apply-log-share-text-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''                .setPositiveButton("Verbinden und prüfen", (d, w) -> {
                    try {''',
        '''                .setPositiveButton("Verbinden und prüfen", (d, w) -> {
                    beginDiagnosticSession("Server + Login", null);
                    appendDiagnosticLog("UI", "Verbinden und prüfen gedrückt", "Eingabeprüfung beginnt", null);
                    try {''',
        "server login diagnostic start",
    )

    text = replace_once(
        text,
        '''                .setPositiveButton("Abrufen und prüfen", (d, w) -> {
                    try { importFromUrl(name.getText().toString(), requireHttpUrl(url.getText().toString()), "Playlist-Link"); }''',
        '''                .setPositiveButton("Abrufen und prüfen", (d, w) -> {
                    beginDiagnosticSession("Playlist-Link", null);
                    appendDiagnosticLog("UI", "Abrufen und prüfen gedrückt", "Eingabeprüfung beginnt", null);
                    try { importFromUrl(name.getText().toString(), requireHttpUrl(url.getText().toString()), "Playlist-Link"); }''',
        "playlist link diagnostic start",
    )

    share_block = r'''    private String readDiagnosticLogText() throws IOException {
        File source = diagnosticLogFile();
        if (!source.isFile() || source.length() == 0) {
            appendDiagnosticLog("INFO", "Leere Logdatei initialisiert", deviceAndNetworkSummary(), null);
        }
        try (FileInputStream in = new FileInputStream(diagnosticLogFile()); ByteArrayOutputStream buffer = new ByteArrayOutputStream()) {
            byte[] chunk = new byte[16 * 1024];
            int read;
            while ((read = in.read(chunk)) >= 0) {
                if (read > 0) buffer.write(chunk, 0, read);
            }
            return buffer.toString(StandardCharsets.UTF_8.name());
        }
    }

    private void shareDiagnosticLog() {
        appendDiagnosticLog("USER", "Logdatei angefordert", "Log-ID=" + diagnosticSessionId, null);
        new Thread(() -> {
            try {
                String logBody = readDiagnosticLogText();
                String shareBody = "Project Lumen Diagnose · Log-ID " + diagnosticSessionId
                        + "\nZugangsdaten und vollständige Adressen wurden ausgeblendet.\n\n"
                        + logBody;
                if (Build.VERSION.SDK_INT >= 29) {
                    String fileName = "Lumen_Diagnose_" + diagnosticSessionId + ".txt";
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
                        share.putExtra(Intent.EXTRA_SUBJECT, "Lumen Flow Diagnose " + diagnosticSessionId);
                        share.putExtra(Intent.EXTRA_TEXT, shareBody);
                        share.putExtra(Intent.EXTRA_STREAM, uri);
                        share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(share, "Logdatei senden"));
                    });
                } else {
                    runOnUiThread(() -> {
                        Intent share = new Intent(Intent.ACTION_SEND);
                        share.setType("text/plain");
                        share.putExtra(Intent.EXTRA_SUBJECT, "Lumen Flow Diagnose " + diagnosticSessionId);
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
        share_block,
        "shareDiagnosticLog",
    )

    text = text.replace('text("v13.1.14"', 'text("v13.1.15"')
    text = text.replace('value.append("App=").append("13.1.14")', 'value.append("App=").append("13.1.15")')
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132400", "versionCode 132500", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.14-diagnostics-log-preview'",
        "versionName '13.1.15-direct-log-share-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.14 Preview", "Project Lumen 13.1.15 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.14", "Project Lumen 13.1.15")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "server attempt starts log": 'beginDiagnosticSession("Server + Login", null);' in text,
        "playlist attempt starts log": 'beginDiagnosticSession("Playlist-Link", null);' in text,
        "full log included in share text": 'share.putExtra(Intent.EXTRA_TEXT, shareBody);' in text,
        "attached txt retained": 'share.putExtra(Intent.EXTRA_STREAM, uri);' in text,
        "download copy retained": 'MediaStore.Downloads.EXTERNAL_CONTENT_URI' in text,
        "sensitive data notice retained": 'Zugangsdaten und vollständige Adressen wurden ausgeblendet.' in text,
        "version 13.1.15": 'text("v13.1.15"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.15 direct log sharing applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
