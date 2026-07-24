#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-media3-sdk35-compat-fix.py <project-root>")
    gradle = pathlib.Path(sys.argv[1]) / "app/build.gradle"
    text = gradle.read_text(encoding="utf-8")
    old = 'def media3_version = "1.10.1"'
    new = 'def media3_version = "1.9.4"'
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one Media3 1.10.1 declaration, found {count}")
    gradle.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("Pinned Media3 to 1.9.4 for compileSdk 35 / AGP 8.8.2 compatibility")


if __name__ == "__main__":
    main()
