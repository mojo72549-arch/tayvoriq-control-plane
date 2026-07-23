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
        raise SystemExit("usage: apply-xtream-source-api-recovery-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import android.widget.VideoView;\n",
        "import android.widget.VideoView;\n"
        "import android.util.JsonReader;\n"
        "import android.util.JsonToken;\n",
        "Android JSON imports",
    )
    text = replace_once(
        text,
        "import java.io.BufferedReader;\n",
        "import java.io.BufferedReader;\n"
        "import java.io.BufferedWriter;\n",
        "buffered writer import",
    )
    text = replace_once(
        text,
        "import java.io.OutputStream;\n",
        "import java.io.OutputStream;\n"
        "import java.io.OutputStreamWriter;\n",
        "output stream writer import",
    )
    text = replace_once(
        text,
        "import java.net.URL;\n",
        "import java.net.URL;\n"
        "import java.net.URLDecoder;\n",
        "URL decoder import",
    )
    text = replace_once(
        text,
        "import java.util.Collections;\n",
        "import java.util.Collections;\n"
        "import java.util.HashMap;\n",
        "hash map import",
    )
    text = replace_once(
        text,
        "import java.util.Locale;\n",
        "import java.util.Locale;\n"
        "import java.util.Map;\n",
        "map import",
    )

    denied_marker = '''                    throw new ImportFailure(
                            "IMPORT-ACCESS-DENIED",
                            "Der Server oder ein vorgeschalteter Filter verweigert den Playlist-Abruf weiterhin (HTTP 451). Die Adresse ist erreichbar, aber dieser Zugriff wird vom Anbieter oder verwendeten Netz nicht freigegeben.",
                            false);
'''
    denied_replacement = '''                    connection.disconnect();
                    if (tryXtreamSourceApiRecovery(original, current, target, connectTimeout)) {
                        return;
                    }
                    throw new ImportFailure(
                            "IMPORT-ACCESS-DENIED",
                            "Der Server oder ein vorgeschalteter Filter verweigert sowohl den Playlist-Abruf als auch den neutralen Source-API-Abruf (HTTP 451). Die Adresse ist erreichbar, aber dieser Zugriff wird vom Anbieter oder verwendeten Netz nicht freigegeben.",
                            false);
'''
    text = replace_once(text, denied_marker, denied_replacement, "HTTP 451 Source API recovery hook")

    helper_block = r'''    private boolean tryXtreamSourceApiRecovery(URL original, URL active, File target, int connectTimeout) {
        XtreamCredentials credentials = extractXtreamCredentials(original);
        if (credentials == null || !isXtreamGetEndpoint(original)) return false;

        runOnUiThread(() -> showDiagnostic(
                "Alternativer Serverzugang wird geprüft",
                "Code IMPORT-XTREAM-API-RECOVERY\n"
                        + "Der direkte M3U-Abruf wird vom CDN-Proxy blockiert.\n"
                        + "Lumen prüft nun den neutralen Source-API-Endpunkt desselben Servers mit denselben Zugangsdaten.\n\n"
                        + "Es wird kein Proxy und kein fremder Server verwendet.",
                false));
        appendDiagnosticLog(
                "RECOVERY",
                "Xtream Source API wird geprüft",
                "Schema=" + active.getProtocol() + " · Port=" + effectivePort(active) + " · Host-ID=" + hashHost(active.getHost()),
                null);

        try {
            Map<String, String> categories = fetchXtreamLiveCategories(active, credentials, connectTimeout);
            int imported = downloadXtreamLiveStreams(active, credentials, categories, target, connectTimeout);
            if (imported <= 0) {
                if (target.exists()) target.delete();
                appendDiagnosticLog("RECOVERY", "Xtream Source API ohne Sender", "Einträge=0", null);
                return false;
            }
            appendDiagnosticLog(
                    "RECOVERY",
                    "Xtream Source API erfolgreich",
                    "Einträge=" + imported + " · Kategorien=" + categories.size() + " · Bytes=" + target.length(),
                    null);
            runOnUiThread(() -> showDiagnostic(
                    "Senderdaten über Source API empfangen",
                    "Code IMPORT-XTREAM-API-OK\n"
                            + imported + " Live-Einträge wurden über den alternativen Endpunkt desselben Servers aufgebaut.\n"
                            + "Die lokale Playlist-Prüfung wird fortgesetzt.",
                    false));
            return true;
        } catch (Exception failure) {
            if (target.exists()) target.delete();
            appendDiagnosticLog(
                    "RECOVERY",
                    "Xtream Source API nicht nutzbar",
                    "Fehler=" + sanitizeLogText(compactNetworkMessage(failure)),
                    failure);
            return false;
        }
    }

    private Map<String, String> fetchXtreamLiveCategories(
            URL active,
            XtreamCredentials credentials,
            int connectTimeout) throws Exception {
        Map<String, String> categories = new HashMap<>();
        URL endpoint = buildXtreamApiUrl(active, credentials, "get_live_categories");
        HttpURLConnection connection = openSourceApiConnection(endpoint, connectTimeout);
        try {
            int status = connection.getResponseCode();
            appendDiagnosticLog(
                    "NETWORK",
                    "Source API Kategorien Antwort",
                    "HTTP=" + status + " · Content-Type=" + sanitizeLogText(valueOrUnknown(connection.getContentType())),
                    null);
            if (status < 200 || status >= 300) return categories;
            try (JsonReader reader = new JsonReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                reader.setLenient(true);
                if (reader.peek() != JsonToken.BEGIN_ARRAY) return categories;
                reader.beginArray();
                while (reader.hasNext() && categories.size() < 10_000) {
                    if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                        reader.skipValue();
                        continue;
                    }
                    String id = "";
                    String name = "";
                    reader.beginObject();
                    while (reader.hasNext()) {
                        String key = reader.nextName();
                        if ("category_id".equals(key)) id = readJsonScalar(reader);
                        else if ("category_name".equals(key)) name = readJsonScalar(reader);
                        else reader.skipValue();
                    }
                    reader.endObject();
                    if (!id.isBlank() && !name.isBlank()) categories.put(id, cleanM3uText(name, "Live TV"));
                }
                reader.endArray();
            }
            return categories;
        } finally {
            connection.disconnect();
        }
    }

    private int downloadXtreamLiveStreams(
            URL active,
            XtreamCredentials credentials,
            Map<String, String> categories,
            File target,
            int connectTimeout) throws Exception {
        URL endpoint = buildXtreamApiUrl(active, credentials, "get_live_streams");
        HttpURLConnection connection = openSourceApiConnection(endpoint, connectTimeout);
        try {
            int status = connection.getResponseCode();
            appendDiagnosticLog(
                    "NETWORK",
                    "Source API Sender Antwort",
                    "HTTP=" + status + " · Content-Type=" + sanitizeLogText(valueOrUnknown(connection.getContentType())),
                    null);
            if (status == 401 || status == 403) {
                throw new ImportFailure("IMPORT-AUTH", "Source API lehnt die Anmeldung ab (HTTP " + status + ").", false);
            }
            if (status == 451) {
                throw new ImportFailure("IMPORT-ACCESS-DENIED", "Auch der Source-API-Endpunkt wird vom CDN-Proxy mit HTTP 451 blockiert.", false);
            }
            if (status < 200 || status >= 300) {
                throw new ImportFailure("IMPORT-XTREAM-API", "Source API antwortet mit HTTP " + status + ".", status >= 500);
            }

            int imported = 0;
            FileOutputStream output = new FileOutputStream(target, false);
            try (FileOutputStream managedOutput = output;
                 BufferedWriter writer = new BufferedWriter(new OutputStreamWriter(managedOutput, StandardCharsets.UTF_8), 128 * 1024);
                 JsonReader reader = new JsonReader(new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                reader.setLenient(true);
                writer.write("#EXTM3U\n");
                if (reader.peek() != JsonToken.BEGIN_ARRAY) return 0;
                reader.beginArray();
                while (reader.hasNext() && imported < MAX_CHANNELS) {
                    if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                        reader.skipValue();
                        continue;
                    }
                    String name = "";
                    String streamId = "";
                    String categoryId = "";
                    String extension = "ts";
                    String directSource = "";
                    reader.beginObject();
                    while (reader.hasNext()) {
                        String key = reader.nextName();
                        if ("name".equals(key)) name = readJsonScalar(reader);
                        else if ("stream_id".equals(key)) streamId = readJsonScalar(reader);
                        else if ("category_id".equals(key)) categoryId = readJsonScalar(reader);
                        else if ("container_extension".equals(key)) extension = readJsonScalar(reader);
                        else if ("direct_source".equals(key)) directSource = readJsonScalar(reader);
                        else reader.skipValue();
                    }
                    reader.endObject();
                    if (streamId.isBlank() && !isSupportedRemoteUrl(directSource)) continue;

                    String channelName = cleanM3uText(name, "Unbenannter Sender " + (imported + 1));
                    String group = categories.getOrDefault(categoryId, "Live TV");
                    String streamUrl = isSupportedRemoteUrl(directSource)
                            ? directSource.trim()
                            : buildXtreamLiveStreamUrl(active, credentials, streamId, extension);
                    writer.write("#EXTINF:-1 group-title=\"");
                    writer.write(cleanM3uText(group, "Live TV"));
                    writer.write("\",");
                    writer.write(channelName);
                    writer.write('\n');
                    writer.write(streamUrl);
                    writer.write('\n');
                    imported++;
                    if (imported % 5_000 == 0) {
                        int progress = imported;
                        runOnUiThread(() -> showDiagnostic(
                                "Source API wird ausgewertet",
                                "Code IMPORT-XTREAM-API-RECOVERY\n"
                                        + progress + " Live-Einträge wurden aufgebaut.\n"
                                        + "Zugangsdaten und vollständige Adressen bleiben ausgeblendet.",
                                false));
                    }
                }
                reader.endArray();
                writer.flush();
                managedOutput.getFD().sync();
            }
            if (target.length() > MAX_PLAYLIST_BYTES) {
                throw new ImportFailure("IMPORT-SIZE", "Die über Source API erzeugte Playlist überschreitet 256 MB.", false);
            }
            return imported;
        } finally {
            connection.disconnect();
        }
    }

    private HttpURLConnection openSourceApiConnection(URL endpoint, int connectTimeout) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) endpoint.openConnection();
        connection.setConnectTimeout(connectTimeout);
        connection.setReadTimeout(READ_TIMEOUT_MS);
        connection.setInstanceFollowRedirects(false);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json,text/plain,*/*");
        connection.setRequestProperty("Accept-Encoding", "identity");
        connection.setRequestProperty("Cache-Control", "no-cache");
        connection.setRequestProperty("Connection", "close");
        connection.setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android 13; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36");
        return connection;
    }

    private static XtreamCredentials extractXtreamCredentials(URL source) {
        try {
            String username = queryParameter(source, "username");
            if (username.isBlank()) username = queryParameter(source, "user");
            String password = queryParameter(source, "password");
            if (password.isBlank()) password = queryParameter(source, "pass");
            if (username.isBlank() || password.isBlank()) return null;
            return new XtreamCredentials(username, password);
        } catch (Exception ignored) {
            return null;
        }
    }

    private static String queryParameter(URL source, String requestedKey) throws Exception {
        String query = source.getQuery();
        if (query == null || query.isBlank()) return "";
        for (String part : query.split("&")) {
            int equals = part.indexOf('=');
            String rawKey = equals < 0 ? part : part.substring(0, equals);
            if (!requestedKey.equalsIgnoreCase(URLDecoder.decode(rawKey, StandardCharsets.UTF_8.name()))) continue;
            String rawValue = equals < 0 ? "" : part.substring(equals + 1);
            return URLDecoder.decode(rawValue, StandardCharsets.UTF_8.name());
        }
        return "";
    }

    private static boolean isXtreamGetEndpoint(URL source) {
        String path = source.getPath();
        if (path == null) return false;
        String normalized = path.toLowerCase(Locale.ROOT);
        return normalized.endsWith("/get.php") || normalized.equals("get.php");
    }

    private static URL buildXtreamApiUrl(URL active, XtreamCredentials credentials, String action) throws Exception {
        String parent = endpointParentPath(active);
        String query = "username=" + URLEncoder.encode(credentials.username, StandardCharsets.UTF_8.name())
                + "&password=" + URLEncoder.encode(credentials.password, StandardCharsets.UTF_8.name())
                + "&action=" + URLEncoder.encode(action, StandardCharsets.UTF_8.name());
        return new URL(active.getProtocol() + "://" + active.getAuthority() + parent + "player_api.php?" + query);
    }

    private static String buildXtreamLiveStreamUrl(
            URL active,
            XtreamCredentials credentials,
            String streamId,
            String requestedExtension) throws Exception {
        String extension = requestedExtension == null ? "ts" : requestedExtension.trim().toLowerCase(Locale.ROOT);
        if (!extension.matches("[a-z0-9]{1,8}")) extension = "ts";
        return active.getProtocol() + "://" + active.getAuthority() + endpointParentPath(active)
                + "live/" + encodePathSegment(credentials.username)
                + "/" + encodePathSegment(credentials.password)
                + "/" + encodePathSegment(streamId)
                + "." + extension;
    }

    private static String endpointParentPath(URL endpoint) {
        String path = endpoint.getPath();
        if (path == null || path.isBlank()) return "/";
        int slash = path.lastIndexOf('/');
        String parent = slash < 0 ? "/" : path.substring(0, slash + 1);
        if (!parent.startsWith("/")) parent = "/" + parent;
        return parent;
    }

    private static String encodePathSegment(String value) throws Exception {
        return URLEncoder.encode(value == null ? "" : value, StandardCharsets.UTF_8.name()).replace("+", "%20");
    }

    private static String readJsonScalar(JsonReader reader) throws Exception {
        JsonToken token = reader.peek();
        if (token == JsonToken.STRING || token == JsonToken.NUMBER) return valueOrEmpty(reader.nextString());
        if (token == JsonToken.BOOLEAN) return Boolean.toString(reader.nextBoolean());
        if (token == JsonToken.NULL) {
            reader.nextNull();
            return "";
        }
        reader.skipValue();
        return "";
    }

    private static boolean isSupportedRemoteUrl(String value) {
        if (value == null) return false;
        String normalized = value.trim().toLowerCase(Locale.ROOT);
        return normalized.startsWith("http://") || normalized.startsWith("https://")
                || normalized.startsWith("rtsp://") || normalized.startsWith("udp://");
    }

    private static String cleanM3uText(String value, String fallback) {
        String cleaned = value == null ? "" : value.replace('\r', ' ').replace('\n', ' ').replace('"', '\'').trim();
        return cleaned.isBlank() ? fallback : cleaned;
    }

    private static String valueOrEmpty(String value) {
        return value == null ? "" : value.trim();
    }

    private static String valueOrUnknown(String value) {
        return value == null || value.isBlank() ? "unbekannt" : value;
    }

    private static final class XtreamCredentials {
        final String username;
        final String password;

        XtreamCredentials(String username, String password) {
            this.username = username;
            this.password = password;
        }
    }

'''

    text = replace_once(
        text,
        "    private static URL buildBrokenHttpsRedirectRecoveryUrl(",
        helper_block + "    private static URL buildBrokenHttpsRedirectRecoveryUrl(",
        "Xtream Source API helper block",
    )

    text = text.replace('text("v13.1.17"', 'text("v13.1.18"')
    text = text.replace('value.append("App=").append("13.1.17")', 'value.append("App=").append("13.1.18")')
    text = text.replace("ProjectLumen/13.1.17 Android", "ProjectLumen/13.1.18 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132700", "versionCode 132800", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.17-http451-recovery-preview'",
        "versionName '13.1.18-source-api-recovery-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.17 Preview", "Project Lumen 13.1.18 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.17", "Project Lumen 13.1.18")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "same-origin Source API hook": "tryXtreamSourceApiRecovery(original, current, target, connectTimeout)" in text,
        "player API endpoint": "player_api.php" in text,
        "streaming JSON parser": "JsonReader" in text and "get_live_streams" in text,
        "M3U generated locally": 'writer.write("#EXTM3U\\n")' in text,
        "same-origin stream URLs": 'active.getAuthority() + endpointParentPath(active)' in text,
        "no proxy or TLS bypass": "Proxy(" not in text and "HostnameVerifier" not in text,
        "version 13.1.18": 'text("v13.1.18"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.18 same-origin Source API recovery patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
