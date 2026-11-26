import base64,json,sys
from pathlib import Path
from urllib.error import HTTPError
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import tayvoriq_artifact_publication_claim as claim
from tayvoriq_artifact_approval import FILES

def test_unrelated_head_change_does_not_block_claim_and_second_upload_stays_blocked(monkeypatch):
    decision=dict(schema='tayvoriq-artifact-approval',state='APPROVED',review_id='100',
        decided_via='telegram_callback',decision_id='user-approval',telegram_message_id=12,
        studio_sha='a'*40,files_sha256={k:'b'*64 for k in FILES})
    def blob(data):return {'sha':'blob','content':base64.b64encode(json.dumps(data).encode()).decode()}
    saved={};writes=[]
    def api(path,body=None):
        if 'decisions' in path:return blob(decision)
        if body is None:return blob(saved[path]) if path in saved else None
        writes.append(body)
        if len(writes)==1:raise HTTPError('fixture',409,'unrelated head update',{},None)
        saved[path]=json.loads(base64.b64decode(body['content']));return {}
    monkeypatch.setattr(claim,'api',api)
    claim.persist('100','claim',decision,'500')
    assert len(writes)==2 and next(iter(saved.values()))['state']=='UPLOAD_STARTED'
    with pytest.raises(RuntimeError,match='PUBLICATION_ALREADY_CLAIMED'):
        claim.persist('100','claim',decision,'501')
    assert len(writes)==2

def test_changed_approval_cannot_reserve_upload(monkeypatch):
    monkeypatch.setattr(claim,'api',lambda *a,**k:None)
    decision=dict(schema='tayvoriq-artifact-approval',state='APPROVED',review_id='100',
        decided_via='control_center',decision_id='approval',telegram_message_id=12,studio_sha='a'*40,
        files_sha256={k:'b'*64 for k in FILES})
    with pytest.raises(RuntimeError,match='PUBLICATION_DECISION_CHANGED'):
        claim.persist('100','claim',decision,'500')
