#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import re
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: apply-channel-adapter-crash-fix.py <project-root>")

    root = pathlib.Path(sys.argv[1])
    main_java = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
    gradle = root / "app/build.gradle"
    strings = root / "app/src/main/res/values/strings.xml"
    readme = root / "README.md"

    text = main_java.read_text(encoding="utf-8")

    # android.R.layout.simple_list_item_2 is a TwoLineListItem container, not a
    # TextView. The three-argument ArrayAdapter constructor treats the layout
    # root as the TextView and therefore crashes before ChannelAdapter.getView
    # can populate text1/text2. Explicitly bind the adapter to text1.
    pattern = re.compile(
        r"super\(\s*context\s*,\s*android\.R\.layout\.simple_list_item_2\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s*\);"
    )
    text, replacements = pattern.subn(
        r"super(context, android.R.layout.simple_list_item_2, android.R.id.text1, \1);",
        text,
        count=1,
    )
    if replacements != 1:
        raise SystemExit(
            "ChannelAdapter constructor: expected one three-argument simple_list_item_2 constructor, "
            f"found {replacements}"
        )

    text = text.replace('text("v13.1.19"', 'text("v13.1.20"')
    text = text.replace('value.append("App=").append("13.1.19")', 'value.append("App=").append("13.1.20")')
    text = text.replace("ProjectLumen/13.1.19 Android", "ProjectLumen/13.1.20 Android")
    main_java.write_text(text, encoding="utf-8")

    gradle_text = gradle.read_text(encoding="utf-8")
    gradle_text = replace_once(gradle_text, "versionCode 132900", "versionCode 133000", "versionCode")
    gradle_text = replace_once(
        gradle_text,
        "versionName '13.1.19-account-status-preview'",
        "versionName '13.1.20-channel-adapter-fix-preview'",
        "versionName",
    )
    gradle.write_text(gradle_text, encoding="utf-8")

    strings_text = strings.read_text(encoding="utf-8")
    strings_text = strings_text.replace("Project Lumen 13.1.19 Preview", "Project Lumen 13.1.20 Preview")
    strings.write_text(strings_text, encoding="utf-8")

    if readme.exists():
        readme_text = readme.read_text(encoding="utf-8")
        readme_text = readme_text.replace("Project Lumen 13.1.19", "Project Lumen 13.1.20")
        readme.write_text(readme_text, encoding="utf-8")

    checks = {
        "TwoLineListItem text field explicitly bound": "android.R.layout.simple_list_item_2, android.R.id.text1" in text,
        "unsafe three-argument constructor removed": pattern.search(text) is None,
        "ChannelAdapter retained": "class ChannelAdapter" in text,
        "version 13.1.20": 'text("v13.1.20"' in text,
        "updated user agent": "ProjectLumen/13.1.20 Android" in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise SystemExit("patch verification failed: " + ", ".join(failed))

    print("Project Lumen 13.1.20 ChannelAdapter crash patch applied")
    for name in checks:
        print(f"OK: {name}")


if __name__ == "__main__":
    main()
