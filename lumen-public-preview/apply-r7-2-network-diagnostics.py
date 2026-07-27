#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
main = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
gradle = root / "app/build.gradle"
if not main.exists() or not gradle.exists():
    raise SystemExit("R7.2 input source missing")


def method_span(text: str, name: str) -> tuple[int, int]:
    pattern = re.compile(
        rf"(?m)^    (?:public|private|protected)\s+(?:static\s+)?[\w<>\[\], ?.]+\s+{re.escape(name)}\s*\([^;{{}}]*\)\s*\{{")
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
                state = "line"
                i += 1
            elif char == "/" and nxt == "*":
                state = "block"
                i += 1
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return match.start(), i + 1
        elif state == "string":
            if char == "\\":
                i += 1
            elif char == '"':
                state = "code"
        elif state == "char":
            if char == "\\":
                i += 1
            elif char == "'":
                state = "code"
        elif state == "line":
            if char == "\n":
                state = "code"
        elif state == "block":
            if char == "*" and nxt == "/":
                state = "code"
                i += 1
        i += 1
    raise SystemExit(f"unterminated method: {name}")


def replace_method(text: str, name: str, replacement: str) -> str:
    start, end = method_span(text, name)
    return text[:start] + replacement.strip("\n") + text[end:]


def insert_before_class_end(text: str, block: str) -> str:
    index = text.rfind("}")
    if index < 0:
        raise SystemExit("class end missing")
    return text[:index] + "\n" + block.strip("\n") + "\n" + text[index:]


g = gradle.read_text(encoding="utf-8")
g = re.sub(r"versionCode\s+\d+", "versionCode 134500", g, count=1)
g = re.sub(r"versionName\s+'[^']+'", "versionName '13.1.35-r7.2-network-diagnostics-pilot'", g, count=1)
gradle.write_text(g, encoding="utf-8")

s = main.read_text(encoding="utf-8")
if "import java.net.UnknownHostException;" not in s:
    s = s.replace("import java.net.SocketTimeoutException;", "import java.net.SocketTimeoutException;\nimport java.net.UnknownHostException;", 1)

if "diagnosticSensitiveHost" not in s:
    marker = '    private String diagnosticSessionId = "not-started";\n'
    if marker not in s:
        raise SystemExit("diagnostic session field marker missing")
    s = s.replace(marker, marker + '    private volatile String diagnosticSensitiveHost = "";\n', 1)

s = s.replace('text("13.1.34"', 'text("13.1.35"')
s = s.replace('Project Lumen 13.1.34 · R7.1 Responsive Typography',
              'Project Lumen 13.1.35 · R7.2 Netzwerk & Diagnose')
s = s.replace(
    '"\\nVerbindungsfenster: " + (connectTimeout / 1000) + " Sekunden"',
    '"\\nVerbindung: " + (connectTimeout / 1000) + " s · Antwort: " + (READ_TIMEOUT_MS / 1000) + " s"')
s = s.replace('"Code " + code + "\\n" + failure.getMessage()',
              '"Code " + code + "\\n" + sanitizeDiagnosticText(failure.getMessage())')

old_connect = '''                } catch (IOException network) {
                    URL recovery = buildHttpOriginRecoveryUrl(original, current, protocolRecoveryUsed, network);'''
new_connect = '''                } catch (IOException network) {
                    if (hasCause(network, UnknownHostException.class)) {
                        throw new ImportFailure(
                                "IMPORT-DNS",
                                "Der Servername konnte über das aktuelle Netzwerk nicht aufgelöst werden. Die gespeicherte Bibliothek bleibt unverändert.",
                                attempt < 2,
                                network);
                    }
                    if (!hasUsableNetwork()) {
                        throw new ImportFailure(
                                "IMPORT-OFFLINE",
                                "Das Gerät hat aktuell keine nutzbare Internetverbindung. Die gespeicherte Bibliothek bleibt unverändert.",
                                false,
                                network);
                    }
                    URL recovery = buildHttpOriginRecoveryUrl(original, current, protocolRecoveryUsed, network);'''
if old_connect not in s:
    raise SystemExit("connect IOException marker missing")
s = s.replace(old_connect, new_connect, 1)
s = s.replace(
    'throw new ImportFailure("IMPORT-CONNECT", "Serververbindung fehlgeschlagen: " + compactNetworkMessage(network), true, network);',
    'throw new ImportFailure("IMPORT-CONNECT", "Die Serververbindung konnte nicht hergestellt werden. Die gespeicherte Bibliothek bleibt unverändert.", true, network);',
    1)
s = s.replace(
    '"Der Server hat innerhalb von " + (connectTimeout / 1000) + " Sekunden nicht geantwortet."',
    '"Der Server hat beim Verbindungsaufbau oder beim Lesen der Antwort nicht rechtzeitig reagiert."',
    1)
s = s.replace('''            return "Schema=" + scheme
                    + " · Port=" + port
                    + " · Port=" + port
                    + " · Host-ID=" + shortHostHash(uri.getHost())''', '''            return "Schema=" + scheme
                    + " · Port=" + port
                    + " · Host-ID=" + shortHostHash(uri.getHost())''', 1)

s = replace_method(s, "beginDiagnosticSession", r'''
    private void beginDiagnosticSession(String origin, String sourceUrl) {
        diagnosticSensitiveHost = "";
        if (sourceUrl != null && !sourceUrl.isBlank()) {
            try {
                URI uri = new URI(sourceUrl);
                diagnosticSensitiveHost = uri.getHost() == null ? "" : uri.getHost();
            } catch (Exception ignored) {}
        }
        synchronized (diagnosticLogLock) {
            diagnosticSessionId = Long.toString(System.currentTimeMillis(), 36).toUpperCase(Locale.ROOT);
            File file = diagnosticLogFile();
            try (FileOutputStream ignored = new FileOutputStream(file, false)) {
                // Neue Import-Sitzung: alte Daten werden bewusst ersetzt.
            } catch (Exception ignored) {}
        }
        appendDiagnosticLog("SESSION", "Neue Diagnose-Sitzung", "Log-ID=" + diagnosticSessionId
                + " · Quelle=" + sanitizeDiagnosticText(origin)
                + " · " + describeEndpoint(sourceUrl)
                + " · " + deviceAndNetworkSummary(), null);
    }
''')

s = replace_method(s, "appendDiagnosticLog", r'''
    private void appendDiagnosticLog(String level, String event, String details, Throwable failure) {
        synchronized (diagnosticLogLock) {
            try {
                File file = diagnosticLogFile();
                if (file.length() > MAX_DIAGNOSTIC_LOG_BYTES) {
                    try (FileOutputStream ignored = new FileOutputStream(file, false)) {
                        // Begrenzung verhindert unbegrenzt wachsende Diagnosedateien.
                    }
                }
                StringBuilder entry = new StringBuilder();
                entry.append(OffsetDateTime.now()).append(" | ")
                        .append(diagnosticSessionId).append(" | ")
                        .append(sanitizeDiagnosticText(level)).append(" | ")
                        .append(sanitizeDiagnosticText(event));
                if (details != null && !details.isBlank()) {
                    entry.append(" | ").append(sanitizeDiagnosticText(details).replace('\n', ' '));
                }
                entry.append('\n');
                if (failure != null) entry.append(compactThrowableForLog(failure));
                try (FileOutputStream out = new FileOutputStream(file, true)) {
                    out.write(entry.toString().getBytes(StandardCharsets.UTF_8));
                    out.flush();
                }
            } catch (Exception ignored) {
                // Logging darf den eigentlichen Import niemals blockieren.
            }
        }
    }
''')

s = replace_method(s, "deviceAndNetworkSummary", r'''
    private String deviceAndNetworkSummary() {
        StringBuilder value = new StringBuilder();
        value.append("App=").append(appVersionName())
                .append(" · Android=").append(Build.VERSION.SDK_INT)
                .append(" · Gerät=").append(sanitizeDiagnosticText(Build.MANUFACTURER + " " + Build.MODEL));
        try {
            ConnectivityManager manager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            Network network = manager == null ? null : manager.getActiveNetwork();
            NetworkCapabilities capabilities = manager == null || network == null ? null : manager.getNetworkCapabilities(network);
            value.append(" · Netz=");
            if (capabilities == null) value.append("nicht erkannt");
            else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) value.append("WLAN");
            else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR)) value.append("Mobilfunk");
            else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)) value.append("Ethernet");
            else if (capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) value.append("VPN");
            else value.append("sonstiges");
            if (capabilities != null) {
                value.append(" · Internet=").append(capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET));
                if (Build.VERSION.SDK_INT >= 23) {
                    value.append(" · validiert=").append(capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED));
                }
            }
            if (manager != null) value.append(" · getaktet=").append(manager.isActiveNetworkMetered());
        } catch (Exception ignored) {
            value.append(" · Netz=unbekannt");
        }
        return value.toString();
    }
''')

s = replace_method(s, "shareDiagnosticLog", r'''
    private void shareDiagnosticLog() {
        appendDiagnosticLog("USER", "Logdatei angefordert", "Log-ID=" + diagnosticSessionId, null);
        new Thread(() -> {
            try {
                String logBody = readDiagnosticLogText();
                String sharedSessionId = resolveSharedSessionId(logBody);
                String shareBody = "Project Lumen Diagnose · Log-ID " + sharedSessionId
                        + "\nZugangsdaten, vollständige Adressen und Servernamen wurden ausgeblendet.\n\n"
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
                        out.write(shareBody.getBytes(StandardCharsets.UTF_8));
                        out.flush();
                    }
                    values.clear();
                    values.put(MediaStore.MediaColumns.IS_PENDING, 0);
                    getContentResolver().update(uri, values, null, null);
                    runOnUiThread(() -> {
                        Intent share = new Intent(Intent.ACTION_SEND);
                        share.setType("text/plain");
                        share.putExtra(Intent.EXTRA_SUBJECT, "Project Lumen Diagnose " + sharedSessionId);
                        share.putExtra(Intent.EXTRA_TEXT,
                                "Project Lumen Diagnose · Log-ID " + sharedSessionId + "\nDie bereinigte Logdatei ist angehängt.");
                        share.putExtra(Intent.EXTRA_STREAM, uri);
                        share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(share, "Logdatei senden"));
                    });
                } else {
                    runOnUiThread(() -> {
                        Intent share = new Intent(Intent.ACTION_SEND);
                        share.setType("text/plain");
                        share.putExtra(Intent.EXTRA_SUBJECT, "Project Lumen Diagnose " + sharedSessionId);
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
''')

s = replace_method(s, "compactNetworkMessage", r'''
    private static String compactNetworkMessage(Exception e) {
        if (hasCause(e, UnknownHostException.class)) return "DNS-Auflösung fehlgeschlagen";
        if (hasCause(e, SocketTimeoutException.class)) return "Zeitüberschreitung";
        return e == null ? "Netzwerkfehler" : e.getClass().getSimpleName();
    }
''')

helpers = r'''
    private String appVersionName() {
        try {
            android.content.pm.PackageInfo info = getPackageManager().getPackageInfo(getPackageName(), 0);
            String value = info.versionName;
            return value == null || value.isBlank() ? "unbekannt" : value;
        } catch (Exception ignored) {
            return "unbekannt";
        }
    }

    private boolean hasUsableNetwork() {
        try {
            ConnectivityManager manager = (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            Network network = manager == null ? null : manager.getActiveNetwork();
            NetworkCapabilities capabilities = manager == null || network == null ? null : manager.getNetworkCapabilities(network);
            return capabilities != null && capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET);
        } catch (Exception ignored) {
            return true;
        }
    }

    private static boolean hasCause(Throwable failure, Class<?> type) {
        Throwable current = failure;
        for (int depth = 0; current != null && depth < 12; depth++, current = current.getCause()) {
            if (type.isInstance(current)) return true;
        }
        return false;
    }

    private String sanitizeDiagnosticText(String value) {
        String cleaned = sanitizeLogText(value);
        String host = diagnosticSensitiveHost;
        if (host != null && !host.isBlank()) {
            cleaned = cleaned.replace(host, "[HOST AUSGEBLENDET]")
                    .replace(host.toLowerCase(Locale.ROOT), "[HOST AUSGEBLENDET]")
                    .replace(host.toUpperCase(Locale.ROOT), "[HOST AUSGEBLENDET]");
        }
        return cleaned;
    }

    private String compactThrowableForLog(Throwable failure) {
        StringBuilder out = new StringBuilder();
        Throwable current = failure;
        for (int causeDepth = 0; current != null && causeDepth < 4; causeDepth++, current = current.getCause()) {
            if (causeDepth > 0) out.append("Caused by: ");
            out.append(current.getClass().getName());
            String message = current.getMessage();
            if (message != null && !message.isBlank()) out.append(": ").append(sanitizeDiagnosticText(message));
            out.append('\n');
            StackTraceElement[] frames = current.getStackTrace();
            int max = Math.min(frames == null ? 0 : frames.length, 10);
            for (int index = 0; index < max; index++) {
                out.append("  at ").append(sanitizeDiagnosticText(String.valueOf(frames[index]))).append('\n');
            }
            if (frames != null && frames.length > max) out.append("  … ").append(frames.length - max).append(" weitere Frames\n");
        }
        return out.toString();
    }
'''
if "private String appVersionName()" not in s:
    s = insert_before_class_end(s, helpers)

main.write_text(s, encoding="utf-8")

checks = {
    "version": "versionCode 134500" in g,
    "dns_code": '"IMPORT-DNS"' in s,
    "dns_retry_limit": "attempt < 2" in s,
    "offline_code": '"IMPORT-OFFLINE"' in s,
    "version_runtime": 'append("App=").append(appVersionName())' in s,
    "host_redaction": "diagnosticSensitiveHost" in s and "[HOST AUSGEBLENDET]" in s,
    "compact_trace": "compactThrowableForLog" in s,
    "share_attachment": "Die bereinigte Logdatei ist angehängt." in s,
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("R7.2 integration checks failed: " + ", ".join(missing))
print("R7.2 network and diagnostic hotfix applied: " + ", ".join(checks))
