import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
RADAR = ROOT / "tools" / "tayvoriq_agent_trend_radar_v8.py"


def test_story_first_v2_contract_is_hard_requirement_in_trend_prompt() -> None:
    source = RADAR.read_text(encoding="utf-8")
    assert "editorial_story_contract_version = 2" in source
    assert "46–49 words before the platform CTA" in source
    assert "MUST NOT simply concatenate the five fallback answers" in source
    assert "verified tension/counterposition when supported" in source
    assert "Never add drama, dates or numbers absent from the sources" in source


def test_corroborated_counterposition_survives_telegram_request_and_spoken_contract(tmp_path):
    import sys
    from copy import deepcopy
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


FLIXTRAIN_STORY = (
    "DB und FlixTrain buchst du bald zusammen. Was passiert, wenn der Anschluss platzt? "
    "Ab dem siebten Dezember gibt es FlixTrain-Tickets im DB Navigator "
    "für Fahrten ab dem dreizehnten Dezember. Kombinierst du beide Züge, bekommst du zwei Fahrkarten. "
    "Bei einem verpassten Anschluss zählen deshalb die Bedingungen der jeweiligen Fahrkarte."
)


def _flixtrain_candidate(story, *, nested=False):
    released = json.loads((ROOT / "requests/telegram-3728-trend-1.json").read_text(encoding="utf-8"))
    source = released["source_context"]
    raw = {
        **source["retention_v5"],
        "title": released["topic"],
        "trend_scope": released["trend_scope"],
        "regional_relevance": "germany",
        "content_angle": released["content_angle"],
        "sources": source["sources"],
        "fallback_editorial_answers": source["fallback_editorial_answers"],
        "criteria": dict.fromkeys(("aktualitaet", "viralitaet", "tayvoriq_passung", "quellenqualitaet", "visuell"), 90),
    }
    fields = {"editorial_story_contract_version": 2, "story_first_script_body": story}
    if nested:
        raw["source_context"] = fields
    else:
        raw.update(fields)
    return released, raw


@pytest.mark.parametrize("nested", [False, True])
def test_verified_flixtrain_story_reaches_the_approved_source_packet(tmp_path, monkeypatch, nested):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from tayvoriq_agent_trend_radar_v8 import base as radar
    from tayvoriq_orchestration_contract import create_from_telegram, validate

    released, raw = _flixtrain_candidate(FLIXTRAIN_STORY, nested=nested)
    trend = radar.normalized_candidate(raw, released["source_context"]["verified_at"])
    assert trend is not None
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps({"selection_id": "test-flixtrain", "slot": "evening", "trends": [{**trend, "id": "1"}]}),
        encoding="utf-8",
    )
    create_from_telegram(SimpleNamespace(
        trend_request=str(selection),
        selection_id="test-flixtrain",
        trend_id="1",
        message_id="5000",
        payload_topic=released["topic"],
        approved_at=released["approved_at"],
        out_dir=str(tmp_path),
    ))

    request = json.loads((tmp_path / "telegram-5000-trend-1.json").read_text(encoding="utf-8"))
    validate(request, require_claimable=True)
    assert request["source_context"]["editorial_story_contract_version"] == 2
    assert request["source_context"]["story_first_script_body"] == FLIXTRAIN_STORY
    assert request["source_context"]["fallback_editorial_answers"] == raw["fallback_editorial_answers"]


@pytest.mark.parametrize(
    "story",
    [
        None,
        FLIXTRAIN_STORY.replace("zwei Fahrkarten", "9 Fahrkarten"),
        "Betroffen sind Reisende. Für dich ändert sich einiges. Prüfe die Bedingungen.",
    ],
)
def test_missing_or_invalid_spoken_story_retains_the_verified_compatibility_answers(story, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from tayvoriq_agent_trend_radar_v8 import base as radar

    released, raw = _flixtrain_candidate(story)
    trend = radar.normalized_candidate(raw, released["source_context"]["verified_at"])
    assert trend is not None
    assert "story_first_script_body" not in trend["source_context"]
    assert "editorial_story_contract_version" not in trend["source_context"]
    assert trend["source_context"]["fallback_editorial_answers"] == raw["fallback_editorial_answers"]


def test_dhl_leads_with_the_supported_price_difference(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from tayvoriq_agent_trend_radar_v2 import _story_first_fields

    body = (
        "Für dasselbe DHL-Päckchen soll der Schalter siebzig Cent mehr kosten. "
        "Ab Januar plant DHL beim Päckchen S für den Versand in Deutschland fünf Euro neunzehn "
        "in der Filiale und vier Euro neunundvierzig online. Dazu kommen Sendungsverfolgung "
        "und Haftung bis zwanzig Euro. Allerdings muss die Bundesnetzagentur die Tarife noch genehmigen."
    )
    source = {"supports": "DHL Päckchen S, Filiale 5,19 Euro, online 4,49 Euro; geplante Tarife ab Januar."}
    normalized = _story_first_fields(
        {"editorial_story_contract_version": 2, "story_first_script_body": body}, [source], {}
    )
    assert normalized["story_first_script_body"].split(".")[0].endswith("siebzig Cent mehr kosten")


def test_confirmed_variant_is_locked_to_the_existing_sources(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.syspath_prepend(str(ROOT / "tools"))
    from tayvoriq_agent_trend_radar_v8 import base as radar
    from tayvoriq_orchestration_contract import create_from_telegram, validate

    alternate = (
        "Die Bahn-App nimmt FlixTrain ab dem siebten Dezember in den Ticketverkauf auf. "
        "Das gilt für Fahrten ab dem dreizehnten Dezember. Du kannst Züge beider Anbieter "
        "in einem Vorgang zusammen buchen, bekommst aber zwei Fahrkarten. "
        "Wer wegen eines verspäteten ICE den FlixTrain verpasst, kann ein neues Ticket brauchen."
    )
    released, raw = _flixtrain_candidate(FLIXTRAIN_STORY)
    raw["story_first_script_body_b"] = alternate
    trend = radar.normalized_candidate(raw, released["source_context"]["verified_at"])
    assert trend["source_context"]["story_first_script_body_b"] == alternate
    path = tmp_path / "selection.json"
    path.write_text(
        json.dumps({"selection_id": "test-alternate", "slot": "evening", "trends": [{**trend, "id": "1"}]}),
        encoding="utf-8",
    )

    def fingerprint(body):
        payload = json.dumps([released["topic"], body], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    args = SimpleNamespace(
        trend_request=str(path), selection_id="test-alternate", trend_id="1", message_id="5000",
        payload_topic=released["topic"], approved_at=released["approved_at"], out_dir=str(tmp_path),
        text_approval="b:0000000000",
    )
    request_path = tmp_path / "telegram-5000-trend-1.json"
    with pytest.raises(SystemExit, match="TEXT_APPROVAL_MISMATCH"):
        create_from_telegram(args)
    assert not request_path.exists()

    digest = fingerprint(alternate)
    args.text_approval = f"b:{digest[:10]}"
    create_from_telegram(args)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    validate(request, require_claimable=True)
    assert request["source_context"]["story_first_script_body"] == alternate
    assert request["source_context"]["text_approval"] == {"variant": "b", "sha256": digest}
    assert request["source_context"]["sources"] == trend["source_context"]["sources"]

    args.text_approval = f"a:{fingerprint(FLIXTRAIN_STORY)[:10]}"
    with pytest.raises(SystemExit, match="TEXT_ALREADY_APPROVED"):
        create_from_telegram(args)
    assert json.loads(request_path.read_text(encoding="utf-8")) == request
