import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import tayvoriq_local_editorial_benchmark as benchmark


VW_REQUEST = ROOT / "requests" / "telegram-3696-trend-1.json"


def test_comparison_shares_the_verified_packet_and_flags_a_false_promise(monkeypatch, capsys):
    draft = {
        "story_first_script_body": (
            "Fünf Prozent mehr Lohn fordert die IG Metall, VW will Nullrunden. "
            "Die erste Tarifrunde in Emden ging ohne Einigung zu Ende. "
            "Für die Beschäftigten geht es gleichzeitig um Zulagen und flexiblere Arbeitszeiten. "
            "Entscheidend ist jetzt, ob in der nächsten Runde ein neues Angebot auf den Tisch kommt."
        ),
        "cta_text": "Folge TAYVORIQ, wenn du wissen willst, was ein neues VW-Angebot für deinen Lohn bedeutet.",
        "follow_reason": "Wir erklären, was ein neues VW-Angebot für die Beschäftigten bedeutet.",
    }
    comparison_inputs = []

    def reply(port, path, timeout, payload=None):
        assert port == 11434
        if path == "/api/tags":
            return {"models": [{"name": model, "digest": model} for model in benchmark.MODELS]}
        assert path == "/api/chat"
        assert payload["format"] == benchmark.SCHEMA
        comparison_inputs.append(payload["messages"])
        response_draft = draft.copy()
        if payload["model"] == benchmark.MODELS[1]:
            response_draft["follow_reason"] = "Das neue Angebot beim VW-Tarif zeigen wir euch morgen."
        return {
            "done_reason": "stop", "message": {"content": json.dumps(response_draft)},
            "total_duration": 4_000_000_000, "eval_count": 90,
        }

    monkeypatch.setattr(benchmark, "ollama_json", reply)
    monkeypatch.setattr(sys, "argv", ["benchmark", str(VW_REQUEST)])

    assert benchmark.main() == 1
    assert comparison_inputs[0] == comparison_inputs[1]
    report = json.loads(capsys.readouterr().out)
    assert report["editorial_review_required"]
    baseline, challenger = report["results"]
    assert not baseline["mechanical_issues"]
    assert baseline["total_seconds"] == 4
    assert baseline["source_context_sha256"] == challenger["source_context_sha256"]
    assert "false_tomorrow_promise" in challenger["mechanical_issues"]


def test_comparison_rejects_changed_source_evidence(tmp_path):
    request = json.loads(VW_REQUEST.read_text(encoding="utf-8"))
    request["source_context"]["sources"][0]["supports"] = "VW bietet fünf Prozent mehr Lohn an."
    path = tmp_path / "tarif.json"
    path.write_text(json.dumps(request), encoding="utf-8")

    with pytest.raises(ValueError, match="source packet hash does not match"):
        benchmark.read_case(path)
