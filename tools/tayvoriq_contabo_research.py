"""Dispatch one immutable research request to the private Contabo worker."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


STUDIO = 'mojo72549-arch/shorts-agent-studio'
WORKFLOW = 'tayvoriq-contabo-research.yml'
ARTIFACT = 'contabo-research-result'


def gh(*args, body=None):
    return subprocess.run(['gh', *args], input=json.dumps(body) if body is not None else None,
                          env={**os.environ, 'GH_TOKEN': os.environ['STUDIO_RESEARCH_TOKEN']},
                          capture_output=True, text=True, check=True, timeout=25).stdout


def find_run(title):
    runs = json.loads(gh('run', 'list', '--repo', STUDIO, '--workflow', WORKFLOW,
                         '--event', 'repository_dispatch', '--limit', '50',
                         '--json', 'displayTitle,databaseId,status,conclusion'))
    matches = [run for run in runs if run['displayTitle'] == title]
    if len(matches) > 1:
        raise RuntimeError('CONTABO_RESEARCH_RUN_NOT_UNIQUE')
    return matches[0] if matches else None


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
    title = f"TAYVORIQ Ollama research {binding['selection']} {binding['controller']}.{binding['attempt']}"
    run = find_run(title)
    if run is None:
        gh('api', f'repos/{STUDIO}/dispatches', '--method', 'POST', '--input', '-',
           body={'event_type': 'tayvoriq_contabo_research', 'client_payload': binding})
    deadline = time.monotonic() + 490
    local_started = False
    while time.monotonic() < deadline:
        run = find_run(title)
        if run and run['status'] == 'completed':
            break
        if run and run['status'] == 'in_progress' and not local_started:
            jobs = json.loads(gh('run', 'view', str(run['databaseId']), '--repo', STUDIO, '--json', 'jobs'))['jobs']
            if any(step['name'] == 'Run source-bound Ollama ranking on Contabo' and step['status'] == 'in_progress'
                   for job in jobs for step in job['steps']):
                print(json.dumps({'event': 'provider_attempt_started', 'provider': 'ollama'}), flush=True)
                local_started = True
        time.sleep(5)
    else:
        raise RuntimeError('CONTABO_RESEARCH_TIMEOUT')

    worker_id = int(run['databaseId'])
    with tempfile.TemporaryDirectory(prefix='contabo-research-') as temporary:
        root = Path(temporary)
        gh('run', 'download', str(worker_id), '--repo', STUDIO, '--name', ARTIFACT, '--dir', str(root))
        if (root / 'events.log').is_file():
            for line in (root / 'events.log').read_text().splitlines():
                if line.startswith('{'):
                    print(line, flush=True)
        if run['conclusion'] != 'success':
            raise RuntimeError(f'CONTABO_RESEARCH_{run["conclusion"].upper()}')
        check_result(root, binding, worker_id)
        shutil.copyfile(root / 'selection.json', args.output)
        shutil.copyfile(root / 'audit.json', args.audit_output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
