import base64
import json
from datetime import datetime,timezone
from urllib.error import HTTPError

from tools import tayvoriq_contabo_observation as observer

def test_only_one_message_is_updated_when_the_confirmed_phase_changes(monkeypatch):
    for key,value in [('TELEGRAM_BOT_TOKEN','test'),('TELEGRAM_CHAT_ID','42')]:monkeypatch.setenv(key,value)
    saved={};calls=[]
    def api(repo,path,token,body=None):
        if path not in saved:raise HTTPError('fixture',404,'missing',{},None)
        return {'content':base64.b64encode(json.dumps(saved[path]).encode()).decode()}
    def mirror(path,data,token):saved[path]=data
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return b'{"ok":true,"result":{"message_id":12}}'
    def send(request,timeout):
        calls.append((request.full_url,json.loads(request.data)))
        return Response()
    monkeypatch.setattr(observer,'api',api);monkeypatch.setattr(observer,'mirror',mirror);monkeypatch.setattr(observer,'urlopen',send)
    receipt=dict(status='RUNNING',request_id='original',controller_run_id=100,source_context_sha256='a'*64)
    progress=dict(observed_at=datetime.now(timezone.utc).isoformat(),current=dict(phase='repair',target='visuals',at='time1',status='started'))
    observer.notify(progress,receipt,'test')
    observer.notify(progress,receipt,'test')
    assert len(calls)==1 and calls[0][0].endswith('/sendMessage')
    progress['current'].update(target='voice',at='time2')
    observer.notify(progress,receipt,'test')
    assert len(calls)==2 and calls[1][0].endswith('/editMessageText')
    assert calls[1][1]['message_id']==12 and 'Sprecheraufnahme' in calls[1][1]['text']
    receipt['status']='SUCCEEDED';progress['current']['at']='time3'
    observer.notify(progress,receipt,'test')
    assert len(calls)==2

    receipt.update(status='FAILED', failure_reason='Stille am Ende des YouTube-Exports.')
    observer.notify({}, receipt, 'test')
    observer.notify({}, receipt, 'test')
    assert len(calls) == 3 and calls[-1][0].endswith('/editMessageText')
    assert calls[-1][1]['message_id'] == 12
    assert 'Produktion gestoppt' in calls[-1][1]['text']
    assert 'Stille am Ende des YouTube-Exports.' in calls[-1][1]['text']

    receipt['status'] = 'RUNNING'
    observer.notify(progress, receipt, 'test')
    assert len(calls) == 3
