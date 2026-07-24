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
        raise SystemExit("usage: apply-xtream-api-recovery-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    old_final_451 = r'''                    throw new ImportFailure(
                            "IMPORT-ACCESS-DENIED",
                            "Der Server oder ein vorgeschalteter Filter verweigert den Playlist-Abruf weiterhin (HTTP 451). Die Adresse ist erreichbar, aber dieser Zugriff wird vom Anbieter oder verwendeten Netz nicht freigegeben.",
                            false);
'''
    new_final_451 = r'''                    if (tryXtreamApiRecovery(current, target, connectTimeout)) {
                        return;
                    }
                    throw new ImportFailure(
                            "IMPORT-ACCESS-DENIED",
                            "Der Server oder ein vorgeschalteter Filter verweigert den Playlist-Abruf weiterhin (HTTP 451). Auch eine unterstützte Alternative desselben Anbieters war über dieses Netz nicht verfügbar.",
                            false);
'''
    text = replace_once(text, old_final_451, new_final_451, "Xtream fallback trigger")

    helper_block = r'''    private boolean tryXtreamApiRecovery(URL blockedPlaylistUrl, File target, int connectTimeout) throws Exception {
        String username = queryValue(blockedPlaylistUrl, "username");
        String password = queryValue(blockedPlaylistUrl, "password");
        if (username == null || username.isBlank() || password == null || password.isBlank()) {
            appendDiagnosticLog("RECOVERY", "Xtream-API nicht anwendbar", "Grund=Zugangsfelder fehlen", null);
            return false;
        }

        runOnUiThread(() -> showDiagnostic(
                "Alternative Anbieter-Schnittstelle wird geprüft",
                "Code IMPORT-XTREAM-RECOVERY\n"
                        + "Der Anbieter blockiert seinen M3U-Endpunkt /get.php.\n"
                        + "Lumen prüft nun einmalig die offizielle Xtream-API desselben Servers und derselben Zugangsdaten.\n\n"
                        + "Es werden weder Proxy/VPN noch fremde Server verwendet. Zugangsdaten bleiben ausgeblendet.",
                false));
        appendDiagnosticLog(
                "RECOVERY",
                "Xtream-API-Wiederherstellung gestartet",
                "Schema=" + blockedPlaylistUrl.getProtocol() + " · Port=" + effectivePort(blockedPlaylistUrl)
                        + " · Host-ID=" + shortHash(blockedPlaylistUrl.getHost()),
                null);

        String encodedUser = java.net.URLEncoder.encode(username, StandardCharsets.UTF_8.name());
        String encodedPassword = java.net.URLEncoder.encode(password, StandardCharsets.UTF_8.name());
        String credentialQuery = "username=" + encodedUser + "&password=" + encodedPassword;

        URL authUrl = buildXtreamApiUrl(blockedPlaylistUrl, credentialQuery);
        org.json.JSONObject authRoot = readXtreamAuth(authUrl, connectTimeout);
        org.json.JSONObject userInfo = authRoot.optJSONObject("user_info");
        int authenticated = userInfo == null ? 0 : userInfo.optInt("auth", 0);
        String accountStatus = userInfo == null ? "unbekannt" : userInfo.optString("status", "unbekannt");
        if (authenticated != 1) {
            throw new ImportFailure(
                    "IMPORT-AUTH",
                    "Die alternative Anbieter-Schnittstelle ist erreichbar, lehnt die Zugangsdaten jedoch ab.",
                    false);
        }
        appendDiagnosticLog(
                "RECOVERY",
                "Xtream-Anmeldung bestätigt",
                "Status=" + sanitizeLogText(accountStatus),
                null);

        java.util.Map<String, String> liveCategories = readXtreamCategories(
                buildXtreamApiUrl(blockedPlaylistUrl, credentialQuery + "&action=get_live_categories"),
                connectTimeout,
                "Live");
        java.util.Map<String, String> vodCategories = readXtreamCategories(
                buildXtreamApiUrl(blockedPlaylistUrl, credentialQuery + "&action=get_vod_categories"),
                connectTimeout,
                "Mediathek");

        File parent = target.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new ImportFailure("IMPORT-STORAGE", "Temporärer Speicherordner konnte nicht erstellt werden.", false);
        }

        int liveCount = 0;
        int vodCount = 0;
        try (java.io.BufferedWriter writer = new java.io.BufferedWriter(
                new java.io.OutputStreamWriter(new FileOutputStream(target, false), StandardCharsets.UTF_8),
                128 * 1024)) {
            writer.write("#EXTM3U");
            writer.newLine();

            ImportFailure liveFailure = null;
            try {
                liveCount = appendXtreamStreams(
                        buildXtreamApiUrl(blockedPlaylistUrl, credentialQuery + "&action=get_live_streams"),
                        blockedPlaylistUrl,
                        username,
                        password,
                        "live",
                        "ts",
                        liveCategories,
                        writer,
                        connectTimeout);
            } catch (ImportFailure failure) {
                liveFailure = failure;
                appendDiagnosticLog("RECOVERY", "Live-API konnte nicht ausgewertet werden", "Code=" + failure.code, failure);
            }

            try {
                vodCount = appendXtreamStreams(
                        buildXtreamApiUrl(blockedPlaylistUrl, credentialQuery + "&action=get_vod_streams"),
                        blockedPlaylistUrl,
                        username,
                        password,
                        "movie",
                        "mp4",
                        vodCategories,
                        writer,
                        connectTimeout);
            } catch (ImportFailure failure) {
                appendDiagnosticLog("RECOVERY", "Mediathek-API konnte nicht ausgewertet werden", "Code=" + failure.code, failure);
                if (liveCount == 0 && liveFailure != null) throw liveFailure;
            }
            writer.flush();
        }

        int total = liveCount + vodCount;
        if (total <= 0) {
            if (target.exists()) target.delete();
            throw new ImportFailure(
                    "IMPORT-XTREAM-EMPTY",
                    "Die Anbieter-Schnittstelle bestätigt die Anmeldung, liefert aber keine Live- oder Mediathek-Einträge.",
                    false);
        }
        if (target.length() > MAX_PLAYLIST_BYTES) {
            target.delete();
            throw new ImportFailure(
                    "IMPORT-SIZE",
                    "Die aus der Anbieter-Schnittstelle erzeugte Senderliste überschreitet 256 MB.",
                    false);
        }

        appendDiagnosticLog(
                "RECOVERY",
                "Playlist über Xtream-API aufgebaut",
                "Live=" + liveCount + " · Mediathek=" + vodCount + " · Gesamt=" + total + " · Bytes=" + target.length(),
                null);
        int finalLiveCount = liveCount;
        int finalVodCount = vodCount;
        runOnUiThread(() -> showDiagnostic(
                "Senderliste über Anbieter-API empfangen",
                "Code IMPORT-XTREAM-OK\n"
                        + "Der gesperrte M3U-Endpunkt wurde nicht weiter angesprochen.\n"
                        + "Lumen hat über die offizielle Schnittstelle desselben Anbieters "
                        + finalLiveCount + " Live- und " + finalVodCount + " Mediathek-Einträge aufgebaut.\n\n"
                        + "Die normale Prüfung und lokale Speicherung läuft weiter.",
                false));
        return true;
    }

    private org.json.JSONObject readXtreamAuth(URL url, int connectTimeout) throws Exception {
        HttpURLConnection connection = openXtreamConnection(url, connectTimeout, "Anmeldung");
        try (InputStream in = connection.getInputStream(); java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream()) {
            byte[] buffer = new byte[16 * 1024];
            int read;
            int total = 0;
            while ((read = in.read(buffer)) >= 0) {
                if (read == 0) continue;
                total += read;
                if (total > 1024 * 1024) {
                    throw new ImportFailure("IMPORT-XTREAM-RESPONSE", "Anmeldeantwort der Anbieter-Schnittstelle ist unerwartet groß.", false);
                }
                out.write(buffer, 0, read);
            }
            String json = out.toString(StandardCharsets.UTF_8.name()).trim();
            if (json.isEmpty() || !json.startsWith("{")) {
                throw new ImportFailure("IMPORT-XTREAM-RESPONSE", "Anbieter-Schnittstelle liefert keine gültige Anmeldeantwort.", false);
            }
            return new org.json.JSONObject(json);
        } catch (ImportFailure failure) {
            throw failure;
        } catch (Exception failure) {
            throw new ImportFailure("IMPORT-XTREAM-RESPONSE", "Anmeldeantwort der Anbieter-Schnittstelle konnte nicht gelesen werden.", false, failure);
        } finally {
            connection.disconnect();
        }
    }

    private java.util.Map<String, String> readXtreamCategories(
            URL url,
            int connectTimeout,
            String fallbackPrefix) {
        java.util.Map<String, String> categories = new java.util.LinkedHashMap<>();
        HttpURLConnection connection = null;
        try {
            connection = openXtreamConnection(url, connectTimeout, fallbackPrefix + "-Kategorien");
            try (android.util.JsonReader reader = new android.util.JsonReader(
                    new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
                reader.beginArray();
                while (reader.hasNext() && categories.size() < 20_000) {
                    String id = null;
                    String name = null;
                    reader.beginObject();
                    while (reader.hasNext()) {
                        String field = reader.nextName();
                        if ("category_id".equals(field)) id = readJsonScalar(reader);
                        else if ("category_name".equals(field)) name = readJsonScalar(reader);
                        else reader.skipValue();
                    }
                    reader.endObject();
                    if (id != null && !id.isBlank()) {
                        categories.put(id, sanitizeM3uText(name == null || name.isBlank() ? fallbackPrefix + " " + id : name));
                    }
                }
                reader.endArray();
            }
        } catch (Exception failure) {
            appendDiagnosticLog(
                    "RECOVERY",
                    fallbackPrefix + "-Kategorien nicht verfügbar",
                    "Fallback=Kategorie-ID",
                    failure);
        } finally {
            if (connection != null) connection.disconnect();
        }
        return categories;
    }

    private int appendXtreamStreams(
            URL apiUrl,
            URL sourceUrl,
            String username,
            String password,
            String streamKind,
            String defaultExtension,
            java.util.Map<String, String> categories,
            java.io.BufferedWriter writer,
            int connectTimeout) throws Exception {
        HttpURLConnection connection = openXtreamConnection(apiUrl, connectTimeout, streamKind);
        int count = 0;
        try (android.util.JsonReader reader = new android.util.JsonReader(
                new InputStreamReader(connection.getInputStream(), StandardCharsets.UTF_8))) {
            reader.beginArray();
            while (reader.hasNext()) {
                String streamId = null;
                String name = null;
                String logo = null;
                String categoryId = null;
                String epgId = null;
                String containerExtension = null;

                reader.beginObject();
                while (reader.hasNext()) {
                    String field = reader.nextName();
                    if ("stream_id".equals(field)) streamId = readJsonScalar(reader);
                    else if ("name".equals(field)) name = readJsonScalar(reader);
                    else if ("stream_icon".equals(field)) logo = readJsonScalar(reader);
                    else if ("category_id".equals(field)) categoryId = readJsonScalar(reader);
                    else if ("epg_channel_id".equals(field)) epgId = readJsonScalar(reader);
                    else if ("container_extension".equals(field)) containerExtension = readJsonScalar(reader);
                    else reader.skipValue();
                }
                reader.endObject();

                if (streamId == null || !streamId.matches("[0-9]+")) continue;
                String safeName = sanitizeM3uText(name == null || name.isBlank() ? "Stream " + streamId : name);
                String safeLogo = sanitizeM3uText(logo == null ? "" : logo);
                String safeEpg = sanitizeM3uText(epgId == null ? "" : epgId);
                String group = categories.get(categoryId);
                if (group == null || group.isBlank()) {
                    group = ("live".equals(streamKind) ? "Live" : "Mediathek")
                            + (categoryId == null || categoryId.isBlank() ? "" : " · " + sanitizeM3uText(categoryId));
                }
                String extension = safeExtension(containerExtension, defaultExtension);
                String streamUrl = buildXtreamStreamUrl(sourceUrl, streamKind, username, password, streamId, extension);

                writer.write("#EXTINF:-1 tvg-id=\"");
                writer.write(safeEpg);
                writer.write("\" tvg-name=\"");
                writer.write(safeName);
                writer.write("\" tvg-logo=\"");
                writer.write(safeLogo);
                writer.write("\" group-title=\"");
                writer.write(sanitizeM3uText(group));
                writer.write("\",");
                writer.write(safeName);
                writer.newLine();
                writer.write(streamUrl);
                writer.newLine();

                count++;
                if (count >= 250_000) {
                    appendDiagnosticLog("RECOVERY", "Xtream-Eintragslimit erreicht", "Typ=" + streamKind + " · Limit=250000", null);
                    while (reader.hasNext()) reader.skipValue();
                    break;
                }
            }
            reader.endArray();
            return count;
        } catch (ImportFailure failure) {
            throw failure;
        } catch (Exception failure) {
            throw new ImportFailure(
                    "IMPORT-XTREAM-RESPONSE",
                    "Die " + ("live".equals(streamKind) ? "Live" : "Mediathek")
                            + "-Antwort der Anbieter-Schnittstelle konnte nicht ausgewertet werden.",
                    false,
                    failure);
        } finally {
            connection.disconnect();
        }
    }

    private HttpURLConnection openXtreamConnection(URL url, int connectTimeout, String phase) throws Exception {
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(connectTimeout);
        connection.setReadTimeout(READ_TIMEOUT_MS);
        connection.setInstanceFollowRedirects(true);
        connection.setUseCaches(false);
        connection.setRequestProperty("Accept", "application/json,text/plain;q=0.9,*/*;q=0.5");
        connection.setRequestProperty("Accept-Encoding", "identity");
        connection.setRequestProperty("Cache-Control", "no-cache");
        connection.setRequestProperty("Connection", "close");
        connection.setRequestProperty("User-Agent", "ProjectLumen/13.1.18 Android");

        final int status;
        try {
            status = connection.getResponseCode();
        } catch (SocketTimeoutException timeout) {
            connection.disconnect();
            throw new ImportFailure(
                    "IMPORT-XTREAM-TIMEOUT",
                    "Die alternative Anbieter-Schnittstelle antwortet in der Phase " + phase + " nicht rechtzeitig.",
                    true,
                    timeout);
        } catch (IOException network) {
            connection.disconnect();
            throw new ImportFailure(
                    "IMPORT-XTREAM-CONNECT",
                    "Die alternative Anbieter-Schnittstelle konnte in der Phase " + phase + " nicht erreicht werden: " + compactNetworkMessage(network),
                    true,
                    network);
        }

        appendDiagnosticLog(
                "NETWORK",
                "Xtream-API-Antwort",
                "Phase=" + sanitizeLogText(phase) + " · HTTP=" + status
                        + " · Server=" + sanitizeLogText(connection.getHeaderField("Server") == null ? "unbekannt" : connection.getHeaderField("Server"))
                        + " · Content-Type=" + sanitizeLogText(connection.getContentType() == null ? "unbekannt" : connection.getContentType()),
                null);

        if (status == 401 || status == 403) {
            connection.disconnect();
            throw new ImportFailure("IMPORT-AUTH", "Die Anbieter-Schnittstelle lehnt die Anmeldung ab (HTTP " + status + ").", false);
        }
        if (status == 451) {
            connection.disconnect();
            throw new ImportFailure(
                    "IMPORT-XTREAM-BLOCKED",
                    "Der Anbieter oder das verwendete Netz blockiert neben /get.php auch die offizielle Xtream-API (HTTP 451). Lumen kann diese serverseitige Freigabe nicht ersetzen.",
                    false);
        }
        if (status == 404) {
            connection.disconnect();
            throw new ImportFailure(
                    "IMPORT-XTREAM-NOT-FOUND",
                    "Dieser Server stellt am erwarteten Pfad keine Xtream-API bereit (HTTP 404).",
                    false);
        }
        if (status < 200 || status >= 300) {
            connection.disconnect();
            throw new ImportFailure(
                    "IMPORT-XTREAM-HTTP",
                    "Die Anbieter-Schnittstelle antwortet in der Phase " + phase + " mit HTTP " + status + ".",
                    status >= 500);
        }
        return connection;
    }

    private static URL buildXtreamApiUrl(URL source, String query) throws Exception {
        String path = source.getPath();
        int slash = path == null ? -1 : path.lastIndexOf('/');
        String basePath = slash >= 0 ? path.substring(0, slash + 1) : "/";
        return new URL(source.getProtocol(), source.getHost(), source.getPort(), basePath + "player_api.php?" + query);
    }

    private static String queryValue(URL url, String requestedName) throws Exception {
        String query = url.getQuery();
        if (query == null || query.isBlank()) return null;
        for (String part : query.split("&")) {
            int equals = part.indexOf('=');
            String rawName = equals < 0 ? part : part.substring(0, equals);
            String rawValue = equals < 0 ? "" : part.substring(equals + 1);
            String name = java.net.URLDecoder.decode(rawName, StandardCharsets.UTF_8.name());
            if (requestedName.equalsIgnoreCase(name)) {
                return java.net.URLDecoder.decode(rawValue, StandardCharsets.UTF_8.name());
            }
        }
        return null;
    }

    private static String readJsonScalar(android.util.JsonReader reader) throws IOException {
        android.util.JsonToken token = reader.peek();
        if (token == android.util.JsonToken.NULL) {
            reader.nextNull();
            return null;
        }
        if (token == android.util.JsonToken.STRING || token == android.util.JsonToken.NUMBER) {
            return reader.nextString();
        }
        if (token == android.util.JsonToken.BOOLEAN) {
            return Boolean.toString(reader.nextBoolean());
        }
        reader.skipValue();
        return null;
    }

    private static String buildXtreamStreamUrl(
            URL source,
            String streamKind,
            String username,
            String password,
            String streamId,
            String extension) throws Exception {
        String path = "/" + streamKind
                + "/" + android.net.Uri.encode(username)
                + "/" + android.net.Uri.encode(password)
                + "/" + streamId + "." + extension;
        return new URL(source.getProtocol(), source.getHost(), source.getPort(), path).toExternalForm();
    }

    private static String safeExtension(String candidate, String fallback) {
        String value = candidate == null ? "" : candidate.trim().toLowerCase(Locale.ROOT);
        if (!value.matches("[a-z0-9]{1,8}")) value = fallback;
        return value;
    }

    private static String sanitizeM3uText(String value) {
        if (value == null) return "";
        return value.replace('"', '\'')
                .replace('\r', ' ')
                .replace('\n', ' ')
                .trim();
    }

    private static int effectivePort(URL url) {
        int port = url.getPort();
        return port >= 0 ? port : url.getDefaultPort();
    }

'''

    text = replace_once(
        text,
        "    private static URL buildBrokenHttpsRedirectRecoveryUrl(",
        helper_block + "    private static URL buildBrokenHttpsRedirectRecoveryUrl(",
        "Xtream helper methods",
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
        "versionName '13.1.18-xtream-api-recovery-preview'",
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
        "451 triggers official Xtream fallback": "tryXtreamApiRecovery(current, target, connectTimeout)" in text,
        "same-provider player API": 'basePath + "player_api.php?" + query' in text,
        "streaming JSON parser": "android.util.JsonReader" in text,
        "live streams": "action=get_live_streams" in text and '"live"' in text,
        "vod streams": "action=get_vod_streams" in text and '"movie"' in text,
        "clear blocked result": "IMPORT-XTREAM-BLOCKED" in text,
        "no proxy or TLS bypass": "Proxy(" not in text and "HostnameVerifier" not in text,
        "version 13.1.18": 'text("v13.1.18"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.18 Xtream API recovery patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
