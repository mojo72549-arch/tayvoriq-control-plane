"""Reserve the exact approved artifact review before an irreversible upload."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

from tayvoriq_artifact_approval import validate_decision


def run(*args):
    subprocess.run(args, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review_id')
    parser.add_argument('action', choices=('claim', 'record'))
    parser.add_argument('--receipt', type=Path)
    args = parser.parse_args()
    decision_path = Path('.automation/tayvoriq-artifact-decisions') / f'{args.review_id}.json'
    decision = json.loads(decision_path.read_text())
    validate_decision(decision, args.review_id)
    path = Path('.automation/tayvoriq-publications') / f'{args.review_id}.json'
    identity = {'review_id': args.review_id, 'telegram_message_id': decision['telegram_message_id'],
                'decision_id': decision['decision_id'], 'publish_run_id': os.environ['GITHUB_RUN_ID']}
    run('git', 'pull', '--ff-only', 'origin', 'main')
    if json.loads(decision_path.read_text()) != decision:
        raise RuntimeError('PUBLICATION_DECISION_CHANGED')
    if args.action == 'claim':
        if path.exists():
            raise RuntimeError('PUBLICATION_ALREADY_CLAIMED')
        state = {'state': 'UPLOAD_STARTED', **identity}
    else:
        claim = json.loads(path.read_text())
        if claim != {'state': 'UPLOAD_STARTED', **identity} or not args.receipt:
            raise RuntimeError('PUBLICATION_CLAIM_MISMATCH')
        result = json.loads(args.receipt.read_text()).get('results', {}).get('youtube_shorts', {})
        if not result.get('video_id') or not result.get('url'):
            raise RuntimeError('YOUTUBE_RECEIPT_MISSING')
        state = {'state': 'YOUTUBE_PUBLISHED', **identity, 'youtube': result,
                 'tiktok_status': 'MANUAL_UPLOAD_REQUIRED'}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    run('git', 'config', 'user.name', 'github-actions[bot]')
    run('git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com')
    run('git', 'add', '--', str(path))
    run('git', 'commit', '-m', f'Record review {args.review_id} {state["state"]}')
    run('git', 'push', 'origin', 'HEAD:main')


if __name__ == '__main__':
    main()
