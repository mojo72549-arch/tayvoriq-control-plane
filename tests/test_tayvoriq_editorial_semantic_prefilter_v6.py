from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import tayvoriq_agent_trend_radar_v6 as radar


def _candidate(why: str, impact: str) -> dict:
    return {
        "source_context": {
            "fallback_editorial_answers": {
                "what_happened": "Deutschland gewinnt bei der EM 21 Medaillen und belegt Rang drei.",
                "why_happening": why,
                "who_is_affected": "Das deutsche Leichtathletik-Team und seine Fans.",
                "personal_impact": impact,
                "action_now": "Prüfe bei der Medaillentabelle zuerst die Goldmedaillen.",
            }
        }
    }


def test_rejects_tautological_medal_explanation() -> None:
    candidate = _candidate(
        "Deutschland ist Dritter, weil Deutschland bei der EM 21 Medaillen gewinnt.",
        "Für dich ändert die Rangfolge, wie du den direkten Vergleich bewertest.",
    )
    assert radar._downstream_editorial_contract_valid(candidate["source_context"]["fallback_editorial_answers"])
    assert radar._editorial_semantics_strong(candidate) is False


def test_accepts_source_bound_explanatory_angle() -> None:
    candidate = _candidate(
        "Die Briten liegen vorn, weil Goldmedaillen in der Rangliste Vorrang haben.",
        "Für dich ändert die Rangfolge, wie du den direkten Vergleich bewertest.",
    )
    assert radar._editorial_semantics_strong(candidate) is True


def test_rejects_editorial_prose_exceeding_spoken_budget():
    candidate = _candidate("Weil " + "Wettbewerb " * 20, "Für dich zählt der direkte Vergleich bei der Einordnung.")
    assert not radar._editorial_semantics_strong(candidate)
