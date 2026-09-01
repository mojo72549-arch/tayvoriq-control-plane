#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

POLICY = Path('tools/tayvoriq_recovery_policy_v1.py')
ORPHAN = Path('tools/tayvoriq_codefix_orphan_reconcile_v1.py')

REPLAY_BLOCK = '''
    # A failed codefix replay is already the bounded second execution of the exact
    # approved request. If that replay reaches the terminal publishability handoff,
    # generic timeout/circuit words elsewhere in the Actions log must never turn it
    # into another blind same-run retry. Keep the same generation armed for a new
    # verified code revision instead.
    if codefix_replay and re.search(r"\\bpublishable_output_retry_required\\b", lowered, flags=re.IGNORECASE):
        state = "PUBLISHABLE_CODEFIX_REQUIRED"
        return RecoveryDecision(
            "deterministic", state, False, "verified-codefix-replay", generation, generation,
            maximum, _stable_signature(state, text),
            "The exact request already failed after a verified codefix replay. Preserve it in the same recovery generation and require another verified relevant code revision; do not blind-rerun transient log noise.",
        )
'''


def patch_policy(text: str) -> str:
    if 'codefix_replay: bool = False' not in text:
        old = '''    owner_current: bool = True,
    exact_request_retry: bool = False,
) -> RecoveryDecision:
'''
        new = '''    owner_current: bool = True,
    exact_request_retry: bool = False,
    codefix_replay: bool = False,
) -> RecoveryDecision:
'''
        if old not in text:
            raise SystemExit('PATCH_FAILED: policy classify signature marker missing')
        text = text.replace(old, new, 1)

    if 'The exact request already failed after a verified codefix replay.' not in text:
        marker = '''    if not owner_current:
        state = "SUPERSEDED_RECOVERY_EVENT"
        return RecoveryDecision("stale", state, False, "none", generation, None, maximum, _stable_signature(state, text), "A newer run already owns the request.")
'''
        if marker not in text:
            raise SystemExit('PATCH_FAILED: policy owner-current marker missing')
        text = text.replace(marker, marker + REPLAY_BLOCK, 1)

    if 'parser.add_argument("--codefix-replay"' not in text:
        marker = '    parser.add_argument("--exact-request-retry", choices=("true", "false"), default="false")\n'
        if marker not in text:
            raise SystemExit('PATCH_FAILED: policy CLI exact-request marker missing')
        text = text.replace(marker, marker + '    parser.add_argument("--codefix-replay", choices=("true", "false"), default="false")\n', 1)

    if 'codefix_replay=args.codefix_replay == "true"' not in text:
        marker = '        exact_request_retry=args.exact_request_retry == "true",\n'
        if marker not in text:
            raise SystemExit('PATCH_FAILED: policy classify invocation marker missing')
        text = text.replace(marker, marker + '        codefix_replay=args.codefix_replay == "true",\n', 1)
    return text


def patch_orphan(text: str) -> str:
    if 'def _policy(logs: Path, run_attempt: int, generation: int, codefix_replay: bool, target: Path)' not in text:
        old='def _policy(logs: Path, run_attempt: int, generation: int, target: Path) -> dict[str, Any] | None:\n'
        new='def _policy(logs: Path, run_attempt: int, generation: int, codefix_replay: bool, target: Path) -> dict[str, Any] | None:\n'
        if old not in text:
            raise SystemExit('PATCH_FAILED: orphan policy signature marker missing')
        text=text.replace(old,new,1)

    if '"--codefix-replay"' not in text:
        marker='''            "--exact-request-retry",
            "true",
            "--output-json",
'''
        replacement='''            "--exact-request-retry",
            "true",
            "--codefix-replay",
            "true" if codefix_replay else "false",
            "--output-json",
'''
        if marker not in text:
            raise SystemExit('PATCH_FAILED: orphan policy CLI marker missing')
        text=text.replace(marker,replacement,1)

    old_call='policy = _policy(logs, _int(run_meta.get("run_attempt")) or 1, generation, policy_path)'
    if old_call in text:
        new_call='''codefix = data.get("codefix_recovery") if isinstance(data.get("codefix_recovery"), dict) else {}
            codefix_replay = (
                str(codefix.get("status") or "") == "REPLAY_DISPATCHED"
                and _int(codefix.get("replay_run_id")) == run_id
            )
            policy = _policy(logs, _int(run_meta.get("run_attempt")) or 1, generation, codefix_replay, policy_path)'''
        text=text.replace(old_call,new_call,1)
    elif 'generation, codefix_replay, policy_path' not in text:
        raise SystemExit('PATCH_FAILED: orphan policy call marker missing')
    return text


def validate(policy: str, orphan: str) -> None:
    required_policy=(
        'codefix_replay: bool = False',
        'PUBLISHABLE_CODEFIX_REQUIRED',
        'The exact request already failed after a verified codefix replay.',
        'parser.add_argument("--codefix-replay"',
        'codefix_replay=args.codefix_replay == "true"',
    )
    required_orphan=(
        'generation: int, codefix_replay: bool, target: Path',
        '"--codefix-replay"',
        '"true" if codefix_replay else "false"',
        'str(codefix.get("status") or "") == "REPLAY_DISPATCHED"',
        '_int(codefix.get("replay_run_id")) == run_id',
        'generation, codefix_replay, policy_path',
    )
    missing=[f'policy:{v}' for v in required_policy if v not in policy]
    missing += [f'orphan:{v}' for v in required_orphan if v not in orphan]
    if missing:
        raise SystemExit('REPLAY_POLICY_HARDENING_CHECK_FAILED:'+';'.join(missing))


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--check',action='store_true'); args=parser.parse_args()
    policy=POLICY.read_text(encoding='utf-8'); orphan=ORPHAN.read_text(encoding='utf-8')
    if not args.check:
        policy=patch_policy(policy); orphan=patch_orphan(orphan)
        POLICY.write_text(policy,encoding='utf-8'); ORPHAN.write_text(orphan,encoding='utf-8')
        print('TAYVORIQ_REPLAY_POLICY_HARDENING_APPLIED')
    validate(policy,orphan)
    print('TAYVORIQ_REPLAY_POLICY_HARDENING_CHECK_PASSED')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
