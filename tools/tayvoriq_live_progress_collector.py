"""Publish bounded, source-bound phase metadata; never control a producer."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.request import Request,urlopen

PHASES={'preflight','script','scenes','voice','visuals','captions','render','quality','repair'}
def now(): return datetime.now(timezone.utc).isoformat()
def binding():
    value={'request_id':os.environ['SOURCE_REQUEST_ID_PIN'],'source_context_sha256':os.environ['SOURCE_CONTEXT_SHA256'],
           'run_id':int(os.environ['GITHUB_RUN_ID']),'run_attempt':int(os.environ['GITHUB_RUN_ATTEMPT'])}
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}',value['request_id']) or not re.fullmatch(r'[a-f0-9]{64}',value['source_context_sha256']): raise ValueError('invalid binding')
    return value

class Observation:
    def __init__(self,identity):
        self.identity=identity;self.events=[];self.active={};self.seen=set();self.completed={};self.failure=None;self.round=None
    def accept(self,row):
        if any(str(row.get(k))!=str(v) for k,v in self.identity.items()) or row.get('phase') not in PHASES or row.get('status') not in {'started','completed','failed'}: return
        try: datetime.fromisoformat(row['at'].replace('Z','+00:00'))
        except (KeyError,TypeError,ValueError): return
        clean={k:row[k] for k in ['phase','status','at','call_id'] if k in row}
        if row.get('platform') in {'youtube_shorts','tiktok'}: clean['platform']=row['platform']
        if row.get('target') in PHASES: clean['target']=row['target']
        for k in ['scene','total','round','timeout_seconds']:
            if type(row.get(k)) is int and 0<row[k]<=7200: clean[k]=row[k]
        key=json.dumps(clean,sort_keys=True)
        if key in self.seen: return
        self.seen.add(key);self.events.append(clean);self.events=self.events[-40:]
        call=clean.get('call_id') or clean['phase']
        if clean.get('round'): self.round=clean['round']
        if clean['status']=='started': self.active[call]=clean;self.failure=None
        else:
            self.active.pop(call,None)
            if clean['status']=='failed' and self.failure is None: self.failure=clean
            if clean['status']=='completed' and clean.get('platform') and clean['phase'] in {'script','scenes','voice','render'}:
                self.completed.setdefault(clean['phase'],set()).add(clean['platform'])
    def checkpoint(self,line):
        try: row=json.loads(line)
        except (ValueError,TypeError): return
        if not isinstance(row,dict): return
        stage=str(row.get('checkpoint_stage',''))
        if row.get('checkpoint_repair_round_failed_audit'):
            for phase in row.get('residual_scopes',[]): self.completed.pop(str(phase).lower(),None)
        phase='quality' if stage.startswith('QUALITY_AUDIT') else 'repair' if stage.startswith(('VOICE_REPAIR','VISUAL_REPAIR')) else None
        if not phase or row.get('status') not in {'started','completed'}: return
        match=re.search(r'_R(\d+)',stage)
        self.accept({**self.identity,'phase':phase,'status':'failed' if row.get('returncode',0)!=0 else row['status'],
            'at':now(),'call_id':'checkpoint-'+stage,'round':int(match[1]) if match else self.round,'timeout_seconds':row.get('timeout_seconds'),
            'target':'voice' if stage.startswith('VOICE_REPAIR') else 'visuals' if stage.startswith('VISUAL_REPAIR') else None})
    def payload(self):
        current=self.failure or (list(self.active.values())[-1] if self.active else None)
        if current: current={**current,'round':current.get('round') or self.round,
            'target':current.get('target') or next((row['target'] for row in reversed(list(self.active.values())) if row.get('target')),None)}
        return {'schema':'tayvoriq-production-progress-v1',**self.identity,'updated_at':self.events[-1]['at'] if self.events else now(),
                'observed_at':now(),'current':current,'events':self.events[-16:],
                'completed_phases':[phase for phase,platforms in self.completed.items() if platforms=={'youtube_shorts','tiktok'}]}

def publish(payload,prefix='run-status/live'):
    if prefix not in {'run-status/live','run-status/self-test'}: return False
    token=os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if not token: return False
    repo=os.environ.get('GITHUB_REPOSITORY','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo): return False
    path=f"{prefix}/{payload['run_id']}-{payload['run_attempt']}.json"
    url=f'https://api.github.com/repos/{repo}/contents/{path}'
    headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','Content-Type':'application/json','User-Agent':'tayvoriq-live-progress'}
    raw=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode()
    for _ in range(3):
        try:
            sha=None
            try:
                with urlopen(Request(url+'?ref=main',headers=headers),timeout=5) as response: sha=json.load(response)['sha']
            except HTTPError as error:
                if error.code!=404: raise
            data={'message':f"ops: production phase {payload['run_id']}.{payload['run_attempt']}",'branch':'main','content':base64.b64encode(raw).decode()}
            if sha: data['sha']=sha
            with urlopen(Request(url,data=json.dumps(data).encode(),headers=headers,method='PUT'),timeout=5) as response: response.read()
            return True
        except HTTPError as error:
            if error.code not in {409,422}: return False
            time.sleep(1)
        except (OSError,ValueError,KeyError): return False
    return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');parser.add_argument('--stop-file',type=Path)
    args=parser.parse_args();identity=binding();state=Observation(identity)
    root=Path(os.environ['GITHUB_WORKSPACE'])/'implementation/out/tayvoriq-self-heal'
    files=[Path(os.environ['TAYVORIQ_PROGRESS_JOURNAL']),root/'controller-console.log',root/'checkpoint-resume-console.log']
    positions={};last_publish=0;last_fingerprint=None;started=time.time()
    while True:
        for path in files:
            if not path.is_file(): continue
            if path!=files[0] and path not in positions and path.stat().st_mtime<started-2:
                positions[path]=path.stat().st_size
            try:
                with path.open(encoding='utf-8',errors='replace') as stream:
                    stream.seek(positions.get(path,0))
                    while True:
                        position=stream.tell();line=stream.readline()
                        if not line or not line.endswith('\n'): stream.seek(position);break
                        if path==files[0]:
                            try: state.accept(json.loads(line))
                            except (ValueError,TypeError,AttributeError): pass
                        else: state.checkpoint(line)
                    positions[path]=stream.tell()
            except OSError: pass
        payload=state.payload();fingerprint=hashlib.sha256(json.dumps([payload['current'],payload['events']],sort_keys=True).encode()).hexdigest()
        if args.once or time.monotonic()-last_publish>30 or fingerprint!=last_fingerprint and time.monotonic()-last_publish>5:
            if publish(payload): last_publish=time.monotonic();last_fingerprint=fingerprint
        if args.once or args.stop_file and args.stop_file.exists(): return
        time.sleep(2)

if __name__=='__main__':
    try: main()
    except (OSError,ValueError,KeyError): print('PRODUCTION_PROGRESS_OBSERVER_UNAVAILABLE')
