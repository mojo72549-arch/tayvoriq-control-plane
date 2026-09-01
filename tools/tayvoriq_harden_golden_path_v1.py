#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

WORKFLOW = Path(".github/workflows/tayvoriq-deliver-video-now.yml")

RESOLVE_BLOCK = '''      - name: Resolve immutable Production Green implementation
        id: production_green
        shell: bash
        run: |
          set -euo pipefail
          python tools/tayvoriq_resolve_production_green_v1.py

      - name: Validate immutable implementation policy
        shell: bash
        run: |
          set -euo pipefail
          python tools/tayvoriq_harden_golden_path_v1.py --check

'''

MUTABLE_CHECKOUT = '''      - name: Checkout implementation
        uses: actions/checkout@v4
        with:
          repository: mojo72549-arch/shorts-agent-studio
          ref: feature/multi-platform-distribution-package
          token: ${{ secrets.PRIVATE_REPO_TOKEN }}
          path: implementation
          fetch-depth: 1
'''

IMMUTABLE_CHECKOUT = '''      - name: Checkout implementation
        uses: actions/checkout@v4
        with:
          repository: mojo72549-arch/shorts-agent-studio
          ref: ${{ steps.production_green.outputs.implementation_sha }}
          token: ${{ secrets.PRIVATE_REPO_TOKEN }}
          path: implementation
          fetch-depth: 1

      - name: Verify immutable implementation checkout
        shell: bash
        run: |
          set -euo pipefail
          actual=$(git -C implementation rev-parse HEAD)
          expected="${{ steps.production_green.outputs.implementation_sha }}"
          test "$actual" = "$expected" || { echo "IMMUTABLE_IMPLEMENTATION_CHECKOUT_FAILED: expected=$expected actual=$actual"; exit 1; }
          echo "Immutable implementation verified: $actual"
'''

OLD_CACHE = '''      - name: Restore pip dependency cache
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: tayvoriq-pip-v3-${{ runner.os }}-py311-${{ hashFiles('implementation/requirements.txt') }}-torch260-chatterbox-65b18437
          restore-keys: |
            tayvoriq-pip-v3-${{ runner.os }}-py311-
'''

NEW_CACHE = '''      - name: Clear stale pip wheel cache before production
        shell: bash
        run: |
          set -euo pipefail
          rm -rf ~/.cache/pip
          mkdir -p ~/.cache/pip
          df -h "$GITHUB_WORKSPACE"
'''

OLD_DEPS = '''          export PIP_DISABLE_PIP_VERSION_CHECK=1
          python -m pip install -r implementation/requirements.txt pytest -q
          python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.6.0" "torchaudio==2.6.0" -q
          python -m pip install "git+https://github.com/resemble-ai/chatterbox.git@65b18437192794391a0308a8f705b1e33e633948" -q
'''

NEW_DEPS = '''          export PIP_DISABLE_PIP_VERSION_CHECK=1
          python - <<'PY'
          from pathlib import Path
          source = Path('implementation/requirements.txt')
          target = Path('/tmp/tayvoriq-production-requirements.txt')
          lines = source.read_text(encoding='utf-8').splitlines()
          filtered = [line for line in lines if 'chatterbox' not in line.casefold()]
          if len(filtered) == len(lines):
              raise SystemExit('DEPENDENCY_POLICY_FAILED: pinned Chatterbox dependency was not found')
          target.write_text('\\n'.join(filtered) + '\\n', encoding='utf-8')
          if 'chatterbox' in target.read_text(encoding='utf-8').casefold():
              raise SystemExit('DEPENDENCY_POLICY_FAILED: Chatterbox remained in filtered requirements')
          PY
          python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.6.0" "torchaudio==2.6.0" -q
          python -m pip install --no-cache-dir -r /tmp/tayvoriq-production-requirements.txt pytest -q
          python -m pip install --no-cache-dir "git+https://github.com/resemble-ai/chatterbox.git@65b18437192794391a0308a8f705b1e33e633948" -q
          python - <<'PY'
          import torch
          version = str(torch.__version__)
          if version.split('+', 1)[0] != '2.6.0':
              raise SystemExit(f'DEPENDENCY_POLICY_FAILED: unexpected torch {version}')
          if torch.cuda.is_available():
              raise SystemExit('DEPENDENCY_POLICY_FAILED: CUDA runtime unexpectedly active on CPU production runner')
          print(f'TAYVORIQ_CPU_TORCH_VERIFIED:{version}')
          PY
'''

OLD_MANIFEST = '              "implementation_branch": "feature/multi-platform-distribution-package",\n'
NEW_MANIFEST = '''              "implementation_ref": sys.argv[2],
              "implementation_binding": "production-green-immutable-sha",
'''


def validate(text: str) -> None:
    failures: list[str] = []
    if MUTABLE_CHECKOUT in text:
        failures.append("mutable implementation checkout remains")
    if "Resolve immutable Production Green implementation" not in text:
        failures.append("production-green resolver step missing")
    if "python tools/tayvoriq_resolve_production_green_v1.py" not in text:
        failures.append("production-green resolver invocation missing")
    if "ref: ${{ steps.production_green.outputs.implementation_sha }}" not in text:
        failures.append("immutable implementation SHA ref missing")
    if "Verify immutable implementation checkout" not in text:
        failures.append("immutable checkout verification missing")
    if OLD_CACHE in text or "Restore pip dependency cache" in text:
        failures.append("stale pip cache restore remains")
    if OLD_DEPS in text or "python -m pip install -r implementation/requirements.txt pytest -q" in text:
        failures.append("unsafe unfiltered production dependency install remains")
    cpu_marker = 'python -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.6.0" "torchaudio==2.6.0" -q'
    chatterbox_marker = 'python -m pip install --no-cache-dir "git+https://github.com/resemble-ai/chatterbox.git@65b18437192794391a0308a8f705b1e33e633948" -q'
    if cpu_marker not in text:
        failures.append("CPU-only torch install missing")
    if chatterbox_marker not in text:
        failures.append("pinned Chatterbox install missing")
    if text.find(cpu_marker) > text.find(chatterbox_marker) >= 0:
        failures.append("Chatterbox is installed before CPU-only torch")
    if '"implementation_binding": "production-green-immutable-sha"' not in text:
        failures.append("production manifest immutable binding missing")
    if failures:
        raise SystemExit("GOLDEN_PATH_HARDENING_CHECK_FAILED:" + ";".join(failures))


def patch(text: str) -> str:
    if "Resolve immutable Production Green implementation" not in text:
        if MUTABLE_CHECKOUT not in text:
            raise SystemExit("PATCH_FAILED: expected mutable implementation checkout not found")
        text = text.replace(MUTABLE_CHECKOUT, RESOLVE_BLOCK + IMMUTABLE_CHECKOUT, 1)
    elif MUTABLE_CHECKOUT in text:
        raise SystemExit("PATCH_FAILED: resolver exists but mutable checkout remains")

    if OLD_CACHE in text:
        text = text.replace(OLD_CACHE, NEW_CACHE, 1)
    elif "Clear stale pip wheel cache before production" not in text:
        raise SystemExit("PATCH_FAILED: expected pip cache block not found")

    if OLD_DEPS in text:
        text = text.replace(OLD_DEPS, NEW_DEPS, 1)
    elif "tayvoriq-production-requirements.txt" not in text:
        raise SystemExit("PATCH_FAILED: expected dependency install block not found")

    if OLD_MANIFEST in text:
        text = text.replace(OLD_MANIFEST, NEW_MANIFEST, 1)
    elif '"implementation_binding": "production-green-immutable-sha"' not in text:
        raise SystemExit("PATCH_FAILED: expected manifest implementation branch marker not found")

    validate(text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if not WORKFLOW.is_file():
        raise SystemExit(f"GOLDEN_PATH_WORKFLOW_MISSING:{WORKFLOW}")
    current = WORKFLOW.read_text(encoding="utf-8")
    if args.check:
        validate(current)
        print("TAYVORIQ_GOLDEN_PATH_HARDENING_CHECK_PASSED")
        return 0
    hardened = patch(current)
    if hardened != current:
        WORKFLOW.write_text(hardened, encoding="utf-8")
        print("TAYVORIQ_GOLDEN_PATH_HARDENING_APPLIED")
    else:
        print("TAYVORIQ_GOLDEN_PATH_ALREADY_HARDENED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
