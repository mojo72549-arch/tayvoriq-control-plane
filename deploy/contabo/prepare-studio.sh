#!/usr/bin/env bash
set -euo pipefail

studio_dir=${1:?Pass the Studio checkout directory}
venv_dir=${TAYVORIQ_VENV:-/var/cache/tayvoriq/venv}
python -c 'import sys; assert sys.version_info[:2] == (3, 11), "Studio requires Python 3.11"'
mkdir -p "$venv_dir"
python -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip
requirements=$(mktemp)
trap 'rm -f "$requirements"' EXIT
python - "$studio_dir/requirements.txt" "$requirements" <<'PY'
import sys
from pathlib import Path

lines = Path(sys.argv[1]).read_text(encoding='utf-8').splitlines()
filtered = [line for line in lines if 'chatterbox' not in line.casefold()]
if len(lines) == len(filtered):
    raise SystemExit('Pinned Chatterbox dependency missing from Studio')
Path(sys.argv[2]).write_text('\n'.join(filtered) + '\n', encoding='utf-8')
PY
"$venv_dir/bin/python" -m pip install --index-url https://download.pytorch.org/whl/cpu \
    'torch==2.6.0' 'torchaudio==2.6.0'
"$venv_dir/bin/python" -m pip install -r "$requirements" pytest
"$venv_dir/bin/python" -m pip install \
    'git+https://github.com/resemble-ai/chatterbox.git@65b18437192794391a0308a8f705b1e33e633948'
"$venv_dir/bin/python" -m pip check
