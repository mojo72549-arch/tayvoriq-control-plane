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
        raise RuntimeError(f"{relative}: expected one anchor, found {count}: {old[:100]!r}")
    write(relative, content.replace(old, new, 1))


def patch_build_config() -> None:
    path = "app/build.gradle"
    content = read(path)
    content, code_count = re.subn(r"versionCode\s+\d+", "versionCode 1320500", content, count=1)
    content, name_count = re.subn(
        r"versionName\s+'[^']+'", "versionName '13.2.0-rc5-stable49-recovery'", content, count=1
    )
    if code_count != 1 or name_count != 1:
        raise RuntimeError("app/build.gradle: version anchors missing")
    write(path, content)


def patch_manifest() -> None:
    replace_once(
        "app/src/main/AndroidManifest.xml",
        '        <activity android:name=".PlayerActivity" android:exported="false" />',
        '        <activity\n'
        '            android:name=".PlayerActivity"\n'
        '            android:configChanges="keyboard|keyboardHidden|orientation|screenSize|smallestScreenSize|uiMode"\n'
        '            android:exported="false"\n'
        '            android:supportsPictureInPicture="true" />',
    )


def patch_player() -> None:
    path = "app/src/main/java/com/projectlumen/pilot/robust/PlayerActivity.java"
    replace_once(path, "import android.app.Activity;\n", "import android.app.Activity;\nimport android.app.PictureInPictureParams;\n")
    replace_once(
        path,
        "import android.content.Context;\n",
        "import android.content.Context;\nimport android.content.pm.PackageManager;\nimport android.content.res.Configuration;\n",
    )
    replace_once(path, "import android.os.Bundle;\n", "import android.os.Build;\nimport android.os.Bundle;\n")
    replace_once(path, "import android.os.SystemClock;\n", "import android.os.SystemClock;\nimport android.util.Rational;\n")
    replace_once(
        path,
        "    private PlayerView playerView;\n    private TextView status;\n",
        "    private PlayerView playerView;\n    private View topOverlay;\n    private TextView status;\n",
    )
    replace_once(
        path,
        "    private boolean fallbackUsed;\n    private boolean audioAutoRecoveryUsed;\n",
        "    private boolean fallbackUsed;\n    private boolean audioAutoRecoveryUsed;\n    private boolean inPictureInPicture;\n",
    )
    replace_once(
        path,
        "    @Override\n    protected void onStart() {\n        super.onStart();\n        if (url != null && !url.isBlank()) startPlayer(false);\n    }\n\n"
        "    @Override\n    protected void onStop() {\n        releasePlayer();\n        super.onStop();\n    }\n",
        "    @Override\n    protected void onStart() {\n        super.onStart();\n        if (url != null && !url.isBlank() && player == null) startPlayer(false);\n    }\n\n"
        "    @Override\n    protected void onStop() {\n        if (!inPictureInPicture) releasePlayer();\n        super.onStop();\n    }\n",
    )
    replace_once(
        path,
        "    private void buildUi() {\n",
        "    @SuppressWarnings(\"deprecation\")\n"
        "    @Override\n"
        "    public void onBackPressed() {\n"
        "        if (enterBackPictureInPicture()) return;\n"
        "        log.event(interaction, \"PLAYER-BACK-NAVIGATE\", \"playing=falseOrTv=true\");\n"
        "        super.onBackPressed();\n"
        "    }\n\n"
        "    private boolean enterBackPictureInPicture() {\n"
        "        if (!supportsPictureInPicture() || !playbackActive() || isFinishing()\n"
        "                || isInPictureInPictureMode()) return false;\n"
        "        try {\n"
        "            PictureInPictureParams params = new PictureInPictureParams.Builder()\n"
        "                    .setAspectRatio(new Rational(16, 9))\n"
        "                    .build();\n"
        "            boolean entered = enterPictureInPictureMode(params);\n"
        "            log.event(interaction, \"PLAYER-BACK-MINIMIZE\", \"accepted=\" + entered);\n"
        "            return entered;\n"
        "        } catch (Throwable failure) {\n"
        "            log.exception(interaction, \"PLAYER-BACK-PIP-ERROR\", failure);\n"
        "            return false;\n"
        "        }\n"
        "    }\n\n"
        "    private boolean supportsPictureInPicture() {\n"
        "        return Build.VERSION.SDK_INT >= Build.VERSION_CODES.O\n"
        "                && !isTelevision()\n"
        "                && getPackageManager().hasSystemFeature(PackageManager.FEATURE_PICTURE_IN_PICTURE);\n"
        "    }\n\n"
        "    private boolean playbackActive() {\n"
        "        if (player == null) return false;\n"
        "        int state = player.getPlaybackState();\n"
        "        return player.getPlayWhenReady() && state != Player.STATE_IDLE && state != Player.STATE_ENDED;\n"
        "    }\n\n"
        "    private boolean isTelevision() {\n"
        "        return (getResources().getConfiguration().uiMode & Configuration.UI_MODE_TYPE_MASK)\n"
        "                == Configuration.UI_MODE_TYPE_TELEVISION;\n"
        "    }\n\n"
        "    @Override\n"
        "    public void onPictureInPictureModeChanged(boolean active, Configuration configuration) {\n"
        "        super.onPictureInPictureModeChanged(active, configuration);\n"
        "        inPictureInPicture = active;\n"
        "        if (playerView != null) {\n"
        "            playerView.setUseController(!active);\n"
        "            if (active) playerView.hideController();\n"
        "        }\n"
        "        if (topOverlay != null) topOverlay.setVisibility(active ? View.GONE : View.VISIBLE);\n"
        "        if (errorCard != null && active) errorCard.setVisibility(View.GONE);\n"
        "        log.event(interaction, active ? \"PIP-ENTERED\" : \"PIP-EXITED\", \"trigger=BACK\");\n"
        "    }\n\n"
        "    private void buildUi() {\n",
    )
    replace_once(
        path,
        "        LinearLayout top = new LinearLayout(this);\n        top.setOrientation(LinearLayout.VERTICAL);\n",
        "        LinearLayout top = new LinearLayout(this);\n        topOverlay = top;\n        top.setOrientation(LinearLayout.VERTICAL);\n",
    )
    replace_once(path, 'setUserAgent("ProjectLumen/13.1.43 Media3")', 'setUserAgent("ProjectLumen/13.2.0-RC5 Media3")')


def patch_playlist_protocol_recovery() -> None:
    path = "app/src/main/java/com/projectlumen/pilot/robust/PlaylistRepository.java"
    replace_once(
        path,
        "    List<Channel> importUrl(String name, String sourceUrl, Progress progress) throws Exception {\n"
        "        URL url = new URL(sourceUrl);\n",
        "    List<Channel> importUrl(String name, String sourceUrl, Progress progress) throws Exception {\n"
        "        try {\n"
        "            return importUrlOnce(name, sourceUrl, progress);\n"
        "        } catch (Exception failure) {\n"
        "            String fallback = httpCompatibilityUrl(sourceUrl, failure);\n"
        "            if (fallback == null) throw failure;\n"
        "            progress.update(\"IMPORT-PROTOCOL-FALLBACK\",\n"
        "                    \"Der Server nutzt auf diesem Port kein TLS. Ein kontrollierter HTTP-Kompatibilitätsversuch startet.\");\n"
        "            return importUrlOnce(name, fallback, progress);\n"
        "        }\n"
        "    }\n\n"
        "    private List<Channel> importUrlOnce(String name, String sourceUrl, Progress progress) throws Exception {\n"
        "        URL url = new URL(sourceUrl);\n",
    )
    replace_once(
        path,
        '        connection.setRequestProperty("User-Agent", "ProjectLumen/13.1.41");',
        '        connection.setRequestProperty("User-Agent", "ProjectLumen/13.2.0-RC5");',
    )
    replace_once(
        path,
        "    List<Channel> importUri(String name, ContentResolver resolver, Uri uri,\n",
        "    private static String httpCompatibilityUrl(String sourceUrl, Exception failure) {\n"
        "        try {\n"
        "            URL parsed = new URL(sourceUrl);\n"
        "            if (!\"https\".equalsIgnoreCase(parsed.getProtocol())) return null;\n"
        "            int port = parsed.getPort();\n"
        "            if (port <= 0 || port == 443 || !isTlsProtocolMismatch(failure)) return null;\n"
        "            return new URL(\"http\", parsed.getHost(), port, parsed.getFile()).toString();\n"
        "        } catch (Exception ignored) {\n"
        "            return null;\n"
        "        }\n"
        "    }\n\n"
        "    private static boolean isTlsProtocolMismatch(Throwable failure) {\n"
        "        Throwable current = failure;\n"
        "        for (int depth = 0; current != null && depth < 8; depth++, current = current.getCause()) {\n"
        "            String message = current.getMessage();\n"
        "            if (message == null) continue;\n"
        "            String normalized = message.toLowerCase(java.util.Locale.ROOT);\n"
        "            if (normalized.contains(\"unable to parse tls packet header\")\n"
        "                    || normalized.contains(\"not an ssl/tls record\")\n"
        "                    || normalized.contains(\"wrong version number\")\n"
        "                    || normalized.contains(\"plaintext connection\")\n"
        "                    || normalized.contains(\"unrecognized ssl message\")) return true;\n"
        "        }\n"
        "        return false;\n"
        "    }\n\n"
        "    List<Channel> importUri(String name, ContentResolver resolver, Uri uri,\n",
    )


def patch_responsive_header() -> None:
    path = "app/src/main/java/com/projectlumen/pilot/robust/MainActivity.java"
    old = '''        Button diagnostics = actionButton("System", false);\n        diagnostics.setOnClickListener(v -> startActivity(\n                new Intent(this, DiagnosticsActivity.class)));\n        header.addView(diagnostics, new LinearLayout.LayoutParams(-2, dp(tv() ? 43 : 37)));\n\n        sourceButton = actionButton("+ Quelle", true);\n        sourceButton.setEnabled(false);\n        sourceButton.setOnClickListener(v -> showSourceMenu());\n        LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(\n                -2, dp(tv() ? 43 : 37));\n        sourceParams.setMargins(dp(7), 0, 0, 0);\n        header.addView(sourceButton, sourceParams);\n        root.addView(header);\n'''
    new = '''        Button diagnostics = actionButton("System", false);\n        diagnostics.setOnClickListener(v -> startActivity(\n                new Intent(this, DiagnosticsActivity.class)));\n\n        sourceButton = actionButton("+ Quelle", true);\n        sourceButton.setEnabled(false);\n        sourceButton.setOnClickListener(v -> showSourceMenu());\n\n        boolean compactPhone = !tv()\n                && getResources().getDisplayMetrics().widthPixels < dp(560);\n        if (!compactPhone) {\n            header.addView(diagnostics, new LinearLayout.LayoutParams(-2, dp(tv() ? 43 : 37)));\n            LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(\n                    -2, dp(tv() ? 43 : 37));\n            sourceParams.setMargins(dp(7), 0, 0, 0);\n            header.addView(sourceButton, sourceParams);\n            root.addView(header);\n        } else {\n            root.addView(header);\n            LinearLayout phoneActions = new LinearLayout(this);\n            phoneActions.setOrientation(LinearLayout.HORIZONTAL);\n            LinearLayout.LayoutParams systemParams = new LinearLayout.LayoutParams(0, dp(42), 1f);\n            phoneActions.addView(diagnostics, systemParams);\n            LinearLayout.LayoutParams sourceParams = new LinearLayout.LayoutParams(0, dp(42), 1f);\n            sourceParams.setMargins(dp(8), 0, 0, 0);\n            phoneActions.addView(sourceButton, sourceParams);\n            LinearLayout.LayoutParams actionRowParams = new LinearLayout.LayoutParams(-1, dp(42));\n            actionRowParams.setMargins(0, dp(8), 0, 0);\n            root.addView(phoneActions, actionRowParams);\n        }\n'''
    replace_once(path, old, new)
    replace_once(
        path,
        '        search.setHint("Sender, Film, Serie oder Kategorie suchen");',
        '        search.setHint(tv() ? "Sender, Film, Serie oder Kategorie suchen" : "Inhalte suchen");',
    )


def verify() -> None:
    build = read("app/build.gradle")
    manifest = read("app/src/main/AndroidManifest.xml")
    player = read("app/src/main/java/com/projectlumen/pilot/robust/PlayerActivity.java")
    repository = read("app/src/main/java/com/projectlumen/pilot/robust/PlaylistRepository.java")
    main = read("app/src/main/java/com/projectlumen/pilot/robust/MainActivity.java")
    required = {
        "version": "13.2.0-rc5-stable49-recovery" in build,
        "pip_manifest": 'android:supportsPictureInPicture="true"' in manifest,
        "pip_back": 'enterBackPictureInPicture()' in player and 'trigger=BACK' in player,
        "tls_fallback": 'IMPORT-PROTOCOL-FALLBACK' in repository,
        "responsive_header": 'compactPhone' in main,
    }
    missing = [name for name, ok in required.items() if not ok]
    if missing:
        raise RuntimeError(f"RC5 patch verification failed: {missing}")
    print("RC5 patch verification passed:", ", ".join(required))


def main() -> None:
    patch_build_config()
    patch_manifest()
    patch_player()
    patch_playlist_protocol_recovery()
    patch_responsive_header()
    verify()


if __name__ == "__main__":
    main()
