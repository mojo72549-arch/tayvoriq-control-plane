"""Check the immutable bundle attached to an authenticated Telegram decision."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


FILES = frozenset({'job.json', 'preapproval_ai_audit.json', 'publication_quality_gate.json',
                   'short_tiktok.mp4', 'short_youtube.mp4', 'tiktok_caption.txt', 'index.html'})


def validate_decision(decision, review_id):
    if (not isinstance(review_id, str) or not re.fullmatch(r'[0-9]{1,20}', review_id)
            or str(decision.get('review_id')) != review_id or decision.get('schema') != 'tayvoriq-artifact-approval'
            or decision.get('state') != 'APPROVED' or decision.get('decided_via') != 'telegram_callback'
            or not decision.get('decision_id') or type(decision.get('telegram_message_id')) is not int
            or decision['telegram_message_id'] < 1):
        raise ValueError('TELEGRAM_BOUND_APPROVAL_REQUIRED')
    if not re.fullmatch(r'[0-9a-f]{40}', str(decision.get('studio_sha') or '')):
        raise ValueError('APPROVED_STUDIO_SHA_INVALID')
    hashes = decision.get('files_sha256')
    if not isinstance(hashes, dict) or hashes.keys() != FILES or any(
            not re.fullmatch(r'[a-f0-9]{64}', str(digest)) for digest in hashes.values()):
        raise ValueError('APPROVED_REVIEW_HASHES_MISSING')


def verify_package(directory: Path, decision, review_id):
    validate_decision(decision, review_id)
    for name, expected in decision['files_sha256'].items():
        path = directory / name
        if not path.is_file() or path.is_symlink():
            raise ValueError('APPROVED_REVIEW_FILE_MISSING:' + name)
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != expected:
                raise ValueError('APPROVED_REVIEW_FILE_CHANGED:' + name)
    job = json.loads((directory / 'job.json').read_text(encoding='utf-8'))
    audit = json.loads((directory / 'publication_quality_gate.json').read_text(encoding='utf-8'))
    if (str(job.get('github_run_id')) != review_id or job.get('render_status') != 'DONE'
            or job.get('quality_report', {}).get('passed') is not True
            or audit.get('passed') is not True or audit.get('quality_gates_weakened') is not False
            or set(audit.get('targets') or ()) != {'youtube_shorts', 'tiktok'}):
        raise ValueError('APPROVED_REVIEW_GATE_UNCONFIRMED')
