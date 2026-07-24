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
        raise SystemExit("usage: apply-import-start-watchdog-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "import java.util.concurrent.Executors;\n",
        "import java.util.concurrent.Executors;\nimport java.util.concurrent.atomic.AtomicBoolean;\n",
        "AtomicBoolean import",
    )

    text = replace_once(
        text,
        "    private final ExecutorService worker = Executors.newSingleThreadExecutor();\n",
        "    private final ExecutorService importWorker = Executors.newSingleThreadExecutor();\n"
        "    private final ExecutorService importFallbackWorker = Executors.newSingleThreadExecutor();\n"
        "    private final ExecutorService storageWorker = Executors.newSingleThreadExecutor();\n",
        "executor separation",
    )

    old_import = '''        worker.execute(() -> {
            File plain = new File(getCacheDir(), "playlist-download.tmp");
            try {
                downloadToFile(sourceUrl, plain);
                parseAndActivate(name, plain, origin);
            } catch (Exception e) {
                plain.delete();
                appendDiagnosticLog("ERROR", "Import fehlgeschlagen", "Code=" + classify(e), e);
                runOnUiThread(() -> showDiagnostic("Import fehlgeschlagen", "Code " + classify(e) + "\\n" + safeMessage(e) + "\\n\\nDer bisherige Stand wurde nicht ersetzt.", false));
            }
        });
'''
    new_import = '''        long queuedAt = System.currentTimeMillis();
        AtomicBoolean importClaimed = new AtomicBoolean(false);
        Runnable importBody = () -> {
            File plain = new File(getCacheDir(), "playlist-download.tmp");
            try {
                downloadToFile(sourceUrl, plain);
                parseAndActivate(name, plain, origin);
            } catch (Exception e) {
                plain.delete();
                appendDiagnosticLog("ERROR", "Import fehlgeschlagen", "Code=" + classify(e), e);
                runOnUiThread(() -> showDiagnostic("Import fehlgeschlagen", "Code " + classify(e) + "\\n" + safeMessage(e) + "\\n\\nDer bisherige Stand wurde nicht ersetzt.", false));
            }
        };
        importWorker.execute(() -> {
            if (!importClaimed.compareAndSet(false, true)) return;
            appendDiagnosticLog("IMPORT", "Import-Worker gestartet",
                    "WartezeitMs=" + (System.currentTimeMillis() - queuedAt) + " · Pfad=primaer", null);
            importBody.run();
        });
        mainHandler.postDelayed(() -> {
            if (!importClaimed.compareAndSet(false, true)) return;
            appendDiagnosticLog("RECOVERY", "Import-Worker startete nicht rechtzeitig",
                    "Code=IMPORT-WORKER-START-TIMEOUT · WartezeitMs=" + (System.currentTimeMillis() - queuedAt)
                            + " · Fallback=separater Executor", null);
            showDiagnostic("Verbindung wird gestartet",
                    "Code IMPORT-WORKER-RECOVERY\\n"
                            + "Der normale Hintergrundauftrag war blockiert. Lumen startet den Import jetzt unabhängig davon neu.",
                    false);
            importFallbackWorker.execute(() -> {
                appendDiagnosticLog("IMPORT", "Import-Fallback gestartet",
                        "WartezeitMs=" + (System.currentTimeMillis() - queuedAt) + " · Pfad=fallback", null);
                importBody.run();
            });
        }, 3_000L);
'''
    text = replace_once(text, old_import, new_import, "network import submission")

    text = replace_once(
        text,
        "            worker.execute(() -> {\n                File plain = new File(getCacheDir(), \"playlist-local.tmp\");",
        "            importWorker.execute(() -> {\n                File plain = new File(getCacheDir(), \"playlist-local.tmp\");",
        "local import executor",
    )
    text = replace_once(
        text,
        "        worker.execute(() -> {\n            File plain = new File(getCacheDir(), \"playlist-restore.tmp\");",
        "        storageWorker.execute(() -> {\n            File plain = new File(getCacheDir(), \"playlist-restore.tmp\");",
        "storage restore executor",
    )

    text = replace_once(
        text,
        "        worker.shutdownNow();\n        mainHandler.removeCallbacksAndMessages(null);",
        "        importWorker.shutdownNow();\n"
        "        importFallbackWorker.shutdownNow();\n"
        "        storageWorker.shutdownNow();\n"
        "        mainHandler.removeCallbacksAndMessages(null);",
        "executor shutdown",
    )

    text = text.replace('text("v13.1.20"', 'text("v13.1.21"')
    text = text.replace('value.append("App=").append("13.1.20")', 'value.append("App=").append("13.1.21")')
    text = text.replace("ProjectLumen/13.1.20 Android", "ProjectLumen/13.1.21 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 133000", "versionCode 133100", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.20-channel-adapter-fix-preview'",
        "versionName '13.1.21-import-start-watchdog-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.20 Preview", "Project Lumen 13.1.21 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.20", "Project Lumen 13.1.21")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "separate import executor": "ExecutorService importWorker" in text,
        "separate storage executor": "ExecutorService storageWorker" in text,
        "fallback executor": "ExecutorService importFallbackWorker" in text,
        "three-second watchdog": "IMPORT-WORKER-START-TIMEOUT" in text and "3_000L" in text,
        "restore isolated": "storageWorker.execute(() ->" in text,
        "primary import logged": "Import-Worker gestartet" in text,
        "version 13.1.21": 'text("v13.1.21"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.21 import-start watchdog patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
