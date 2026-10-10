"""Explicit completion signal; the Orchestrator remains the decision owner."""
from __future__ import annotations

import json
import os
import subprocess
import time

WORKFLOWS = {
    'TAYVORIQ-X Golden Path', 'TAYVORIQ Production Green Promoter',
    'TAYVORIQ Deterministic Codefix Continuity', 'TAYVORIQ Delivery Watch',
    'TAYVORIQ Autonomous Codefix Builder',
}
WORKFLOW_PATHS = {
    '.github/workflows/tayvoriq-deliver-video-now.yml',
    '.github/workflows/tayvoriq-production-green-promoter.yml',
    '.github/workflows/tayvoriq-deterministic-codefix-continuity.yml',
    '.github/workflows/tayvoriq-delivery-watch.yml',
    '.github/workflows/tayvoriq-autonomous-codefix-builder.yml',
}


def await_completion(fetch, run_id, attempt, *, pause=time.sleep, polls=25):
    """Allow the signalling final step and Actions post steps to finish."""
    if run_id <= 0 or attempt <= 0:
        raise ValueError('LIFECYCLE_SIGNAL_ID_INVALID')
    for index in range(polls):
        run = fetch(run_id)
        # GitHub reports a configured run-name as name as well as display_title.
        # Correlated lifecycle executors therefore need their stable API path.
        path = str(run.get('path') or '').split('@', 1)[0]
        known = path in WORKFLOW_PATHS if path else run.get('name') in WORKFLOWS
        if int(run.get('id') or 0) != run_id or not known:
            raise ValueError('LIFECYCLE_SIGNAL_WORKFLOW_INVALID')
        if int(run.get('run_attempt') or 0) != attempt:
            return 'SUPERSEDED'
        if run.get('status') == 'completed':
            return 'COMPLETED'
        if index + 1 < polls:
            pause(5)
    return 'TIMEOUT'


def signal():
    run_id = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    payload = {'ref': 'main', 'inputs': {'reconcile_only': 'true',
               'signal_run_id': str(run_id), 'signal_run_attempt': str(attempt)}}
    # POST dispatch is explicitly permitted for GITHUB_TOKEN. No implicit chained
    # workflow_run event or delayed cron tick is needed for this handoff.
    subprocess.run(['gh', 'api', '--method', 'POST',
        f'repos/{os.environ["GITHUB_REPOSITORY"]}/actions/workflows/tayvoriq-agent-orchestrator-v2.yml/dispatches',
        '--input', '-'], input=json.dumps(payload), text=True, check=True)
    print(f'LIFECYCLE_SIGNAL_ACCEPTED:{run_id}:{attempt}')


if __name__ == '__main__':
    signal()

