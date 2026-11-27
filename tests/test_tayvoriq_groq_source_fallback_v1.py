"""No-paid-add-on Groq/RSS recovery with strict immutable source IDs."""
import json
import os
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

    def test_ollama_rates_one_bound_source_pair_per_request(self):
        calls = []

        def decide(payload, *, time_limit):
            self.assertGreater(time_limit, 0)
            calls.append(payload)
            key, = payload['format']['required']
            return {'choices': [{'message': {'content': json.dumps({key: None})}}]}

        with patch.object(hf.local, 'complete', side_effect=decide), \
                patch.object(hf.rss, 'enrich_evidence', side_effect=lambda records: records):
            with self.assertRaises(hf.InsufficientSourceEvidence):
                hf.structure('German source-bound research', '', self.pool, 'multi-publisher-rss', provider_kind='ollama')
        self.assertEqual(len(calls), 2)
        observed = set()
        for request in calls:
            key, = request['format']['required']
            observed.add(key)
            prompt = request['messages'][1]['content']
            self.assertIn('criteria und die sieben einzelnen Trend-Scores verwenden die Skala 0–100', prompt)
            self.assertIn('Skala 0–5 gilt ausschließlich für y und t', prompt)
            sources = json.loads(prompt.split('\nMeldungen: ', 1)[1])
            self.assertEqual([source['source_id'] for source in sources], key.split('+'))
        self.assertEqual(len(observed), 2)

    def test_targeted_local_research_only_submits_the_requested_pair(self):
        def decide(payload, *, time_limit):
            self.assertGreater(time_limit, 0)
            key, = payload['format']['required']
            return {'choices': [{'message': {'content': json.dumps({key: {}})}}]}

        with patch.dict(os.environ, {'TAYVORIQ_EDITORIAL_TOPIC': 'Bosch Halbleiterfabrik'}), \
             patch.object(hf.rss, 'source_pool', return_value=self.pool), \
             patch.object(hf.rss, 'enrich_evidence', side_effect=lambda records: records), \
             patch.object(hf.local, 'complete', side_effect=decide) as model, \
             patch.object(hf, 'complete_scorecards'), patch.object(hf, '_repair_editorial_fields'), \
             patch.object(hf, 'evaluate_regional_relevance', return_value={'passed': True}):
            data, chunks, _, provider = resilience.local_grounded('targeted')
            model.assert_called_once()
            self.assertEqual(provider, 'ollama_rss')
            self.assertEqual([row['title'] for row in data['candidates']], ['Bosch eröffnet Reutlingen Halbleiterfabrik'])
            self.assertEqual({chunk['uri'] for chunk in chunks}, {row['url'] for row in self.pool[2:4]})
            with patch.dict(os.environ, {'TAYVORIQ_EDITORIAL_TOPIC': 'S-Bahn Verspätungen'}):
                with self.assertRaises(hf.InsufficientFeedEvidence):
                    hf.structure('targeted', '', self.pool, 'multi-publisher-rss', provider_kind='ollama', allow_single=True)
            model.assert_called_once()

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
        prompt = payload["messages"][1]["content"]
        self.assertNotIn('"aktualitaet":0', prompt)
        self.assertIn('"aktualitaet":<integer 0-100>', prompt)
        self.assertEqual(key, "existing-groq-key")
        self.assertEqual(payload["model"], "openai/gpt-oss-20b")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_completion_tokens"], 4000)
        self.assertEqual(payload["reasoning_effort"], 'low')
        for item in data["candidates"]:
            for source in item["sources"]:
                record = self.by_id[source["source_id"]]
                self.assertEqual(source["supports"], f'{record["title"]} {record["context"]}')
                self.assertEqual(source["support_origin"], "retrieved_source_title_and_context")
                self.assertEqual(len(source["source_record_sha256"]), 64)
                self.assertNotIn("Quelle bestätigt Sachverhalt", source["supports"])

    def test_regional_rubric_requires_original_quotes_and_both_platforms(self):
        import tayvoriq_regional_relevance as rubric
        sources = [{"source_id": "S003", "url": "https://a.de/id", "supports": "Der Fahrplan gilt ab Montag."},
                   {"source_id": "S007", "url": "https://b.de/id", "supports": "Pendler erreichen die Innenstadt früher."}]
        card = {"ratings": {key: [4, 4, "Der neue Fahrplan kürzt Wartezeiten."] for key in rubric.WEIGHTS},
                "evidence": {s["source_id"]: s["supports"] for s in sources},
                "platform_fit": {"youtube": "Der Fahrplan erklärt die neue Verbindung.",
                                 "tiktok": "Der direkte Vergleich zeigt die Zeitersparnis."}}
        for source in sources:
            sid = source["source_id"]
            source["evidence_options"] = rubric.evidence_options(sid, source["supports"], "")
            card["evidence"][sid] = sid + ":title"
        score = rubric.evaluate(card, sources)
        self.assertEqual(score["evidence"][sources[0]["url"]], sources[0]["supports"])
        card["evidence"]["S007"] = "S003:title"
        self.assertFalse(rubric.evaluate(card, sources)["passed"])
        card["evidence"]["S007"] = "S007:title"
        self.assertEqual(score["scores"], {"youtube": 80, "tiktok": 80})
        self.assertTrue(score["passed"])
        card["ratings"]["consequence"][1] = 2
        self.assertFalse(rubric.evaluate(card, sources)["passed"])
        card["ratings"]["consequence"][1] = 4
        card["evidence"]["S007"] = "Der Fahrplan gilt ab Montag."
        self.assertEqual(rubric.evaluate(card, sources)["reason"], "quote_absent_from_retrieved_record:S007")
        self.assertFalse(rubric.evaluate(rubric.bind_corroborated_headline(card, sources, sources[0]["supports"]),
                                        sources)["passed"])

    def test_missing_quote_recovers_only_a_verbatim_verified_claim_from_each_publisher(self):
        import tayvoriq_regional_relevance as rubric
        headline = "Mercedes investiert in Werk Stuttgart"
        sources = [{"source_id": sid, "url": f"https://{sid}.de/a", "supports": headline,
                    "evidence_options": rubric.evidence_options(sid, headline, "")}
                   for sid in ("S003", "S007")]
        card = {"ratings": {key: [4, 4, "Das Werk bekommt weitere Investitionen."] for key in rubric.WEIGHTS},
                "evidence": {"S003": "S007:title", "S007": "Mercedes schafft neue Arbeitsplätze."},
                "platform_fit": {"youtube": "Der Betrieb lässt sich einordnen.",
                                 "tiktok": "Das Werk ist gut erkennbar."}}
        bound = rubric.bind_corroborated_headline(card, sources, headline)
        self.assertEqual(bound["evidence"], {"S003": "S003:title", "S007": "S007:title"})
        self.assertEqual(rubric.evaluate(bound, sources)["evidence"], {s["url"]: headline for s in sources})
        card["ratings"]["consequence"][1] = 2
        self.assertFalse(rubric.evaluate(rubric.bind_corroborated_headline(card, sources, headline), sources)["passed"])

    def test_base_gate_reports_each_missing_or_low_field(self):
        raw = {"title": "Test", "trend_scope": "business_economy",
               "criteria": {"aktualitaet": 0, "quellenqualitaet": 90}}
        issues = hf.base.base_editorial_fields(raw)[-1]
        self.assertIn("criterion_below_minimum:aktualitaet=0<35", issues)
        self.assertIn("missing_criterion:visuell", issues)
        self.assertIn("usable_publishers:0<2", issues)
        self.assertIn("missing_editorial_answer:personal_impact", issues)
        self.assertFalse(any("quellenqualitaet" in issue for issue in issues))

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

    def test_qwen_gets_only_corroborated_evidence_without_gpt_specific_options(self):
        captured = []

        def respond(payload, key, timeout):
            captured.append(payload)
            prompt = payload['messages'][1]['content']
            evidence = json.loads(prompt.split('SOURCE RECORDS (multi-publisher-rss):\n')[1])
            self.assertEqual(len(evidence), 4)
            self.assertTrue(all('aktualisiert' not in row['title'] for row in evidence))
            candidates = [{'title': title, 'sources': [{'source_id': row['source_id']} for row in evidence
                           if row['title'] == title]} for title in dict.fromkeys(row['title'] for row in evidence)]
            return {'choices': [{'message': {'content': json.dumps({'candidates': candidates})}}]}

        with patch.object(hf.provider, 'post_groq', respond):
            data, chunks, model = hf.structure('prompt', 'key', self.pool, 'multi-publisher-rss',
                                               provider_kind='groq', model_override='qwen/qwen3.8-27b')
        self.assertEqual(len(data['candidates']), 2)
        self.assertEqual(len(chunks), 4)
        self.assertIn('qwen/qwen3.8-27b', model)
        self.assertNotIn('reasoning_effort', captured[0])

    def test_duplicate_story_and_source_pair_do_not_satisfy_minimum_grounding(self):
        candidate = self._candidate(
            self.ids[("tagesschau.de", "Mercedes investiert in Werk Stuttgart")],
            self.ids[("dw.com", "Mercedes investiert in Werk Stuttgart")])
        renamed = {**candidate, 'title': 'Mercedes investiert in Stuttgart Werk'}
        def fake(*args, **kwargs):
            return {"choices": [{"message": {"content": json.dumps({"candidates": [candidate, renamed]})}}]}
        with patch.object(hf.provider, "post_groq", fake), self.assertRaisesRegex(RuntimeError, 'valid_candidates=1 grounding_chunks=2'):
            hf.structure('prompt', 'key', self.pool, 'rss', provider_kind='groq')

    def test_editorial_rescan_fetches_context_only_for_shortlisted_publishers(self):
        def deepen(records):
            self.assertEqual(len(records), 4)
            self.assertTrue(all('aktualisiert' not in row['title'] for row in records))
            return [{**row, 'context': row['context'] + ' Originalartikel liefert konkrete Hintergründe.'}
                    for row in records]

        def respond(payload, key, timeout):
            prompt = payload['messages'][1]['content']
            records = json.loads(prompt.split('SOURCE RECORDS (multi-publisher-rss):\n')[1])
            self.assertTrue(all('konkrete Hintergründe' in row['context'] for row in records))
            candidates = [{'title': title, 'sources': [{'source_id': row['source_id']} for row in records
                           if row['title'] == title]} for title in dict.fromkeys(row['title'] for row in records)]
            return {'choices': [{'message': {'content': json.dumps({'candidates': candidates})}}]}

        for marker in hf.RESCAN_MARKERS:
            with self.subTest(marker=marker), patch.object(hf.rss, 'enrich_evidence', deepen), \
                 patch.object(hf.provider, 'post_groq', respond):
                data, chunks, _ = hf.structure('prompt' + marker, 'key', self.pool,
                                               'multi-publisher-rss', provider_kind='groq')
                self.assertEqual(len(chunks), 4)
                for candidate in data['candidates']:
                    for source in candidate['sources']:
                        self.assertIn('Originalartikel', source['supports'])

    def test_research_rescan_and_scheduled_retry_reach_other_corroborated_topics(self):
        pool = [
            record(publisher, f"Nachrichtenüberblick Meldung {i}", i)
            for i in range(110) for publisher in ("a.de", "b.de")
        ]
        topics = [
            "Mercedes investiert in Werk Stuttgart",
            "Bosch eröffnet Reutlingen Halbleiterfabrik",
            "Warnstreik bei Verkehrsbetrieben in Ulm",
            "DHL startet neue Paketstationen in Ludwigsburg",
            "Bahn meldet Ausfall der Regionalzüge in Stuttgart",
            "Allianz eröffnet Berufsschule in Karlsruhe",
        ]
        for i, title in enumerate(topics, len(pool)):
            pool.extend(record(publisher, title, i * 2 + j)
                        for j, publisher in enumerate(("a.de", "b.de")))

        def respond(payload, key, timeout):
            prompt = payload["messages"][1]["content"]
            records = json.loads(prompt.split("SOURCE RECORDS (multi-publisher-rss):\n")[1])
            candidates = [
                {"title": title,
                 "sources": [{"source_id": row["source_id"]} for row in records if row["title"] == title]}
                for title in dict.fromkeys(row["title"] for row in records)
            ]
            return {"choices": [{"message": {"content": json.dumps({"candidates": candidates})}}]}

        def titles(prompt, retry_attempt):
            with patch.object(hf, "_research_retry_attempt", return_value=retry_attempt):
                data, chunks, _ = hf.structure(prompt, "key", pool, "multi-publisher-rss", provider_kind="groq")
            self.assertEqual(len(chunks), 6)
            return {candidate["title"] for candidate in data["candidates"]}

        with patch.object(hf.provider, "post_groq", respond), \
             patch.object(hf.rss, "enrich_evidence", side_effect=lambda records: records):
            first = titles("prompt", 0)
            rescan = titles("prompt" + hf.EDITORIAL_RESCAN + "\nPreviously drafted source headlines: "
                            + json.dumps(sorted(first)), 0)
            retry = titles("prompt", 1)
        self.assertEqual(len(first), 3)
        self.assertEqual(first | rescan, set(topics))
        self.assertEqual(rescan, retry)

    def test_source_bound_model_cannot_bind_a_url_or_ignore_an_extra_source(self):
        def respond(payload, key, timeout):
            prompt = payload["messages"][1]["content"]
            records = json.loads(prompt.split("SOURCE RECORDS (multi-publisher-rss):\n")[1])
            titles = list(dict.fromkeys(row["title"] for row in records))
            first, second = [[row for row in records if row["title"] == title] for title in titles]
            first_url = self.by_id[first[0]["source_id"]]["url"]
            candidates = [
                {"title": titles[0], "sources": [{"url": first_url}, {"source_id": first[1]["source_id"]}]},
                {"title": titles[1], "sources": [{"source_id": row["source_id"]} for row in second]
                 + [{"source_id": "S999"}]},
            ]
            return {"choices": [{"message": {"content": json.dumps({"candidates": candidates})}}]}

        with patch.object(hf.provider, "post_groq", respond), \
             self.assertRaisesRegex(hf.InsufficientSourceEvidence, "valid_candidates=0"):
            hf.structure("prompt", "key", self.pool, "multi-publisher-rss", provider_kind="groq")

    def test_canonical_title_and_sources_are_resolved_from_the_returned_pair_id(self):
        def respond(payload, key, timeout):
            prompt = payload["messages"][1]["content"]
            records = json.loads(prompt.split("SOURCE RECORDS (multi-publisher-rss):\n")[1])
            pairs = [[row["source_id"] for row in records if row["title"] == title]
                     for title in dict.fromkeys(row["title"] for row in records)]
            candidates = [{"source_pair_id": "+".join(sorted(pair))} for pair in pairs]
            candidates.insert(0, {"source_pair_id": candidates[0]["source_pair_id"],
                                  "title": "Erfundener neuer Ausgang"})
            candidates.insert(1, {"source_pair_id": "S777+S888"})
            return {"choices": [{"message": {"content": json.dumps({"candidates": candidates})}}]}

        with patch.object(hf.provider, "post_groq", respond):
            data, chunks, _ = hf.structure("prompt", "key", self.pool, "multi-publisher-rss", provider_kind="groq")
        expected = {"Mercedes investiert in Werk Stuttgart", "Bosch eröffnet Reutlingen Halbleiterfabrik"}
        self.assertEqual({row["title"] for row in data["candidates"]}, expected)
        self.assertEqual(len(chunks), 4)
        for candidate in data["candidates"]:
            self.assertEqual(len(candidate["sources"]), 2)
            self.assertTrue(all(source["supports"].startswith(candidate["title"]) for source in candidate["sources"]))

    def test_single_story_recovery_keeps_the_original_pair_and_regional_gate(self):
        pool = self.pool[:2] + self.pool[4:] + [record('tagesschau.de', 'Weitere Meldung', 20),
                                                record('dw.com', 'Andere Meldung', 21)]

        def respond(payload, key, timeout):
            prompt = payload["messages"][1]["content"]
            records = json.loads(prompt.split("SOURCE RECORDS (rss-article-context):\n")[1])
            self.assertEqual(len(records), 2)
            pair = "+".join(sorted(row["source_id"] for row in records))
            return {"choices": [{"message": {"content": json.dumps({"candidates": [{"source_pair_id": pair}]})}}]}

        with patch.object(hf.provider, "post_groq", side_effect=respond) as post, \
             patch.object(hf, "complete_scorecards"), patch.object(hf, "_repair_editorial_fields"), \
             patch.object(hf, "evaluate_regional_relevance", return_value={"passed": True}) as assess:
            with self.assertRaises(hf.InsufficientFeedEvidence):
                hf.structure("prompt", "key", pool, "rss-article-context", provider_kind="groq")
            post.assert_not_called()
            data, chunks, _ = hf.structure("prompt", "key", pool, "rss-article-context",
                                           provider_kind="groq", allow_single=True)
            self.assertEqual(len(data["candidates"]), 1)
            self.assertEqual({row["uri"] for row in chunks}, {row["url"] for row in pool[:2]})
            assess.return_value = {"passed": False}
            with self.assertRaisesRegex(hf.InsufficientSourceEvidence, "No eligible individual candidate"):
                hf.structure("prompt", "key", pool, "rss-article-context", provider_kind="groq", allow_single=True)

    def test_editorial_repair_only_changes_requested_fields_of_a_qualified_draft(self):
        sources = [{"source_id": "S003", "supports": "Die Kette plant einen Zusammenschluss."},
                   {"source_id": "S009", "supports": "Für Kunden bleiben die Märkte zunächst geöffnet."}]
        draft = {"title": "Die Ketten planen einen Zusammenschluss", "sources": sources,
                 "_retrieved_regional_assessment": {"passed": True}, "fallback_editorial_answers": {"why": "Planung"},
                 "explanation_core": "Die Ketten planen eine Fusion.", "cta_text": "Was heißt das für deinen Markt?",
                 "follow_reason": "Hier erfährst du was ähnliche Veränderungen für deinen Alltag bedeuten.",
                 "surprise_or_reframe": "Für Kundinnen und Kunden bleiben die Märkte vorerst geöffnet und wie gewohnt erreichbar."}
        rejected = {**draft, "_retrieved_regional_assessment": {"passed": False}}
        def rewrite(batch):
            self.assertEqual(set(batch), {"S003+S009"})
            self.assertEqual(set(batch["S003+S009"]["missing"]), {"cta_text", "explanation_core"})
            return {"S003+S009": {"cta_text": "Bei TAYVORIQ erklären wir, was sich in deinem Markt ändern könnte.",
                                  "explanation_core": "Die Baumarktketten planen einen Zusammenschluss. Für Menschen, "
                                  "die dort regelmäßig einkaufen, ist wichtig, was bisher über beide Ketten feststeht.",
                                  "title": "Unbestätigter Titel", "_retrieved_regional_assessment": {"passed": False}}}

        hf._repair_editorial_fields([draft, rejected], rewrite)
        self.assertIn("TAYVORIQ", draft["cta_text"])
        self.assertGreaterEqual(len(draft["explanation_core"].split()), 14)
        self.assertEqual(draft["title"], rejected["title"])
        self.assertEqual(draft["sources"], sources)
        self.assertTrue(draft["_retrieved_regional_assessment"]["passed"])
        self.assertEqual(rejected["explanation_core"], "Die Ketten planen eine Fusion.")

    def test_platform_rejection_opens_other_source_pools_instead_of_rerating_the_same_pair(self):
        rejected = [
            {"title": "Mercedes investiert in Werk Stuttgart", "fields": ["tiktok:regional_score_below_75"]},
            {"title": "Bosch eröffnet Reutlingen Halbleiterfabrik", "fields": ["invalid_evidence_quote:S008"]},
        ]
        prompt = ("prompt" + hf.EDITORIAL_RESCAN + "\nPrevious base-field findings for the source-bound drafts: "
                  + json.dumps(rejected))
        with patch.object(hf.provider, "post_groq") as model, \
             self.assertRaisesRegex(hf.InsufficientFeedEvidence, "corroborated_headlines=1"):
            hf.structure(prompt, "key", self.pool, "multi-publisher-rss", provider_kind="groq")
        model.assert_not_called()

    def test_incomplete_scorecard_does_not_reject_a_topic_on_platform_relevance(self):
        prompt = hf.EDITORIAL_RESCAN + "\nPrevious base-field findings for the source-bound drafts: " + json.dumps([
            {"title": "Valid assessment", "fields": ["tiktok:regional_score_below_75"]},
            {"title": "Missing grade", "fields": ["tiktok:regional_score_below_75",
                                                "invalid_or_unexplained_rating:timeliness"]},
            {"title": "Missing fit", "fields": ["youtube:regional_score_below_75", "platform_fit_missing:tiktok"]},
        ])
        self.assertEqual(hf._below_platform_minimum(prompt), ["Valid assessment"])

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

    def test_production_feed_pool_cannot_spend_model_quota_on_uncorroborated_stories(self):
        pool = [record(f"publisher{i}.de", f"Warnstreiks bei Betrieb{i} in Region{i}", i)
                for i in range(10)]
        with patch.object(hf.provider, "post_groq") as call:
            with self.assertRaisesRegex(RuntimeError, "corroborated_headlines=0"):
                hf.structure("prompt", "key", pool, "multi-publisher-rss", provider_kind="groq")
            call.assert_not_called()

    def test_supported_lead_omits_unconfirmed_context_but_not_a_tentative_qualifier(self):
        lead = "Warnstreiks in der Metall- und Elektroindustrie halten an"
        a = record("tagesschau.de", f"{lead} – Bundesverband nimmt Stellung", 1)
        b = record("dw.com", f"{lead} – Tarifgespräche am Donnerstag", 2)
        self.assertEqual(hf.corroborated_headline(a, b), lead)
        tentative = record("dw.com", f"{lead} – Ausweitung ist geplant", 3)
        self.assertEqual(hf.corroborated_headline(a, tentative), "")

    def test_common_publisher_lead_retains_event_and_modality(self):
        lead = "Bosch investiert in das Werk in Stuttgart"
        first = record("a.de", "Bosch investiert nach Aufsichtsratsbeschluss in Stuttgart", 1)
        second = record("b.de", "Unternehmensleitung investiert in Bosch-Werk in Stuttgart", 2)
        first["context"] = lead + ". Die Geschäftsführung legte ihren Plan vor."
        second["context"] = "In Stuttgart investiert Bosch in das Werk. Beschäftigte erfuhren am Montag davon."
        self.assertEqual(hf.corroborated_headline(first, second), lead)
        second["title"] = "Unternehmensleitung plant Investitionen in Stuttgart"
        self.assertFalse(hf.corroborated_headline(first, second))

    def test_merger_of_named_chains_is_distinct_from_closures_and_other_chains(self):
        a = record("a.de", "Obi und Toom: Baumarktketten fusionieren, Marke Toom soll wegfallen", 1)
        b = record("b.de", "Marke Toom soll wegfallen: Baumärkte Obi und Toom schließen sich zusammen", 2)
        self.assertEqual(hf._events(b["title"]), {"merger"})
        self.assertTrue(hf.corroborated_headline(a, b))
        self.assertEqual(hf._events("Ketten schließen sich zusammen und schließen Filialen"), {"merger", "closure"})
        for other in ("Marke Toom soll wegfallen: Obi und Toom schließen Filialen",
                      "Marke Toom soll wegfallen: Andere Baumärkte schließen sich zusammen",
                      "Obi und Toom dementieren: Baumärkte schließen sich zusammen"):
            self.assertTrue(hf.validate_pair({"title": a["title"]}, [a, record("b.de", other, 2)]))

    def test_independent_headlines_can_use_different_words_for_the_same_confirmed_claim(self):
        reform = [
            record("sueddeutsche.de", "Rente: Studie: Altersteilzeit-Reform könnte Fiskus Milliarden bringen", 1),
            record("n-tv.de", "Erst mit 58 statt 55 Jahren?: Strengere Altersteilzeit-Regeln könnten Staat Milliarden bringen", 2),
        ]
        appointment = [
            record("zdfheute.de", "Freie Wähler: Gotthardt folgt Aiwanger als Wirtschaftsminister", 3),
            record("tagesschau.de", "Nachfolge von Aiwanger: Tobias Gotthardt wird Wirtschaftsminister", 4),
        ]
        appointment[0]["context"] = "Staatssekretär Tobias Gotthardt wird Nachfolger von Hubert Aiwanger."
        for pair in (reform, appointment):
            self.assertGreater(hf._source_pair_score(*pair), 0)
            lead = hf.corroborated_headline(*pair)
            self.assertTrue(lead)
            self.assertEqual(hf.validate_pair({"title": lead}, pair), [])
        self.assertTrue(hf.validate_pair({"title":"Altersteilzeit-Reform bringt Fiskus Milliarden"}, reform))
        self.assertTrue(hf.validate_pair({"title":"Tobias Gotthardt wird Finanzminister"}, appointment))

    def test_ranker_receives_two_distinct_topics_without_a_shared_source_id(self):
        alternatives = {
            ("S001","S002"): "Altersteilzeit-Reform könnte Fiskus Milliarden bringen",
            ("S003","S004"): "Rente - Reform der Altersteilzeit könnte Staat Milliarden bringen",
        }
        self.assertEqual(hf._independent_headline_pairs(alternatives), {})
        alternatives["S002","S005"] = "Tobias Gotthardt wird Wirtschaftsminister"
        selected = hf._independent_headline_pairs(alternatives)
        self.assertEqual(list(selected), [("S003","S004"),("S002","S005")])

    def test_ranking_keeps_the_verified_title_when_the_model_changes_only_the_separator(self):
        records = [{**row} for row in self.pool]
        old = "Mercedes investiert in Werk Stuttgart"
        trusted = "Mercedes - Mercedes investiert in Werk Stuttgart"
        for row in records:
            if row["title"] == old:
                row["title"] = trusted
        ids = {(row["domain"],row["title"]):f"S{i:03d}"
               for i,row in enumerate(hf._balanced_compact_records(records),1)}
        candidates = [
            {"title":"Mercedes: Mercedes investiert in Werk Stuttgart",
             "sources":[{"source_id":ids[(domain,trusted)]} for domain in ("tagesschau.de","dw.com")]},
            {"title":"Bosch eröffnet Reutlingen Halbleiterfabrik",
             "sources":[{"source_id":ids[(domain,"Bosch eröffnet Reutlingen Halbleiterfabrik")]}
                        for domain in ("bbc.com","theguardian.com")]},
        ]
        response = {"choices":[{"message":{"content":json.dumps({"candidates":candidates})}}]}
        with patch.object(hf.provider, "post_groq", return_value=response):
            data, chunks, _ = hf.structure("prompt", "key", records, "multi-publisher-rss", provider_kind="groq")
        self.assertEqual(data["candidates"][0]["title"], trusted)
        self.assertEqual(len(chunks), 4)
        key = hf._headline_presentation_key
        self.assertNotEqual(key("Rente - plus 5 Euro"), key("Rente: plus 50 Euro"))
        self.assertNotEqual(key("Saldo - 5 Euro"), key("Saldo: 5 Euro"))

    def test_scheduled_slot_does_not_wait_for_the_browser_when_sources_are_ready(self):
        with patch.dict("os.environ", {"TAYVORIQ_RESEARCH_SLOT":"morning"}), \
                patch.object(resilience.rss, "source_pool", return_value=self.pool), \
                patch.object(resilience.hf, "structure", return_value=({}, [], "test-model")), \
                patch.object(resilience.provider, "groq_browser_then_structure") as browser:
            self.assertEqual(resilience.grounded("prompt", "", "groq-key")[-1], "groq_rss")
        browser.assert_not_called()

    def test_corrected_editorial_fields_can_replace_an_invalid_draft(self):
        import tayvoriq_agent_trend_radar_v5 as radar
        previous, corrected = {"draft":"first"}, {"draft":"corrected"}
        with patch.object(radar, "apply_trend_contract", side_effect=[ValueError("too thin"), {}]):
            self.assertTrue(radar._verified_editorial_repair(previous, corrected))
        with patch.object(radar, "apply_trend_contract", return_value={}) as validate:
            self.assertFalse(radar._verified_editorial_repair(previous, corrected))
            validate.assert_called_once_with(previous, strict=True)

    def test_missing_feed_evidence_is_enriched_from_its_original_article(self):
        calls = []
        article = '''<script type="application/ld+json">
        {"@type":"NewsArticle","headline":"Mercedes investiert in Werk Stuttgart",
         "description":"Die Investition betrifft die Produktion im Werk.",
         "articleBody":"Die Investitionen beginnen im Herbst."}</script>'''
        parsed = resilience.rss.article_context(article, "Mercedes investiert in Werk Stuttgart")
        self.assertIn("beginnen im Herbst", parsed)
        self.assertEqual(resilience.rss.article_context(article, "Anderes Werk schließt in Emden"), "")
        paywalled = article.replace('"articleBody"', '"isAccessibleForFree":false,"articleBody"')
        self.assertNotIn("beginnen im Herbst", resilience.rss.article_context(paywalled, "Mercedes investiert in Werk Stuttgart"))

        def structure(_prompt, _key, records, label, **kwargs):
            calls.append(label)
            if label == "multi-publisher-rss":
                raise hf.InsufficientFeedEvidence("feed excerpt has no corroborated headline")
            self.assertEqual(label, "rss-article-context")
            self.assertIn(parsed, records[0]["context"])
            self.assertEqual(records[0]["url"], self.pool[0]["url"])
            return {}, [], "groq"

        with patch.dict("os.environ", {"TAYVORIQ_RESEARCH_SELECTION_ID":"review-morning-123"}), \
                patch.object(resilience.rss, "source_pool", return_value=self.pool), \
                patch.object(resilience.hf, "_groq_source_records", return_value=self.pool), \
                patch.object(resilience.rss, "enrich_evidence",
                             side_effect=lambda records: [{**records[0], "context":parsed}, *records[1:]]), \
                patch.object(resilience.hf, "structure", side_effect=structure):
            self.assertEqual(resilience.grounded("prompt", "", "groq")[-1], "groq_rss")
        self.assertEqual(calls[-1], "rss-article-context")

    def test_browser_dossier_failure_recovers_without_huggingface_charge(self):
        with patch.object(resilience.provider, "groq_browser_then_structure", side_effect=RuntimeError("browser research dossier unexpectedly short")), \
             patch.object(resilience.rss, "source_pool", return_value=self.pool), \
             patch.object(resilience.hf, "structure", return_value=({"candidates": [{"title": "verified"}]}, [{"uri": "a"}]*4, "groq/test")) as structure, \
             patch.object(resilience.gdelt, "source_pool", side_effect=AssertionError("GDELT should not be needed")), \
             patch.object(resilience.http, "retry", side_effect=AssertionError("Gemini should not be used")):
            out = resilience.grounded("prompt", "", "existing-groq-key")
        self.assertEqual(out[3], "groq_rss")
        self.assertEqual(structure.call_args.kwargs["provider_kind"], "groq")

    def test_article_research_prioritizes_another_story_over_verified_repeats(self):
        repeated = [
            record(f"publisher-{i}.example", "Mercedes investiert in Werk Stuttgart", i)
            for i in range(10)
        ]
        first = record("publisher-a.example", "Bosch eröffnet Halbleiterfabrik in Reutlingen im Herbst", 11)
        second = record("publisher-b.example", "Bosch eröffnet neue Halbleiterfabrik in Reutlingen im Oktober", 12)
        self.assertTrue(hf.corroborated_headline(*repeated[:2]))
        self.assertFalse(hf.corroborated_headline(first, second))
        self.assertEqual(hf.article_research_records([*repeated, first, second]), [first, second])
        expanded = {**second, "context": second["context"] + " Die Eröffnung findet im Herbst statt."}
        self.assertEqual(hf.corroborated_headline(first, expanded), first["title"])

    def test_large_pool_keeps_cross_publisher_stories_within_small_budget(self):
        fillers = [record('one.example', f'Unrelated headline number {i}', i)
                   for i in range(80)]
        originals = self.pool + fillers
        selected = hf._groq_source_records(fillers + self.pool)
        serialized = [{'source_id': f'S{i:03d}', **{k: row.get(k) for k in
                      ('domain', 'title', 'context', 'seen_date', 'feed')}}
                      for i, row in enumerate(selected, 1)]
        self.assertLessEqual(len(json.dumps(serialized, ensure_ascii=False)), 9000)
        for title in ('Mercedes investiert in Werk Stuttgart',
                      'Bosch eröffnet Reutlingen Halbleiterfabrik'):
            pair = [row for row in selected if row['title'] == title]
            self.assertEqual(len({row['domain'] for row in pair}), 2)
            self.assertTrue(all(row in originals for row in pair))



    def test_large_source_pool_keeps_correlated_german_news_pairs_adjacent(self):
        # Regression: old alphabetic domain rotation fed Groq only unrelated
        # single reports, so the strict independent-source gate rejected all.
        fillers = [record(f'publisher{i}.example',
                          f'Unrelated global headline {i}', i + 50)
                   for i in range(45)]
        pool = fillers + self.pool
        selected = hf._groq_source_records(pool)
        pair_titles = ('Mercedes investiert in Werk Stuttgart',
                       'Bosch eröffnet Reutlingen Halbleiterfabrik')
        for title in pair_titles:
            indexes = [i for i, row in enumerate(selected)
                       if row['title'] == title]
            self.assertEqual(len(indexes), 2, title)
            self.assertEqual(abs(indexes[0] - indexes[1]), 1, title)
            self.assertEqual(len({selected[i]['domain'] for i in indexes}), 2)
        serialized = [{'source_id': f'S{i+1:03d}', **{k: row.get(k) for k in
                       ('domain', 'title', 'context', 'seen_date', 'feed')}}
                      for i, row in enumerate(selected)]
        self.assertLessEqual(len(json.dumps(serialized, ensure_ascii=False)), 9000)

    def test_pair_pack_does_not_treat_same_company_different_events_as_confirmation(self):
        pool = [record('a.example', 'Mercedes investiert in Stuttgart Werk', 1),
                record('b.example', 'Mercedes schließt Stuttgart Werk', 2)]
        pool += [record(f'other{i}.example', f'Global unrelated update {i}', i + 30)
                 for i in range(20)]
        selected = hf._groq_source_records(pool)
        self.assertTrue(selected)
        # Mere proximity in the prompt never constitutes evidence.
        self.assertIn(
            'source_2_does_not_support_headline',
            hf.validate_pair({'title': pool[0]['title']}, [pool[0], pool[1]]))


if __name__ == "__main__":
    unittest.main()


def test_article_retry_inspects_other_distinct_leads(monkeypatch):
    pairs = [[record(f"paper-{n}-{side}.example", f"Report {n} {side}", 1) for side in ("a","b")]
             for n in range(8)]
    pool = [row for pair in pairs for row in pair]
    monkeypatch.setattr(hf, "_source_pair_score", lambda a,b: 2 if a["title"][:-1]==b["title"][:-1] else 0)
    monkeypatch.setattr(hf, "corroborated_headline", lambda a,b: None)
    monkeypatch.setattr(hf, "distinct_headlines", lambda a,b: a[:-1]!=b[:-1])
    monkeypatch.setattr(hf, "_research_retry_attempt", lambda:0)
    original = hf.article_research_records(pool)
    monkeypatch.setattr(hf, "_research_retry_attempt", lambda:1)
    second = hf.article_research_records(pool)
    assert len(original) == len(second) == 8
    assert {r["url"] for r in original}.isdisjoint(r["url"] for r in second)


def test_generic_viewer_payoff_is_repaired_only_with_source_evidence():
    import json
    from copy import deepcopy
    import tayvoriq_agent_trend_radar_v6 as radar
    request = json.loads((Path(__file__).resolve().parents[1] / "requests/telegram-3696-trend-1.json").read_text())
    ctx = request["source_context"]
    draft = {**ctx["retention_v5"], "title": request["topic"], "sources":[{**s,"source_id":str(i)} for i,s in enumerate(ctx["sources"])],
             "_retrieved_regional_assessment":{"passed":True}, "fallback_editorial_answers":{**ctx["fallback_editorial_answers"],
             "action_now":"Achte auf weitere Entwicklungen."}}
    # The editor cannot add an amount absent from the two original articles.
    draft["fallback_editorial_answers"]["why_happening"]="Weil die Arbeitskosten steigen, will der Konzern bei den Löhnen sparen."
    for action,accepted in [("Prüfe die nächste Runde im Dezember auf ein konkretes Ergebnis.",True),
                            ("Prüfe die Zahlung von 700 Euro für alle Beschäftigten.",False)]:
        candidate=deepcopy(draft)
        hf._repair_editorial_fields([candidate],lambda batch:{k:{**{key:candidate.get(key,"") for key in v["missing"]},
                                                                "action_now":action} for k,v in batch.items()})
        assert (candidate["fallback_editorial_answers"]["action_now"]==action) is accepted
        if accepted:
            assert radar._downstream_editorial_contract_valid(candidate["fallback_editorial_answers"])
