"""Build the durable archive from publication receipts, without publishing anything."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ARCHIVE = 'state/tayvoriq-video-archive.json'
VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')


def read(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def dated(value):
    try:
        date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return str(value) if date.tzinfo else None
    except ValueError:
        return None


def platform_receipts(publication, approval, review_id):
    """An upload claim, approval or downloadable package is never publication proof."""
    if str(publication.get('review_id')) != review_id:
        return None
    youtube = {'status': 'UNVERIFIED', 'url': None, 'published_at': None}
    tiktok = {'status': 'UNVERIFIED', 'url': None, 'published_at': None}
    if (publication.get('platform') == 'youtube' and publication.get('privacy') == 'public'
            and publication.get('idempotency_lock') is True
            and VIDEO_ID.fullmatch(str(publication.get('video_id') or ''))
            and publication.get('url') == 'https://www.youtube.com/shorts/' + publication['video_id']
            and dated(publication.get('published_at'))):
        youtube = {'status': 'PUBLISHED', 'url': publication['url'],
                   'published_at': publication['published_at'], 'video_id': publication['video_id']}
    result = publication.get('youtube') or {}
    if (publication.get('state') == 'YOUTUBE_PUBLISHED'
            and approval.get('state') == 'APPROVED'
            and str(approval.get('review_id')) == review_id
            and publication.get('decision_id') == approval.get('decision_id')
            and approval.get('decision_id')
            and result.get('status') == 'uploaded'
            and VIDEO_ID.fullmatch(str(result.get('video_id') or ''))
            and result.get('url') in {'https://www.youtube.com/shorts/' + result['video_id'],
                                      'https://www.youtube.com/watch?v=' + result['video_id']}):
        youtube = {'status': 'PUBLISHED', 'url': result['url'], 'video_id': result['video_id'],
                   'published_at': dated(publication.get('published_at'))}
    # TikTok needs an actual platform receipt. Delivery to Telegram is insufficient.
    tt = publication.get('tiktok') or {}
    if (tt.get('status') == 'PUBLISHED' and tt.get('verified') is True
            and re.fullmatch(r'https://www\.tiktok\.com/@[\w.]+/video/\d+', str(tt.get('url') or ''))
            and dated(tt.get('published_at'))):
        tiktok = {'status': 'PUBLISHED', 'url': tt['url'], 'published_at': tt['published_at']}
    elif (publication.get('tiktok_status') == 'MANUAL_UPLOAD_REQUIRED'
          or approval.get('tiktok_status') == 'MANUAL_UPLOAD_REQUIRED'):
        tiktok['status'] = 'MANUAL_UPLOAD_REQUIRED'
    if youtube['status'] != 'PUBLISHED' and tiktok['status'] != 'PUBLISHED':
        return None
    return {'youtube': youtube, 'tiktok': tiktok}


def build(root):
    old = read(root / ARCHIVE)
    records = {str(r['review_id']): r for r in old.get('records', [])
               if isinstance(r, dict) and re.fullmatch(r'\d{1,20}', str(r.get('review_id', '')))}
    requests = {}
    for path in (root / 'requests').glob('*.json'):
        request = read(path)
        run = request.get('golden_path_run_id')
        if type(run) is int:
            requests[str(run)] = request
    for path in sorted((root / '.automation/tayvoriq-publications').glob('*.json')):
        rid = path.stem
        if not re.fullmatch(r'\d{1,20}', rid):
            continue
        publication = read(path)
        decision_path = root / '.automation/tayvoriq-artifact-decisions' / path.name
        approval = read(decision_path) or read(root / '.automation/tayvoriq-reviews' / path.name)
        platforms = platform_receipts(publication, approval, rid)
        if not platforms:
            continue
        request = requests.get(rid, {})
        payload = approval.get('published_payload') or {}
        receipt = request.get('production_completion') or {}
        source = request.get('source_context') or {}
        evidence_files = sorted((root / 'run-status/production').glob(rid + '-*.json'),
                                key=lambda p: int(p.stem.split('-')[-1]))
        evidence = read(evidence_files[-1]) if evidence_files else {}
        bound = (str(evidence.get('run_id')) == rid
                 and evidence.get('source_request_id') == request.get('request_id')
                 and evidence.get('source_context_sha256') == request.get('source_context_sha256'))
        review_delivered = (receipt.get('state') == 'REVIEW_READY'
                            and receipt.get('golden_path_run_id') == int(rid)
                            and receipt.get('reference_only') is not True
                            and receipt.get('quality_gates_weakened') is False
                            and type(receipt.get('telegram_message_id')) is int
                            and receipt['telegram_message_id'] > 0)
        review_url = approval.get('review_url')
        if not review_url and review_delivered:
            review_url = f'https://mojo72549-arch.github.io/mind-reset-daily/tayvoriq/runs/{rid}/'
        complete = all(item['status'] == 'PUBLISHED' for item in platforms.values())
        record = {
            'review_id': rid, 'request_id': request.get('request_id'), 'run_id': int(rid),
            'topic': request.get('topic') or payload.get('title') or approval.get('title'),
            'slot': request.get('slot') or next((slot for slot in ('morning', 'evening')
                    if f'-{slot}-' in str(request.get('selection_id', ''))), None),
            'production_date': receipt.get('completed_at'),
            'published_at': publication.get('published_at') or approval.get('published_at'),
            'state': 'PUBLISHED' if complete else 'PARTIALLY_PUBLISHED',
            'fully_published': complete, 'publication_offered': False,
            'platforms': platforms, 'review_url': review_url,
            'videos': {'youtube': approval.get('youtube_video_url'),
                       'tiktok': approval.get('tiktok_video_url')},
            'sources': source.get('sources') or [],
            'script': source.get('story_first_script_body'),
            'script_kind': 'source_context_draft',
            'final_scripts': evidence.get('scripts') if bound else None,
            'source_context_sha256': request.get('source_context_sha256'),
            'history': request.get('state_history') or [],
            'quality': evidence.get('scores') if bound else None,
            'tools': evidence.get('tools') if bound else None,
            'metrics': {'youtube': None, 'tiktok': None},
            'evidence': {'publication': str(path.relative_to(root)),
                         'request': f'requests/{request["request_id"]}.json' if request else None,
                         'production': str(evidence_files[-1].relative_to(root)) if bound else None},
        }
        if review_delivered and review_url:
            for platform in ('youtube', 'tiktok'):
                record['videos'][platform] = record['videos'][platform] or review_url + f'short_{platform}.mp4'
        records[rid] = record
    return {'schema': 'tayvoriq-video-archive-v1',
            'records': sorted(records.values(), key=lambda r: r['run_id'], reverse=True)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path('.'))
    args = parser.parse_args()
    archive = build(args.root)
    target = args.root / ARCHIVE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'records': len(archive['records']),
                      'fully_published': sum(r['fully_published'] for r in archive['records'])}))


if __name__ == '__main__':
    main()
