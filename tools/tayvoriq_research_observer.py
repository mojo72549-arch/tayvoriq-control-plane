"""Run one bound explicit research request with shared cooldowns and bounded local recovery."""
import argparse
import base64
import queue
import tempfile
import threading
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

REPO = 'mojo72549-arch/tayvoriq-control-plane'
PROVIDERS = ('gemini', 'groq', 'huggingface', 'ollama')
STOPPED = 130
WORKER_FAILURES = {'WORKER_START_TIMEOUT', 'WORKER_RESULT_TIMEOUT', 'WORKER_WAKEUP_FAILED'}


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
        if slot not in {'morning', 'evening'} or f'-{slot}-' not in selection:
            raise ValueError('Invalid research slot')
        if not re.fullmatch(rf'(?:\d{{8}}-{slot}-agentv2(?:-[rc][0-9a-f]{{1,8}})?|review-{slot}-[1-9]\d{{0,19}})', selection):
            raise ValueError('Invalid research selection')
        if not str(run_id).isdigit() or not str(attempt).isdigit():
            raise ValueError('Invalid run binding')
        self.saved, self.rejected = set(), 0
        self.data = {'schema': 'tayvoriq-research-observation-v1', 'selection_id': selection,
                     'slot': slot, 'run_id': int(run_id), 'run_attempt': int(attempt),
                     'state': 'SEARCHING', 'started_at': stamp(), 'updated_at': stamp(),
                     'sources_seen': None, 'drafts_saved': 0, 'quality_rejections': 0,
                     'corroborated_headlines': None,
                     'provider': None, 'issues': [], 'exit_code': None, 'history': []}

    def record(self, event, **facts):
        """Keep a bounded history of verified facts, with the time they were observed."""
        history = self.data['history']
        entry = {'event': event, **facts}
        if history and {k: v for k, v in history[-1].items() if k != 'at'} == entry:
            return
        history.append({'at': stamp(), **entry})
        del history[:-40]

    def event(self, row):
        if not isinstance(row, dict):
            return False
        event = row.get('event')
        if event == 'contabo_worker_wakeup' and row.get('wake_attempt') in (1, 2):
            check = row.get('next_check_epoch')
            self.data['handoff'] = {'state': 'WAITING_FOR_WORKER', 'wake_attempt': row['wake_attempt'],
                'max_wake_attempts': 2, 'owner': 'contabo_research_worker',
                'wakeup_confirmed': row.get('confirmed') is True,
                'next_check_at': datetime.fromtimestamp(check, timezone.utc).isoformat()
                    if type(check) in (int, float) and 0 < check < 253402300799 else None}
            self.record(event, wake_attempt=row['wake_attempt'], confirmed=row.get('confirmed') is True)
        elif event == 'contabo_worker_started' and type(row.get('worker_run_id')) is int and row['worker_run_id'] > 0:
            self.data.setdefault('handoff', {}).update(state='RUNNING', worker_run_id=row['worker_run_id'],
                next_check_at=None, owner='contabo_research_worker')
            self.data['issues'] = [issue for issue in self.data['issues'] if issue['code'] != 'WORKER_WAKEUP_FAILED']
            self.record(event, worker_run_id=row['worker_run_id'])
        elif event == 'contabo_worker_finished' and row.get('status') in {'SUCCEEDED', 'FAILED'}:
            self.data.setdefault('handoff', {}).update(state='COMPLETED' if row['status'] == 'SUCCEEDED' else 'FAILED',
                next_check_at=None)
            self.record(event, status=row['status'])
        elif event == 'insufficient_corroborated_stories' and isinstance(row.get('corroborated_titles'), list):
            self.data['corroborated_headlines'] = len(row['corroborated_titles'])
            self.issue('source evidence insufficient', None)
            self.record(event, count=self.data['corroborated_headlines'])
        elif event == 'contabo_worker_failure' and row.get('code') in WORKER_FAILURES:
            code = row['code']
            issue = {'code': code, 'provider': None}
            if issue not in self.data['issues']:
                self.data['issues'] = [*self.data['issues'], issue][-12:]
            if code == 'WORKER_WAKEUP_FAILED' and row.get('cause') in {'ACCESS', 'UNCONFIRMED'}:
                self.data['wakeup_failure_cause'] = row['cause']
            self.record(event, code=code, cause=row.get('cause') if row.get('cause') in ('ACCESS', 'UNCONFIRMED') else None)
            if row.get('terminal', True):
                self.data.setdefault('handoff', {}).update(state='BLOCKED', next_check_at=None,
                    owner='production_engineering', action_required='CHECK_BOUND_WORKER_RESULT'
                    if code == 'WORKER_RESULT_TIMEOUT' else 'CHECK_RESEARCH_WAKEUP_ACCESS'
                    if any(i['code'] == 'WORKER_WAKEUP_FAILED' for i in self.data['issues'])
                    else 'CHECK_CONTABO_RESEARCH_RUNNER')
        elif event == 'source_records_loaded':
            value = row.get('total_records')
            if type(value) is int and 0 <= value <= 100000:
                self.data['sources_seen'] = value
                self.record(event, count=value)
        elif event == 'research_draft_saved':
            self.saved.add(hashlib.sha256(str(row.get('title', '')).encode()).hexdigest())
            self.data['drafts_saved'] = len(self.saved)
        elif event == 'source_headline_preflight':
            value = row.get('corroborated_headlines')
            if type(value) is int and 0 <= value <= 100000:
                self.data['corroborated_headlines'] = value
                self.record(event, count=value)
                if value >= 2:
                    self.data['issues'] = [issue for issue in self.data['issues'] if issue['code'] != 'SOURCES']
        elif event == 'candidate_editorial_rejection':
            self.rejected += 1
            self.data['quality_rejections'] = self.rejected
            details = row.get('details') or []
            incomplete = ('invalid_or_unexplained_rating:', 'platform_fit_missing:')
            if (any(str(d).startswith(incomplete) for d in details)
                    or row.get('reason') in {'regional_scorecard_missing', 'regional_ratings_or_platform_fit_missing'}):
                code = 'EDITORIAL_FIELDS'
            elif row.get('reason') == 'claim_coherence':
                code = 'CLAIM_SUPPORT'
            elif any(str(d).startswith('tiktok:regional_score_below') for d in details):
                code = 'TIKTOK_FIT'
            else:
                code = 'EDITORIAL_QUALITY'
            issue = {'code': code, 'provider': None}
            if issue not in self.data['issues']:
                self.data['issues'] = [*self.data['issues'], issue][-12:]
        elif event == 'regional_editorial_validation':
            pass  # A batch summary is not another rejected candidate.
        elif event == 'research_deadline_reached':
            self.issue('Research timeout', self.data.get('provider'))
            self.record(event)
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

    def waiting(self, retry_at, attempt):
        self.data.update(state='WAITING', next_retry_at=datetime.fromtimestamp(retry_at, timezone.utc).isoformat(),
                         local_attempt=attempt, max_local_attempts=3, updated_at=stamp())
        self.record('retry_waiting', next_retry_at=self.data['next_retry_at'], local_attempt=attempt)

    def finish(self, code):
        if code == 124 and self.data.get('handoff', {}).get('state') in {'WAITING_FOR_WORKER', 'RUNNING'}:
            self.event({'event': 'contabo_worker_failure', 'code': 'WORKER_RESULT_TIMEOUT'
                if self.data['handoff'].get('worker_run_id') else 'WORKER_START_TIMEOUT'})
        if self.data.get('handoff'):
            self.data['handoff']['next_check_at'] = None
            if code == 0:
                self.data['handoff']['state'] = 'COMPLETED'
            elif code == STOPPED:
                self.data['handoff']['state'] = 'STOPPED'
            elif self.data['handoff']['state'] in {'RUNNING', 'FAILED', 'WAITING_FOR_WORKER'}:
                source_blocked = any(issue['code'] == 'SOURCES' for issue in self.data['issues'])
                self.data['handoff'].update(state='BLOCKED', owner='research_controller' if source_blocked else 'production_engineering',
                    action_required='RESEARCH_ADDITIONAL_ORIGINAL_SOURCES' if source_blocked else 'CHECK_BOUND_WORKER_RESULT')
        self.data.update(state='GENERATED' if code == 0 else 'FAILED', exit_code=code,
                         next_retry_at=None, updated_at=stamp())
        self.record('research_finished', exit_code=code)


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


def load_json(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}


def control_center_stopped(selection, token, *, request=urlopen):
    url = f'https://api.github.com/repos/{REPO}/contents/state/tayvoriq-control-center-research.json?ref=main'
    headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'tayvoriq-research-observer',
               'Cache-Control': 'no-cache'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    with request(Request(url, headers=headers), timeout=8) as response:
        pointer = json.loads(base64.b64decode(json.load(response)['content']))
    if pointer.get('schema') != 'tayvoriq-control-center-research-v1':
        raise ValueError('Invalid Control Center research pointer')
    return pointer.get('selection_id') != selection or bool(pointer.get('cancel_requested_at'))


def context(selection, slot, root, temporary, *, now=None):
    """Explicit requests share provider cooldowns, but never another slot's drafts or retry budget."""
    now = time.time() if now is None else now
    scope = '.automation/tayvoriq-agent-v2'
    paths = {'health': scope + '/provider-health.json',
             'drafts': scope + '/research-candidates/' + selection + '.json',
             'retry': scope + '/control-center-retries/' + selection + '.json'}
    files, original = {}, {}
    for kind, relative in paths.items():
        value = load_json(root / relative)
        original[kind] = value
        path = temporary / (kind + '.json')
        if value:
            path.write_text(json.dumps(value), encoding='utf-8')
        files[kind] = path
    previous = original['retry']
    budget = 835 if os.environ.get('TAYVORIQ_CONTROL_REVISION') else 600
    deadline = min(now + budget, float(previous.get('valid_until_epoch') or now + budget))
    env = {**os.environ, 'PYTHONUNBUFFERED': '1', 'TAYVORIQ_RESEARCH_SLOT': slot,
           'TAYVORIQ_RESEARCH_SELECTION_ID': selection,
           'TAYVORIQ_RESEARCH_STARTED_AT_EPOCH': str(int(previous.get('first_deferred_at_epoch') or now)),
           'TAYVORIQ_PROVIDER_HEALTH_FILE': str(files['health']),
           'TAYVORIQ_RESEARCH_CHECKPOINT_FILE': str(files['drafts']),
           'TAYVORIQ_RESEARCH_RETRY_FILE': str(files['retry'])}
    platform_key = '.'.join(os.getenv(name, '') for name in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'))
    if re.fullmatch(r'[1-9][0-9]*\.[1-9][0-9]*', platform_key):
        env['TAYVORIQ_RESEARCH_RUN_KEY'] = platform_key
    else:
        env.pop('TAYVORIQ_RESEARCH_RUN_KEY', None)
    return {'paths': paths, 'files': files, 'original': original, 'env': env, 'deadline': deadline}


def merge_health(original, updated, latest):
    merged = dict(latest.get('providers') or {})
    before, after = original.get('providers') or {}, updated.get('providers') or {}
    for name in before.keys() - after.keys():
        if merged.get(name) == before[name]:
            merged.pop(name, None)
    for name, record in after.items():
        if float(record.get('observed_at_epoch') or 0) >= float((merged.get(name) or {}).get('observed_at_epoch') or 0):
            merged[name] = record
    return {'schema': 'tayvoriq-provider-health-v1', 'providers': merged}


def persist_context(state, token, *, request=urlopen):
    for kind, path in state['files'].items():
        updated = load_json(path)
        if not updated or updated == state['original'][kind]:
            continue
        relative = state['paths'][kind]
        url = f'https://api.github.com/repos/{REPO}/contents/{relative}'
        headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                   'Content-Type': 'application/json', 'User-Agent': 'tayvoriq-research-context'}
        for _ in range(3):
            sha, latest = None, {}
            try:
                with request(Request(url + '?ref=main', headers=headers), timeout=8) as response:
                    meta = json.load(response)
                sha = meta['sha']
                latest = json.loads(base64.b64decode(meta['content']))
            except HTTPError as error:
                if error.code != 404:
                    raise
            value = merge_health(state['original'][kind], updated, latest) if kind == 'health' else updated
            payload = {'branch': 'main', 'message': 'Preserve research context ' + kind,
                       'content': base64.b64encode((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()).decode()}
            if sha:
                payload['sha'] = sha
            try:
                with request(Request(url, data=json.dumps(payload).encode(), headers=headers, method='PUT'), timeout=8):
                    state['original'][kind] = json.loads(json.dumps(updated))
                    break
            except HTTPError as error:
                if error.code not in {409, 422}:
                    raise
        else:
            raise RuntimeError('Research context version changed repeatedly')


def run_child(command, env, deadline, observation, save, *, clock=time.time, stopped=lambda: False, stop_interval=5):
    """Keep the original research result, with a real wall-clock timeout and heartbeat."""
    if env.get('TAYVORIQ_LOCAL_RESEARCH') == 'true' or env.get('TAYVORIQ_CONTROL_REVISION'):
        env = {**env, 'TAYVORIQ_RESEARCH_DEADLINE_EPOCH': str(deadline)}
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    lines = queue.SimpleQueue()
    def read():
        try:
            for line in child.stdout:
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    next_stop_check = clock() + stop_interval
    try:
        while True:
            now = clock()
            if now >= deadline:
                if env.get('TAYVORIQ_LOCAL_RESEARCH') == 'true':
                    print(json.dumps({'event': 'research_deadline_reached'}), flush=True)
                return 124
            if now >= next_stop_check:
                if stopped():
                    return STOPPED
                next_stop_check = now + stop_interval
            try:
                line = lines.get(timeout=1)
            except queue.Empty:
                save()
                continue
            if line is None:
                return child.wait()
            sys.stdout.write(line)
            try:
                observation.event(json.loads(line))
            except ValueError:
                pass
            save()
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        reader.join(timeout=1)
        child.stdout.close()


def execute(command, state, observation, save, persist, *, clock=time.time, pause=time.sleep, run=run_child,
            stopped=lambda: False):
    def finish_stopped():
        observation.finish(STOPPED)
        observation.data['state'] = 'STOPPED'
        save(True)
        return STOPPED

    previous = load_json(state['files']['retry'])
    attempts = int(previous.get('attempts') or 0)
    if previous.get('state') == 'EXHAUSTED' or state['deadline'] - clock() < 45:
        observation.finish(124)
        save(True)
        return 124
    for attempt in range(attempts + 1, 4):
        if stopped():
            return finish_stopped()
        observation.data.update(state='SEARCHING', local_attempt=attempt, max_local_attempts=3, next_retry_at=None)
        state['env']['TAYVORIQ_RESEARCH_LOCAL_ATTEMPT'] = str(attempt)
        save(True)
        seconds = 775 if state['env'].get('TAYVORIQ_CONTROL_REVISION') else 420
        code = run(command, state['env'], min(clock() + seconds, state['deadline'] - 35), observation, save)
        if code == STOPPED or stopped():
            return finish_stopped()
        try:
            persist()
        except Exception:
            print('Research context could not be persisted; no additional automatic retry is started.', file=sys.stderr)
            observation.finish(code)
            save(True)
            return code
        if code == 0:
            observation.finish(0)
            save(True)
            return 0
        retry = load_json(state['files']['retry'])
        retry_at = float(retry.get('retry_at_epoch') or 0)
        if (retry.get('state') != 'WAITING' or attempt >= 3 or retry_at <= 0
                or max(clock(), retry_at) + 45 >= state['deadline']):
            observation.finish(code)
            save(True)
            return code
        observation.waiting(retry_at, attempt)
        save(True)
        while clock() < retry_at:
            pause(min(5, retry_at - clock()))
            if stopped():
                return finish_stopped()
            save()
    observation.finish(1)
    save(True)
    return 1


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
        observation.data['updated_at'] = stamp()
        try:
            publish(observation.data, os.environ['GH_TOKEN'])
        except Exception:
            print('Research telemetry unavailable; the original research result remains authoritative.', file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix='tayvoriq-research-') as temporary:
        state = context(args.selection_id, args.slot, Path.cwd(), Path(temporary))
        def stopped():
            return (os.environ.get('TAYVORIQ_CONTROL_CENTER_RESEARCH') == 'true'
                    and control_center_stopped(args.selection_id, os.environ['GH_TOKEN']))

        return execute(command, state, observation, save, lambda: persist_context(state, os.environ['GH_TOKEN']),
                       stopped=stopped, run=partial(run_child, stopped=stopped))


if __name__ == '__main__':
    raise SystemExit(main())
