"""Evidence-backed request transitions for the candidate Control Plane."""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import datetime

from tayvoriq_orchestration_contract import validate
from tayvoriq_stale_news_reconcile_v1 import has_delivery_evidence


STAGES = {
    'APPROVED': ('control', 'SOURCES_VALID', 'SOURCE_FAILED'),
    'SOURCES_VALID': ('studio', 'SCRIPT_READY', 'SCRIPT_FAILED'),
    'SCRIPT_READY': ('studio', 'AUDIO_READY', 'AUDIO_FAILED'),
    'AUDIO_READY': ('studio', 'VISUALS_READY', 'VISUAL_FAILED'),
    'VISUALS_READY': ('studio', 'MASTER_READY', 'RENDER_FAILED'),
    'MASTER_READY': ('studio', 'QUALITY_PASSED', 'QUALITY_FAILED'),
    'QUALITY_PASSED': ('control', 'REVIEW_DELIVERED', 'DELIVERY_FAILED'),
    'REVIEW_DELIVERED': ('control', 'PUBLISHED', 'PUBLISH_FAILED'),
}

# Regeneration starts from the rejected product. Any dependent outputs need
# fresh evidence even if the resulting bytes happen to match an earlier run.
QUALITY_TARGETS = {
    'script': 'SOURCES_VALID', 'audio': 'SCRIPT_READY',
    'visuals': 'AUDIO_READY', 'render': 'VISUALS_READY',
}
MAX_RETRIES = {'transient': 2, 'quality': 1}
HASH = re.compile(r'[0-9a-f]{64}')
REQUEST_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')


def _digest(value):
    return isinstance(value, str) and HASH.fullmatch(value) is not None


def _positive_id(value):
    return type(value) is int and value > 0


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def start(request, *, cutoff):
    """Initialize from a verified immutable Telegram approval and freshness cutoff."""
    validate(request, require_claimable=True)
    if not REQUEST_ID.fullmatch(request['request_id']):
        raise ValueError('REQUEST_ID_INVALID')
    if (request.get('source') != 'telegram_trend_approval'
            or not request['approval_key'].startswith('telegram:')
            or not _positive_id(request.get('telegram_message_id'))):
        raise ValueError('TELEGRAM_APPROVAL_REQUIRED')
    if not (request.get('retention_contract_version') == 'v5'
            and _digest(request.get('source_context_sha256')) and _text(request.get('content_angle'))):
        raise ValueError('APPROVED_SOURCE_AND_ANGLE_REQUIRED')
    approved = datetime.fromisoformat(request['approved_at'].replace('Z', '+00:00'))
    if approved.tzinfo is None or cutoff.tzinfo is None or approved < cutoff:
        raise ValueError('REQUEST_STALE')
    if has_delivery_evidence(request) or request.get('tiktok_post_id'):
        raise ValueError('REQUEST_ALREADY_HANDLED')
    return {'request_id': request['request_id'], 'contract_sha256': request['contract_sha256'],
            'source_context_sha256': request['source_context_sha256'],
            'revision': 0, 'state': 'APPROVED', 'lease': None, 'evidence': {},
            'retries': {}, 'failure': None, 'publication_approval': None}


def claim(record, revision, *, actor, run, attempt):
    _check_revision(record, revision)
    stage = STAGES.get(record['state'])
    if not stage or actor != stage[0] or not (_positive_id(run) and _positive_id(attempt)):
        raise ValueError('INVALID_STAGE_OWNER')
    if record['lease'] is not None:
        raise ValueError('REQUEST_ALREADY_CLAIMED')
    if record['state'] == 'REVIEW_DELIVERED' and record['publication_approval'] is None:
        raise ValueError('PUBLICATION_APPROVAL_REQUIRED')
    return _updated(record, lease={'owner': actor, 'run': run, 'attempt': attempt})


def _check_revision(record, revision):
    if type(revision) is not int or record['revision'] != revision:
        raise ValueError('STALE_REQUEST_REVISION')


def _updated(record, **changes):
    result = deepcopy(record)
    result.update(deepcopy(changes), revision=record['revision'] + 1)
    return result


def _check_lease(record, revision, actor, run, attempt):
    _check_revision(record, revision)
    expected = {'owner': actor, 'run': run, 'attempt': attempt}
    if not (_positive_id(run) and _positive_id(attempt)) or record['lease'] != expected:
        raise ValueError('STAGE_LEASE_MISMATCH')


def _evidence_valid(record, target, proof):
    if any(proof.get(key) != record[key] for key in ('request_id', 'contract_sha256', 'source_context_sha256')):
        return False
    if target == 'SOURCES_VALID':
        return proof.get('duplicates_clear') is True
    if target in {'SCRIPT_READY', 'AUDIO_READY', 'VISUALS_READY'}:
        return _digest(proof.get('artifact_sha256')) and proof.get('passed') is True
    if target == 'MASTER_READY':
        return proof.get('media_probe_passed') is True and all(
            _digest(proof.get(key)) for key in ('youtube_sha256', 'tiktok_sha256'))
    if target == 'QUALITY_PASSED':
        master = record['evidence']['MASTER_READY']
        return (proof.get('passed') is True and _digest(proof.get('artifact_sha256'))
                and all(proof.get(key) == master[key] for key in ('youtube_sha256', 'tiktok_sha256')))
    if target == 'REVIEW_DELIVERED':
        audit = record['evidence']['QUALITY_PASSED']
        return (proof.get('confirmed') is True and _positive_id(proof.get('message_id'))
                and _digest(proof.get('review_sha256')) and proof.get('audit_sha256') == audit['artifact_sha256']
                and proof.get('video_sha256') == audit['tiktok_sha256'])
    if target == 'PUBLISHED':
        approval = record['publication_approval']
        return (proof.get('approval_id') == approval['approval_id']
                and proof.get('approved_message_id') == approval['message_id']
                and _positive_id(proof.get('approved_message_id'))
                and all(_text(proof.get(key)) for key in ('youtube_video_id', 'tiktok_post_id')))
    return False


def complete(record, revision, *, actor, run, attempt, proof):
    _check_lease(record, revision, actor, run, attempt)
    target = STAGES[record['state']][1]
    if not _evidence_valid(record, target, proof):
        raise ValueError('STAGE_EVIDENCE_REQUIRED:' + target)
    evidence = {**record['evidence'], target: {**proof, 'run': run, 'attempt': attempt}}
    return _updated(record, state=target, evidence=evidence, lease=None, failure=None)


def approve_publication(record, revision, *, actor, message_id, approval_id, review_sha256):
    """Bind the authenticated review callback before either publisher can claim."""
    _check_revision(record, revision)
    if actor != 'control' or record['state'] != 'REVIEW_DELIVERED':
        raise ValueError('PUBLICATION_APPROVAL_OWNER_REQUIRED')
    review = record['evidence']['REVIEW_DELIVERED']
    if (not _positive_id(message_id) or message_id != review['message_id']
            or review_sha256 != review['review_sha256'] or not _text(approval_id)):
        raise ValueError('PUBLICATION_APPROVAL_REVIEW_MISMATCH')
    approval = {'message_id': message_id, 'approval_id': approval_id, 'review_sha256': review_sha256}
    if record['publication_approval'] is not None:
        raise ValueError('PUBLICATION_ALREADY_APPROVED')
    return _updated(record, publication_approval=approval)


def fail(record, revision, *, actor, run, attempt, kind, proof_sha256, dimension=None):
    _check_lease(record, revision, actor, run, attempt)
    stage = record['state']
    target = {'transient': STAGES[stage][2], 'quality': 'QUALITY_FAILED',
              'external': 'EXTERNAL_BLOCKER', 'defect': 'CODE_DEFECT',
              'transcript_normalization': 'TRANSCRIPT_NORMALIZATION_DEFECT',
              'unknown_delivery': STAGES[stage][2]}.get(kind)
    if target is None or not _digest(proof_sha256):
        raise ValueError('FAILURE_EVIDENCE_REQUIRED')
    if kind == 'unknown_delivery' and stage not in {'QUALITY_PASSED', 'REVIEW_DELIVERED'}:
        raise ValueError('INVALID_DELIVERY_STAGE')
    if kind == 'quality' and (stage != 'MASTER_READY' or dimension not in QUALITY_TARGETS):
        raise ValueError('REPAIR_DIMENSION_REQUIRED')
    failure = {'stage': stage, 'kind': kind, 'proof_sha256': proof_sha256,
               'dimension': dimension, 'run': run, 'attempt': attempt}
    return _updated(record, state=target, lease=None, failure=failure)


def recover(record, revision, *, actor):
    """Return only the exact authorized continuation after a classified failure."""
    _check_revision(record, revision)
    if actor != 'recovery' or record['lease'] is not None or record['failure'] is None:
        raise ValueError('RECOVERY_OWNER_REQUIRED')
    failure = record['failure']
    kind = failure['kind']
    if kind not in MAX_RETRIES:
        raise ValueError('AUTOMATIC_RECOVERY_FORBIDDEN:' + kind)
    target = QUALITY_TARGETS[failure['dimension']] if kind == 'quality' else failure['stage']
    key = kind + ':' + target
    count = record['retries'].get(key, 0)
    if count >= MAX_RETRIES[kind]:
        raise ValueError('STAGE_RETRY_LIMIT_REACHED')
    stages = tuple(STAGES)
    valid_stages = set(stages[:stages.index(target) + 1])
    evidence = {stage: proof for stage, proof in record['evidence'].items() if stage in valid_stages}
    return _updated(record, state=target, evidence=evidence, failure=None,
                    retries={**record['retries'], key: count + 1})
