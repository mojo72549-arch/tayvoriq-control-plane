import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_lifecycle_controller_v1 import decide
from tayvoriq_recovery_policy_v1 import classify_failure
from tayvoriq_lifecycle_handoff_v1 import await_completion


def test_completion_signal_waits_for_real_terminal_status():
    replies = iter(['in_progress', 'in_progress', 'completed'])
    sleeps = []
    def fetch(rid):
        return dict(id=rid, name='TAYVORIQ-X Golden Path', run_attempt=2, status=next(replies))
    assert await_completion(fetch, 42, 2, pause=sleeps.append) == 'COMPLETED'
    assert sleeps == [5, 5]


def test_handoff_is_bounded_and_old_attempt_does_not_hold_new_attempt():
    run = dict(id=42, name='TAYVORIQ Delivery Watch', run_attempt=3, status='in_progress')
    assert await_completion(lambda _: run, 42, 2) == 'SUPERSEDED'
    assert await_completion(lambda _: run, 42, 3, pause=lambda _: None, polls=2) == 'TIMEOUT'
    try:
        await_completion(lambda _: {**run, 'name': 'unrelated workflow'}, 42, 3)
    except ValueError as exc:
        assert 'WORKFLOW_INVALID' in str(exc)
    else:
        raise AssertionError('unknown signal source accepted')


def fixture():
    pointer = {'schema': 'tayvoriq-active-production-request-v1', 'state': 'ACTIVE',
               'request_id': 'telegram-3155-trend-1', 'golden_path_run_id': 42,
               'approval_key': 'approved', 'source_context_sha256': 'sources',
               'contract_sha256': 'contract', 'recovery_generation': 0}
    request = {**pointer, 'source': 'telegram_trend_approval', 'status': 'DISPATCHED',
               'codefix_recovery': {'status': 'ARMED', 'request_substate': 'AWAITING_CODEFIX',
                                   'failed_run_id': 42,
                                   'failure_state': 'LOCAL_REPAIR_CODEFIX_REQUIRED',
                                   'failure_signature': 'same-failure'}}
    run = {'id': 42, 'status': 'completed', 'conclusion': 'failure', 'run_attempt': 3}
    return pointer, request, run


def test_nested_armed_request_is_taken_over_on_builder_completion_and_timer():
    for event in ('', 'TAYVORIQ Autonomous Codefix Builder', 'TAYVORIQ Deterministic Codefix Continuity'):
        result = decide(*fixture(), event_name=event)
        assert result['action'] == 'CODEFIX_CONTINUITY'
        assert result['state'] == 'RECOVERY_REQUIRED'


def test_stale_codefix_flags_cannot_override_current_local_voice_failure():
    pointer, request, run = fixture()
    request['codefix_recovery'].update({
        'status': 'ARMED',
        'request_substate': 'AWAITING_CODEFIX',
        'failed_run_id': 42,
        'failure_state': 'TRANSIENT_AUDIO_FAILURE',
    })
    result = decide(pointer, request, run)
    assert result['action'] == 'DELIVERY_WATCH'
    assert result['state'] == 'RECOVERY_REQUIRED'


def test_armed_codefix_for_other_run_cannot_bypass_delivery_watch():
    pointer, request, run = fixture()
    request['codefix_recovery']['failed_run_id'] = 41
    result = decide(pointer, request, run)
    assert result['action'] == 'DELIVERY_WATCH'
    assert result['state'] == 'RECOVERY_REQUIRED'


def test_successful_helper_without_progress_cannot_create_dispatch_loop():
    first = decide(*fixture(), revision='fixed-code')
    previous = {**first, 'dispatch_verified': True}
    second = decide(*fixture(), revision='fixed-code', previous=previous)
    assert second['action'] == 'NONE'
    assert second['state'] == 'BLOCKED'
    assert second['reason'] == 'EXECUTOR_COMPLETED_WITHOUT_REQUEST_PROGRESS'
    # A relevant revision can unlock a new verified repair; resetting a status cannot.
    changed = decide(*fixture(), revision='new-fix', previous=previous)
    assert changed['action'] == 'CODEFIX_CONTINUITY'


def test_running_replay_is_not_restarted_even_when_old_codefix_is_armed():
    pointer, request, run = fixture()
    for state in ('queued', 'in_progress', 'waiting', 'pending', 'requested'):
        assert decide(pointer, request, {**run, 'status': state})['state'] == 'RUNNING'
        assert decide(pointer, request, {**run, 'status': state})['action'] == 'NONE'


def test_completed_github_job_alone_is_not_review_ready():
    pointer, request, run = fixture()
    result = decide(pointer, request, {**run, 'conclusion': 'success'})
    assert result['state'] == 'BLOCKED'
    assert result['reason'] == 'SUCCESS_WITHOUT_REVIEW_DELIVERY_PROOF'
    pointer['state'] = 'COMPLETED'
    request['production_completion'] = {'state': 'REVIEW_READY', 'golden_path_run_id': 42,
                                        'quality_gates_weakened': False}
    result = decide(pointer, request, {**run, 'conclusion': 'success'})
    assert result['state'] == 'REVIEW_READY'
    assert result['action'] == 'NONE'
    assert 'USER_APPROVAL' in result['reason']


def test_wrong_source_owner_or_generation_is_never_dispatched():
    pointer, request, run = fixture()
    for field, value in [('request_id', 'other'), ('golden_path_run_id', 41),
                         ('source_context_sha256', 'other'), ('contract_sha256', 'other'),
                         ('approval_key', ''), ('recovery_generation', 1), ('source', 'manual')]:
        result = decide(pointer, {**request, field: value}, run)
        assert result['state'] == 'BLOCKED', field
        assert result['action'] == 'NONE', field


def test_old_event_and_external_blocker_cannot_restart_request():
    assert decide(*fixture(), event_name='TAYVORIQ-X Golden Path', event_run=41)['reason'] == 'STALE_GOLDEN_PATH_EVENT'
    pointer, request, run = fixture()
    request['codefix_recovery']['failure_state'] = 'EXTERNAL_ACTION_REQUIRED'
    assert decide(pointer, request, run)['reason'] == 'EXTERNAL_BLOCKER_FAIL_CLOSED'


def test_real_binding_failure_wins_over_echoed_old_local_repair_error():
    logs = ('2026-10-01T22:16:35Z \x1b[36;1mif "bounded localized repair exhausted" in text:\x1b[0m\n'
            '2026-10-01T22:16:43Z REPLAY_READINESS_CANONICAL_BIND_TIMEOUT:telegram-3155-trend-1:42')
    for evidence in (None, {'state': 'CONTROL_PLANE_BINDING_FAILURE'}):
        result = classify_failure(logs, run_attempt=3, structured_evidence=evidence)
        assert result.mode == 'deterministic'
        assert result.state == 'CONTROL_PLANE_BINDING_CODEFIX_REQUIRED'
        assert result.next_generation == 0
    # Source-code text mentioning the binding marker alone is not runtime proof.
    echoed = 'echo "REPLAY_READINESS_CANONICAL_BIND_TIMEOUT:$SOURCE_REQUEST_ID_PIN:$GITHUB_RUN_ID"'
    result = classify_failure(echoed + '\nbounded localized repair exhausted', run_attempt=3)
    assert result.state == 'LOCAL_REPAIR_CODEFIX_REQUIRED'




def test_binding_gates_agree_on_armed_and_authorized_replay(tmp_path=None):
    import subprocess
    import tempfile
    import textwrap
    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/tayvoriq-deliver-video-now.yml').read_text()
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'request.json'
        for state, expected in [('ARMED', False), ('REPLAY_DISPATCHED', True), ('FRESH_RECOVERY_DISPATCHED', True)]:
            data = {'status': 'DISPATCHED', 'golden_path_run_id': 42, 'previous_golden_path_run_ids': [41],
                    'replacement_reason': 'BOUNDED_REQUEST_RECOVERY', 'codefix_recovery': {
                        'status': state, 'request_substate': 'DISPATCHED' if state != 'ARMED' else 'AWAITING_CODEFIX',
                        'failed_run_id': 42, 'replay_run_id': 42, 'fresh_recovery_run_id': 42}}
            path.write_text(json.dumps(data))
            for name in ('Early recovery binding gate', 'Exact-request replay readiness gate'):
                section = workflow.split('- name: ' + name, 1)[1]
                program = textwrap.dedent(section.split("<<'PY'\n", 1)[1].split('\n          PY', 1)[0])
                output = subprocess.run([sys.executable, '-c', program, str(path), '42', '3'], capture_output=True, text=True)
                assert (output.returncode == 0) == expected, (name, state, output.stderr)


def load_tests(loader, tests, pattern):
    import unittest
    return unittest.TestSuite(unittest.FunctionTestCase(value) for name, value in globals().items()
                              if name.startswith('test_') and callable(value))
