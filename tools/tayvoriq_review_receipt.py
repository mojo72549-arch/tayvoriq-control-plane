"""Reconcile a receipt from an isolated, non-publishing approved replay."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from tayvoriq_stale_news_reconcile_v1 import has_delivery_evidence

REPLAY_PATH = '.github/workflows/tayvoriq-isolated-approved-replay.yml'
REPLAY_BRANCH = 'validation/tayvoriq-approved-replay'
REPLAY_STEPS = (
    'Verify the original Telegram approval, exact sources and duplicates',
    'Verify immutable Studio checkout and retention contract',
    'Verify both masters and the generated review page; run final audit',
    'Retain review page, both MP4s and immutable binding',
    'Deliver isolated review to the configured Telegram chat',
    'Store the Telegram receipt',
)


def bind_review_receipt(pointer: dict[str, Any], request: dict[str, Any], run: dict[str, Any],
                        jobs: dict[str, Any], artifacts: dict[str, Any], receipt: dict[str, Any],
                        *, expected_ref: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Close the legacy owner only with exact request and reviewed-run evidence.

    Caller fetches the receipt from the identified GitHub Actions run artifact.
    The original failed run remains in the request history; no publishing input
    or permission is synthesized for the replay review.
    """
    request_id = request.get('request_id')
    original_id = pointer.get('golden_path_run_id')
    run_id = run.get('id')
    fields = ('request_id', 'source_context_sha256', 'contract_sha256', 'content_angle')
    if (pointer.get('state') != 'ACTIVE' or pointer.get('allow_publish') is not False
            or pointer.get('schema') != 'tayvoriq-active-production-request-v1'
            or request.get('source') != 'telegram_trend_approval' or request.get('status') != 'DISPATCHED'
            or type(original_id) is not int or original_id <= 0
            or request.get('golden_path_run_id') != original_id or has_delivery_evidence(request)
            or any(not request.get(key) or request[key] != pointer.get(key)
                   for key in ('request_id', 'source_context_sha256', 'contract_sha256', 'approval_key'))):
        raise ValueError('REVIEW_RECEIPT_OWNER_MISMATCH')
    if (type(run_id) is not int or run_id <= 0 or run_id == original_id
            or not re.fullmatch(r'[0-9a-f]{40}', expected_ref)
            or run.get('head_branch') != REPLAY_BRANCH or run.get('head_sha') != expected_ref
            or str(run.get('path') or '').split('@', 1)[0] != REPLAY_PATH
            or run.get('event') != 'push' or run.get('run_attempt') != 1
            or run.get('status') != 'completed' or run.get('conclusion') != 'success'):
        raise ValueError('REVIEW_RECEIPT_RUN_MISMATCH')
    verified = [job for job in jobs.get('jobs', []) if job.get('name') == 'review'
                and job.get('run_id') == run_id and job.get('conclusion') == 'success']
    if len(verified) != 1 or any(
            {step.get('name'): step.get('conclusion') for step in verified[0].get('steps', [])}.get(step) != 'success'
            for step in REPLAY_STEPS):
        raise ValueError('REVIEW_RECEIPT_GATES_UNCONFIRMED')
    names = {item.get('name') for item in artifacts.get('artifacts', [])
             if item.get('expired') is False and item.get('size_in_bytes', 0) > 0}
    if not {f'tayvoriq-telegram-review-receipt-{run_id}', f'tayvoriq-approved-replay-{run_id}'} <= names:
        raise ValueError('REVIEW_RECEIPT_ARTIFACTS_MISSING')
    message_id = receipt.get('telegram_message_id')
    if (str(receipt.get('run_id')) != str(run_id) or receipt.get('quality_gate') != 'passed'
            or not re.fullmatch(r'[0-9a-f]{40}', str(receipt.get('studio_sha') or ''))
            or type(message_id) is not int or message_id <= 0 or message_id == request.get('telegram_message_id')
            or any(not request.get(key) or request[key] != receipt.get(key) for key in fields)):
        raise ValueError('REVIEW_RECEIPT_IDENTITY_MISMATCH')
    completed = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
    if completed.tzinfo is None:
        raise ValueError('REVIEW_RECEIPT_TIMESTAMP_INVALID')
    at = completed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    result = {'state': 'REVIEW_READY', 'golden_path_run_id': run_id, 'telegram_message_id': message_id,
              'completed_at': at, 'quality_gates_weakened': False, 'publishable_review': False,
              'reference_only': True, 'origin_run_id': original_id, 'studio_sha': receipt['studio_sha']}
    history = [*request['state_history'], {'state': request['status'], 'at': at,
               'actor': 'reference_review_reconcile', 'meta': {'reference_run_id': run_id,
               'prior_failed_run_id': original_id, 'telegram_message_id': message_id}}]
    return ({**request, 'golden_path_run_id': run_id, 'state_history': history,
             'production_completion': result, 'recovery_owner': 'none', 'codefix_recovery': {
                 **(request.get('codefix_recovery') or {}), 'status': 'CLOSED_REFERENCE_REVIEW',
                 'request_substate': 'REVIEW_DELIVERED', 'review_run_id': run_id}},
            {**pointer, 'golden_path_run_id': run_id, 'state': 'COMPLETED', 'allow_recovery': False,
             'allow_publish': False, 'reference_only': True, 'completed_at': at, 'updated_at': at,
             'reason': 'verified_reference_review_delivered'})
