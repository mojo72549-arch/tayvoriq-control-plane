#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-media3-sdk35-compat-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    gradle = root / "app/build.gradle"
    java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"

    gradle_text = gradle.read_text(encoding="utf-8")
    old_version = 'def media3_version = "1.10.1"'
    new_version = 'def media3_version = "1.9.4"'
    count = gradle_text.count(old_version)
    if count != 1:
        raise SystemExit(f"expected one Media3 1.10.1 declaration, found {count}")
    gradle.write_text(gradle_text.replace(old_version, new_version, 1), encoding="utf-8")

    java_text = java.read_text(encoding="utf-8")
    legacy = "if (diagnosticPanel == null || videoView != null) return;"
    replacement = "if (diagnosticPanel == null || playerView != null) return;"
    count = java_text.count(legacy)
    if count != 1:
        raise SystemExit(f"expected one final diagnostic VideoView reference, found {count}")
    java_text = java_text.replace(legacy, replacement, 1)
    if "videoView" in java_text or "VideoView" in java_text:
        raise SystemExit("legacy VideoView reference remains after compatibility repair")
    java.write_text(java_text, encoding="utf-8")

    print("Pinned Media3 to 1.9.4 for compileSdk 35 / AGP 8.8.2 compatibility")
    print("Removed final legacy VideoView reference from diagnostics guard")


if __name__ == "__main__":
    main()
