"""Queue one immutable research request for the private Contabo worker."""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


STUDIO = 'mojo72549-arch/shorts-agent-studio'
CONTROL = 'mojo72549-arch/tayvoriq-control-plane'
RECEIPTS = '.automation/contabo-research-receipts'
QUEUE = '.github/state/tayvoriq-contabo-research-queue'


def gh(*args, body=None, missing=False, public_write=False):
    token = (os.getenv('STUDIO_RESEARCH_TOKEN') if not public_write else None) or os.getenv('GH_TOKEN')
    if not token:
        raise RuntimeError('CONTABO_RESEARCH_TOKEN_MISSING')
    result = subprocess.run(['gh', *args], input=json.dumps(body) if body is not None else None,
                            env={**os.environ, 'GH_TOKEN': token},
                            capture_output=True, text=True, timeout=25)
    if result.returncode:
        if missing and '(HTTP 404)' in result.stderr:
            return None
        error = result.stderr.replace(token, '***').strip().splitlines()
        raise RuntimeError(f'CONTABO_RESEARCH_GITHUB: {error[-1][:300] if error else result.returncode}')
    return result.stdout


def receipt_api(binding):
    return f"repos/{STUDIO}/contents/{RECEIPTS}/{binding['selection']}-{binding['controller']}.{binding['attempt']}.json"


def read_receipt(binding):
    meta = gh('api', receipt_api(binding) + '?ref=main', missing=True)
    if meta is None:
        return None, None
    version = json.loads(meta)
    receipt = json.loads(base64.b64decode(version['content']))
    if receipt.get('binding') != binding:
        raise RuntimeError('CONTABO_RESEARCH_BINDING_MISMATCH')
    return receipt, version['sha']


def write_receipt(binding, worker_id, status, root):
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
    gh('api', receipt_api(binding), '--method', 'PUT', '--input', '-', body=payload)


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


def enqueue(binding):
    lane = 'verification' if binding['origin'] == 'verification' else 'explicit'
    path = f'repos/{CONTROL}/contents/{QUEUE}/{lane}.json'
    current = gh('api', path + '?ref=main', missing=True, public_write=True)
    queued = {'binding': binding, 'expires_at': int(time.time()) + 770}
    payload = {'branch': 'main', 'message': f"Queue Contabo research {binding['controller']}",
               'content': base64.b64encode(json.dumps(queued).encode()).decode()}
    if current:
        meta = json.loads(current)
        previous = json.loads(base64.b64decode(meta['content']))
        if previous.get('binding') == binding:
            return
        payload['sha'] = meta['sha']
    gh('api', path, '--method', 'PUT', '--input', '-', body=payload, public_write=True)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--slot', choices=['morning', 'evening'], required=True)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--audit-output', type=Path, required=True)
    args = cli.parse_args()
    binding = dict(selection=os.environ['TAYVORIQ_RESEARCH_SELECTION_ID'], slot=args.slot,
                   revision=os.environ['TAYVORIQ_CONTROL_REVISION'],
                   controller=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                   topic=os.getenv('TAYVORIQ_EDITORIAL_TOPIC', ''),
                   origin=os.getenv('TAYVORIQ_CONTABO_RESEARCH_ORIGIN', 'telegram_command'))
    receipt, _ = read_receipt(binding)
    if receipt is None:
        enqueue(binding)
    deadline = time.monotonic() + 760
    local_started = False
    while time.monotonic() < deadline:
        receipt, _ = read_receipt(binding)
        if receipt and receipt['status'] != 'RUNNING':
            break
        if receipt and not local_started:
            print(json.dumps({'event': 'provider_attempt_started', 'provider': 'ollama'}), flush=True)
            local_started = True
        time.sleep(5)
    else:
        raise RuntimeError('CONTABO_RESEARCH_TIMEOUT')

    print(f"Verified private worker run {receipt['worker_run_id']}: {receipt['status']}", flush=True)
    for event in receipt.get('events', []):
        print(event, flush=True)
    if receipt['status'] != 'SUCCEEDED':
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
