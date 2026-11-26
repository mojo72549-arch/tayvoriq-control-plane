"""Attach one already delivered Contabo review to the existing immutable approval protocol."""
import argparse
import hashlib
import json
import os
import re
import base64
import shutil
from pathlib import Path
import requests
from tayvoriq_artifact_approval import FILES, verify_evidence

def pending(root,request,review_id,artifact_run_id,studio_sha):
    assert re.fullmatch(r'[a-f0-9]{40}',studio_sha), 'REVIEW_IMPLEMENTATION_INVALID'
    assert type(artifact_run_id) is int and artifact_run_id>0
    receipt=request['production_completion']
    assert request['execution_backend']=='contabo_private_runner'
    assert request['golden_path_run_id']==int(review_id)==receipt['golden_path_run_id']
    assert receipt['state']=='REVIEW_READY' and receipt['quality_gates_weakened'] is False
    assert type(receipt['telegram_message_id']) is int and receipt['telegram_message_id']>0
    job_path=root/'job.json';job=json.loads(job_path.read_text())
    owners={str(review_id),str(request['contabo_handoff']['worker_run_id']),
        *map(str,request.get('previous_golden_path_run_ids',[]))}
    assert str(job.get('github_run_id')) in owners, 'REVIEW_PROVENANCE_MISMATCH'
    if str(job['github_run_id'])!=str(review_id):
        job['checkpoint_origin_run_id']=job['github_run_id'];job['github_run_id']=str(review_id)
        job_path.write_text(json.dumps(job,ensure_ascii=False,indent=2)+'\n')
    hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in FILES}
    verify_evidence(root,hashes,str(review_id))
    return dict(schema='tayvoriq-artifact-approval',state='PENDING',review_id=str(review_id),
        request_id=request['request_id'],source_context_sha256=request['source_context_sha256'],
        telegram_message_id=receipt['telegram_message_id'],studio_sha=studio_sha,
        artifact_run_id=int(artifact_run_id),files_sha256=hashes)

def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['resolve','prepare','activate'])
    p.add_argument('--review',required=True);a=p.parse_args()
    rid=int(a.review)
    requests_for_run=[]
    for file in Path('requests').glob('*.json'):
        request=json.loads(file.read_text())
        if request.get('production_completion',{}).get('golden_path_run_id')==rid and request.get('execution_backend')=='contabo_private_runner':
            requests_for_run.append(request)
    assert len(requests_for_run)==1,'EXACT_DELIVERED_CONTABO_REVIEW_REQUIRED'
    request=requests_for_run[0]
    decision_path=Path('.automation/tayvoriq-artifact-decisions')/(str(rid)+'.json')
    if a.operation=='resolve':
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:
            out.write('review_id='+str(rid)+'\n')
        return
    if a.operation=='prepare':
        if decision_path.exists():
            decision=json.loads(decision_path.read_text())
            assert decision['request_id']==request['request_id']
            assert decision['telegram_message_id']==request['production_completion']['telegram_message_id']
            if decision['state']!='PENDING':
                print('Review already has a decision.');return
            Path('/tmp/contabo-pending-review.json').write_text(json.dumps(decision))
            with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('activate=true\n')
            return
        root=Path('returned/site/tayvoriq/runs')/str(rid)
        manifest=json.loads(Path('returned/out/control-plane/production-manifest.json').read_text())
        result=json.loads(Path('returned/out/control-plane/contabo-result.json').read_text())
        assert result['request_id']==request['request_id'] and str(result['run_id'])==str(rid)
        assert result['source_context_sha256']==request['source_context_sha256']
        assert result['quality_passed'] is True and result['quality_gates_weakened'] is False
        decision=pending(root,request,rid,int(os.environ['GITHUB_RUN_ID']),manifest['implementation_sha'])
        target=Path('approved/implementation/site/tayvoriq/runs')/str(rid)
        shutil.copytree(root,target,dirs_exist_ok=True)
        Path('/tmp/contabo-pending-review.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2)+'\n')
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:
            out.write('prepared=true\nactivate=true\n')
    else:
        decision=json.loads(Path('/tmp/contabo-pending-review.json').read_text())
        # Publish the PENDING record before exposing its buttons. Never approve here.
        url='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/'+str(decision_path)
        headers={'Authorization':'Bearer '+os.environ['CONTROL_TOKEN'],'Accept':'application/vnd.github+json'}
        existing=requests.get(url,headers=headers,timeout=30)
        if existing.status_code==404:
            response=requests.put(url,headers=headers,json={'branch':'main',
                'message':'Bind exact Contabo review '+str(rid)+' for manual approval',
                'content':base64.b64encode((json.dumps(decision,ensure_ascii=False,indent=2)+'\n').encode()).decode()},timeout=30)
            response.raise_for_status()
        else:
            existing.raise_for_status()
            current=json.loads(base64.b64decode(existing.json()['content']))
            assert current['files_sha256']==decision['files_sha256']
            assert current['telegram_message_id']==decision['telegram_message_id']
            if current['state']!='PENDING':return
        markup={'inline_keyboard':[
            [{'text':'✅ Freigeben','callback_data':f'tayvoriq:artifact:approve:{rid}'},
             {'text':'❌ Ablehnen','callback_data':f'tayvoriq:artifact:reject:{rid}'}],
            [{'text':'Control Center öffnen','url':'https://tayvoriq-control-center-mo61.vercel.app'}]]}
        response=requests.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/editMessageReplyMarkup',
            json={'chat_id':os.environ['TELEGRAM_CHAT_ID'],'message_id':decision['telegram_message_id'],'reply_markup':markup},timeout=30)
        assert response.status_code==200 and response.json().get('ok') is True, 'TELEGRAM_REVIEW_BUTTON_BINDING_FAILED'

if __name__=='__main__':main()
