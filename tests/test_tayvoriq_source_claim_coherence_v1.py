from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import tayvoriq_agent_trend_radar_v4 as radar


def _candidate(title: str, supports: list[str], why: str) -> dict:
    return {
        "title": title,
        "source_context": {
            "sources": [
                {"publisher": f"source-{index}", "url": f"https://example{index}.org/story", "supports": support}
                for index, support in enumerate(supports, start=1)
            ],
            "fallback_editorial_answers": {"why_happening": why},
        },
    }


def test_rejects_german_four_gold_claim_when_second_source_is_amy_hunt_only():
    candidate = _candidate(
        "Deutsche Leichtathleten erobern EM mit vier Gold",
        [
            "Die deutschen Leichtathleten haben bei der EM ein Medaillen-Feuerwerk gezündet.",
            "Amy Hunt gewann vier Goldmedaillen bei den Europameisterschaften.",
        ],
        "Gezielte Trainingsprogramme und starke Nachwuchsförderung führen zu Spitzenleistungen.",
    )
    passed, reasons = radar._source_claim_coherent(candidate)
    assert passed is False
    assert "source_1_missing_title_number" in reasons
    assert "source_2_missing_title_country" in reasons
    assert "why_happening_not_supported_by_source_claims" in reasons


def test_accepts_numeric_country_claim_when_both_sources_support_core_claim_and_why():
    candidate = _candidate(
        "Deutschland beendet die EM mit sechs Goldmedaillen",
        [
            "Deutschland beendet die EM mit sechs Goldmedaillen und 21 Medaillen insgesamt.",
            "Das deutsche Team holte sechs Goldmedaillen; mehrere Favoriten gewannen ihre Finals.",
        ],
        "Mehrere deutsche Favoriten gewannen ihre Finals, dadurch kamen sechs Goldmedaillen zusammen.",
    )
    passed, reasons = radar._source_claim_coherent(candidate)
    assert passed is True
    assert reasons == []


def test_rejects_unbacked_causal_why_even_without_numeric_country_title():
    candidate = _candidate(
        "Stadt meldet überraschenden Besucherrekord",
        [
            "Die Stadt meldet einen neuen Besucherrekord für dieses Wochenende.",
            "Der Veranstalter bestätigt die Rekordzahl der Gäste.",
        ],
        "Dank einer neuen Social-Media-Kampagne stiegen die Besucherzahlen.",
    )
    passed, reasons = radar._source_claim_coherent(candidate)
    assert passed is False
    assert reasons == ["why_happening_not_supported_by_source_claims"]
