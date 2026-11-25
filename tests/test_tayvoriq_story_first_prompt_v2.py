from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RADAR = ROOT / "tools" / "tayvoriq_agent_trend_radar_v8.py"


def test_story_first_v2_contract_is_hard_requirement_in_trend_prompt() -> None:
    source = RADAR.read_text(encoding="utf-8")
    assert "source_context.editorial_story_contract_version = 2" in source
    assert "source_context.story_first_script_body" in source
    assert "MUST NOT simply concatenate the five fallback answers" in source
    assert "verified tension/counterposition when supported" in source
    assert "Never add a dramatic claim not present in the evidence" in source


def test_corroborated_counterposition_survives_telegram_request_and_spoken_contract(tmp_path):
    import json
    import sys
    from copy import deepcopy
    from types import SimpleNamespace
    sys.path.insert(0, str(ROOT / "tools"))
    import tayvoriq_agent_trend_radar_v2 as radar
    from tayvoriq_agent_trend_radar_v6 import _downstream_editorial_contract_valid
    from tayvoriq_orchestration_contract import create_from_telegram, validate

    # Exercise the same raw packet shape and five answers used by the morning export.
    released = json.loads((ROOT / "requests/telegram-3696-trend-1.json").read_bytes())
    source = released["source_context"]
    raw = {**source["retention_v5"], "title":released["topic"], "trend_scope":"business_economy",
           "regional_relevance":"germany", "content_angle":released["content_angle"],
           "sources":source["sources"], "fallback_editorial_answers":source["fallback_editorial_answers"],
           "criteria":dict.fromkeys(("aktualitaet","viralitaet","tayvoriq_passung","quellenqualitaet","visuell"),90)}
    trend = radar.normalized_candidate(raw, source["verified_at"])
    selection = {"selection_id":"test-tarif", "slot":"evening", "trends":[{**trend,"id":"1"}]}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(selection))
    create_from_telegram(SimpleNamespace(trend_request=str(path), selection_id="test-tarif", trend_id="1",
                         message_id="5000", payload_topic=raw["title"], approved_at=released["approved_at"],
                         out_dir=str(tmp_path)))
    request = json.loads((tmp_path / "telegram-5000-trend-1.json").read_text())
    validate(request, require_claimable=True)
    answers = request["source_context"]["fallback_editorial_answers"]
    assert _downstream_editorial_contract_valid(answers)
    assert "Nullrunde" in answers["why_happening"]
    assert "Forderung der IG Metall nach fünf Prozent mehr Lohn" in answers["action_now"]
    for claim in ("sechs Prozent", "nicht fünf Prozent"):
        changed = deepcopy(raw)
        changed["sources"][1]["supports"] = changed["sources"][1]["supports"].replace("fünf Prozent", claim)
        assert radar.normalized_candidate(changed, source["verified_at"])["source_context"]["fallback_editorial_answers"] == raw["fallback_editorial_answers"]
