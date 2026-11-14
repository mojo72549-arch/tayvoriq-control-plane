import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from tayvoriq_orchestration_contract import validate
from tayvoriq_lifecycle_controller_v1 import decide
from tayvoriq_review_receipt import REPLAY_BRANCH, REPLAY_PATH, REPLAY_STEPS, bind_review_receipt
from tayvoriq_slot_serialization_v1 import reference_review_verified


def evidence():
    request = json.loads((ROOT / 'requests/telegram-3549-trend-1.json').read_text())
    request.pop('production_completion', None)
    request.pop('publication', None)
    request['golden_path_run_id'] = 42983272199
    pointer = {**{key: request[key] for key in ('request_id', 'source_context_sha256', 'contract_sha256',
                                                'approval_key', 'golden_path_run_id', 'recovery_generation')},
               'schema': 'tayvoriq-active-production-request-v1', 'state': 'ACTIVE', 'allow_publish': False}
    run = dict(id=43123456, head_sha='a' * 40, head_branch=REPLAY_BRANCH, event='push', run_attempt=1,
               path=REPLAY_PATH, status='completed', conclusion='success', updated_at='2026-11-14T08:14:35Z')
    jobs = {'jobs': [{'name': 'review', 'run_id': run['id'], 'conclusion': 'success',
                      'steps': [{'name': name, 'conclusion': 'success'} for name in REPLAY_STEPS]}]}
    artifacts = {'artifacts': [{'name': name + str(run['id']), 'size_in_bytes': 400, 'expired': False}
                              for name in ('tayvoriq-telegram-review-receipt-', 'tayvoriq-approved-replay-')]}
    receipt = {**{k: request[k] for k in ('request_id', 'source_context_sha256', 'contract_sha256', 'content_angle')},
               'quality_gate': 'passed', 'run_id': str(run['id']), 'telegram_message_id': 3574,
               'studio_sha': 'b' * 40}
    return pointer, request, run, jobs, artifacts, receipt


def test_reference_receipt_is_reviewed_without_publish_authority():
    pointer, request, run, jobs, artifacts, receipt = evidence()
    persisted, owner = bind_review_receipt(pointer, request, run, jobs, artifacts, receipt, expected_ref='a' * 40)
    validate(persisted)
    assert persisted['contract_sha256'] == request['contract_sha256']
    assert persisted['source_context'] == request['source_context']
    assert persisted['golden_path_run_id'] == run['id']
    assert persisted['production_completion']['origin_run_id'] == pointer['golden_path_run_id']
    assert persisted['production_completion']['telegram_message_id'] == 3574
    assert owner['state'] == 'COMPLETED'
    assert owner['allow_publish'] is owner['allow_recovery'] is False
    assert reference_review_verified(persisted, run, jobs)
    assert decide(owner, persisted, run)['reason'] == 'VERIFIED_REFERENCE_REVIEW_DELIVERED'
    with pytest.raises(ValueError, match='OWNER_MISMATCH'):
        bind_review_receipt(owner, persisted, run, jobs, artifacts, receipt, expected_ref='a' * 40)


@pytest.mark.parametrize('bad', ['binding', 'message', 'audit', 'artifact', 'foreign_branch', 'ref'])
def test_incomplete_or_foreign_reference_cannot_release_ownership(bad):
    pointer, request, run, jobs, artifacts, receipt = evidence()
    if bad == 'binding':
        receipt['source_context_sha256'] = '0' * 64
    elif bad == 'message':
        receipt['telegram_message_id'] = request['telegram_message_id']
    elif bad == 'audit':
        jobs['jobs'][0]['steps'][2]['conclusion'] = 'failure'
    elif bad == 'artifact':
        artifacts['artifacts'].pop()
    elif bad == 'foreign_branch':
        run['head_branch'] = 'main'
    else:
        run['head_sha'] = 'b' * 40
    with pytest.raises(ValueError, match='REVIEW_RECEIPT_'):
        bind_review_receipt(pointer, request, run, jobs, artifacts, receipt, expected_ref='a' * 40)
