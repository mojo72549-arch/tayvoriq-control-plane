"""A migrated Butterpreis request must never inherit the retired VW push payload."""
import json,os,subprocess
from pathlib import Path
import yaml

WORKFLOW=Path('.github/workflows/tayvoriq-deliver-video-now.yml')

def resolve(tmp_path,request,request_id):
    document=yaml.safe_load(WORKFLOW.read_text())
    step=next(s for s in document['jobs']['orchestrate']['steps'] if s.get('id')=='resolve_request')
    (tmp_path/'.github/run-now').mkdir(parents=True)
    (tmp_path/'requests').mkdir()
    (tmp_path/'.github/run-now/tayvoriq-x-request.json').write_text(json.dumps(dict(
        source_request_id='retired-vw-request',topic='Alte VW-Meldung',trend_id='99')))
    (tmp_path/'requests'/f'{request_id}.json').write_text(json.dumps(request))
    env={**os.environ,'TAYVORIQ_EXECUTION_BACKEND':'contabo_private_runner',
        'EVENT_SOURCE_REQUEST_ID':request_id,'GITHUB_OUTPUT':str(tmp_path/'output'),
        'GITHUB_ENV':str(tmp_path/'env')}
    result=subprocess.run(['bash','-c',step['run']],cwd=tmp_path,env=env,text=True,capture_output=True)
    return result,(tmp_path/'env').read_text() if (tmp_path/'env').exists() else ''

def test_contabo_uses_only_the_approved_request_despite_an_old_push_payload(tmp_path):
    request=json.loads(Path('requests/telegram-3751-trend-1.json').read_text())
    result,environment=resolve(tmp_path,request,request['request_id'])
    assert result.returncode==0,result.stderr
    assert 'TOPIC=Discounter senken Butterpreis unter einen Euro' in environment
    assert 'TREND_ID=1\n' in environment
    assert 'Alte VW-Meldung' not in environment

def test_mismatched_canonical_identity_blocks_before_any_production(tmp_path):
    request=dict(request_id='wrong-request',topic='Falscher Inhalt',trend_id='1')
    result,environment=resolve(tmp_path,request,'telegram-3751-trend-1')
    assert result.returncode!=0
    assert 'CONTABO_REQUEST_IDENTITY_FAILED' in result.stderr
    assert not environment
