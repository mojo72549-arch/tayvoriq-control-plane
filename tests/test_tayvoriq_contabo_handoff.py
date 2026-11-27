import copy,json
import pytest
from tools.tayvoriq_contabo_handoff import bind,verify,identity

@pytest.fixture
def context(tmp_path,monkeypatch):
    from pathlib import Path
    request=json.loads(Path('requests/telegram-3751-trend-1.json').read_text())
    pointer=json.loads(Path('.github/state/tayvoriq-active-production-request.json').read_text())
    request.pop('production_completion', None)
    pointer.update({key: request[key] for key in ('request_id', 'golden_path_run_id', 'source_context_sha256',
                                                  'contract_sha256', 'approval_key')}, state='ACTIVE')
    green=json.loads(Path('.github/state/tayvoriq-production-green.json').read_text())
    monkeypatch.chdir(tmp_path)
    Path('.github/state').mkdir(parents=True)
    Path('.github/state/tayvoriq-production-green.json').write_text(json.dumps(green))
    return request,pointer

def test_migration_preserves_approval_sources_generation_and_previous_owner(context):
    request,pointer=context
    frozen=copy.deepcopy(request)
    bind(request,pointer,90001,90002,'private-checkpoint')
    verify(request,pointer,90001,90002)
    for key in ('source_context','source_context_sha256','contract_sha256','approval_key','approved_at','recovery_generation'):
        assert request[key]==frozen[key]
    assert frozen['golden_path_run_id'] in request['previous_golden_path_run_ids']
    assert pointer['allow_recovery'] is False
    assert 'production_completion' not in request

def test_wrong_worker_and_changed_sources_are_rejected(context):
    request,pointer=context
    bind(request,pointer,90001,90002,'private-checkpoint')
    with pytest.raises(AssertionError):verify(request,pointer,90001,90003)
    request['source_context']['changed']=True
    with pytest.raises(AssertionError):identity(request,pointer)

def test_verified_quality_cannot_be_reused_from_another_implementation(context):
    request,pointer=context
    bind(request,pointer,90001,90002,'private-checkpoint')
    with pytest.raises(AssertionError):verify(request,pointer,90001,90002,dict(
        implementation_sha='0'*40,lightweight_preflight_passed=True,quality_gates_weakened=False))

def test_already_delivered_request_cannot_start_a_second_compute_run(context):
    request,pointer=context
    request['production_completion']={'telegram_message_id':1234}
    with pytest.raises(AssertionError):bind(request,pointer,90001,90002,'private-checkpoint')

def test_intermediate_checkpoint_implementation_is_preserved_before_next_bind(context):
    request,pointer=context
    request['codefix_recovery']['replay_implementation_sha']='a'*40
    request['codefix_recovery']['replay_run_id']=80001
    bind(request,pointer,90001,90002,'private-checkpoint')
    record=request['state_history'][-1]
    assert record['meta']['replay_implementation_sha']=='a'*40
    assert record['meta']['golden_path_run_id']==80001
