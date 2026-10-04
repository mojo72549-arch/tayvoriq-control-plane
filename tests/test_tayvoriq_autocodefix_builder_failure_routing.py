from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tayvoriq-autonomous-codefix-builder.yml"


def test_editorial_length_failures_take_priority_over_speech_noise():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "r'script_too_short'" in text
    assert "r'verified-editorial-postcondition-drift'" in text
    assert "editorial_length_failure=any(" in text
    assert "action='repair_bounded_v20_length_contract_then_resume_approved_request'" in text
    assert "'runtime_patches/tayvoriq_german_hyphen_guard.py'" in text
    assert "'runtime_patches/tayvoriq_v20_final_length_guard.py'" in text

    editorial_branch = text.index("elif editorial_length_failure:")
    number_branch = text.index("elif number_failure:")
    pronunciation_branch = text.index("elif pronunciation_failure:")
    assert editorial_branch < number_branch < pronunciation_branch


def test_number_and_pronunciation_routing_use_failure_focus_not_full_log():
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "failure_focus=(quality_evidence + '\\n' + failed_log).casefold()" in text
    assert "'48.000'" not in text[text.index("number_failure=any("):text.index("if source_hash_failure:")]
    assert "'number-pronunciation-not-confirmed'" in text
    assert "'critical_pronunciation_missing'" in text
