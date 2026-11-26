"""Bind private computation to one public controller and unchanged editorial evidence."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

STUDIO = 'mojo72549-arch/shorts-agent-studio'
POINTER = Path('.github/state/tayvoriq-active-production-request.json')

def read(path):
    return json.loads(Path(path).read_text())

def write(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def identity(request, pointer):
    assert request['request_id'] == pointer['request_id'], 'REQUEST_MISMATCH'
    for key in ('source_context_sha256', 'contract_sha256', 'approval_key'):
        assert request[key] and request[key] == pointer[key], 'BINDING_MISMATCH:'+key
    actual = hashlib.sha256(json.dumps(request['source_context'], ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert actual == request['source_context_sha256'], 'SOURCES_CHANGED'
    assert request['source_context'].get('quality_gates_weakened') is not True
    assert request.get('quality_gates_weakened') is not True
    assert request.get('approved_at') and request.get('telegram_message_id'), 'APPROVAL_MISSING'

def prepare(request,pointer,controller):
    identity(request,pointer)
    assert not request.get('production_completion',{}).get('telegram_message_id'), 'ALREADY_DELIVERED'
    previous=int(request['golden_path_run_id'])
    if previous!=controller:
        request['previous_golden_path_run_ids']=list(dict.fromkeys(request.get('previous_golden_path_run_ids',[])+[previous]))
    request.update(status='DISPATCHED',golden_path_run_id=controller,execution_backend='contabo_private_runner')
    pointer.update(golden_path_run_id=controller,execution_backend='contabo_private_runner',execution_repository=STUDIO,
        execution_run_id=None,allow_recovery=False,reason='contabo-handoff-preparing',updated_at=datetime.now(timezone.utc).isoformat())

def bind(request, pointer, controller, worker, release):
    identity(request, pointer)
    assert not request.get('production_completion', {}).get('telegram_message_id'), 'ALREADY_DELIVERED'
    assert pointer['state'] == 'ACTIVE' and controller > 0 and worker > 0
    previous = int(request['golden_path_run_id'])
    if previous != controller:
        request['previous_golden_path_run_ids'] = list(dict.fromkeys(
            request.get('previous_golden_path_run_ids', []) + [previous]))
    handoff = dict(schema='tayvoriq-contabo-handoff-v1', controller_run_id=controller,
        worker_run_id=worker, execution_repository=STUDIO, checkpoint_release=release,
        request_id=request['request_id'], source_context_sha256=request['source_context_sha256'],
        contract_sha256=request['contract_sha256'], quality_gates_weakened=False)
    checkpoint=Path('implementation/out/recovery-checkpoint/meta.json')
    if checkpoint.is_file():
        meta=read(checkpoint)
        assert meta['source_context_sha256']==request['source_context_sha256']
        handoff['checkpoint_parent']=dict(run_id=int(meta['run_id']),run_attempt=int(meta['run_attempt']),source_request_id=request['request_id'],source_context_sha256=meta['source_context_sha256'],verified_recovery=True)
    green=read('.github/state/tayvoriq-production-green.json')
    recovery=request.get('codefix_recovery',{})
    recovery.update(status='REPLAY_DISPATCHED',request_substate='DISPATCHED',replay_run_id=controller,
        replay_implementation_sha=green['implementation_sha'],codefix_detection_reason='production-green-implementation-changed',
        active_pointer_verified=True,exact_source_request_required=True,same_generation_replay_required=True,
        quality_gates_weakened=False)
    request['codefix_recovery']=recovery
    request.update(status='DISPATCHED', golden_path_run_id=controller,
        execution_backend='contabo_private_runner', contabo_handoff=handoff)
    pointer.update(golden_path_run_id=controller, execution_backend='contabo_private_runner',
        execution_repository=STUDIO, execution_run_id=worker, allow_recovery=False,
        reason='contabo-controller-owns-private-computation', updated_at=datetime.now(timezone.utc).isoformat())

def verify(request, pointer, controller, worker, manifest=None):
    identity(request, pointer)
    handoff = request['contabo_handoff']
    assert handoff['schema'] == 'tayvoriq-contabo-handoff-v1'
    assert pointer['state'] == 'ACTIVE' and pointer['execution_backend'] == 'contabo_private_runner'
    assert int(request['golden_path_run_id']) == int(pointer['golden_path_run_id']) == controller
    assert handoff['controller_run_id'] == controller
    assert handoff['worker_run_id'] == pointer['execution_run_id'] == worker
    assert pointer['execution_repository'] == handoff['execution_repository'] == STUDIO
    assert handoff['source_context_sha256'] == request['source_context_sha256']
    assert handoff['contract_sha256'] == request['contract_sha256']
    assert handoff['quality_gates_weakened'] is False
    if manifest is not None:
        green = read('.github/state/tayvoriq-production-green.json')
        assert manifest['implementation_sha'] == green['implementation_sha']
        assert green['full_preflight_passed'] is True and green['quality_gates_weakened'] is False
        assert manifest['lightweight_preflight_passed'] is True
        assert manifest['quality_gates_weakened'] is False

def main():
    p=argparse.ArgumentParser()
    p.add_argument('operation', choices=['prepare','bind','verify','finalize'])
    p.add_argument('--request', required=True)
    p.add_argument('--controller', type=int, required=True)
    p.add_argument('--worker', type=int, required=True)
    p.add_argument('--release', default='')
    p.add_argument('--manifest')
    p.add_argument('--message', type=int)
    a=p.parse_args(); request=read(a.request); pointer=read(POINTER)
    if a.operation=='prepare':
        prepare(request,pointer,a.controller)
    elif a.operation=='bind':
        bind(request,pointer,a.controller,a.worker,a.release)
    else:
        verify(request,pointer,a.controller,a.worker,read(a.manifest) if a.manifest else None)
        if a.operation=='finalize':
            assert a.message and a.message>0, 'TELEGRAM_RECEIPT_REQUIRED'
            now=datetime.now(timezone.utc).isoformat()
            request['production_completion']=dict(state='REVIEW_READY',golden_path_run_id=a.controller,
                telegram_message_id=a.message, completed_at=now, quality_gates_weakened=False)
            pointer.update(state='COMPLETED',reason='contabo-review-delivered',completed_at=now,updated_at=now)
    if a.operation!='verify':
        write(a.request,request);write(POINTER,pointer)
    print('CONTABO_'+a.operation.upper()+'_VERIFIED')

if __name__=='__main__':
    main()
