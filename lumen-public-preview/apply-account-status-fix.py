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
        raise SystemExit("usage: apply-account-status-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    old_status_block = r'''        appendDiagnosticLog(
                "RECOVERY",
                "Xtream-Anmeldung bestätigt",
                "Status=" + sanitizeLogText(accountStatus),
                null);

        java.util.Map<String, String> liveCategories = readXtreamCategories(
'''
    new_status_block = r'''        String normalizedAccountStatus = accountStatus == null
                ? ""
                : accountStatus.trim().toLowerCase(Locale.ROOT);
        if ("expired".equals(normalizedAccountStatus)) {
            appendDiagnosticLog(
                    "RECOVERY",
                    "Xtream-Zugang abgelaufen",
                    "Status=" + sanitizeLogText(accountStatus),
                    null);
            throw new ImportFailure(
                    "IMPORT-SUBSCRIPTION-EXPIRED",
                    "Der Anbieter erkennt die Zugangsdaten, meldet den Zugang jedoch als abgelaufen (Status: Expired). Bitte die Freischaltung beim Anbieter prüfen oder verlängern. Lumen kann ohne aktiven Zugang keine Senderliste laden.",
                    false);
        }
        if ("disabled".equals(normalizedAccountStatus)
                || "banned".equals(normalizedAccountStatus)) {
            appendDiagnosticLog(
                    "RECOVERY",
                    "Xtream-Zugang deaktiviert",
                    "Status=" + sanitizeLogText(accountStatus),
                    null);
            throw new ImportFailure(
                    "IMPORT-ACCOUNT-INACTIVE",
                    "Der Anbieter erkennt die Zugangsdaten, meldet den Zugang jedoch als deaktiviert (Status: "
                            + sanitizeLogText(accountStatus)
                            + "). Bitte die Freischaltung direkt beim Anbieter prüfen.",
                    false);
        }
        appendDiagnosticLog(
                "RECOVERY",
                "Xtream-Anmeldung bestätigt",
                "Status=" + sanitizeLogText(accountStatus),
                null);

        java.util.Map<String, String> liveCategories = readXtreamCategories(
'''
    text = replace_once(text, old_status_block, new_status_block, "Xtream account-state handling")

    text = text.replace('text("v13.1.18"', 'text("v13.1.19"')
    text = text.replace('value.append("App=").append("13.1.18")', 'value.append("App=").append("13.1.19")')
    text = text.replace("ProjectLumen/13.1.18 Android", "ProjectLumen/13.1.19 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132800", "versionCode 132900", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.18-xtream-api-recovery-preview'",
        "versionName '13.1.19-account-status-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.18 Preview", "Project Lumen 13.1.19 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.18", "Project Lumen 13.1.19")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "expired status code": "IMPORT-SUBSCRIPTION-EXPIRED" in text,
        "inactive status code": "IMPORT-ACCOUNT-INACTIVE" in text,
        "stops before catalogue calls": text.index("IMPORT-SUBSCRIPTION-EXPIRED") < text.index("action=get_live_categories"),
        "clear expired message": "Status: Expired" in text,
        "version 13.1.19": 'text("v13.1.19"' in text,
        "updated user agent": "ProjectLumen/13.1.19 Android" in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.19 account-status patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
