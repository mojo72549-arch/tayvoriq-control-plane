#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import sys


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-xtream-source-api-compile-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    text = main_java.read_text(encoding="utf-8")

    old = '"Schema=" + active.getProtocol() + " · Port=" + effectivePort(active) + " · Host-ID=" + hashHost(active.getHost()),'
    new = '"Schema=" + active.getProtocol() + " · Port=" + (active.getPort() > 0 ? active.getPort() : active.getDefaultPort()) + " · Host-ID=" + shortHostHash(active.getHost()),'
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"compile helper replacement expected once, found {count}")
    text = text.replace(old, new, 1)
    main_java.write_text(text, encoding="utf-8")

    checks = {
        "existing host hash helper used": "shortHostHash(active.getHost())" in text,
        "port resolved from URL": "active.getDefaultPort()" in text,
        "undefined effectivePort removed": "effectivePort(active)" not in text,
        "undefined hashHost removed": "hashHost(active.getHost())" not in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("compile patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.18 Source API compile fix applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
