import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_editorial_value_v1 as gate

# Fictional offline fixture, not a claim about a real research result.
STORY = ("Warum spart dieser Chip nur manchmal Strom? Ein Labortest zeigt geringeren Verbrauch bei einer bestimmten Aufgabe. "
         "Der Grund ist ein kürzerer Datenweg, nicht mehr Rechenleistung. "
         "Für andere Aufgaben fehlt der Nachweis noch. Entscheidend ist deshalb, welche Arbeit der Chip tatsächlich übernimmt.")


def candidate():
    return {"title": "Testchip", "content_angle": "Grenzen des Stromvorteils",
            "cta_text": "Folge TAYVORIQ für Technik erklärt statt nur angekündigt.",
            "follow_reason": "Verstehe die Grenzen neuer Chips.", "open_loop_status": "NONE",
            "source_context": {"story_first_script_body": STORY, "editorial_story_contract_version": 2,
                               "sources": [{"supports": STORY, "url": "https://example.test/lab"}],
                               "fallback_editorial_answers": {"what_happened": "Testchip"}}}


def review_response(items, fail=None):
    return {"reviews": [{"id": str(i), "checks": {
        name: {"passed": name != fail, "quote": item["source_context"]["story_first_script_body"].split("?")[0] + "?",
               "reason": "Beispielhafte redaktionelle Begründung im Test."} for name in gate.CHECKS},
        "facts_supported": True, "payoff_delivered": True, "honest_follow_promise": True}
        for i, item in enumerate(items)]}


def sequence(*responses):
    calls = []
    def call(prompt):
        calls.append(prompt)
        assert len(calls) <= len(responses), "unbounded retry"
        return copy.deepcopy(responses[len(calls)-1])
    return call, calls


def test_pass_is_bound_to_audible_packet_and_does_not_mutate_input():
    original = candidate()
    before = copy.deepcopy(original)
    call, calls = sequence(review_response([original]))
    result = gate.review_candidates([original], call)
    assert original == before and len(calls) == 1
    report = result[0]["source_context"]["editorial_value_review"]
    assert report["packet_sha256"] == gate.digest(gate.packet(original, 0))
    assert report["observed_retention"] is None


@pytest.mark.parametrize("criterion", gate.CHECKS)
def test_each_missing_quality_criterion_blocks_even_with_good_metadata(criterion):
    item = candidate()
    failed = review_response([item], fail=criterion)
    call, calls = sequence(failed, {"rewrites": [{"id": "0", "story": STORY, "cta": item["cta_text"]}]}, failed)
    with pytest.raises(ValueError, match="EDITORIAL_REWRITE_REQUIRED"):
        gate.review_candidates([item], call)
    assert len(calls) == 3


def test_rewrite_is_rechecked_and_preserves_sources_angle_and_input():
    item = candidate()
    before = copy.deepcopy(item)
    improved = STORY.replace("Warum spart", "Wieso spart")
    rewritten = copy.deepcopy(item)
    rewritten["source_context"]["story_first_script_body"] = improved
    call, calls = sequence(review_response([item], "insight"),
                           {"rewrites": [{"id": "0", "story": improved, "cta": item["cta_text"]}]},
                           review_response([rewritten]))
    result = gate.review_candidates([item], call)[0]
    assert result["source_context"]["story_first_script_body"] == improved
    assert result["source_context"]["sources"] == before["source_context"]["sources"]
    assert result["content_angle"] == before["content_angle"] and item == before
    assert len(calls) == 3


def test_metadata_or_cta_quote_cannot_prove_explanation_in_body():
    item = candidate()
    response = review_response([item])["reviews"][0]
    response["checks"]["insight"]["quote"] = item["cta_text"]
    assert "insight" in gate.issues_for(gate.packet(item, 0), response)


@pytest.mark.parametrize("flag", ["facts_supported", "payoff_delivered", "honest_follow_promise"])
def test_facts_payoff_and_honest_promise_are_mandatory(flag):
    item = candidate()
    response = review_response([item])["reviews"][0]
    response[flag] = False
    assert flag in gate.issues_for(gate.packet(item, 0), response)


@pytest.mark.parametrize("rows", [[], [{"id": "9"}], [{"id": "0"}, {"id": "0"}]])
def test_incomplete_cross_candidate_or_duplicate_reviews_rejected(rows):
    with pytest.raises(ValueError, match="identity_mismatch"):
        gate.review_candidates([candidate()], lambda _: {"reviews": rows})


def test_provider_failure_does_not_return_success():
    def unavailable(_):
        raise TimeoutError("offline")
    with pytest.raises(TimeoutError):
        gate.review_candidates([candidate()], unavailable)


def test_rewrite_cannot_replace_sources():
    item = candidate()
    call, _ = sequence(review_response([item], "importance"),
                       {"rewrites": [{"id": "0", "story": STORY, "cta": item["cta_text"], "sources": []}]})
    with pytest.raises(ValueError, match="invalid_fields"):
        gate.review_candidates([item], call)


def test_normalizer_retains_story_without_replacing_validated_sources(monkeypatch):
    import tayvoriq_agent_trend_radar_v8 as radar
    normalized = {"source_context": {"sources": ["verified"], "fallback_editorial_answers": {"kept": True}}}
    monkeypatch.setattr(radar, "_original_normalized_candidate", lambda *_: copy.deepcopy(normalized))
    result = radar.normalized_candidate({"source_context": {"sources": ["unvalidated"],
                                        "story_first_script_body": STORY, "editorial_story_contract_version": 2}}, "now")
    assert result["source_context"]["story_first_script_body"] == STORY
    assert result["source_context"]["sources"] == ["verified"]


def test_no_configured_reviewer_blocks_without_network(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ValueError, match="reviewer_unavailable"):
        gate.call_json("test")


def test_radar_cannot_deliver_unreviewed_selection(monkeypatch):
    import tayvoriq_agent_trend_radar_v8 as radar
    items = [dict(candidate(), regional_relevance="global") for _ in range(5)]
    monkeypatch.setattr(radar.retention_v5, "apply_trend_contract", lambda item, **_: copy.deepcopy(item))
    monkeypatch.setattr(radar, "_original_diversify", lambda items, _: items)
    monkeypatch.setattr(radar, "_selection_key", lambda _: 1)
    monkeypatch.setattr(radar, "_reach_gate", lambda _: 1)
    markers = []
    monkeypatch.setattr(radar, "_mark_research_deferred", lambda *args, **kwargs: markers.append((args, kwargs)))
    def failed(_):
        raise gate.EditorialRejected({"0": ["insight"]})
    monkeypatch.setattr(radar.editorial_value, "review_candidates", failed)
    with pytest.raises(SystemExit, match="EDITORIAL_REVIEW_DEFERRED"):
        radar.diversify(items, "evening")
    assert markers[0][1]["production_started"] is False
    assert markers[0][1]["editorial_issues"] == {"0": ["insight"]}


@pytest.mark.parametrize("provider", ["groq", "gemini"])
def test_reviewer_transport_has_no_search_or_tools(monkeypatch, provider):
    monkeypatch.setenv("GROQ_API_KEY", "fixture" if provider == "groq" else "")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture" if provider == "gemini" else "")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self):
            content = json.dumps({"reviews": []})
            raw = {"choices": [{"message": {"content": content}}]} if provider == "groq" else {
                "candidates": [{"content": {"parts": [{"text": content}]}}]}
            return json.dumps(raw).encode()
    def open_request(request, timeout):
        body = json.loads(request.data)
        assert "tools" not in body and timeout == 90
        assert "google_search" not in request.data.decode()
        return Response()
    monkeypatch.setattr(gate.urllib.request, "urlopen", open_request)
    assert gate.call_json("editorial fixture") == {"reviews": []}


def test_groq_formatter_receives_complete_editorial_contract(monkeypatch):
    import tayvoriq_agent_trend_provider_v3 as provider
    prompts = []
    def post(payload, *_args, **_kwargs):
        prompts.append(payload["messages"][-1]["content"])
        text = "source-backed dossier " * 50 if len(prompts) == 1 else '{"candidates": []}'
        return {"choices": [{"message": {"content": text}}]}
    monkeypatch.setattr(provider, "post_groq", post)
    provider.groq_browser_then_structure("A" * 4000 + "EDITORIAL_END_MARKER", "fixture")
    assert all("EDITORIAL_END_MARKER" in prompt for prompt in prompts)
    assert "story_first_script_body" in prompts[1]
