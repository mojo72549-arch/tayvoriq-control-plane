#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-diagnostics-compile-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    text = main_java.read_text(encoding="utf-8")

    if "import java.io.ByteArrayOutputStream;" not in text:
        marker = "import java.io.InputStreamReader;\n"
        if marker not in text:
            raise SystemExit("ByteArrayOutputStream import marker not found")
        text = text.replace(marker, "import java.io.ByteArrayOutputStream;\n" + marker, 1)

    text = text.replace("BuildConfig.VERSION_NAME", '"13.1.14"')
    text = text.replace("MediaStore.Downloads.DISPLAY_NAME", "MediaStore.MediaColumns.DISPLAY_NAME")
    text = text.replace("MediaStore.Downloads.MIME_TYPE", "MediaStore.MediaColumns.MIME_TYPE")
    text = text.replace("MediaStore.Downloads.RELATIVE_PATH", "MediaStore.MediaColumns.RELATIVE_PATH")
    text = text.replace("MediaStore.Downloads.IS_PENDING", "MediaStore.MediaColumns.IS_PENDING")

    main_java.write_text(text, encoding="utf-8")

    checks = {
        "ByteArrayOutputStream imported": "import java.io.ByteArrayOutputStream;" in text,
        "no BuildConfig dependency": "BuildConfig.VERSION_NAME" not in text,
        "MediaColumns used": "MediaStore.MediaColumns.DISPLAY_NAME" in text,
        "download collection retained": "MediaStore.Downloads.EXTERNAL_CONTENT_URI" in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("compile fix verification failed: " + ", ".join(failed))

    print("Project Lumen diagnostics compile fix applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
