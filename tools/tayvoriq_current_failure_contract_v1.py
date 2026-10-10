"""Bind the current producer failure, never an earlier checkpoint finding."""
from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

if __package__:
    from .tayvoriq_recovery_policy_v1 import (
        EDITORIAL_CODEFIX_PATTERNS, SEMANTIC_CODEFIX_PATTERNS, _matches, runtime_log_text,
        LOCAL_VOICE_RETRY_PATTERNS, LOCAL_VISUAL_RETRY_PATTERNS,
    )
else:
    from tayvoriq_recovery_policy_v1 import (
        EDITORIAL_CODEFIX_PATTERNS, SEMANTIC_CODEFIX_PATTERNS, _matches, runtime_log_text,
        LOCAL_VOICE_RETRY_PATTERNS, LOCAL_VISUAL_RETRY_PATTERNS,
    )


def bind_current_failure(payload, console, *, run_id, run_attempt, request_id):
    result = dict(payload)
    result.update(run_id=int(run_id), run_attempt=int(run_attempt), request_id=request_id)
    # A console emitted by this controller invocation may terminate before it
    # refreshes report.json. Explicit runtime contract errors supersede that old
    # report's local repair targets. Echoed workflow source is never proof.
    state, detail = "", ""
    for line in runtime_log_text(console).splitlines():
        if _matches(line, EDITORIAL_CODEFIX_PATTERNS):
            state = "EDITORIAL_VALIDATOR_CODEFIX_REQUIRED"
            detail = line
        elif _matches(line, SEMANTIC_CODEFIX_PATTERNS):
            state = "SEMANTIC_CODEFIX_REQUIRED"
            detail = line
        elif _matches(line, LOCAL_VOICE_RETRY_PATTERNS + LOCAL_VISUAL_RETRY_PATTERNS):
            # A later local failure owns the terminal result if the earlier
            # editorial defect was repaired within this same controller attempt.
            state, detail = "", ""
    if state:
        result.update(state=state, failure_class="DETERMINISTIC_CODE",
                      repair_target_stages=[], master_reusable=False,
                      failure_detail=detail[-1000:])
    return result


def _runtime_objects(console):
    for line in runtime_log_text(console).splitlines():
        start = line.find('{')
        if start < 0:
            continue
        raw = line[start:].strip()
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            try:
                payload = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                continue
        if isinstance(payload, dict):
            yield payload


def recover_production_manifest(console, *, run_id, run_attempt, request_id):
    recovered = None
    for payload in _runtime_objects(console):
        if (payload.get('control_plane_schema') != 'x-v3'
                or payload.get('implementation_binding') != 'production-green-immutable-sha'):
            continue
        if (str(payload.get('run_id')) != str(run_id)
                or str(payload.get('run_attempt')) != str(run_attempt)
                or payload.get('source_request_id') != request_id
                or any(payload.get(key) is not True for key in
                       ('approved_trend_pinned', 'source_context_bound', 'source_request_pinned'))
                or payload.get('quality_gates_weakened') is not False
                or any(not re.fullmatch(r'[0-9a-f]{40}', str(payload.get(key) or ''))
                       for key in ('implementation_sha', 'control_plane_sha'))
                or not re.fullmatch(r'[0-9a-f]{64}', str(payload.get('source_context_sha256') or ''))):
            return None
        recovered = payload
    return recovered


def recover_failure_contract(console, *, run_id, run_attempt, request_id):
    """Recover a producer-printed contract from exact-attempt logs only.

    This is for missing legacy artifacts. Echoed workflow source is excluded,
    quality proof is mandatory, and any explicit identity must still match.
    """
    recovered = None
    for payload in _runtime_objects(console):
        if not isinstance(payload, dict) or payload.get('schema') != 'tayvoriq-failure-contract-v2':
            continue
        if payload.get('quality_gates_weakened') is not False:
            return None
        for name, expected in [('run_id', int(run_id)), ('run_attempt', int(run_attempt)), ('request_id', request_id)]:
            if name in payload and str(payload[name]) != str(expected):
                return None
        recovered = payload
    if recovered is None:
        return None
    result = bind_current_failure(recovered, console, run_id=run_id,
                                  run_attempt=run_attempt, request_id=request_id)
    result['evidence_provenance'] = 'exact-run-attempt-console'
    manifest = recover_production_manifest(console, run_id=run_id,
                                           run_attempt=run_attempt, request_id=request_id)
    if manifest:
        result.update(failed_implementation_sha=manifest['implementation_sha'],
                      failed_control_plane_sha=manifest['control_plane_sha'],
                      producer_source_context_sha256=manifest['source_context_sha256'])
    return result


def main():
    parser = argparse.ArgumentParser()
    for name in ('logs-file', 'contract-file', 'run-id', 'run-attempt', 'request-id'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    path = Path(args.contract_file)
    payload = json.loads(path.read_text()) if path.is_file() else {}
    console = Path(args.logs_file).read_text(encoding='utf-8', errors='replace')
    identity = dict(run_id=args.run_id, run_attempt=args.run_attempt, request_id=args.request_id)
    if payload:
        if not isinstance(payload, dict) or payload.get('quality_gates_weakened') is not False:
            raise RuntimeError('CURRENT_FAILURE_CONTRACT_UNTRUSTED')
        for key, value in identity.items():
            if key in payload and str(payload[key]) != str(value):
                raise RuntimeError('CURRENT_FAILURE_CONTRACT_IDENTITY_MISMATCH')
        result = bind_current_failure(payload, console, **identity)
    else:
        result = recover_failure_contract(console, **identity) or {}
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    main()
