"""Retry a terminal software-workplace clip failure after verified promotion."""

import json
import os
import re
from pathlib import Path

from tayvoriq_contabo_handoff import POINTER, identity, read
from tayvoriq_slot_serialization_v1 import CONTABO_WORKFLOWS, contabo_publishability_failed, github_json
from tayvoriq_stale_news_reconcile_v1 import has_delivery_evidence


def plan(root, repo, token, *, expected_run=None):
    pointer = read(root / POINTER)
    request_id = str(pointer.get('request_id') or '')
    old_run = pointer.get('golden_path_run_id')
    if (pointer.get('state') != 'ACTIVE' or pointer.get('execution_backend') != 'contabo_private_runner'
            or not re.fullmatch(r'[A-Za-z0-9_-]{4,80}', request_id) or type(old_run) is not int or old_run <= 0
            or (expected_run is not None and old_run != expected_run)):
        return None
    request = read(root / 'requests' / f'{request_id}.json')
    if (request.get('status') != 'DISPATCHED' or request.get('visual_recovery') or has_delivery_evidence(request)
            or not contabo_publishability_failed(root, pointer, request)):
        return None
    identity(request, pointer)
    failure = read(root / 'run-status/contabo' / f'{old_run}.json').get('failure_detail') or {}
    topic = str(request.get('topic') or '').casefold()
    if (failure.get('code') != 'REAL_VIDEO_SCENE_REQUIRED' or type(failure.get('scene')) is not int
            or not 1 <= failure['scene'] <= 99
            or not re.search(r'\b(?:sap|softwareunternehmen|softwarekonzern|softwareanbieter)\b', topic)
            or not re.search(r'\b(?:stellenabbau|umbau|umstrukturierung|personalabbau|arbeitsplätze|stellen)\b', topic)):
        return None
    green = read(root / '.github/state/tayvoriq-production-green.json')
    implementation = green.get('implementation_sha') or ''
    if (green.get('schema') != 'tayvoriq-production-green-v1' or green.get('full_preflight_passed') is not True
            or green.get('quality_gates_weakened') is not False or green.get('software_workplace_search_verified') is not True
            or not re.fullmatch(r'[a-f0-9]{40}', implementation)
            or implementation == (request.get('codefix_recovery') or {}).get('replay_implementation_sha')):
        return None
    run = github_json(f'https://api.github.com/repos/{repo}/actions/runs/{old_run}', token)
    if (run.get('id') != old_run or run.get('status') != 'completed' or run.get('conclusion') != 'failure'
            or run.get('head_branch') != 'main' or str(run.get('path') or '').split('@')[0] not in CONTABO_WORKFLOWS):
        return None
    return {'schema':'tayvoriq-contabo-visual-recovery-v1','request_id':request_id,'previous_run_id':old_run,
            'implementation_sha':implementation,'scene':failure['scene'],'quality_gates_weakened':False}


if __name__ == '__main__':
    result = plan(Path('.'), os.environ['GITHUB_REPOSITORY'], os.environ['GH_TOKEN'])
    if result:
        print(json.dumps(result))
