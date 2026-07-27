#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else "project-lumen-preview")
main = root / "app/src/main/java/com/projectlumen/publicpreview/MainActivity.java"
if not main.exists():
    raise SystemExit("MainActivity.java missing")
text = main.read_text(encoding="utf-8")
if "import android.content.SharedPreferences;" not in text:
    marker = "import android.content.Intent;\n"
    if marker not in text:
        raise SystemExit("Intent import marker missing")
    text = text.replace(marker, marker + "import android.content.SharedPreferences;\n", 1)
main.write_text(text, encoding="utf-8")
if "import android.content.SharedPreferences;" not in text:
    raise SystemExit("SharedPreferences import not applied")
print("13.1.38 compile import fix applied")
