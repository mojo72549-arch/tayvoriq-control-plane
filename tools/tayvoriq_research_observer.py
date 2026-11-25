"""Observe research events without changing its selection, retries or quality gates."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = 'mojo72549-arch/tayvoriq-control-plane'
PROVIDERS = ('gemini', 'groq', 'huggingface')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def issue_code(text):
    text = str(text).lower()
    if re.search(r'\b40[13]\b|access_blocked', text):
        return 'ACCESS'
    if 'cooldown/payment' in text or 'account/payment' in text:
        return 'PROVIDER_UNAVAILABLE'
    if re.search(r'\b402\b|payment required|payment_blocked', text):
        return 'PAYMENT'
    if re.search(r'\b429\b|quota|rate.limit|cooldown', text):
        return 'QUOTA'
    if 'timed out' in text or 'timeout' in text:
        return 'TIMEOUT'
    if any(word in text for word in ('contract insufficient', 'source pool', 'evidence', 'regional_minimum')):
        return 'SOURCES'
    return 'PROVIDER_ERROR'


class Observation:
    def __init__(self, selection, slot, run_id, attempt):
        if not re.fullmatch(r'\d{8}-(morning|evening)-agentv2(?:-[rc][0-9a-f]{1,8})?', selection):
            raise ValueError('Invalid research selection')
        if slot not in {'morning', 'evening'} or f'-{slot}-' not in selection:
            raise ValueError('Invalid research slot')
        if not str(run_id).isdigit() or not str(attempt).isdigit():
            raise ValueError('Invalid run binding')
        self.saved, self.rejected = set(), 0
        self.data = {'schema': 'tayvoriq-research-observation-v1', 'selection_id': selection,
                     'slot': slot, 'run_id': int(run_id), 'run_attempt': int(attempt),
                     'state': 'SEARCHING', 'started_at': stamp(), 'updated_at': stamp(),
                     'sources_seen': None, 'drafts_saved': 0, 'quality_rejections': 0,
                     'provider': None, 'issues': [], 'exit_code': None}

    def event(self, row):
        if not isinstance(row, dict):
            return False
        event = row.get('event')
        if event == 'source_records_loaded':
            value = row.get('total_records')
            if type(value) is int and 0 <= value <= 100000:
                self.data['sources_seen'] = value
        elif event == 'research_draft_saved':
            self.saved.add(hashlib.sha256(str(row.get('title', '')).encode()).hexdigest())
            self.data['drafts_saved'] = len(self.saved)
        elif event in {'candidate_editorial_rejection', 'regional_editorial_validation'}:
            self.rejected += 1
            self.data['quality_rejections'] = self.rejected
        elif event in {'provider_attempt_started', 'provider_success', 'provider_attempt_failed'}:
            provider = next((p for p in PROVIDERS if str(row.get('provider', '')).lower().startswith(p)), None)
            if provider:
                self.data['provider'] = provider
            if event == 'provider_attempt_failed':
                self.issue(row.get('error', ''), provider)
        elif event == 'research_deferred':
            for error in row.get('errors', [])[:20]:
                provider = next((p for p in PROVIDERS if p in str(error).lower()), None)
                self.issue(error, provider)
        else:
            return False
        self.data['updated_at'] = stamp()
        return True

    def issue(self, text, provider):
        # Publish codes only. Raw provider errors may contain URLs or credentials.
        issue = {'code': issue_code(text), 'provider': provider}
        if issue not in self.data['issues']:
            self.data['issues'] = [*self.data['issues'], issue][-12:]

    def finish(self, code):
        self.data.update(state='GENERATED' if code == 0 else 'FAILED', exit_code=code, updated_at=stamp())


def publish(data, token, *, request=urlopen):
    path = f"state/tayvoriq-research-progress/{data['selection_id']}.json"
    url = f'https://api.github.com/repos/{REPO}/contents/{path}'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'Content-Type': 'application/json', 'User-Agent': 'tayvoriq-research-observer'}
    sha = None
    try:
        with request(Request(url + '?ref=main', headers=headers), timeout=8) as response:
            meta = json.load(response)
        import base64
        previous = json.loads(base64.b64decode(meta['content']))
        if (previous.get('run_id') != data['run_id'] or
                previous.get('run_attempt', 0) > data['run_attempt']):
            return False
        sha = meta['sha']
    except HTTPError as error:
        if error.code != 404:
            raise
    import base64
    body = {'message': 'Observe research checkpoints ' + data['selection_id'], 'branch': 'main',
            'content': base64.b64encode((json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode()).decode()}
    if sha:
        body['sha'] = sha
    with request(Request(url, data=json.dumps(body).encode(), headers=headers, method='PUT'), timeout=8):
        return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--selection-id', required=True)
    parser.add_argument('--slot', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('Research command required')
    observation = Observation(args.selection_id, args.slot, os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT'])
    last = 0

    def save(force=False):
        nonlocal last
        if not force and time.monotonic() - last < 20:
            return
        last = time.monotonic()
        try:
            publish(observation.data, os.environ['GH_TOKEN'])
        except Exception:
            print('Research telemetry unavailable; the original research result remains authoritative.', file=sys.stderr)

    save(True)
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, env={**os.environ, 'PYTHONUNBUFFERED': '1'})
    for line in child.stdout:
        sys.stdout.write(line)
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if observation.event(row):
            save()
    code = child.wait()
    observation.finish(code)
    save(True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
