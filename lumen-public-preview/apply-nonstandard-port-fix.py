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
        raise SystemExit("usage: apply-nonstandard-port-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    text = replace_once(
        text,
        '''                                "Code IMPORT-HTTP-RECOVERY\\n"
                                        + "Die Quelle wurde ausdrücklich mit HTTP eingegeben. Der Server hat zwischendurch fälschlich HTTPS verwendet.\\n"
                                        + "Lumen setzt den Abruf automatisch über HTTP fort.\\n\\n"
                                        + "Adresse und Zugangsdaten bleiben ausgeblendet.",''',
        '''                                "Code IMPORT-PROTOCOL-RECOVERY\\n"
                                        + "Der angesprochene Nichtstandard-Port liefert kein TLS.\\n"
                                        + "Lumen setzt den Abruf einmalig über HTTP fort.\\n\\n"
                                        + "Adresse und Zugangsdaten bleiben ausgeblendet.",''',
        "protocol recovery diagnostic",
    )

    text = replace_once(
        text,
        '''        if (recoveryAlreadyUsed || !isTlsPlaintextMismatch(failure)) return null;
        if (!"http".equalsIgnoreCase(original.getProtocol())) return null;
        if (!"https".equalsIgnoreCase(current.getProtocol())) return null;

        int recoveryPort = current.getPort();''',
        '''        if (recoveryAlreadyUsed || !isTlsPlaintextMismatch(failure)) return null;
        if (!"https".equalsIgnoreCase(current.getProtocol())) return null;

        boolean originalHttp = "http".equalsIgnoreCase(original.getProtocol());
        boolean explicitNonStandardHttps = "https".equalsIgnoreCase(original.getProtocol())
                && original.getPort() > 0
                && original.getPort() != 443;
        if (!originalHttp && !explicitNonStandardHttps) return null;

        int recoveryPort = current.getPort();''',
        "direct HTTPS nonstandard-port recovery guard",
    )

    text = replace_once(
        text,
        'text("v13.1.12"',
        'text("v13.1.13"',
        "visible version",
    )
    text = text.replace("ProjectLumen/13.1.11 Android", "ProjectLumen/13.1.13 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132200", "versionCode 132300", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.12-large-library-preview'",
        "versionName '13.1.13-nonstandard-port-recovery-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.12 Preview", "Project Lumen 13.1.13 Preview")
    strings_text = strings_text.replace("Project Lumen 13.1.11 Preview", "Project Lumen 13.1.13 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.12", "Project Lumen 13.1.13")
        readme_text = readme_text.replace("Project Lumen 13.1.11", "Project Lumen 13.1.13")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "direct nonstandard HTTPS recovery": "explicitNonStandardHttps" in text,
        "protocol recovery diagnostic": "IMPORT-PROTOCOL-RECOVERY" in text,
        "standard port 443 protected": "recoveryPort == 443" in text and "original.getPort() != 443" in text,
        "single recovery guard": "recoveryAlreadyUsed" in text,
        "large library paging retained": "LIVE_PAGE_SIZE = 200" in text,
        "version 13.1.13": 'text("v13.1.13"' in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.13 nonstandard-port protocol recovery applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
