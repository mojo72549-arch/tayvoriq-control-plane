"""Real discovery shapes: original leads, inflections and distinct reporting origins."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_agent_hf_v2 as hf
from tayvoriq_source_evidence_v1 import validate_pair


def record(host, title, context):
    return {"url": "https://" + host + "/story", "domain": host,
            "title": title, "context": context}


def butter():
    return [
        record("tagesschau.de", "Discounter senken Butterpreis unter einen Euro",
               "Die Discounter Lidl und Aldi haben den Preis für ein Stück Butter unter einen Euro gesenkt. "
               "Das liege an gesunkenen Einkaufspreisen."),
        record("n-tv.de", "Starke Schwankungen: Butterpreis fällt unter einen Euro pro Packung",
               "Bei zwei großen Discountern kostet eine Packung nun weniger als ein Euro. "
               "Die Händler verweisen auf gesunkene Rohstoff- und Einkaufspreise."),
    ]


def test_price_change_inflections_are_one_action_with_the_original_claim_intact():
    pair = butter()
    assert hf._source_pair_score(*pair) > 0
    assert hf.corroborated_headline(*pair) == pair[0]["title"]
    assert validate_pair({"title": pair[0]["title"]}, pair) == []


def test_a_price_action_may_be_documented_in_the_original_lead():
    pair = butter()
    pair[1] = record("swr.de", "Butter bei Lidl und Aldi für unter einem Euro",
                     "Lidl folgt auf Aldi und senkt den Butterpreis auf unter einen Euro. "
                     "Der Landesbauernverband nennt die Discounter ideenlos.")
    assert hf._source_pair_score(*pair) > 0
    assert validate_pair({"title": pair[0]["title"]}, pair) == []
    # An action from another retailer or object cannot corroborate the headline.
    pair[1]["context"] = "Die Discounter senken den Kaffeepreis unter einen Euro."
    assert validate_pair({"title": pair[0]["title"]}, pair)


def test_price_direction_modality_numbers_and_actors_cannot_be_normalized_away():
    for replacement in ("Discounter erhöhen Butterpreis unter einen Euro",
                        "Discounter wollen Butterpreis unter einen Euro senken",
                        "Discounter senken Butterpreis nicht unter einen Euro",
                        "Discounter senken Kaffeepreis unter einen Euro"):
        pair = butter()
        pair[1]["title"], pair[1]["context"] = replacement, replacement + "."
        assert validate_pair({"title": pair[0]["title"]}, pair)
    pair = butter()
    assert validate_pair({"title": "Discounter senken Butterpreis unter 0,79 Euro"}, pair)


def test_a_tentative_price_lead_cannot_supply_a_confirmed_action():
    pair = butter()
    pair[1] = record("other.de", "Butterpreis unter einem Euro bei Discountern",
                     "Die Discounter planen den Butterpreis unter einen Euro zu senken.")
    assert "shared_headline_event_anchor_required" in validate_pair({"title": pair[0]["title"]}, pair)


def test_syndicated_regional_price_reports_still_count_as_one_origin():
    pair = butter()
    pair[1] = {**pair[0], "url": "https://www.swr.de/swraktuell/butter.html"}
    pair[0]["url"] = "https://www.tagesschau.de/inland/regional/badenwuerttemberg/swr-butter-100.html"
    assert "requires_two_independent_publishers" in validate_pair({"title": pair[0]["title"]}, pair)
    pair = butter()
    for row in pair:
        row["origin"] = "dpa"
    assert "same_declared_reporting_origin" in validate_pair({"title": pair[0]["title"]}, pair)


def test_ticket_availability_handles_inflection_without_turning_plans_into_sales():
    pair = [
        record("tagesschau.de", "Flixtrain-Tickets bald auch bei Deutscher Bahn buchbar",
               "Reisende können demnächst auch Tickets für Flixtrain bei der Deutschen Bahn buchen."),
        record("manager-magazin.de", "Deutsche Bahn: Konzern verkauft demnächst Tickets für Flixtrain",
               "Reisende können künftig über die Plattformen der Deutschen Bahn auch Tickets von Flixtrain kaufen. "
               "Die Vereinbarung gilt nur für den Ticketvertrieb, nicht für die Fahrgastrechte."),
    ]
    assert hf.corroborated_headline(*pair) == pair[0]["title"]
    assert validate_pair({"title": "Deutsche Bahn verkauft Flixtrain-Tickets"}, pair)


def test_a_short_publisher_transaction_clause_does_not_add_an_outcome_or_buyer():
    pair = [
        record("faz.net", "Verkauf von Ziehl-Abegg: Gefährliche Entwicklung",
               "Die Eigentümerfamilien verkaufen ihr Geschäft ins Ausland."),
        record("swr.de", "So wird der Verkauf von Ziehl-Abegg bewertet",
               "Der Ventilatorenhersteller Ziehl-Abegg wird an einen Konzern verkauft."),
    ]
    assert hf.corroborated_headline(*pair) == "Verkauf von Ziehl-Abegg"
    assert validate_pair({"title": "Verkauf von Ziehl-Abegg an Siemens"}, pair)


def test_ranking_prefers_substantive_verified_evidence_over_a_duplicate_alert():
    records = {"A": {"context": "a" * 200}, "B": {"context": "b" * 50},
               "C": {"context": "c" * 250}, "D": {"context": "d" * 220}}
    title = "Flixtrain-Tickets bald bei der Deutschen Bahn buchbar"
    pairs = {("A", "B"): title, ("C", "D"): title}
    ranked = hf._rank_corroborated_pairs(pairs.items(), [], 0, records)
    assert list(ranked) == [("C", "D"), ("A", "B")]


def test_optional_scorecard_completion_cannot_hide_a_real_provider_quota():
    import pytest
    from urllib.error import HTTPError
    from tayvoriq_regional_relevance import complete_scorecards

    candidate = {"title": "Discounter senken Butterpreis", "sources": [
        {"source_id": "A", "url": "https://a.de/1", "supports": "Die Discounter senken den Butterpreis."},
        {"source_id": "B", "url": "https://b.de/2", "supports": "Der Butterpreis wird erneut gesenkt."}],
        "fallback_editorial_answers": {"what_happened": "Die Discounter senken den Butterpreis."}}
    error = HTTPError("https://provider.example", 429, "rate limit", {"retry-after": "30"}, None)
    def blocked(_batch):
        raise RuntimeError("provider request unavailable") from error
    with pytest.raises(RuntimeError) as raised:
        complete_scorecards([candidate], {}, blocked)
    from tayvoriq_provider_health_v1 import http_failure
    assert http_failure(raised.value) == (429, {"retry-after": "30"})


def test_optional_editorial_repair_cannot_report_success_after_quota_exhaustion():
    import pytest
    from urllib.error import HTTPError
    candidate = {"title": "Die Ketten planen einen Zusammenschluss",
                 "sources": [{"source_id": "A", "supports": "Die Ketten planen einen Zusammenschluss."},
                             {"source_id": "B", "supports": "Für Kunden bleiben die Märkte geöffnet."}],
                 "_retrieved_regional_assessment": {"passed": True},
                 "fallback_editorial_answers": {"what_happened": "Die Ketten planen einen Zusammenschluss."},
                 "explanation_core": "Die Ketten fusionieren.", "cta_text": "Was heißt das für deinen Markt?"}
    def blocked(_batch):
        raise HTTPError("https://provider.example", 402, "payment blocked", {}, None)
    with pytest.raises(HTTPError) as raised:
        hf._repair_editorial_fields([candidate], blocked)
    assert raised.value.code == 402
