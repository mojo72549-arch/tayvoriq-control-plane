#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
pkg = root / "app/src/main/java/com/projectlumen/publicpreview"
main = pkg / "MainActivity.java"
gradle = root / "app/build.gradle"
manifest = root / "app/src/main/AndroidManifest.xml"
support = Path(__file__).resolve().parent / "r4-src"

for path in (main, gradle, manifest, support / "ProfileStore.java",
             support / "ParentalPolicy.java", support / "ProfilesActivity.java"):
    if not path.exists():
        raise SystemExit(f"missing R4 input: {path}")

pkg.mkdir(parents=True, exist_ok=True)
for name in ("ProfileStore.java", "ParentalPolicy.java", "ProfilesActivity.java"):
    shutil.copy2(support / name, pkg / name)

manifest_text = manifest.read_text(encoding="utf-8")
if "ProfilesActivity" not in manifest_text:
    activity = '''        <activity
            android:name=".ProfilesActivity"
            android:exported="false"
            android:label="Profile &amp; Jugendschutz"
            android:screenOrientation="unspecified" />
'''
    if "</application>" not in manifest_text:
        raise SystemExit("manifest application marker missing")
    manifest_text = manifest_text.replace("</application>", activity + "    </application>")
manifest.write_text(manifest_text, encoding="utf-8")

gradle_text = gradle.read_text(encoding="utf-8")
gradle_text = re.sub(r"versionCode\s+\d+", "versionCode 133900", gradle_text, count=1)
gradle_text = re.sub(r"versionName\s+'[^']+'",
                     "versionName '13.1.29-r4-profiles-pin-tv-preview'",
                     gradle_text, count=1)
gradle.write_text(gradle_text, encoding="utf-8")

source = main.read_text(encoding="utf-8")
source = source.replace('text("v13.1.28"', 'text("v13.1.29"')
source = source.replace('text("v13.1.27"', 'text("v13.1.29"')

if "LUMEN_MENU_PROFILES" not in source:
    integration = r'''
    private static final int LUMEN_MENU_PROFILES = 0x4C554D50;

    private void openLumenProfiles() {
        startActivity(new android.content.Intent(this, ProfilesActivity.class));
    }

    private void refreshLumenProfileTitle() {
        try {
            setTitle("Project Lumen · " + ProfileStore.activeName(this));
        } catch (Throwable ignored) {
            setTitle("Project Lumen");
        }
    }

    @Override
    public boolean onCreateOptionsMenu(android.view.Menu menu) {
        android.view.MenuItem item = menu.add(android.view.Menu.NONE,
                LUMEN_MENU_PROFILES, android.view.Menu.NONE,
                "Profile & Jugendschutz");
        item.setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_IF_ROOM);
        return true;
    }

    @Override
    public boolean onOptionsItemSelected(android.view.MenuItem item) {
        if (item.getItemId() == LUMEN_MENU_PROFILES) {
            openLumenProfiles();
            return true;
        }
        return super.onOptionsItemSelected(item);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refreshLumenProfileTitle();
    }

    @Override
    public boolean onKeyLongPress(int keyCode, android.view.KeyEvent event) {
        if (keyCode == android.view.KeyEvent.KEYCODE_MENU ||
                keyCode == android.view.KeyEvent.KEYCODE_PROG_RED) {
            openLumenProfiles();
            return true;
        }
        return super.onKeyLongPress(keyCode, event);
    }
'''
    if re.search(r"\bprotected\s+void\s+onResume\s*\(", source):
        integration = integration.replace('''    @Override
    protected void onResume() {
        super.onResume();
        refreshLumenProfileTitle();
    }

''', '')
        source = re.sub(
            r"(protected\s+void\s+onResume\s*\([^)]*\)\s*\{)",
            r"\1\n        refreshLumenProfileTitle();",
            source, count=1)

    if re.search(r"\bboolean\s+onCreateOptionsMenu\s*\(", source):
        generated = re.search(
            r"    @Override\n    public boolean onCreateOptionsMenu[\s\S]*?\n    }\n",
            integration)
        if generated:
            integration = integration.replace(generated.group(0), "")
        source = re.sub(
            r"(boolean\s+onCreateOptionsMenu\s*\(android\.view\.Menu\s+menu\)\s*\{)",
            r'\1\n        menu.add(android.view.Menu.NONE, LUMEN_MENU_PROFILES, android.view.Menu.NONE, "Profile & Jugendschutz");',
            source, count=1)

    if re.search(r"\bboolean\s+onOptionsItemSelected\s*\(", source):
        generated = re.search(
            r"    @Override\n    public boolean onOptionsItemSelected[\s\S]*?\n    }\n",
            integration)
        if generated:
            integration = integration.replace(generated.group(0), "")
        source = re.sub(
            r"(boolean\s+onOptionsItemSelected\s*\(android\.view\.MenuItem\s+item\)\s*\{)",
            r"\1\n        if (item.getItemId() == LUMEN_MENU_PROFILES) { openLumenProfiles(); return true; }",
            source, count=1)

    end = source.rfind("}")
    if end < 0:
        raise SystemExit("MainActivity class end missing")
    source = source[:end] + integration + "\n" + source[end:]


def method_ranges(text: str):
    pattern = re.compile(
        r"(?m)^\s*(?:public|private|protected)\s+(?:static\s+)?"
        r"[\w<>\[\], ?]+\s+(\w+)\s*\([^;{}]*\)\s*\{")
    for match in pattern.finditer(text):
        depth = 0
        cursor = match.end() - 1
        while cursor < len(text):
            if text[cursor] == "{":
                depth += 1
            elif text[cursor] == "}":
                depth -= 1
                if depth == 0:
                    yield match.group(1), match.start(), cursor + 1
                    break
            cursor += 1


if "PARENTAL-R4-FILTER" not in source:
    edits = []
    for name, start, end in method_ranges(source):
        lowered = name.lower()
        if name not in {"mediaPage", "globalSearchPage", "favoritesPage",
                        "epgPage", "startPage", "searchPage"} and not any(
                token in lowered for token in ("media", "search", "favorite")):
            continue
        block = source[start:end]
        for loop in re.finditer(
                r"for\s*\(\s*Channel\s+(\w+)\s*:\s*[^)]+\)\s*\{", block):
            variable = loop.group(1)
            edits.append((start + loop.end(),
                          "\n            if (!ParentalPolicy.isAllowed(this, " +
                          variable + ")) continue; // PARENTAL-R4-FILTER"))
    for position, insertion in sorted(edits, reverse=True):
        source = source[:position] + insertion + source[position:]
    if not edits:
        end = source.rfind("}")
        hook = '''
    private boolean lumenProfileAllows(Object item) {
        return ParentalPolicy.isAllowed(this, item); // PARENTAL-R4-FILTER
    }
'''
        source = source[:end] + hook + source[end:]

source = re.sub(
    r'getSharedPreferences\("([^"]*favorite[^"]*)"\s*,',
    r'getSharedPreferences(ProfileStore.favoriteNamespace(this),',
    source, flags=re.I)
source = re.sub(
    r'getSharedPreferences\("([^"]*history[^"]*)"\s*,',
    r'getSharedPreferences(ProfileStore.historyNamespace(this),',
    source, flags=re.I)

main.write_text(source, encoding="utf-8")

checks = {
    "version": "v13.1.29" in source,
    "menu": "LUMEN_MENU_PROFILES" in source,
    "activity": "ProfilesActivity" in manifest.read_text(encoding="utf-8"),
    "keystore": "AndroidKeyStore" in (pkg / "ProfileStore.java").read_text(encoding="utf-8"),
    "pbkdf2": "PBKDF2WithHmacSHA256" in (pkg / "ProfileStore.java").read_text(encoding="utf-8"),
    "parental": "PARENTAL-R4-FILTER" in source,
    "versionCode": "versionCode 133900" in gradle.read_text(encoding="utf-8"),
}
missing = [name for name, passed in checks.items() if not passed]
if missing:
    raise SystemExit("R4 static checks failed: " + ", ".join(missing))
print("R4 integration applied: " + ", ".join(checks))
