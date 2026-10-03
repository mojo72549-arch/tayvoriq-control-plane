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


def await_completion(fetch, run_id, attempt, *, pause=time.sleep, polls=25):
    """Allow the signalling final step and Actions post steps to finish."""
    if run_id <= 0 or attempt <= 0:
        raise ValueError('LIFECYCLE_SIGNAL_ID_INVALID')
    for index in range(polls):
        run = fetch(run_id)
        if int(run.get('id') or 0) != run_id or run.get('name') not in WORKFLOWS:
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
