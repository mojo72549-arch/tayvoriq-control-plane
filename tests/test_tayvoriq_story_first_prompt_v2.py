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
