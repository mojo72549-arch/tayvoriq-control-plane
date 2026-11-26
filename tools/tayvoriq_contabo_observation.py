"""Mirror only authenticated, request-bound private progress for public observation."""
import base64
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

CONTROL='mojo72549-arch/tayvoriq-control-plane'
STUDIO='mojo72549-arch/shorts-agent-studio'

def api(repo,path,token,body=None):
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json',
        'Content-Type':'application/json','User-Agent':'tayvoriq-contabo-observation'}
    request=Request('https://api.github.com/repos/'+repo+'/contents/'+path,
        headers=headers,data=json.dumps(body).encode() if body else None,
        method='PUT' if body else 'GET')
    with urlopen(request,timeout=12) as response:return json.load(response)

def mirror(path,data,token):
    for attempt in range(3):
        try:
            previous=None
            try:previous=api(CONTROL,path,token)
            except HTTPError as e:
                if e.code!=404:raise
            if previous and json.loads(base64.b64decode(previous['content']))==data:return
            body=dict(message='Observe canonical Contabo execution',branch='main',
                content=base64.b64encode((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode()).decode())
            if previous:body['sha']=previous['sha']
            api(CONTROL,path,token,body);return
        except HTTPError as error:
            if error.code not in (409,422) or attempt==2:raise

def main():
    rid=os.environ['REQUEST_ID'];run=int(os.environ['GITHUB_RUN_ID'])
    request=json.loads(Path('requests',rid+'.json').read_text())
    receipt=json.loads(base64.b64decode(Path('/tmp/contabo-receipt-base64').read_text()))
    assert receipt['request_id']==rid and receipt['controller_run_id']==run
    assert receipt['source_context_sha256']==request['source_context_sha256']
    token=os.environ['CONTABO_CONTROL_TOKEN']
    mirror(f'run-status/contabo/{run}.json',receipt,token)
    try:
        meta=api(STUDIO,f'run-status/live/{run}-1.json',os.environ['GH_TOKEN'])
    except HTTPError as error:
        if error.code==404:return
        raise
    progress=json.loads(base64.b64decode(meta['content']))
    assert progress['schema']=='tayvoriq-production-progress-v1'
    assert progress['request_id']==rid and int(progress['run_id'])==run
    assert progress['source_context_sha256']==request['source_context_sha256']
    mirror(f'run-status/live/{run}-1.json',progress,token)

if __name__=='__main__':
    try:main()
    except Exception as error:print('CONTABO_OBSERVATION_UNAVAILABLE:'+type(error).__name__)
