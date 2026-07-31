from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, content: str) -> None:
    (ROOT / relative).write_text(content, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    content = read(relative)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"{relative}: expected one anchor, found {count}: {old[:120]!r}")
    write(relative, content.replace(old, new, 1))


def patch_version_and_label() -> None:
    path = "app/build.gradle"
    content = read(path)
    content, code_count = re.subn(r"versionCode\s+\d+", "versionCode 1320600", content, count=1)
    content, name_count = re.subn(
        r"versionName\s+'[^']+'", "versionName '13.2.0-rc6-playback-persistence-ux'", content, count=1
    )
    if code_count != 1 or name_count != 1:
        raise RuntimeError("app/build.gradle: version anchors missing")
    write(path, content)

    strings = "app/src/main/res/values/strings.xml"
    content = read(strings)
    content, label_count = re.subn(
        r'<string name="app_name">[^<]+</string>',
        '<string name="app_name">Project Lumen RC6</string>',
        content,
        count=1,
    )
    if label_count != 1:
        raise RuntimeError("strings.xml: app_name anchor missing")
    write(strings, content)


def patch_player_recovery() -> None:
    path = "app/src/main/java/com/projectlumen/pilot/robust/PlayerActivity.java"
    replace_once(
        path,
        "    private boolean fallbackUsed;\n    private boolean audioAutoRecoveryUsed;\n    private boolean inPictureInPicture;\n",
        "    private boolean fallbackUsed;\n"
        "    private boolean audioAutoRecoveryUsed;\n"
        "    private boolean protocolFallbackUsed;\n"
        "    private boolean firstFrameRendered;\n"
        "    private boolean inPictureInPicture;\n",
    )
    replace_once(
        path,
        "        openedAt = SystemClock.elapsedRealtime();\n        errorCard.setVisibility(View.GONE);\n",
        "        openedAt = SystemClock.elapsedRealtime();\n"
        "        firstFrameRendered = false;\n"
        "        errorCard.setVisibility(View.GONE);\n",
    )
    replace_once(
        path,
        "        public void onRenderedFirstFrame() {\n            log.event(interaction, \"PLAY-FIRST-FRAME\", \"elapsedMs=\" + elapsed() + \" engine=Media3\");\n        }\n",
        "        public void onRenderedFirstFrame() {\n"
        "            firstFrameRendered = true;\n"
        "            log.event(interaction, \"PLAY-FIRST-FRAME\", \"elapsedMs=\" + elapsed() + \" engine=Media3\");\n"
        "        }\n",
    )
    replace_once(
        path,
        "            if (!fallbackUsed && !forceTs && shouldFallback(errorName, url)) {\n",
        "            String compatibleUrl = StreamUrlPolicy.httpCompatibilityUrl(url, error);\n"
        "            if (!protocolFallbackUsed && compatibleUrl != null) {\n"
        "                protocolFallbackUsed = true;\n"
        "                url = compatibleUrl;\n"
        "                forceTs = false;\n"
        "                fallbackUsed = false;\n"
        "                log.event(interaction, \"PLAY-PROTOCOL-FALLBACK\",\n"
        "                        \"reason=tls-on-custom-port target=http\");\n"
        "                status.setText(\"Serverprotokoll wird kompatibel neu verbunden …\");\n"
        "                playerView.postDelayed(() -> startPlayer(false), 180);\n"
        "                return;\n"
        "            }\n"
        "            if (!fallbackUsed && !forceTs && shouldFallback(errorName, url)) {\n",
    )
    replace_once(
        path,
        "        fallbackUsed = false;\n        forceTs = false;\n        audioAutoRecoveryUsed = false;\n",
        "        fallbackUsed = false;\n"
        "        protocolFallbackUsed = false;\n"
        "        forceTs = false;\n"
        "        audioAutoRecoveryUsed = false;\n",
    )
    replace_once(
        path,
        "        if (forcedTs || lower.endsWith(\".ts\") || lower.contains(\".ts?\")) {\n",
        "        if (forcedTs || StreamUrlPolicy.shouldForceMpegTs(streamUrl)) {\n",
    )
    replace_once(
        path,
        "            log.event(interaction, \"PLAY-PREPARE-START\", \"engine=Media3 forcedTs=\"\n                    + forcedTs + \" profile=\" + profile(url) + \" decoderFallback=true\");\n",
        "            log.event(interaction, \"PLAY-PREPARE-START\", \"engine=Media3 forcedTs=\"\n"
        "                    + forcedTs + \" profile=\" + profile(url)\n"
        "                    + \" decoderFallback=true immediateTs=\"\n"
        "                    + StreamUrlPolicy.shouldForceMpegTs(url));\n",
    )


def patch_import_speed_and_persistence() -> None:
    path = "app/src/main/java/com/projectlumen/pilot/robust/PlaylistRepository.java"
    replace_once(path, "import java.util.List;\n", "import java.util.List;\nimport java.util.zip.GZIPInputStream;\n")
    replace_once(
        path,
        "    private static final long DOWNLOAD_REPORT_BYTES = 4L * 1024L * 1024L;\n"
        "    private static final long DOWNLOAD_REPORT_INTERVAL_MS = 1_500L;\n",
        "    private static final long DOWNLOAD_REPORT_BYTES = 8L * 1024L * 1024L;\n"
        "    private static final long DOWNLOAD_REPORT_INTERVAL_MS = 2_500L;\n",
    )
    replace_once(
        path,
        "        if (!current.exists()) return Collections.emptyList();\n",
        "        if (!current.exists() && !CatalogCache.usable(cacheCurrent)) {\n"
        "            return Collections.emptyList();\n"
        "        }\n",
    )
    replace_once(
        path,
        "                cacheCurrent.delete();\n            }\n        }\n\n        progress.update(\"RESTORE-DECRYPT-START\",\n",
        "                cacheCurrent.delete();\n"
        "                if (!current.exists()) return Collections.emptyList();\n"
        "            }\n"
        "        }\n\n"
        "        progress.update(\"RESTORE-DECRYPT-START\",\n",
    )
    replace_once(
        path,
        '        connection.setRequestProperty("Accept", "*/*");\n',
        '        connection.setRequestProperty("Accept", "*/*");\n'
        '        connection.setRequestProperty("Accept-Encoding", "gzip");\n'
        '        connection.setRequestProperty("Connection", "keep-alive");\n',
    )
    replace_once(
        path,
        "            try (InputStream input = new BufferedInputStream(\n"
        "                    connection.getInputStream(), 1024 * 1024)) {\n",
        "            try (InputStream input = new BufferedInputStream(\n"
        "                    responseStream(connection), 4 * 1024 * 1024)) {\n",
    )
    replace_once(
        path,
        "    private static String httpCompatibilityUrl(String sourceUrl, Exception failure) {\n",
        "    private static InputStream responseStream(HttpURLConnection connection) throws IOException {\n"
        "        InputStream raw = connection.getInputStream();\n"
        "        String encoding = connection.getHeaderField(\"Content-Encoding\");\n"
        "        if (encoding != null && encoding.toLowerCase(java.util.Locale.ROOT).contains(\"gzip\")) {\n"
        "            return new GZIPInputStream(raw, 4 * 1024 * 1024);\n"
        "        }\n"
        "        return raw;\n"
        "    }\n\n"
        "    private static String httpCompatibilityUrl(String sourceUrl, Exception failure) {\n",
    )
    replace_once(
        path,
        "        prefs.edit()\n"
        "                .putString(\"source_name\", safeName(name))\n"
        "                .putLong(\"source_bytes\", bytes)\n"
        "                .putInt(\"source_entries\", entries)\n"
        "                .putLong(\"source_activated_at\", System.currentTimeMillis())\n"
        "                .apply();\n",
        "        boolean saved = prefs.edit()\n"
        "                .putString(\"source_name\", safeName(name))\n"
        "                .putLong(\"source_bytes\", bytes)\n"
        "                .putInt(\"source_entries\", entries)\n"
        "                .putLong(\"source_activated_at\", System.currentTimeMillis())\n"
        "                .commit();\n"
        "        if (!saved) throw new IllegalStateException(\"Bibliotheksstatus konnte nicht dauerhaft gespeichert werden.\");\n",
    )
    replace_once(
        path,
        "        prefs.edit()\n"
        "                .remove(\"pending_source_name\")\n"
        "                .remove(\"pending_source_bytes\")\n"
        "                .remove(\"pending_started_at\")\n"
        "                .apply();\n",
        "        prefs.edit()\n"
        "                .remove(\"pending_source_name\")\n"
        "                .remove(\"pending_source_bytes\")\n"
        "                .remove(\"pending_started_at\")\n"
        "                .commit();\n",
    )
    replace_once(
        path,
        "            BufferedOutputStream raw = new BufferedOutputStream(\n                    file, 1024 * 1024);\n",
        "            BufferedOutputStream raw = new BufferedOutputStream(\n                    file, 4 * 1024 * 1024);\n",
    )


def patch_parser_and_cache_buffers() -> None:
    parser = "app/src/main/java/com/projectlumen/pilot/robust/M3uParser.java"
    replace_once(parser, "    private static final int READER_BUFFER = 1024 * 1024;\n", "    private static final int READER_BUFFER = 4 * 1024 * 1024;\n")
    replace_once(parser, "    private static final int PROGRESS_EVERY_ENTRIES = 5_000;\n", "    private static final int PROGRESS_EVERY_ENTRIES = 10_000;\n")
    replace_once(parser, "    private static final int DEADLINE_CHECK_EVERY_LINES = 2_048;\n", "    private static final int DEADLINE_CHECK_EVERY_LINES = 8_192;\n")

    cache = "app/src/main/java/com/projectlumen/pilot/robust/CatalogCache.java"
    replace_once(cache, "    private static final int BUFFER_BYTES = 1024 * 1024;\n", "    private static final int BUFFER_BYTES = 4 * 1024 * 1024;\n")


def patch_main_ux_diagnostics() -> None:
    path = "app/src/main/java/com/projectlumen/pilot/robust/MainActivity.java"
    replace_once(
        path,
        '                + " languages=" + Math.max(0, snapshot.languages.size() - 1)\n',
        '                + " languages=" + snapshot.languages.size()\n',
    )
    replace_once(
        path,
        '                reimportRequired ? "Bitte den Playlist-Link einmal über + Quelle neu laden."\n'
        '                        : candidate ? "Die geladene Playlist wird blockweise migriert und indexiert."\n'
        '                        : "Gespeicherter Schnellindex wird geladen.");\n',
        '                reimportRequired ? "Bitte den Playlist-Link einmal über + Quelle neu laden."\n'
        '                        : candidate ? "Die geladene Playlist wird sicher abgeschlossen."\n'
        '                        : "Gespeicherte Bibliothek wird direkt aus dem Schnellindex geöffnet.");\n',
    )


def verify() -> None:
    build = read("app/build.gradle")
    strings = read("app/src/main/res/values/strings.xml")
    player = read("app/src/main/java/com/projectlumen/pilot/robust/PlayerActivity.java")
    repository = read("app/src/main/java/com/projectlumen/pilot/robust/PlaylistRepository.java")
    catalog = read("app/src/main/java/com/projectlumen/pilot/robust/ProviderCatalog.java")
    required = {
        "version": "13.2.0-rc6-playback-persistence-ux" in build,
        "label": "Project Lumen RC6" in strings,
        "playback_http_fallback": "PLAY-PROTOCOL-FALLBACK" in player,
        "immediate_mpegts": "StreamUrlPolicy.shouldForceMpegTs" in player,
        "gzip_import": "GZIPInputStream" in repository,
        "durable_metadata": ".commit()" in repository,
        "cache_first_restore": "!current.exists() && !CatalogCache.usable(cacheCurrent)" in repository,
        "unified_groups": "isDominantProviderRoot" in catalog,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise RuntimeError(f"RC6 patch verification failed: {missing}")
    print("RC6 patch verification passed:", ", ".join(required))


def main() -> None:
    patch_version_and_label()
    patch_player_recovery()
    patch_import_speed_and_persistence()
    patch_parser_and_cache_buffers()
    patch_main_ux_diagnostics()
    verify()


if __name__ == "__main__":
    main()
