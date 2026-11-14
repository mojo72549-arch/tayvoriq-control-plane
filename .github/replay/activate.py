from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    api = 'https://api.github.com/repos/' + repo
    review_id = os.environ['BOUND_REVIEW_RUN_ID']
    package = Path('review/implementation/site/tayvoriq/runs') / review_id
    receipt = json.loads(Path('receipt/telegram-receipt.json').read_text())
    if str(receipt.get('run_id')) != review_id or receipt.get('quality_gate') != 'passed':
        raise RuntimeError('REPLAY_RECEIPT_INVALID')
    mid = receipt.get('telegram_message_id')
    if type(mid) is not int or mid <= 0:
        raise RuntimeError('REPLAY_TELEGRAM_ID_INVALID')
    run = github(api, f'/actions/runs/{review_id}')
    if (run.get('conclusion') != 'success' or run.get('head_sha') != os.environ['BOUND_REPLAY_SHA']
            or str(run.get('id')) != review_id):
        raise RuntimeError('REPLAY_RUN_INVALID')
    deploy = github(api, '/contents/state/tayvoriq-telegram-worker-deploy-receipt.json?ref=main')
    import base64
    live = json.loads(base64.b64decode(deploy['content']))
    expected_deploy = os.environ['APPROVAL_DEPLOY_SHA']
    if not (live.get('deploy_verified') is True and live.get('webhook_verified') is True
            and live.get('commit_sha') == expected_deploy):
        raise RuntimeError('TELEGRAM_WORKER_DEPLOYMENT_UNVERIFIED')
    hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in package.iterdir() if path.is_file()}
    decision = {'schema': 'tayvoriq-artifact-approval', 'state': 'PENDING', 'review_id': review_id,
                'telegram_message_id': mid, 'request_id': receipt['request_id'],
                'source_context_sha256': receipt['source_context_sha256'], 'studio_sha': receipt['studio_sha'],
                'files_sha256': hashes}
    from tayvoriq_artifact_approval import verify_package
    verify_package(package, {**decision, 'state': 'APPROVED', 'decision_id': 'verification-only',
                             'decided_via': 'telegram_callback'}, review_id)
    endpoint = f'/contents/.automation/tayvoriq-artifact-decisions/{review_id}.json'
    current = github(api, endpoint + '?ref=main', missing_ok=True)
    if current:
        previous = json.loads(base64.b64decode(current['content']))
        if previous != decision:
            raise RuntimeError('REVIEW_DECISION_ALREADY_EXISTS')
    else:
        content = base64.b64encode((json.dumps(decision, ensure_ascii=False, indent=2) + '\n').encode()).decode()
        github(api, endpoint, method='PUT', body={'message': f'Bind pending Telegram decision {review_id}',
                                                  'branch': 'main', 'content': content})
    keyboard = [[{'text': 'Review-Artefakt', 'url': f'https://github.com/{repo}/actions/runs/{review_id}/artifacts/{os.environ["BOUND_REVIEW_ARTIFACT_ID"]}'}],
                [{'text': '✅ Freigeben', 'callback_data': f'tayvoriq:artifact:approve:{review_id}'},
                 {'text': '❌ Ablehnen', 'callback_data': f'tayvoriq:artifact:reject:{review_id}'}]]
    payload = {'chat_id': os.environ['TELEGRAM_CHAT_ID'], 'message_id': mid,
               'caption': 'TAYVORIQ · Geprüftes Video zur Freigabe\n\nFreigeben startet den YouTube-Upload. Das TikTok-Paket kommt zur manuellen Veröffentlichung. Ablehnen beendet die Freigabe.',
               'reply_markup': {'inline_keyboard': keyboard}}
    try:
        telegram = fetch(f'https://api.telegram.org/bot{os.environ["TELEGRAM_BOT_TOKEN"]}/editMessageCaption',
                         method='POST', body=payload)
    except Exception as exc:
        raise RuntimeError(f'TELEGRAM_CAPTION_EDIT_UNCONFIRMED:{type(exc).__name__}') from None
    result = telegram.get('result') or {}
    if telegram.get('ok') is not True or result.get('message_id') != mid or result.get('reply_markup') != payload['reply_markup']:
        raise RuntimeError('TELEGRAM_APPROVAL_BUTTONS_UNCONFIRMED')
    print(f'TELEGRAM_APPROVAL_BUTTONS_CONFIRMED:{review_id}:{mid}')


def fetch(url, *, method='GET', body=None, headers=None):
    req = Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                  headers={'Content-Type': 'application/json', **(headers or {})})
    with urlopen(req, timeout=25) as response:
        return json.load(response)


def github(api, path, *, method='GET', body=None, missing_ok=False):
    try:
        return fetch(api + path, method=method, body=body,
                     headers={'Accept': 'application/vnd.github+json', 'Authorization': 'Bearer ' + os.environ['GH_TOKEN']})
    except HTTPError as exc:
        if exc.code == 404 and missing_ok:
            return None
        raise RuntimeError(f'GITHUB_REVIEW_ACTIVATION_FAILED:{exc.code}') from None


if __name__ == '__main__':
    main()
