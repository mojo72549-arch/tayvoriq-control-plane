"""A dispatch receipt requires an exact observed executor, not HTTP acceptance."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import time

WORKFLOWS = {
    'DELIVERY_WATCH': 'tayvoriq-delivery-watch.yml',
    'CODEFIX_CONTINUITY': 'tayvoriq-deterministic-codefix-continuity.yml',
    'CONTABO_QUALITY_RECOVERY': 'tayvoriq-contabo-controller.yml',
}


def dispatch_verified(action, request_id, run_id, decision_key, *, list_runs,
                      dispatch, reserve=None, pause=time.sleep, polls=8):
    if action not in WORKFLOWS or not re.fullmatch(r'[a-f0-9]{64}', decision_key):
        raise ValueError('LIFECYCLE_DISPATCH_IDENTITY_INVALID')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', request_id):
        raise ValueError('LIFECYCLE_DISPATCH_REQUEST_INVALID')
    if not str(run_id).isdigit() or int(run_id) <= 0:
        raise ValueError('LIFECYCLE_DISPATCH_RUN_INVALID')
    workflow = WORKFLOWS[action]
    title = 'TAYVORIQ lifecycle ' + decision_key

    def receipt():
        exact = [r for r in list_runs(workflow)
                 if r.get('display_title') == title
                 and r.get('event') == 'workflow_dispatch'
                 and r.get('head_branch') == 'main' and int(r.get('id') or 0) > 0]
        if len(exact) > 1:
            raise RuntimeError('LIFECYCLE_DISPATCH_DUPLICATE_EXECUTORS')
        return exact[0] if exact else None

    existing = receipt()
    if existing:
        return existing
    # A lost response can still have created the executor. Poll for its exact
    # correlation key before reporting failure; never blindly dispatch twice.
    transport_error = None
    if reserve is None or reserve(request_id, int(run_id), decision_key):
        try:
            dispatch(workflow, action, request_id, str(run_id), decision_key)
        except subprocess.CalledProcessError as error:
            transport_error = error
    for poll in range(polls):
        try:
            found = receipt()
        except subprocess.CalledProcessError:
            found = None
        if found:
            return found
        if poll + 1 < polls:
            pause(3)
    raise RuntimeError('LIFECYCLE_DISPATCH_NOT_ACKNOWLEDGED') from transport_error


def reserve_contabo_dispatch(repo, request_id, run_id, key):
    # The repository file is created without a SHA. A second process can read
    # the receipt, but only the process that created it may make the dispatch call.
    path = f'repos/{repo}/contents/run-status/contabo/dispatch-claims/{key}.json'
    decision = {'schema': 'tayvoriq-contabo-dispatch-claim-v1', 'request_id': request_id,
                'controller_run_id': run_id, 'decision_key': key, 'action': 'CONTABO_QUALITY_RECOVERY'}
    command = ['gh', 'api', path]
    payload = {'branch': 'main', 'message': 'Reserve one approved Contabo repair dispatch',
               'content': base64.b64encode(json.dumps(decision).encode()).decode()}
    try:
        subprocess.check_output([*command, '--method', 'PUT', '--input', '-'],
                                input=json.dumps(payload), text=True)
        return True
    except subprocess.CalledProcessError:
        current = json.loads(subprocess.check_output(command, text=True))
        if json.loads(base64.b64decode(current['content'])) != decision:
            raise RuntimeError('CONTABO_DISPATCH_CLAIM_BINDING_MISMATCH')
        return False


def main():
    parser = argparse.ArgumentParser()
    for name in ('action', 'request-id', 'run-id', 'decision-key'):
        parser.add_argument('--' + name, required=True)
    args = parser.parse_args()
    repo = os.environ['GITHUB_REPOSITORY']

    def list_runs(workflow):
        path = f'repos/{repo}/actions/workflows/{workflow}/runs?branch=main&event=workflow_dispatch&per_page=100'
        return json.loads(subprocess.check_output(['gh', 'api', path], text=True))['workflow_runs']

    def dispatch(workflow, action, request_id, run_id, key):
        command = ['gh', 'workflow', 'run', workflow, '--ref', 'main',
                   '-f', 'orchestrator_decision_key=' + key]
        if action == 'DELIVERY_WATCH':
            command += ['-f', 'run_id=' + run_id]
        elif action == 'CONTABO_QUALITY_RECOVERY':
            command += ['-f', 'quality_parent_run_id=' + run_id, '-f', 'source_request_id=' + request_id]
        else:
            command += ['-f', 'failed_run_id=' + run_id,
                        '-f', 'source_request_id=' + request_id]
        subprocess.run(command, check=True)

    reserve = None
    if args.action == 'CONTABO_QUALITY_RECOVERY':
        reserve = lambda request_id, run_id, key: reserve_contabo_dispatch(repo, request_id, run_id, key)
    executor = dispatch_verified(args.action, args.request_id, args.run_id,
                                 args.decision_key, list_runs=list_runs, dispatch=dispatch, reserve=reserve)
    with open(os.environ['GITHUB_OUTPUT'], 'a') as handle:
        handle.write('dispatch_verified=true\n')
        handle.write(f'executor_run_id={executor["id"]}\n')
        handle.write(f'executor_workflow={WORKFLOWS[args.action]}\n')
    print(f'LIFECYCLE_DISPATCH_ACKNOWLEDGED:{args.decision_key}:{executor["id"]}')


if __name__ == '__main__':
    main()
