"""Mirror only authenticated, request-bound private progress for public observation."""
import base64
import json
import os
from datetime import datetime, timezone
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

def notify(progress,receipt,token):
    """Keep one Telegram status message aligned with actual phase changes."""
    bot=os.environ.get('TELEGRAM_BOT_TOKEN');chat=os.environ.get('TELEGRAM_CHAT_ID')
    if not bot or not chat or receipt['status']!='RUNNING':return
    if (datetime.now(timezone.utc)-datetime.fromisoformat(progress['observed_at'])).total_seconds()>90:return
    event=progress.get('current') or {}
    if event.get('status')!='started':return
    phase=event.get('target') if event.get('phase')=='repair' else event.get('phase')
    labels={'voice':'Sprecheraufnahme wird korrigiert und geprüft.',
        'visuals':'Beanstandete Bilder werden korrigiert und geprüft.',
        'quality':'Das Video wird erneut auf Qualität geprüft.',
        'render':'Die Video-Datei wird zusammengesetzt.',
        'captions':'Untertitel werden vorbereitet.',
        'script':'Das freigegebene Thema wird zum Skript ausgearbeitet.',
        'scenes':'Die Szenen werden geplant.'}
    if phase not in labels:return
    key=str(event.get('at'))+':'+phase
    path='run-status/contabo/notifications/'+str(receipt['controller_run_id'])+'.json'
    previous=None
    try:previous=json.loads(base64.b64decode(api(CONTROL,path,token)['content']))
    except HTTPError as error:
        if error.code!=404:raise
    if previous and previous.get('phase_key')==key:return
    text='TAYVORIQ · '+labels[phase]+'\n'
    text+='Auftrag: '+receipt['request_id']+'\n'
    text+='Die endgültige Qualitätsfreigabe und Zustellung stehen noch aus.\n'
    text+='Live-Stand: https://tayvoriq-control-center-mo61.vercel.app'
    method='editMessageText' if previous else 'sendMessage'
    body={'chat_id':chat,'text':text,'disable_web_page_preview':True}
    if previous:body['message_id']=previous['telegram_message_id']
    request=Request('https://api.telegram.org/bot'+bot+'/'+method,
        headers={'Content-Type':'application/json'},data=json.dumps(body).encode())
    with urlopen(request,timeout=15) as response:result=json.load(response)
    assert result.get('ok') is True,'TELEGRAM_PROGRESS_NOT_CONFIRMED'
    message=previous['telegram_message_id'] if previous else result['result']['message_id']
    mirror(path,dict(schema='tayvoriq-contabo-progress-notification-v1',
        request_id=receipt['request_id'],controller_run_id=receipt['controller_run_id'],
        source_context_sha256=receipt['source_context_sha256'],phase_key=key,telegram_message_id=message),token)

def main():
    rid=os.environ['REQUEST_ID'];run=int(os.environ.get('CONTABO_OBSERVED_RUN_ID') or os.environ['GITHUB_RUN_ID'])
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
    notify(progress,receipt,token)

if __name__=='__main__':
    try:main()
    except Exception as error:print('CONTABO_OBSERVATION_UNAVAILABLE:'+type(error).__name__)
