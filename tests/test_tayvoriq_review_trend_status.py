import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_review_trend_status as status


def test_expired_review_gets_one_terminal_telegram_receipt(tmp_path, monkeypatch):
    selection = "review-evening-123"
    plan = {"selection_id": selection, "new_trends_requested": True, "selection_delivered": False}
    retry = tmp_path / "research-retries" / f"{selection}.json"
    retry.parent.mkdir()
    retry.write_text(json.dumps({"valid_until_epoch": 1000, "attempts": 1}))
    monkeypatch.setattr(status, "ROOT", tmp_path)
    monkeypatch.setattr(status, "DEFERRED", tmp_path / "deferred")
    monkeypatch.setenv("TAYVORIQ_RESEARCH_RETRY_FILE", str(retry))
    monkeypatch.setattr(sys, "argv", ["review", selection, "expire"])
    notice = Mock(side_effect=[OSError(), 45])
    monkeypatch.setattr(status, "send_notice", notice)

    assert not status.needs_expiry(plan, 999)
    assert status.needs_expiry(plan, 1000)
    status.main()
    assert status.needs_expiry(plan, 1001)
    status.main()
    assert not status.needs_expiry(plan, 1002)
    status.main()
    assert notice.call_count == 2
    record = status.load(tmp_path / "review-trend-status" / f"{selection}.json")
    assert record["state"] == "BLOCKED"
    assert record["reason"] == "RESEARCH_RETRY_EXPIRED"
    assert record["telegram_notices"]["BLOCKED"] == 45


def test_interactive_retry_stays_inside_the_original_window(tmp_path, monkeypatch):
    deferred = tmp_path / "deferred"
    deferred.write_text(json.dumps({"errors": ["Groq failed: connection reset"]}))
    monkeypatch.setattr(status, "DEFERRED", deferred)
    run = Mock(side_effect=[subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)])
    pause = Mock()
    assert status.research(["research"], 600, clock=lambda: 200, run=run, pause=pause) == (0, 2)
    assert run.call_count == 2
    pause.assert_called_once_with(8)
    assert status.research(["research"], 600, clock=lambda: 575, run=Mock()) == (124, 0)
    assert status.blocker_for("finish", {}, {"errors": ["source contract insufficient"]}, "", "") == "SOURCE_QUALITY"
