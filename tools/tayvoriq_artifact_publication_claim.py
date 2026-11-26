"""Atomically reserve one approved artifact before an irreversible upload."""
from __future__ import annotations
import argparse
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from tayvoriq_artifact_approval import validate_decision


def api(path,body=None):
    url='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/'+path
    request=Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],
        'Accept':'application/vnd.github+json','Content-Type':'application/json'},
        data=json.dumps(body).encode() if body else None,method='PUT' if body else 'GET')
    try:
        with urlopen(request,timeout=30) as response:return json.load(response)
    except HTTPError as error:
        if error.code==404 and body is None:return None
        raise


def decode(meta):return json.loads(base64.b64decode(meta['content']))


def persist(review_id,action,decision,publish_run_id,receipt=None):
    validate_decision(decision,review_id)
    decision_path=f'.automation/tayvoriq-artifact-decisions/{review_id}.json'
    path=f'.automation/tayvoriq-publications/{review_id}.json'
    identity=dict(review_id=review_id,telegram_message_id=decision['telegram_message_id'],
        decision_id=decision['decision_id'],publish_run_id=publish_run_id)
    claim={'state':'UPLOAD_STARTED',**identity}
    for attempt in range(4):
        current_decision=api(decision_path)
        if current_decision is None or decode(current_decision)!=decision:
            raise RuntimeError('PUBLICATION_DECISION_CHANGED')
        previous=api(path)
        if action=='claim':
            if previous is not None:raise RuntimeError('PUBLICATION_ALREADY_CLAIMED')
            state=claim
        else:
            if previous is None or decode(previous)!=claim or not receipt:
                raise RuntimeError('PUBLICATION_CLAIM_MISMATCH')
            result=json.loads(receipt.read_text()).get('results',{}).get('youtube_shorts',{})
            if not result.get('video_id') or not result.get('url'):
                raise RuntimeError('YOUTUBE_RECEIPT_MISSING')
            state={'state':'YOUTUBE_PUBLISHED',**identity,'youtube':result,'tiktok_status':'MANUAL_UPLOAD_REQUIRED'}
        body=dict(branch='main',message=f'Record review {review_id} {state["state"]}',
            content=base64.b64encode((json.dumps(state,indent=2)+'\n').encode()).decode())
        if previous is not None:body['sha']=previous['sha']
        try:
            api(path,body);return
        except HTTPError as error:
            if error.code not in (409,422) or attempt==3:raise
    raise RuntimeError('PUBLICATION_WRITE_NOT_CONFIRMED')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('review_id');parser.add_argument('action',choices=('claim','record'))
    parser.add_argument('--receipt',type=Path);args=parser.parse_args()
    decision=json.loads((Path('.automation/tayvoriq-artifact-decisions')/(args.review_id+'.json')).read_text())
    persist(args.review_id,args.action,decision,os.environ['GITHUB_RUN_ID'],args.receipt)

if __name__=='__main__':main()
