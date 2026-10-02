"""Reconcile the canonical approved request, never executor exit codes alone."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ACTIVE = {'queued', 'in_progress', 'waiting', 'requested', 'pending'}
EXECUTORS = ('tayvoriq-deterministic-codefix-continuity.yml',
             'tayvoriq-delivery-watch.yml', 'tayvoriq-autonomous-codefix-builder.yml')
STATE = Path('.github/state/tayvoriq-lifecycle-decision.json')


def decide(pointer, request, run, *, event_name='', event_run=0,
           revision='', green='', previous=None):
    result = dict(action='NONE', state='IDLE', reason='NO_ACTIVE_REQUEST',
                  request_id='', run_id='0', generation='0', request_status='',
                  request_substate='', decision_key='', dispatch_verified=False)
    if pointer.get('schema') != 'tayvoriq-active-production-request-v1':
        return result
    rid = str(pointer.get('request_id') or '')
    run_id = int(pointer.get('golden_path_run_id') or 0)
    result.update(request_id=rid, run_id=str(run_id),
                  generation=str(pointer.get('recovery_generation') or 0))

    def finish(state, reason, action='NONE'):
        result.update(state=state, reason=reason, action=action)
        return result

    if (not run_id or request.get('request_id') != rid
            or int(request.get('golden_path_run_id') or 0) != run_id
            or int(request.get('recovery_generation') or 0) != int(result['generation'])):
        return finish('BLOCKED', 'CANONICAL_OWNER_MISMATCH')
    for field in ('approval_key', 'source_context_sha256', 'contract_sha256'):
        if not pointer.get(field) or pointer[field] != request.get(field):
            return finish('BLOCKED', 'IMMUTABLE_REQUEST_MISMATCH:' + field)
    if request.get('source') != 'telegram_trend_approval':
        return finish('BLOCKED', 'TELEGRAM_APPROVAL_REQUIRED')
    completion = request.get('production_completion') or {}
    if (pointer.get('state') == 'COMPLETED'
            and completion.get('state') == 'REVIEW_READY'
            and int(completion.get('golden_path_run_id') or 0) == run_id
            and completion.get('quality_gates_weakened') is False):
        return finish('REVIEW_READY', 'VERIFIED_REVIEW_DELIVERED_AWAITING_USER_APPROVAL')
    if request.get('status') not in {'APPROVED', 'DISPATCHING', 'DISPATCHED'}:
        return finish('BLOCKED', 'REQUEST_NOT_APPROVED_FOR_CONTINUATION')
    if pointer.get('allow_recovery') is False:
        return finish('BLOCKED', 'RECOVERY_DISABLED_FOR_REQUEST')
    if pointer.get('state') != 'ACTIVE':
        return finish('BLOCKED', 'TERMINAL_POINTER_WITHOUT_REVIEW_PROOF')
    if event_name == 'TAYVORIQ-X Golden Path' and event_run and event_run != run_id:
        return finish('WAITING', 'STALE_GOLDEN_PATH_EVENT')
    if int(run.get('id') or 0) != run_id:
        return finish('BLOCKED', 'ACTIVE_RUN_STATUS_UNAVAILABLE')
    if run.get('status') in ACTIVE:
        return finish('RUNNING', 'VERIFIED_ACTIVE_PRODUCTION')
    if run.get('status') != 'completed':
        return finish('BLOCKED', 'ACTIVE_RUN_STATUS_UNKNOWN')
    if run.get('conclusion') == 'success':
        return finish('BLOCKED', 'SUCCESS_WITHOUT_REVIEW_DELIVERY_PROOF')
    codefix = request.get('codefix_recovery') or {}
    status = str(request.get('status') or '').upper()
    substate = str(codefix.get('request_substate') or request.get('request_substate') or '').upper()
    failure = str(codefix.get('failure_state') or request.get('failure_state') or '').upper()
    result.update(request_status=status, request_substate=substate)
    if any(t in failure for t in ('EXTERNAL', 'PAYMENT', 'SECRET_MISSING', 'PERMISSION_REQUIRED')):
        return finish('BLOCKED', 'EXTERNAL_BLOCKER_FAIL_CLOSED')
    deterministic = (codefix.get('status') == 'ARMED' or substate == 'AWAITING_CODEFIX'
                     or 'CODEFIX' in failure or failure in {'CODE_REPAIR_REQUIRED', 'DETERMINISTIC_STOP'})
    # State-only commits and helper workflow successes are not new repair evidence.
    identity = [rid, run_id, run.get('run_attempt', 1), result['generation'],
                codefix.get('failure_signature'), revision, green]
    result['decision_key'] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    if previous and previous.get('decision_key') == result['decision_key'] and previous.get('dispatch_verified'):
        return finish('BLOCKED', 'EXECUTOR_COMPLETED_WITHOUT_REQUEST_PROGRESS')
    reason = 'PRODUCTION_GREEN_READY' if event_name == 'TAYVORIQ Production Green Promoter' else 'ACTIVE_REQUEST_REQUIRES_CONTINUATION'
    return finish('RECOVERY_REQUIRED', reason, 'CODEFIX_CONTINUITY' if deterministic else 'DELIVERY_WATCH')


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def main():
    pointer = read('.github/state/tayvoriq-active-production-request.json')
    rid = str(pointer.get('request_id') or '')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', rid):
        request, run = {}, {}
    else:
        request = read(Path('requests') / (rid + '.json'))
        run_id = int(pointer.get('golden_path_run_id') or 0)
        run = api(f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{run_id}') if run_id else {}
    revision = subprocess.check_output(['git', 'log', '-1', '--format=%H', '--',
        'tools', 'scripts', '.github/workflows'], text=True).strip()
    green = read('.github/state/tayvoriq-production-green.json').get('implementation_sha', '')
    previous = read(STATE)
    result = decide(pointer, request, run, event_name=os.environ.get('EVENT_WORKFLOW', ''),
                    event_run=int(os.environ.get('EVENT_RUN_ID') or 0), revision=revision,
                    green=green, previous=previous.get('last_dispatch'))
    if result['state'] in {'RECOVERY_REQUIRED', 'BLOCKED'} and result['decision_key']:
        for workflow in EXECUTORS:
            runs = api(f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/workflows/{workflow}/runs?branch=main&per_page=20')
            active = [r for r in runs.get('workflow_runs', []) if r.get('status') in ACTIVE]
            if active:
                result.update(action='NONE', state='RECOVERING', reason='VERIFIED_ACTIVE_EXECUTOR',
                              executor_run_id=active[0]['id'])
                break
    result['decision_owner'] = 'tayvoriq-agent-orchestrator-v2'
    result['last_dispatch'] = previous.get('last_dispatch', {})
    Path('/tmp/tayvoriq-lifecycle-decision.json').write_text(json.dumps(result, indent=2) + '\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
        for key, value in result.items():
            if isinstance(value, (str, int, bool)):
                handle.write(f'{key}={str(value).replace(chr(10), " ")}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
