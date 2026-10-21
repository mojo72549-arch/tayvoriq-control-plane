"""No-paid-add-on Groq/RSS recovery with strict immutable source IDs."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_agent_hf_v2 as hf
import tayvoriq_agent_research_resilience_v2 as resilience


def record(domain, title, index):
    return {
        "title": title, "context": f"{title}: unabhängig bestätigte Meldung {index}.",
        "url": f"https://{domain}/artikel-{index}", "domain": domain,
        "seen_date": "Mon, 19 Oct 2026 12:00:00 GMT", "feed": domain,
    }


class GroqSourceContractTests(unittest.TestCase):
    def setUp(self):
        self.pool = [
            record(domain, title, i)
            for i, (domain, title) in enumerate([
                ("tagesschau.de", "Mercedes investiert in Werk Stuttgart"),
                ("dw.com", "Mercedes investiert in Werk Stuttgart"),
                ("bbc.com", "Bosch eröffnet Reutlingen Halbleiterfabrik"),
                ("theguardian.com", "Bosch eröffnet Reutlingen Halbleiterfabrik"),
                ("tagesschau.de", "Erste Meldung aktualisiert"),
                ("dw.com", "Erste Meldung aktualisiert"),
                ("bbc.com", "Zweite Meldung aktualisiert"),
                ("theguardian.com", "Zweite Meldung aktualisiert"),
            ], 1)
        ]
        ordered = hf._balanced_compact_records(self.pool)
        self.ids = {
            (row["domain"], row["title"]): f"S{i:03d}"
            for i, row in enumerate(ordered, 1)
        }
        self.by_id = {f"S{i:03d}": row for i, row in enumerate(ordered, 1)}

    def _candidate(self, first, second):
        return {
            "title": self.by_id.get(first, {}).get("title", "Unbekannter Sachverhalt"),
            "sources": [{"source_id": first, "supports": "Quelle bestätigt Sachverhalt"},
                        {"source_id": second, "supports": "Weitere Quelle bestätigt Sachverhalt"}],
        }

    def test_groq_json_result_uses_existing_exact_url_and_independence_validator(self):
        ids = self.ids
        a = self._candidate(
            ids[("tagesschau.de", "Mercedes investiert in Werk Stuttgart")],
            ids[("dw.com", "Mercedes investiert in Werk Stuttgart")])
        b = self._candidate(
            ids[("bbc.com", "Bosch eröffnet Reutlingen Halbleiterfabrik")],
            ids[("theguardian.com", "Bosch eröffnet Reutlingen Halbleiterfabrik")])
        sent = []
        def groq(payload, key, timeout=0):
            sent.append((payload, key, timeout))
            return {"choices": [{"message": {"content": json.dumps({"candidates": [a, b]})}}]}

        with patch.object(hf.provider, "post_groq", groq):
            data, chunks, model = hf.structure(
                "German verified current sources only", "existing-groq-key", self.pool,
                "rss", provider_kind="groq")
        self.assertEqual(len(chunks), 4)
        self.assertTrue(model.startswith("groq/"))
        self.assertEqual(len(data["candidates"]), 2)
        for candidate in data["candidates"]:
            urls = [src["url"] for src in candidate["sources"]]
            self.assertTrue(all(url in {r["url"] for r in self.pool} for url in urls))
            self.assertEqual(len({hf.domain(url) for url in urls}), 2)
        payload, key, timeout = sent[0]
        self.assertEqual(key, "existing-groq-key")
        self.assertEqual(payload["model"], "openai/gpt-oss-20b")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_completion_tokens"], 8000)
        for item in data["candidates"]:
            for source in item["sources"]:
                record = self.by_id[source["source_id"]]
                self.assertEqual(source["supports"], f'{record["title"]} {record["context"]}')
                self.assertEqual(source["support_origin"], "retrieved_source_title_and_context")
                self.assertEqual(len(source["source_record_sha256"]), 64)
                self.assertNotIn("Quelle bestätigt Sachverhalt", source["supports"])

    def test_unrelated_valid_ids_and_invented_support_cannot_be_grounded(self):
        ids = self.ids
        candidate = self._candidate(
            ids[("tagesschau.de", "Mercedes investiert in Werk Stuttgart")],
            ids[("bbc.com", "Bosch eröffnet Reutlingen Halbleiterfabrik")])
        candidate["sources"][1]["supports"] = candidate["title"]
        def fake(*args, **kwargs):
            return {"choices": [{"message": {"content": json.dumps({"candidates": [candidate, candidate]})}}]}
        with patch.object(hf.provider, "post_groq", fake), self.assertRaisesRegex(RuntimeError, "source contract insufficient"):
            hf.structure("prompt", "key", self.pool, "rss", provider_kind="groq")

    def test_duplicate_story_and_source_pair_do_not_satisfy_minimum_grounding(self):
        candidate = self._candidate(
            self.ids[("tagesschau.de", "Mercedes investiert in Werk Stuttgart")],
            self.ids[("dw.com", "Mercedes investiert in Werk Stuttgart")])
        renamed = {**candidate, 'title': 'Mercedes investiert in Stuttgart Werk'}
        def fake(*args, **kwargs):
            return {"choices": [{"message": {"content": json.dumps({"candidates": [candidate, renamed]})}}]}
        with patch.object(hf.provider, "post_groq", fake), self.assertRaisesRegex(RuntimeError, 'valid_candidates=1 grounding_chunks=2'):
            hf.structure('prompt', 'key', self.pool, 'rss', provider_kind='groq')

    def test_unknown_and_same_domain_ids_fail_closed(self):
        ids = self.ids
        wrong = self._candidate("S999", ids[("dw.com", "Mercedes investiert in Werk Stuttgart")])
        same = self._candidate(
            ids[("dw.com", "Mercedes investiert in Werk Stuttgart")],
            ids[("dw.com", "Erste Meldung aktualisiert")])
        def fake(payload, key, timeout=0):
            return {"choices": [{"message": {"content": json.dumps({"candidates": [wrong, same]})}}]}
        with patch.object(hf.provider, "post_groq", fake), self.assertRaisesRegex(RuntimeError, "source contract insufficient"):
            hf.structure("prompt", "key", self.pool, "rss", provider_kind="groq")

    def test_invalid_provider_is_never_called(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_SOURCE_STRUCTURE_PROVIDER"):
            hf.structure("prompt", "key", self.pool, provider_kind="unknown")

    def test_browser_dossier_failure_recovers_without_huggingface_charge(self):
        with patch.object(resilience.provider, "groq_browser_then_structure", side_effect=RuntimeError("browser research dossier unexpectedly short")), \
             patch.object(resilience.rss, "source_pool", return_value=self.pool), \
             patch.object(resilience.hf, "structure", return_value=({"candidates": [{"title": "verified"}]}, [{"uri": "a"}]*4, "groq/test")) as structure, \
             patch.object(resilience.gdelt, "source_pool", side_effect=AssertionError("GDELT should not be needed")), \
             patch.object(resilience.http, "retry", side_effect=AssertionError("Gemini should not be used")):
            out = resilience.grounded("prompt", "", "existing-groq-key")
        self.assertEqual(out[3], "groq_rss")
        self.assertEqual(structure.call_args.kwargs["provider_kind"], "groq")


if __name__ == "__main__":
    unittest.main()
