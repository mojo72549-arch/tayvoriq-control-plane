#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

GOLDEN = Path('.github/workflows/tayvoriq-deliver-video-now.yml')
CONTINUITY = Path('.github/workflows/tayvoriq-deterministic-codefix-continuity.yml')

OLD_DISPATCH = "  workflow_dispatch:\n"
NEW_DISPATCH = '''  workflow_dispatch:
    inputs:
      failed_run_id:
        description: Exact failed Golden Path run to finalize
        required: false
        type: string
      source_request_id:
        description: Exact active source request bound to the failed run
        required: false
        type: string
'''

CHECKOUT_MARKER = '''      - name: Checkout control plane
        uses: actions/checkout@v4
        with:
          ref: main
          fetch-depth: 0
'''

WAIT_STEP = '''
      - name: Wait for exact dispatched failure completion
        if: github.event_name == 'workflow_dispatch' && github.event.inputs.failed_run_id != ''
        shell: bash
        env:
          FINALIZER_RUN_ID: ${{ github.event.inputs.failed_run_id }}
          FINALIZER_REQUEST_ID: ${{ github.event.inputs.source_request_id }}
        run: |
          set -euo pipefail
          [[ "$FINALIZER_RUN_ID" =~ ^[0-9]+$ ]] || { echo 'CODEFIX_FINALIZER_RUN_ID_INVALID'; exit 1; }
          [ -n "$FINALIZER_REQUEST_ID" ] || { echo 'CODEFIX_FINALIZER_REQUEST_ID_MISSING'; exit 1; }
          python - "$ACTIVE_REQUEST_POINTER" "$FINALIZER_REQUEST_ID" "$FINALIZER_RUN_ID" <<'PY'
          import json,sys
          from pathlib import Path
          p=Path(sys.argv[1]); expected_request=sys.argv[2]; expected_run=int(sys.argv[3])
          if not p.is_file(): raise SystemExit('CODEFIX_FINALIZER_ACTIVE_POINTER_MISSING')
          data=json.loads(p.read_text(encoding='utf-8'))
          if data.get('schema')!='tayvoriq-active-production-request-v1' or data.get('state')!='ACTIVE':
              raise SystemExit('CODEFIX_FINALIZER_ACTIVE_POINTER_INVALID')
          if str(data.get('request_id') or '') != expected_request:
              raise SystemExit('CODEFIX_FINALIZER_REQUEST_NOT_ACTIVE')
          if int(data.get('golden_path_run_id') or 0) != expected_run:
              raise SystemExit('CODEFIX_FINALIZER_RUN_NOT_ACTIVE')
          print(f'CODEFIX_FINALIZER_OWNER_VERIFIED:{expected_request}:{expected_run}')
          PY
          completed=false
          for poll in $(seq 1 36); do
            gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${FINALIZER_RUN_ID}" > /tmp/finalizer-run.json
            status=$(python -c "import json; print(json.load(open('/tmp/finalizer-run.json')).get('status',''))")
            if [ "$status" = "completed" ]; then completed=true; break; fi
            sleep 5
          done
          [ "$completed" = "true" ] || { echo 'CODEFIX_FINALIZER_RUN_DID_NOT_COMPLETE'; exit 1; }
          readarray -t final_meta < <(python - <<'PY'
          import json
          d=json.load(open('/tmp/finalizer-run.json',encoding='utf-8'))
          print(str(d.get('name') or ''))
          print(str(d.get('conclusion') or ''))
          PY
          )
          [ "${final_meta[0]:-}" = "TAYVORIQ-X Golden Path" ] || { echo 'CODEFIX_FINALIZER_WORKFLOW_MISMATCH'; exit 1; }
          [ "${final_meta[1]:-}" != "success" ] || { echo 'CODEFIX_FINALIZER_SUCCESS_RUN_REJECTED'; exit 1; }
          echo "CODEFIX_FINALIZER_FAILED_RUN_CONFIRMED:${FINALIZER_RUN_ID}:${final_meta[1]:-unknown}"
'''

FINALIZER_STEP = '''
      - name: Dispatch exact deterministic failure finalizer
        if: failure()
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          if [ -z "$SOURCE_REQUEST_ID_PIN" ]; then
            echo 'CODEFIX_FINALIZER_SKIPPED_UNPINNED_REQUEST'
            exit 0
          fi
          python - "$SOURCE_REQUEST_ID_PIN" "$GITHUB_RUN_ID" <<'PY'
          import json,sys
          from pathlib import Path
          request_id=sys.argv[1]; run_id=int(sys.argv[2])
          pointer_path=Path('.github/state/tayvoriq-active-production-request.json')
          request_path=Path('requests') / f'{request_id}.json'
          if not pointer_path.is_file() or not request_path.is_file():
              raise SystemExit('CODEFIX_FINALIZER_OWNER_FILES_MISSING')
          pointer=json.loads(pointer_path.read_text(encoding='utf-8'))
          request=json.loads(request_path.read_text(encoding='utf-8'))
          if pointer.get('schema')!='tayvoriq-active-production-request-v1' or pointer.get('state')!='ACTIVE':
              raise SystemExit('CODEFIX_FINALIZER_ACTIVE_POINTER_INVALID')
          if str(pointer.get('request_id') or '')!=request_id or int(pointer.get('golden_path_run_id') or 0)!=run_id:
              raise SystemExit('CODEFIX_FINALIZER_ACTIVE_OWNER_CHANGED')
          if str(request.get('request_id') or '')!=request_id or int(request.get('golden_path_run_id') or 0)!=run_id:
              raise SystemExit('CODEFIX_FINALIZER_REQUEST_OWNER_CHANGED')
          for field in ('approval_key','source_context_sha256','contract_sha256'):
              pv=str(pointer.get(field) or '').strip(); rv=str(request.get(field) or '').strip()
              if pv and pv!=rv: raise SystemExit(f'CODEFIX_FINALIZER_{field.upper()}_MISMATCH')
          print(f'CODEFIX_FINALIZER_DISPATCH_OWNER_VERIFIED:{request_id}:{run_id}')
          PY
          gh workflow run tayvoriq-deterministic-codefix-continuity.yml --ref main \
            -f "failed_run_id=$GITHUB_RUN_ID" \
            -f "source_request_id=$SOURCE_REQUEST_ID_PIN"
          echo "CODEFIX_FINALIZER_DISPATCHED:$SOURCE_REQUEST_ID_PIN:$GITHUB_RUN_ID"
'''


def _patch_continuity(text: str) -> str:
    if 'failed_run_id:\n        description: Exact failed Golden Path run to finalize' not in text:
        if OLD_DISPATCH not in text:
            raise SystemExit('PATCH_FAILED: continuity workflow_dispatch marker missing')
        text = text.replace(OLD_DISPATCH, NEW_DISPATCH, 1)
    if 'Wait for exact dispatched failure completion' not in text:
        if CHECKOUT_MARKER not in text:
            raise SystemExit('PATCH_FAILED: continuity checkout marker missing')
        text = text.replace(CHECKOUT_MARKER, CHECKOUT_MARKER + WAIT_STEP, 1)
    return text


def _patch_golden(text: str) -> str:
    if 'Dispatch exact deterministic failure finalizer' in text:
        return text
    marker = '''      - name: Upload lean diagnostics
        if: always()
        continue-on-error: true
        uses: actions/upload-artifact@v4
        with:
          name: tayvoriq-x-diagnostics-${{ github.run_id }}-attempt-${{ github.run_attempt }}
          path: implementation/out/diagnostics-bundle/**
          if-no-files-found: warn
          retention-days: 14
          compression-level: 6
'''
    if marker not in text:
        raise SystemExit('PATCH_FAILED: diagnostics upload marker missing')
    return text.replace(marker, marker + FINALIZER_STEP, 1)


def _validate(golden: str, continuity: str) -> None:
    missing=[]
    for value in (
        'Resolve immutable Production Green implementation',
        'ref: ${{ steps.production_green.outputs.implementation_sha }}',
        'Verify immutable implementation checkout',
        'Dispatch exact deterministic failure finalizer',
        'gh workflow run tayvoriq-deterministic-codefix-continuity.yml --ref main',
        '-f "failed_run_id=$GITHUB_RUN_ID"',
        '-f "source_request_id=$SOURCE_REQUEST_ID_PIN"',
    ):
        if value not in golden: missing.append(f'golden:{value}')
    for value in (
        'failed_run_id:',
        'source_request_id:',
        'Wait for exact dispatched failure completion',
        'CODEFIX_FINALIZER_OWNER_VERIFIED',
        'CODEFIX_FINALIZER_FAILED_RUN_CONFIRMED',
        'Reconcile only active orphan',
        'Replay exact active request after verified codefix',
    ):
        if value not in continuity: missing.append(f'continuity:{value}')
    if 'ref: feature/multi-platform-distribution-package' in golden:
        missing.append('golden:mutable implementation branch remains')
    if missing:
        raise SystemExit('FAILURE_FINALIZER_HARDENING_CHECK_FAILED:' + ';'.join(missing))


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    golden=GOLDEN.read_text(encoding='utf-8')
    continuity=CONTINUITY.read_text(encoding='utf-8')
    if not args.check:
        new_golden=_patch_golden(golden)
        new_continuity=_patch_continuity(continuity)
        GOLDEN.write_text(new_golden,encoding='utf-8')
        CONTINUITY.write_text(new_continuity,encoding='utf-8')
        golden,continuity=new_golden,new_continuity
        print('TAYVORIQ_FAILURE_FINALIZER_HARDENING_APPLIED')
    _validate(golden,continuity)
    print('TAYVORIQ_FAILURE_FINALIZER_HARDENING_CHECK_PASSED')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
