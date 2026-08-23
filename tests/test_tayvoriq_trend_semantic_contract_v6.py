from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import tayvoriq_agent_trend_radar_v6 as v6


BROKEN_BOSCH = {
    "what_happened": "Bosch will ab 2027 im Werk Bühl humanoide KI-Roboter für das britische Unternehmen Humanoid fertigen.",
    "why_happening": "Humanoide Robotik bewegt sich vom Prototypen in Richtung industrielle Skalierung. Humanoid entwickelt die Maschinen, während Bosch Fertigungs-Know-how und möglicherweise eigene Komponenten einbringt.",
    "who_is_affected": "Relevant ist das für Industrie- und Logistikunternehmen, Robotik-Anbieter, Beschäftigte in automatisierten Produktionsumgebungen und den Technologiestandort Baden-Württemberg.",
    "personal_impact": "Physical AI wird damit in Deutschland greifbarer: Roboter mit menschenähnlichem Körper sollen zunächst Aufgaben in Fabriken und Logistik übernehmen.",
    "action_now": "Im Short zeigen, was diese Roboter tatsächlich zuerst tun sollen, warum Bosch in Bühl produziert und weshalb das für Baden-Württemberg technologisch interessant ist.",
}

SAFE_BOSCH = {
    "what_happened": "Bosch will ab 2027 in Bühl humanoide Roboter fertigen.",
    "why_happening": "Weil Humanoid die Roboter entwickelt, übernimmt Bosch Industrialisierung und Fertigung.",
    "who_is_affected": "Relevant ist das für Industrie, Logistik, Beschäftigte und Baden-Württemberg.",
    "personal_impact": "Für dich wird Physical AI in Fabrik und Logistik greifbarer.",
    "action_now": "Prüfe geplante Roboter-Aufgaben und die Rolle von Bosch in Bühl.",
}


def test_exact_bosch_failure_is_rejected_before_telegram() -> None:
    assert v6._downstream_editorial_contract_valid(BROKEN_BOSCH) is False


def test_compact_source_bound_bosch_packet_is_contract_safe() -> None:
    assert v6._downstream_editorial_contract_valid(SAFE_BOSCH) is True


def test_provider_prompt_contains_downstream_constraints() -> None:
    prompt = v6.prompt_for("evening", datetime(2026, 8, 23, 18, 0, 0))
    assert "5-15 words" in prompt
    assert "38-49 words" in prompt
    assert "personal_impact must explicitly contain 'Für dich'" in prompt
    assert "action_now must begin with one of" in prompt
