"""Queue one immutable research request for the private Contabo worker."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


STUDIO = 'mojo72549-arch/shorts-agent-studio'
CONTROL = 'mojo72549-arch/tayvoriq-control-plane'
RECEIPTS = '.automation/contabo-research-receipts'
QUEUE = '.github/state/tayvoriq-contabo-research-queue'
WAKEUP = '.automation/contabo-research-wakeup.json'
WORKER_START_TIMEOUT = 71
WORKER_RESULT_TIMEOUT = 72
OLLAMA_MODEL_TIMEOUT = 73
WAKEUP_ACCESS_DENIED = 77


def api(path, *, body=None, missing=False, public_write=False, wake_write=False):
    token = (os.getenv('STUDIO_RESEARCH_WAKE_TOKEN') if wake_write else None) or (
        os.getenv('STUDIO_RESEARCH_TOKEN') if not public_write else None) or os.getenv('GH_TOKEN')
    if not token:
        raise RuntimeError('CONTABO_RESEARCH_TOKEN_MISSING')
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
               'User-Agent': 'TAYVORIQ-Contabo-Research', 'Content-Type': 'application/json',
               'Cache-Control': 'no-cache'}
    request = Request('https://api.github.com/' + path, headers=headers,
                      data=json.dumps(body).encode() if body is not None else None,
                      method='PUT' if body is not None else 'GET')
    try:
        with urlopen(request, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        if missing and error.code == 404:
            return None
        raise RuntimeError(f'CONTABO_RESEARCH_GITHUB: HTTP {error.code}') from None


def receipt_api(binding):
    return f"repos/{STUDIO}/contents/{RECEIPTS}/{binding['selection']}-{binding['controller']}.{binding['attempt']}.json"


def read_receipt(binding):
    version = api(receipt_api(binding) + '?ref=main', missing=True)
    if version is None:
        return None, None
    receipt = json.loads(base64.b64decode(version['content']))
    if receipt.get('binding') != binding:
        raise RuntimeError('CONTABO_RESEARCH_BINDING_MISMATCH')
    return receipt, version['sha']


def write_receipt(binding, worker_id, status, root):
    if status == 'RUNNING' and not queue_current(binding):
        raise RuntimeError('CONTABO_RESEARCH_QUEUE_EXPIRED_OR_SUPERSEDED')
    current, sha = read_receipt(binding)
    if current and (current['worker_run_id'] != worker_id or current['status'] != 'RUNNING'):
        raise RuntimeError('CONTABO_RESEARCH_WORKER_ALREADY_BOUND')
    proof = {'binding': binding, 'worker_run_id': worker_id, 'status': status}
    if status != 'RUNNING':
        events = root / 'events.log'
        proof['events'] = [line for line in events.read_text().splitlines() if line.startswith('{')][-100:] if events.is_file() else []
    if status == 'SUCCEEDED':
        files = {name: (root / name).read_bytes() for name in ('selection.json', 'audit.json')}
        proof['files'] = {name: base64.b64encode(data).decode() for name, data in files.items()}
        proof['sha256'] = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    raw = json.dumps(proof, ensure_ascii=False).encode()
    if len(raw) > 900_000:
        raise RuntimeError('CONTABO_RESEARCH_RESULT_TOO_LARGE')
    payload = {'branch': 'main', 'message': f"Record Contabo research {binding['controller']}: {status}",
               'content': base64.b64encode(raw).decode()}
    if sha:
        payload['sha'] = sha
    api(receipt_api(binding), body=payload)


def check_result(root, expected, worker_id):
    proof = json.loads((root / 'receipt.json').read_text())
    if proof.get('binding') != expected or proof.get('worker_run_id') != worker_id:
        raise RuntimeError('CONTABO_RESEARCH_BINDING_MISMATCH')
    audit = json.loads((root / 'audit.json').read_text())
    providers = audit.get('provider', '').split('+')
    if not all(provider in {'ollama_rss', 'ollama_gdelt'} for provider in providers) or audit.get('quality_gates_weakened') is not False:
        raise RuntimeError('CONTABO_RESEARCH_PROVIDER_UNVERIFIED')
    for filename in ('selection.json', 'audit.json'):
        if hashlib.sha256((root / filename).read_bytes()).hexdigest() != proof.get('sha256', {}).get(filename):
            raise RuntimeError('CONTABO_RESEARCH_RESULT_CHANGED')


def queue_lane(binding):
    return {'verification': 'verification', 'scheduled': binding['slot'], 'review': 'review'}.get(
        binding['origin'], 'explicit')


def queue_api(binding):
    return f'repos/{CONTROL}/contents/{QUEUE}/{queue_lane(binding)}.json'


def queue_current(binding):
    current = api(queue_api(binding) + '?ref=main', missing=True, public_write=True)
    if not current:
        return False
    queued = json.loads(base64.b64decode(current['content']))
    if queued.get('binding') != binding or queued.get('expires_at', 0) <= time.time():
        return False
    if binding['origin'] == 'control_center':
        from tayvoriq_research_observer import control_center_stopped
        return not control_center_stopped(binding['selection'], os.getenv('GH_TOKEN', ''))
    return True


def resolve_queue(root, *, wake_revision=''):
    """Give a push wake priority only for its exact, still-current queued request."""
    pending = []
    for lane in ('explicit', 'morning', 'evening', 'review', 'verification'):
        path = root / QUEUE / f'{lane}.json'
        if path.is_file():
            item = json.loads(path.read_text())
            if item['expires_at'] > time.time() and queue_lane(item['binding']) == lane:
                pending.append(item)
    if wake_revision and pending:
        meta = api(f'repos/{STUDIO}/contents/{WAKEUP}?ref={wake_revision}', missing=True)
        if meta:
            binding = json.loads(base64.b64decode(meta['content'])).get('binding')
            pending.sort(key=lambda item: item['binding'] != binding)
    for item in pending:
        binding = item['binding']
        if read_receipt(binding)[0] is None and queue_current(binding):
            return item
    return None


def enqueue(binding, wait_seconds=760):
    path = queue_api(binding)
    current = api(path + '?ref=main', missing=True, public_write=True)
    queued = {'binding': binding, 'expires_at': int(time.time()) + wait_seconds + 10}
    payload = {'branch': 'main', 'message': f"Queue Contabo research {binding['controller']}",
               'content': base64.b64encode(json.dumps(queued).encode()).decode()}
    if current:
        previous = json.loads(base64.b64decode(current['content']))
        if previous.get('binding') == binding:
            return previous['expires_at']
        payload['sha'] = current['sha']
    api(path, body=payload, public_write=True)
    return queued['expires_at']


def wake_worker(binding, wake_attempt=1):
    """Wake the existing consumer; its receipt remains the exclusive worker claim."""
    if wake_attempt not in (1, 2):
        raise ValueError('CONTABO_RESEARCH_WAKEUP_BUDGET')
    if not queue_current(binding):
        raise RuntimeError('CONTABO_RESEARCH_QUEUE_EXPIRED_OR_SUPERSEDED')
    path = f'repos/{STUDIO}/contents/{WAKEUP}'
    for _ in range(3):
        current = api(path + '?ref=main', missing=True)
        if current:
            previous = json.loads(base64.b64decode(current['content']))
            if previous.get('binding') == binding and previous.get('wake_attempt', 0) >= wake_attempt:
                return
        value = {'binding': binding, 'wake_attempt': wake_attempt}
        payload = {'branch': 'main', 'message': f"Wake Contabo research {binding['controller']}.{binding['attempt']}",
                   'content': base64.b64encode(json.dumps(value).encode()).decode()}
        if current:
            payload['sha'] = current['sha']
        try:
            api(path, body=payload, wake_write=True)
            return
        except RuntimeError as error:
            if not str(error).endswith(('HTTP 409', 'HTTP 422')):
                raise
    raise RuntimeError('CONTABO_RESEARCH_WAKEUP_CONFLICT')


def event(name, **values):
    print(json.dumps({'event': name, **values}), flush=True)


def wait_for_result(binding, wait_seconds, *, deadline=None):
    deadline = min(deadline or float('inf'), time.monotonic() + wait_seconds)
    retry_at = time.monotonic() + 90
    wake_attempt, worker_started, access_denied = 0, False, False
    while time.monotonic() < deadline:
        receipt, _ = read_receipt(binding)
        if receipt:
            if not worker_started:
                event('contabo_worker_started', worker_run_id=receipt['worker_run_id'])
                worker_started = True
            if receipt['status'] != 'RUNNING':
                event('contabo_worker_finished', status=receipt['status'], worker_run_id=receipt['worker_run_id'])
                return receipt, 0
        elif wake_attempt == 0 or (wake_attempt == 1 and not access_denied and time.monotonic() >= retry_at):
            wake_attempt += 1
            confirmed = True
            try:
                wake_worker(binding, wake_attempt)
            except RuntimeError as error:
                confirmed = False
                access_denied = str(error).endswith(('HTTP 401', 'HTTP 403'))
                event('contabo_worker_failure', code='WORKER_WAKEUP_FAILED', terminal=False,
                      cause='ACCESS' if access_denied else 'UNCONFIRMED')
            retry_at = time.monotonic() + 90
            event('contabo_worker_wakeup', wake_attempt=wake_attempt, confirmed=confirmed,
                  next_check_epoch=time.time() + 90
                  if wake_attempt == 1 and not access_denied and retry_at < deadline else None)
        time.sleep(max(0, min(5, deadline - time.monotonic())))
    event('contabo_worker_failure', code='WORKER_RESULT_TIMEOUT' if worker_started else 'WORKER_START_TIMEOUT')
    if worker_started:
        return None, WORKER_RESULT_TIMEOUT
    return None, WAKEUP_ACCESS_DENIED if access_denied else WORKER_START_TIMEOUT


def worker_failure_code(events):
    if any(row.get('event') in {'regional_editorial_validation', 'candidate_editorial_rejection'}
           for row in events):
        return 65
    if any(row.get('event') == 'provider_attempt_failed' and row.get('provider') == 'ollama'
           and row.get('error') == 'Model timeout' for row in events):
        return OLLAMA_MODEL_TIMEOUT
    return 1


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--slot', choices=['morning', 'evening'], required=True)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--audit-output', type=Path, required=True)
    cli.add_argument('--wait-seconds', type=int, default=760, choices=range(1, 761), metavar='1-760')
    args = cli.parse_args()
    deadline = time.monotonic() + min(args.wait_seconds,
        float(os.getenv('TAYVORIQ_RESEARCH_DEADLINE_EPOCH') or time.time() + args.wait_seconds + 5) - time.time() - 5)
    binding = dict(selection=os.environ['TAYVORIQ_RESEARCH_SELECTION_ID'], slot=args.slot,
                   revision=os.environ['TAYVORIQ_CONTROL_REVISION'],
                   controller=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                   topic=os.getenv('TAYVORIQ_EDITORIAL_TOPIC', ''),
                   origin=os.getenv('TAYVORIQ_CONTABO_RESEARCH_ORIGIN', 'telegram_command'))
    receipt, _ = read_receipt(binding)
    if receipt is None:
        expires_at = enqueue(binding, max(1, int(deadline - time.monotonic())))
        deadline = min(deadline, time.monotonic() + expires_at - time.time() - 10)
    receipt, failure = wait_for_result(binding, args.wait_seconds, deadline=deadline)
    if receipt is None:
        return failure

    print(f"Verified private worker run {receipt['worker_run_id']}: {receipt['status']}", flush=True)
    for event in receipt.get('events', []):
        print(event, flush=True)
    if receipt['status'] != 'SUCCEEDED':
        events = [row for line in receipt.get('events', []) if isinstance((row := json.loads(line)), dict)]
        code = worker_failure_code(events)
        if code == OLLAMA_MODEL_TIMEOUT or (code == 65 and binding['origin'] in {'scheduled', 'review'}):
            return code
        raise RuntimeError(f"CONTABO_RESEARCH_{receipt['status']}")
    with tempfile.TemporaryDirectory(prefix='contabo-research-') as temporary:
        root = Path(temporary)
        (root / 'receipt.json').write_text(json.dumps(receipt))
        for name in ('selection.json', 'audit.json'):
            (root / name).write_bytes(base64.b64decode(receipt['files'][name]))
        check_result(root, binding, receipt['worker_run_id'])
        shutil.copyfile(root / 'selection.json', args.output)
        shutil.copyfile(root / 'audit.json', args.audit_output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
