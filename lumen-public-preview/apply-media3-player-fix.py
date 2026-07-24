#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def block(text: str, start: str, end: str, new: str, label: str) -> str:
    first = text.find(start)
    if first < 0:
        raise SystemExit(f"{label}: start not found")
    last = text.find(end, first)
    if last < 0:
        raise SystemExit(f"{label}: end not found")
    return text[:first] + new + text[last:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-media3-player-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = java.read_text(encoding="utf-8")

    text = once(
        text,
        "import android.media.MediaPlayer;\n",
        "import androidx.media3.common.MediaItem;\n"
        "import androidx.media3.common.PlaybackException;\n"
        "import androidx.media3.common.Player;\n"
        "import androidx.media3.datasource.DefaultDataSource;\n"
        "import androidx.media3.datasource.DefaultHttpDataSource;\n"
        "import androidx.media3.datasource.HttpDataSource;\n"
        "import androidx.media3.exoplayer.ExoPlayer;\n"
        "import androidx.media3.exoplayer.source.DefaultMediaSourceFactory;\n"
        "import androidx.media3.ui.PlayerView;\n",
        "Media3 imports",
    )
    text = once(text, "import android.widget.MediaController;\n", "", "remove MediaController import")
    text = once(text, "import android.widget.VideoView;\n", "", "remove VideoView import")
    text = once(text, "import java.util.Locale;\n", "import java.util.Locale;\nimport java.util.Map;\n", "Map import")

    text = once(
        text,
        "    private VideoView videoView;\n    private TextView playerOverlay;\n",
        "    private PlayerView playerView;\n    private ExoPlayer exoPlayer;\n    private TextView playerOverlay;\n",
        "player fields",
    )

    player = r'''    private void play(Channel channel) {
        if (channel == null || channel.url.isBlank()) {
            showDiagnostic("Wiedergabe nicht gestartet", "Code PLAY-NO-SOURCE\nKeine abspielbare Adresse vorhanden.", false);
            return;
        }
        removePlayer();
        page.setVisibility(View.GONE);
        diagnosticPanel.setVisibility(View.GONE);
        diagnosticFab.setVisibility(View.GONE);

        playerView = new PlayerView(this);
        playerView.setBackgroundColor(Color.BLACK);
        playerView.setUseController(!television);
        playerView.setControllerAutoShow(true);
        playerView.setKeepScreenOn(true);
        root.addView(playerView, match());

        playerOverlay = text(channel.name + "\nPhase PLAY-01 · Stream wird geöffnet\nMedia3 prüft Server, Container und Decoder …\n\nTippen/OK: Diagnose schließen · Zurück: Player schließen", television ? 20 : 15, Color.WHITE, false);
        playerOverlay.setPadding(dp(18), dp(16), dp(18), dp(16));
        playerOverlay.setBackground(roundRect(0xE607111E, 18));
        playerOverlay.setOnClickListener(v -> setPlayerOverlay(false));
        FrameLayout.LayoutParams overlay = new FrameLayout.LayoutParams(Math.min(getResources().getDisplayMetrics().widthPixels - dp(24), dp(television ? 580 : 400)), ViewGroup.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM | Gravity.END);
        overlay.setMargins(dp(12), dp(12), dp(12), dp(12));
        root.addView(playerOverlay, overlay);

        playerDiagnosticButton = button("Diagnose", true);
        playerDiagnosticButton.setVisibility(View.GONE);
        playerDiagnosticButton.setOnClickListener(v -> setPlayerOverlay(true));
        FrameLayout.LayoutParams diag = new FrameLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, dp(television ? 54 : 46), Gravity.BOTTOM | Gravity.END);
        diag.setMargins(dp(12), dp(12), dp(12), dp(12));
        root.addView(playerDiagnosticButton, diag);

        DefaultHttpDataSource.Factory httpFactory = new DefaultHttpDataSource.Factory()
                .setUserAgent("VLC/3.0.20 LibVLC/3.0.20")
                .setConnectTimeoutMs(30_000)
                .setReadTimeoutMs(45_000)
                .setAllowCrossProtocolRedirects(true)
                .setDefaultRequestProperties(Map.of("Accept", "*/*"));
        DefaultDataSource.Factory dataSourceFactory = new DefaultDataSource.Factory(this, httpFactory);
        DefaultMediaSourceFactory mediaSourceFactory = new DefaultMediaSourceFactory(dataSourceFactory);
        ExoPlayer player = new ExoPlayer.Builder(this)
                .setMediaSourceFactory(mediaSourceFactory)
                .build();
        exoPlayer = player;
        playerView.setPlayer(player);

        appendDiagnosticLog("PLAYBACK", "Media3-Wiedergabe gestartet",
                "Engine=Media3 · " + describeStreamEndpoint(channel.url), null);

        player.addListener(new Player.Listener() {
            @Override
            public void onPlaybackStateChanged(int playbackState) {
                if (player != exoPlayer) return;
                if (playbackState == Player.STATE_BUFFERING) {
                    showPlayerText(channel.name + "\nPhase PLAY-02 · Pufferung\nDer Stream wurde geöffnet; Daten und Decoder werden vorbereitet.", true);
                } else if (playbackState == Player.STATE_READY) {
                    showPlayerText(channel.name + "\nPhase PLAY-03 · Wiedergabe bereit\n\nTippen/OK: Diagnose schließen · Zurück: Player schließen", false);
                } else if (playbackState == Player.STATE_ENDED) {
                    showPlayerText(channel.name + "\nWiedergabe beendet", true);
                }
            }

            @Override
            public void onIsPlayingChanged(boolean isPlaying) {
                if (player != exoPlayer || !isPlaying) return;
                appendDiagnosticLog("PLAYBACK", "Wiedergabe läuft",
                        "Engine=Media3 · " + describeStreamEndpoint(channel.url), null);
                showPlayerText(channel.name + "\nPhase PLAY-03 · Wiedergabe läuft\n\nTippen/OK: Diagnose schließen · Zurück: Player schließen", false);
            }

            @Override
            public void onPlayerError(PlaybackException error) {
                if (player != exoPlayer) return;
                int httpStatus = playbackHttpStatus(error);
                String codeName = error.getErrorCodeName();
                String category = playbackErrorCategory(codeName, httpStatus);
                Throwable cause = deepestCause(error);
                String causeName = cause == null ? "unbekannt" : cause.getClass().getSimpleName();
                String details = "Code=PLAY-MEDIA3-" + codeName
                        + " · Kategorie=" + category
                        + (httpStatus > 0 ? " · HTTP=" + httpStatus : "")
                        + " · Ursache=" + sanitizeLogText(causeName)
                        + " · " + describeStreamEndpoint(channel.url);
                appendDiagnosticLog("PLAYBACK", "Wiedergabe fehlgeschlagen", details, null);
                showPlayerText(channel.name
                        + "\nWiedergabe nicht möglich"
                        + "\nCode PLAY-MEDIA3-" + codeName
                        + (httpStatus > 0 ? "\nHTTP-Status " + httpStatus : "")
                        + "\n" + playbackErrorHint(category, httpStatus)
                        + "\n\nZurück: Player schließen", true);
            }
        });

        player.setMediaItem(MediaItem.fromUri(Uri.parse(channel.url)));
        player.prepare();
        player.play();
        playerView.requestFocus();
    }

    private static int playbackHttpStatus(Throwable error) {
        Throwable current = error;
        for (int depth = 0; current != null && depth < 12; depth++) {
            if (current instanceof HttpDataSource.InvalidResponseCodeException invalid) {
                return invalid.responseCode;
            }
            current = current.getCause();
        }
        return -1;
    }

    private static Throwable deepestCause(Throwable error) {
        Throwable current = error;
        Throwable deepest = error;
        for (int depth = 0; current != null && depth < 12; depth++) {
            deepest = current;
            current = current.getCause();
        }
        return deepest;
    }

    private static String playbackErrorCategory(String codeName, int httpStatus) {
        String code = codeName == null ? "" : codeName.toUpperCase(Locale.ROOT);
        if (httpStatus > 0 || code.contains("HTTP")) return "HTTP";
        if (code.contains("NETWORK") || code.contains("CONNECTION") || code.contains("TIMEOUT")) return "NETZWERK";
        if (code.contains("DECOD") || code.contains("AUDIO_TRACK") || code.contains("VIDEO_TRACK")) return "DECODER";
        if (code.contains("PARSING") || code.contains("CONTENT_TYPE") || code.contains("CONTAINER")) return "FORMAT";
        return "UNBEKANNT";
    }

    private static String playbackErrorHint(String category, int httpStatus) {
        if ("HTTP".equals(category)) {
            if (httpStatus == 401 || httpStatus == 403 || httpStatus == 451) {
                return "Der Streaming-Server hat diesen Abruf abgewiesen. Zugang, Freischaltung oder Anbieterregeln müssen geprüft werden.";
            }
            if (httpStatus == 404 || httpStatus == 410) {
                return "Die Streamadresse ist beim Anbieter nicht mehr vorhanden.";
            }
            if (httpStatus >= 500) {
                return "Der Streaming-Server meldet derzeit einen internen Fehler.";
            }
            return "Der Streaming-Server hat keine verwertbare Antwort geliefert.";
        }
        if ("NETZWERK".equals(category)) {
            return "Die Verbindung zum Streaming-Server wurde unterbrochen oder hat das Zeitlimit überschritten.";
        }
        if ("DECODER".equals(category)) {
            return "Das Gerät kann mindestens eine verwendete Video- oder Audiospur nicht decodieren.";
        }
        if ("FORMAT".equals(category)) {
            return "Streamcontainer oder Wiedergabeliste konnten nicht zuverlässig erkannt werden.";
        }
        return "Media3 konnte den Stream nicht vorbereiten. Die Diagnose enthält jetzt die technische Ursache.";
    }

    private static String describeStreamEndpoint(String raw) {
        if (raw == null || raw.isBlank()) return "Stream=leer";
        try {
            URI uri = new URI(raw);
            String scheme = uri.getScheme() == null ? "unbekannt" : uri.getScheme().toLowerCase(Locale.ROOT);
            int port = uri.getPort();
            if (port < 0) port = "https".equals(scheme) ? 443 : "http".equals(scheme) ? 80 : -1;
            String path = uri.getPath() == null ? "" : uri.getPath().toLowerCase(Locale.ROOT);
            String kind = path.contains("/live/") ? "live"
                    : path.contains("/movie/") ? "vod"
                    : path.contains("/series/") ? "series"
                    : "unbekannt";
            String extension = "keine";
            int slash = path.lastIndexOf('/');
            int dot = path.lastIndexOf('.');
            if (dot > slash && dot + 1 < path.length()) {
                String candidate = path.substring(dot + 1);
                if (candidate.length() <= 10 && candidate.matches("[a-z0-9]+")) extension = candidate;
            }
            return "Schema=" + scheme
                    + " · Port=" + port
                    + " · Host-ID=" + shortHostHash(uri.getHost())
                    + " · Streamtyp=" + kind
                    + " · Endung=" + extension;
        } catch (Exception ignored) {
            return "Stream=unvollständig/ausgeblendet";
        }
    }

'''
    text = block(text, "    private void play(Channel channel) {\n", "    private void showPlayerText(String value, boolean keep) {\n", player, "player implementation")

    old_remove = '''    private void removePlayer() {
        if (videoView != null) {
            try { videoView.stopPlayback(); } catch (Exception ignored) {}
            root.removeView(videoView);
        }
        if (playerOverlay != null) root.removeView(playerOverlay);
        if (playerDiagnosticButton != null) root.removeView(playerDiagnosticButton);
        videoView = null;
        playerOverlay = null;
        playerDiagnosticButton = null;
    }
'''
    new_remove = '''    private void removePlayer() {
        if (playerView != null) {
            try { playerView.setPlayer(null); } catch (Exception ignored) {}
        }
        if (exoPlayer != null) {
            try { exoPlayer.stop(); } catch (Exception ignored) {}
            try { exoPlayer.release(); } catch (Exception ignored) {}
        }
        if (playerView != null) root.removeView(playerView);
        if (playerOverlay != null) root.removeView(playerOverlay);
        if (playerDiagnosticButton != null) root.removeView(playerDiagnosticButton);
        playerView = null;
        exoPlayer = null;
        playerOverlay = null;
        playerDiagnosticButton = null;
    }
'''
    text = once(text, old_remove, new_remove, "player cleanup")
    text = text.replace("if (videoView != null && event.getAction()", "if (playerView != null && event.getAction()")
    text = text.replace("if (videoView != null) { closePlayer(); return; }", "if (playerView != null) { closePlayer(); return; }")
    text = once(
        text,
        "    protected void onDestroy() {\n        importWorker.shutdownNow();",
        "    protected void onDestroy() {\n        removePlayer();\n        importWorker.shutdownNow();",
        "release player on destroy",
    )

    text = text.replace('text("v13.1.22"', 'text("v13.1.23"')
    text = text.replace('value.append("App=").append("13.1.22")', 'value.append("App=").append("13.1.23")')
    text = text.replace("ProjectLumen/13.1.22 Android", "ProjectLumen/13.1.23 Android")
    java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = once(gradle_text, "versionCode 133200", "versionCode 133300", "versionCode")
    gradle_text = once(
        gradle_text,
        "versionName '13.1.22-poc-home-persistence-preview'",
        "versionName '13.1.23-media3-player-preview'",
        "versionName",
    )
    if "androidx.media3:media3-exoplayer" not in gradle_text:
        gradle_text += '''

dependencies {
    def media3_version = "1.10.1"
    implementation "androidx.media3:media3-exoplayer:$media3_version"
    implementation "androidx.media3:media3-exoplayer-hls:$media3_version"
    implementation "androidx.media3:media3-exoplayer-dash:$media3_version"
    implementation "androidx.media3:media3-exoplayer-rtsp:$media3_version"
    implementation "androidx.media3:media3-ui:$media3_version"
}
'''
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8").replace(
        "Project Lumen 13.1.22 Preview", "Project Lumen 13.1.23 Preview"
    )
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme.write_text(
            readme.read_text(encoding="utf-8").replace("Project Lumen 13.1.22", "Project Lumen 13.1.23"),
            encoding="utf-8",
        )

    checks = {
        "Media3 PlayerView": "private PlayerView playerView" in text,
        "Media3 ExoPlayer": "private ExoPlayer exoPlayer" in text,
        "HTTP user agent": 'setUserAgent("VLC/3.0.20 LibVLC/3.0.20")' in text,
        "redirect support": "setAllowCrossProtocolRedirects(true)" in text,
        "sanitized endpoint": "describeStreamEndpoint" in text,
        "separate error categories": "playbackErrorCategory" in text,
        "legacy VideoView removed": "VideoView" not in text,
        "legacy native error removed": "PLAY-\" + what + \"-\" + extra" not in text,
        "version 13.1.23": 'text("v13.1.23"' in text,
        "Media3 dependency": "androidx.media3:media3-exoplayer" in gradle_text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.23 Media3 player patch applied")
    for name in checks:
        print("OK: " + name)


if __name__ == "__main__":
    main()
