"""Reconcile the canonical approved request, never executor exit codes alone."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tayvoriq_lifecycle_handoff_v1 import await_completion
from tayvoriq_research_retry_v1 import lifecycle as research_lifecycle
from tayvoriq_rejected_review_followup import followup
from tayvoriq_stale_news_reconcile_v1 import verified_quarantine
from tayvoriq_chat_direct_approval_v1 import authorized_for_review
from tayvoriq_contabo_recovery_decision import contabo_decision, private_diagnostics
from tayvoriq_slot_serialization_v1 import is_verified_cta_content_repair

ACTIVE = {'queued', 'in_progress', 'waiting', 'requested', 'pending'}
EXECUTORS = ('tayvoriq-deterministic-codefix-continuity.yml',
             'tayvoriq-delivery-watch.yml', 'tayvoriq-autonomous-codefix-builder.yml',
             'tayvoriq-production-green-promoter.yml', 'tayvoriq-contabo-controller.yml')
STATE = Path('.github/state/tayvoriq-lifecycle-decision.json')


def review_message_id(request, run_id):
    completion = request.get('production_completion')
    if not run_id or not isinstance(completion, dict):
        return None
    message_id = completion.get('telegram_message_id')
    if (completion.get('state') == 'REVIEW_READY'
            and str(completion.get('golden_path_run_id') or '') == str(run_id)
            and completion.get('quality_gates_weakened') is False
            and type(message_id) is int and message_id > 0):
        return message_id
    return None


def decide(pointer, request, run, *, event_name='', event_run=0,
           revision='', green='', previous=None, review_followup=None, approved_parent=None,
           contabo=None):
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
    inherited = (approved_parent and approved_parent.get('source') == 'telegram_trend_approval'
                 and is_verified_cta_content_repair(request, approved_parent, approved_parent.get('request_id')))
    if request.get('source') != 'telegram_trend_approval' and not authorized_for_review(request) and not inherited:
        return finish('BLOCKED', 'USER_APPROVAL_PROVENANCE_REQUIRED')
    # A separately audited, unpublished and expired news request is terminal
    # history, not an active delivery blocker. Keep hard contract checks above.
    if pointer.get('state') == 'EXPIRED' or request.get('status') == 'EXPIRED':
        if verified_quarantine(pointer, request, run):
            result.update(request_status='EXPIRED', request_substate='EXPIRED')
            return finish('IDLE', 'EXPIRED_NEWS_QUARANTINED_AWAITING_FRESH_TREND')
        return finish('BLOCKED', 'EXPIRED_QUARANTINE_EVIDENCE_INVALID')
    if pointer.get('state') == 'COMPLETED' and review_message_id(request, run_id):
        if (review_followup and review_followup.get('request_id') == rid
                and review_followup.get('rejected_run_id') == run_id):
            if not review_followup.get('rejection_reason'):
                return finish('REJECTED', 'REJECTION_REASON_REQUIRED')
            if review_followup.get('selection_delivered'):
                return finish('REJECTED', 'REPLACEMENT_TRENDS_DELIVERED_AWAITING_TREND_APPROVAL')
            if review_followup.get('research_state') == 'BLOCKED':
                return finish('REJECTED', 'REPLACEMENT_TRENDS_BLOCKED')
            if review_followup.get('new_trends_requested'):
                return finish('REJECTED', 'REPLACEMENT_TRENDS_REQUESTED')
            if review_followup.get('replacement_dispatch_allowed'):
                return finish('REJECTED', 'TARGETED_REVIEW_REPAIR_RUNNING' if review_followup.get('repair_run_id')
                              else 'TARGETED_REVIEW_REPAIR_PENDING')
            return finish('REJECTED', 'REJECTION_FOLLOWUP_PENDING')
        if request['production_completion'].get('reference_only') is True and pointer.get('allow_publish') is False:
            return finish('REVIEW_READY', 'VERIFIED_REFERENCE_REVIEW_DELIVERED')
        return finish('REVIEW_READY', 'VERIFIED_REVIEW_DELIVERED_AWAITING_USER_APPROVAL')
    if request.get('status') not in {'APPROVED', 'DISPATCHING', 'DISPATCHED'}:
        return finish('BLOCKED', 'REQUEST_NOT_APPROVED_FOR_CONTINUATION')
    if pointer.get('execution_backend') == 'contabo_private_runner' and pointer.get('state') == 'ACTIVE':
        if contabo:
            result['contabo_repair'] = contabo
            if contabo['state'] == 'RETRY_ELIGIBLE':
                result['decision_key'] = contabo['decision_key']
                if previous and previous.get('decision_key') == result['decision_key'] and previous.get('dispatch_verified'):
                    try:
                        ack = datetime.fromisoformat(previous['checked_at'])
                        if datetime.now(timezone.utc) - ack >= timedelta(minutes=10):
                            return finish('RECOVERY_FAILED', 'CONTABO_REPAIR_HANDOFF_TIMEOUT')
                    except (KeyError, ValueError, TypeError):
                        return finish('RECOVERY_FAILED', 'CONTABO_REPAIR_ACK_TIME_INVALID')
                    return finish('RECOVERING', 'CONTABO_REPAIR_RUN_DISPATCHED')
                return finish('RECOVERY_REQUIRED', contabo['state'], 'CONTABO_QUALITY_RECOVERY')
            return finish('REPAIR_REQUIRED', contabo['state'])
        if int(run.get('id') or 0) == run_id and run.get('status') in ACTIVE:
            return finish('RUNNING', 'VERIFIED_CONTABO_OWNER_ACTIVE')
        return finish('BLOCKED', 'CONTABO_OWNER_OR_TERMINAL_EVIDENCE_UNCONFIRMED')
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
    # A completed Delivery Watch may have exhausted its bounded media/voice
    # recovery without changing the producer's DISPATCHED request status.
    # The exact, persisted classifier receipt outranks the previous successful
    # *executor dispatch*. It does not claim the video was delivered.
    outcome = request.get('recovery_outcome')
    if isinstance(outcome, dict) and str(outcome.get('run_id') or '') == str(run_id):
        valid = (
            outcome.get('schema') == 'tayvoriq-recovery-outcome-v1'
            and outcome.get('state') == 'EXHAUSTED'
            and outcome.get('request_id') == rid
            and int(outcome.get('recovery_generation') if outcome.get('recovery_generation') is not None else -1) == int(result['generation'])
            and int(outcome.get('run_attempt') or 0) == int(run.get('run_attempt') or 0)
            and outcome.get('reason') in {
                'LOCAL_VISUAL_RECOVERY_EXHAUSTED', 'LOCAL_VOICE_RECOVERY_EXHAUSTED'
            }
            and bool(re.fullmatch(r'[a-f0-9]{20}', str(outcome.get('failure_signature') or '')))
            and outcome.get('quality_gates_weakened') is False
            and outcome.get('publish_allowed') is False
            and outcome.get('next_action') == 'AWAIT_VERIFIED_MEDIA_OR_CODE_REPAIR'
        )
        if not valid:
            return finish('BLOCKED', 'RECOVERY_OUTCOME_IDENTITY_INVALID')
        result.update(request_status=str(request.get('status') or ''),
                      request_substate='RECOVERY_EXHAUSTED')
        # The only automatic way out of a proven exhausted media repair is a
        # *different*, strictly verified Production Green implementation.
        # Reuse the same request and same generation; never retry old code.
        failed_impl = str(outcome.get('implementation_sha') or '')
        if (re.fullmatch(r'[a-f0-9]{40}', str(green or ''))
                and re.fullmatch(r'[a-f0-9]{40}', failed_impl)
                and green != failed_impl):
            action = 'DELIVERY_WATCH'
            identity = [rid, run_id, run.get('run_attempt', 1),
                        result['generation'], outcome['failure_signature'],
                        revision, green, action, 'exhausted-advanced-green']
            result['decision_key'] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
            if previous and previous.get('decision_key') == result['decision_key'] and previous.get('dispatch_verified'):
                return finish('RECOVERY_FAILED', 'VERIFIED_GREEN_REPLAY_EXECUTOR_MISSING_OUTCOME')
            return finish('RECOVERY_REQUIRED', 'VERIFIED_GREEN_ADVANCED_AFTER_EXHAUSTION', action)
        return finish('REPAIR_REQUIRED', str(outcome['reason']))
    codefix = request.get('codefix_recovery') or {}
    status = str(request.get('status') or '').upper()
    substate = str(codefix.get('request_substate') or request.get('request_substate') or '').upper()
    failure = str(codefix.get('failure_state') or request.get('failure_state') or '').upper()
    result.update(request_status=status, request_substate=substate)
    if any(t in failure for t in ('EXTERNAL', 'PAYMENT', 'SECRET_MISSING', 'PERMISSION_REQUIRED')):
        return finish('BLOCKED', 'EXTERNAL_BLOCKER_FAIL_CLOSED')
    try:
        codefix_failed_run = int(codefix.get('failed_run_id') or 0)
    except (TypeError, ValueError):
        codefix_failed_run = 0
    deterministic_failure = (
        'CODEFIX' in failure
        or failure in {'CODE_DEFECT', 'TRANSCRIPT_NORMALIZATION_DEFECT', 'CODE_REPAIR_REQUIRED',
                       'DETERMINISTIC_STOP', 'DETERMINISTIC_PREFLIGHT_FAILURE'}
    )
    # Only an exact, already-armed deterministic handoff may bypass Delivery Watch.
    # A stale ARMED/AWAITING_CODEFIX flag from an earlier classifier must never
    # override the current producer failure contract.
    deterministic = (
        codefix.get('status') == 'ARMED'
        and substate == 'AWAITING_CODEFIX'
        and codefix_failed_run == run_id
        and deterministic_failure
    )
    # State-only commits and helper workflow successes are not new repair evidence.
    # Classification and codefix continuity are different acknowledged handoffs.
    # A verified ARMED transition must unlock continuity without reopening the
    # already completed classifier or requiring another code change.
    action = 'CODEFIX_CONTINUITY' if deterministic else 'DELIVERY_WATCH'
    identity = [rid, run_id, run.get('run_attempt', 1), result['generation'],
                codefix.get('failure_signature'), revision, green, action]
    result['decision_key'] = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    if previous and previous.get('decision_key') == result['decision_key'] and previous.get('dispatch_verified'):
        if deterministic:
            return finish('AWAITING_CODEFIX', failure)
        return finish('RECOVERY_FAILED', 'RECOVERY_EXECUTOR_MISSING_OUTCOME')
    reason = 'PRODUCTION_GREEN_READY' if event_name == 'TAYVORIQ Production Green Promoter' else 'ACTIVE_REQUEST_REQUIRES_CONTINUATION'
    return finish('RECOVERY_REQUIRED', reason, action)


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def read(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def main():
    signal_id = int(os.environ.get('SIGNAL_RUN_ID') or 0)
    signal_attempt = int(os.environ.get('SIGNAL_RUN_ATTEMPT') or 0)
    receipt = ''
    if signal_id:
        receipt = await_completion(
            lambda rid: api(f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{rid}'),
            signal_id, signal_attempt)
        # The producer may have committed the final request state while its
        # post steps completed. Reconcile that committed state, not checkout age.
        subprocess.run(['git', 'pull', '--ff-only', 'origin', 'main'], check=True)
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
    verified_green = read('.github/state/tayvoriq-production-green.json')
    green_sha = str(verified_green.get('implementation_sha') or '')
    green = green_sha if (
        verified_green.get('schema') == 'tayvoriq-production-green-v1'
        and verified_green.get('full_preflight_passed') is True
        and verified_green.get('quality_gates_weakened') is False
        and bool(re.fullmatch(r'[a-f0-9]{40}', green_sha))
    ) else ''
    previous = read(STATE)
    parent_id = str(request.get('repair_of_request_id') or '')
    parent = read(Path('requests') / (parent_id + '.json')) if re.fullmatch(r'[A-Za-z0-9_-]{4,80}', parent_id) else None
    terminal = None
    if pointer.get('execution_backend') == 'contabo_private_runner' and run.get('conclusion') == 'failure':
        try:
            terminal = contabo_decision(pointer, request, run, verified_green,
                read(Path('run-status/contabo') / (str(run_id) + '.json')),
                diagnostics=lambda worker: private_diagnostics(worker, os.environ.get('STUDIO_READ_TOKEN', ''), controller=run_id))
        except (AssertionError, KeyError, ValueError, TypeError):
            pass
    result = decide(pointer, request, run, event_name=os.environ.get('EVENT_WORKFLOW', ''),
                    event_run=int(os.environ.get('EVENT_RUN_ID') or 0), revision=revision,
                    green=green, previous=previous.get('last_dispatch'), review_followup=followup(),
                    approved_parent=parent, contabo=terminal)
    result = research_lifecycle(result)
    if result['state'] in {'RECOVERY_REQUIRED', 'BLOCKED'} and result['decision_key']:
        for workflow in EXECUTORS:
            runs = api(f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/workflows/{workflow}/runs?branch=main&per_page=20')
            active = [r for r in runs.get('workflow_runs', []) if r.get('status') in ACTIVE]
            if active:
                result.update(action='NONE', state='RECOVERING', reason='VERIFIED_ACTIVE_EXECUTOR',
                              executor_run_id=active[0]['id'])
                break
    result['decision_owner'] = 'tayvoriq-agent-orchestrator-v2'
    if signal_id:
        result.update(signal_run_id=signal_id, signal_run_attempt=signal_attempt,
                      signal_receipt=receipt)
        if receipt == 'TIMEOUT':
            result.update(action='NONE', state='BLOCKED', reason='COMPLETION_HANDOFF_TIMEOUT')
    result['last_dispatch'] = previous.get('last_dispatch', {})
    Path('/tmp/tayvoriq-lifecycle-decision.json').write_text(json.dumps(result, indent=2) + '\n')
    with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
        for key, value in result.items():
            if isinstance(value, (str, int, bool)):
                handle.write(f'{key}={str(value).replace(chr(10), " ")}\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()

