#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-xtream-compile-fix.py <project-root>")

    main_java = pathlib.Path(sys.argv[1]) / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    text = main_java.read_text(encoding="utf-8")
    old = 'shortHash(blockedPlaylistUrl.getHost())'
    new = 'Integer.toHexString(blockedPlaylistUrl.getHost().toLowerCase(Locale.ROOT).hashCode())'
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Xtream host-id compile fix expected one match, found {count}")
    text = text.replace(old, new, 1)
    main_java.write_text(text, encoding="utf-8")
    print("Project Lumen 13.1.18 Xtream host-id compile fix applied")


if __name__ == "__main__":
    main()
