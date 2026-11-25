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


def test_terminal_notice_rebases_without_runner_identity(tmp_path, monkeypatch):
    """The observer advances main after checkout; terminal delivery must survive that rebase."""
    import subprocess

    # Reproduce the hosted runner with no configured or inherited Git identity.
    for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "EMAIL",
                 "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    identity = ["-c", "user.name=github-actions[bot]", "-c",
                "user.email=github-actions[bot]@users.noreply.github.com"]

    def git(directory, *args, identified=False):
        return subprocess.run(["git", "-C", str(directory), *(identity if identified else []), *args],
                              check=True, capture_output=True, text=True).stdout.strip()

    remote, peer, worker = (tmp_path / name for name in ("remote.git", "peer", "worker"))
    git(tmp_path, "init", "--bare", "--initial-branch=main", str(remote))
    git(tmp_path, "clone", str(remote), str(peer))
    (peer / "initial.txt").write_text("initial")
    git(peer, "add", ".")
    git(peer, "commit", "-m", "Seed", identified=True)
    git(peer, "push", "origin", "main")
    git(tmp_path, "clone", str(remote), str(worker))
    (peer / "observer-progress.json").write_text('{"state":"FAILED"}')
    git(peer, "add", ".")
    git(peer, "commit", "-m", "Concurrent observer checkpoint", identified=True)
    git(peer, "push", "origin", "main")

    monkeypatch.chdir(worker)
    monkeypatch.setattr(notice.time, "sleep", lambda seconds: None)
    path = Path(".automation/tayvoriq-agent-v2/research-notices") / (SID + "-FAILED.json")
    for state in ("SENDING", "DELIVERED"):
        notice.persist(path, {"selection_id": SID, "state": state})
    persisted = json.loads(git(remote, "show", "main:" + str(path)))
    assert persisted["state"] == "DELIVERED"
    assert json.loads(git(remote, "show", "main:observer-progress.json"))["state"] == "FAILED"
    assert git(worker, "status", "--porcelain") == ""
    # The fix must not install a user identity into the runner's local Git config.
    assert subprocess.run(["git", "config", "--local", "--get", "user.name"], capture_output=True).returncode == 1
