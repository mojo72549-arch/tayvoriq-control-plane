import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from tayvoriq_artifact_approval import FILES,verify_package,validate_decision
from tayvoriq_contabo_review_binding import pending

@pytest.fixture
def package(tmp_path):
    for name in FILES:(tmp_path/name).write_bytes(b'actual-content-fixture')
    (tmp_path/'job.json').write_text(json.dumps(dict(github_run_id='88',render_status='DONE',quality_report={'passed':True})))
    (tmp_path/'publication_quality_gate.json').write_text(json.dumps(dict(passed=True,quality_gates_weakened=False,targets=['youtube_shorts','tiktok'])))
    request=dict(request_id='telegram-3751-trend-1',golden_path_run_id=100,source_context_sha256='b'*64,
        execution_backend='contabo_private_runner',contabo_handoff={'worker_run_id':101},previous_golden_path_run_ids=[88],
        production_completion=dict(golden_path_run_id=100,state='REVIEW_READY',quality_gates_weakened=False,telegram_message_id=234))
    return tmp_path,request

def test_only_delivered_pair_is_bound_and_still_needs_user_approval(package):
    root,request=package
    before=(root/'short_youtube.mp4').read_bytes()
    decision=pending(root,request,100,200,'a'*40)
    assert decision['state']=='PENDING' and decision['artifact_run_id']==200
    assert decision['telegram_message_id']==234 and decision['request_id']==request['request_id']
    assert (root/'short_youtube.mp4').read_bytes()==before
    assert json.loads((root/'job.json').read_text())['checkpoint_origin_run_id']=='88'
    with pytest.raises(ValueError,match='TELEGRAM_BOUND_APPROVAL_REQUIRED'):verify_package(root,decision,'100')
    approved={**decision,'state':'APPROVED','decided_via':'control_center','decision_id':'user-action'}
    verify_package(root,approved,'100')
    with pytest.raises(ValueError,match='APPROVED_ARTIFACT_RUN_INVALID'):
        validate_decision({**approved,'artifact_run_id':'other-run'},'100')

def test_foreign_provenance_and_failed_quality_cannot_be_bound(package):
    root,request=package
    foreign=copy.deepcopy(request);foreign['previous_golden_path_run_ids']=[]
    with pytest.raises(AssertionError,match='REVIEW_PROVENANCE_MISMATCH'):pending(root,foreign,100,200,'a'*40)
    (root/'publication_quality_gate.json').write_text(json.dumps(dict(passed=False,quality_gates_weakened=False,targets=['youtube_shorts','tiktok'])))
    with pytest.raises(ValueError,match='APPROVED_REVIEW_GATE_UNCONFIRMED'):pending(root,request,100,200,'a'*40)

def test_delivery_receipt_is_mandatory(package):
    root,request=package
    request['production_completion']['telegram_message_id']=0
    with pytest.raises(AssertionError):pending(root,request,100,200,'a'*40)
