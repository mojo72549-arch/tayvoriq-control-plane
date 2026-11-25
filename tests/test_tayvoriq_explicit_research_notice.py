import io
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tayvoriq_research_terminal_notice as notice

SID = '20261125-evening-agentv2-c5187225d'


def setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'test')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', '-12')
    monkeypatch.setenv('GITHUB_RUN_ID', '456')
    monkeypatch.setattr(notice, 'persist', notice.write)
    return Path('.automation/tayvoriq-agent-v2/research-notices') / (SID + '-FAILED.json')


def test_explicit_failure_claims_before_sending_and_never_duplicates(tmp_path, monkeypatch):
    path = setup(tmp_path, monkeypatch)
    calls = []
    def send(request, **kwargs):
        assert json.loads(path.read_text())['state'] == 'SENDING'
        body = json.loads(request.data)
        assert '\n\n' in body['text'] and '\\n' not in body['text']
        calls.append(body)
        return io.BytesIO(json.dumps({'ok': True, 'result': {'message_id': 91, 'chat': {'id': -12}}}).encode())
    monkeypatch.setattr(notice.urllib.request, 'urlopen', send)
    notice.main(SID)
    notice.main(SID)
    assert len(calls) == 1
    assert json.loads(path.read_text())['telegram_delivery_verified'] is True


def test_an_ambiguous_send_is_not_repeated(tmp_path, monkeypatch):
    path = setup(tmp_path, monkeypatch)
    calls = []
    def send(*args, **kwargs):
        calls.append(True)
        raise TimeoutError('ambiguous')
    monkeypatch.setattr(notice.urllib.request, 'urlopen', send)
    with pytest.raises(RuntimeError):
        notice.main(SID)
    notice.main(SID)
    assert len(calls) == 1
    assert json.loads(path.read_text())['state'] == 'UNCONFIRMED'


def test_delivered_or_superseded_selections_never_send_a_stale_failure(tmp_path, monkeypatch):
    path = setup(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs):
        raise AssertionError('stale failure must not be sent')
    monkeypatch.setattr(notice.urllib.request, 'urlopen', forbidden)
    receipt = Path('.automation/tayvoriq-agent-v2/deliveries') / (SID + '.json')
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps({'selection_id': SID, 'telegram_delivery_verified': True, 'telegram_message_id': 3728}))
    notice.main(SID)
    assert not path.exists()
    receipt.unlink()
    pointer = Path('state/tayvoriq-control-center-research.json')
    pointer.parent.mkdir()
    pointer.write_text(json.dumps({'schema': 'tayvoriq-control-center-research-v1', 'selection_id': '20261125-evening-agentv2-c00000000'}))
    notice.main(SID)
    assert not path.exists()


def test_invalid_selection_cannot_choose_an_arbitrary_notice_file(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        notice.main('../../../outside')
