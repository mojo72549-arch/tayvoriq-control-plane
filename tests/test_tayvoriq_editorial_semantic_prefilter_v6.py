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
                "what_happened": "Deutschland beendet die EM mit 21 Medaillen: sechs Gold, zehn Silber und fünf Bronze – Rang drei.",
                "why_happening": why,
                "who_is_affected": "Das deutsche Leichtathletik-Team und seine Fans.",
                "personal_impact": impact,
                "action_now": "Die finale Tabelle jetzt einordnen.",
            }
        }
    }


def test_rejects_tautological_medal_explanation() -> None:
    candidate = _candidate(
        "Deutschland kam auf Rang drei, weil das Team sechs Gold-, zehn Silber- und fünf Bronzemedaillen gewann; zusammen sind das 21 Medaillen.",
        "Für deutsche Sportfans zeigt die Bilanz die Einordnung direkt: Nur Italien und Großbritannien lagen in der Medaillenwertung vor Deutschland.",
    )
    assert radar._editorial_semantics_strong(candidate) is False


def test_accepts_source_bound_explanatory_angle() -> None:
    candidate = _candidate(
        "Deutschland gewann insgesamt sogar mehr Medaillen als Großbritannien, landete aber trotzdem hinter den Briten: Für die Platzierung waren die Goldmedaillen entscheidend – Italien hatte zehn, Großbritannien neun und Deutschland sechs.",
        "Für Zuschauer erklärt das den scheinbaren Widerspruch: 21 deutsche Medaillen sind mehr als die 19 britischen, trotzdem steht Deutschland nur auf Rang drei. Wer nur die Gesamtzahl betrachtet, würde die Bilanz falsch einordnen.",
    )
    assert radar._editorial_semantics_strong(candidate) is True
