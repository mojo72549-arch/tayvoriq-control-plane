import copy
import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import tayvoriq_agent_hf_v2 as hf
import tayvoriq_agent_research_resilience_v2 as resilience


class LocalArticleResearchTests(unittest.TestCase):
    def records(self, *, expanded=False):
        records = []
        for story, lead in [('bosch', 'Bosch eröffnet Halbleiterfabrik in Reutlingen'),
                            ('mercedes', 'Mercedes investiert in Werk in Stuttgart')]:
            for publisher, ending, context in [
                ('a', 'und stärkt Entwicklung', 'Der Unternehmensbericht liegt vor.'),
                ('b', 'und erweitert Fertigung', 'Die Redaktion berichtet vom Standort.')
            ]:
                records.append({'url': f'https://{publisher}.example/{story}',
                    'domain': f'{publisher}.example', 'title': lead + ' ' + ending,
                    'context': context, 'seen_date': 'Fri, 27 Nov 2026 15:00:00 +0000',
                    'feed': f'{publisher}-wirtschaft', 'origin': f'Redaktion {publisher}'})
        records.extend({'url': f'https://noise.example/{index}', 'domain': 'noise.example',
                        'title': f'Hintergrund {index}', 'context': 'Ein anderer Bericht.',
                        'seen_date': 'Fri, 27 Nov 2026 14:00:00 +0000', 'origin': 'Redaktion c'}
                       for index in range(4))
        return records

    def test_article_context_updates_existing_urls_before_ranking_and_retains_provenance(self):
        original = self.records()
        snapshot = copy.deepcopy(original)
        calls = []
        leads = {'bosch': 'Bosch eröffnet Halbleiterfabrik in Reutlingen.',
                 'mercedes': 'Mercedes investiert in Werk in Stuttgart.'}

        def enrich(records):
            self.assertLessEqual(len(records), 8)
            return [{**record, 'context': record['context'] + ' ' + leads[record['url'].rsplit('/', 1)[1]]}
                    for record in records]

        def structure(prompt, token, records, label, *, provider_kind):
            calls.append((label, copy.deepcopy(records)))
            self.assertEqual(provider_kind, 'ollama')
            self.assertEqual(token, '')
            pairs = []
            for story in leads:
                pair = [record for record in records if record['url'].endswith('/' + story)]
                headline = hf.corroborated_headline(*pair)
                if headline:
                    self.assertEqual(hf.validate_pair({'title': headline}, pair), [])
                    pairs.append(headline)
            if len(pairs) != 2:
                raise hf.InsufficientFeedEvidence('Original feed snippets do not jointly support the headlines')
            return {'candidates': [{'title': title} for title in pairs]}, [], 'local-test-model'

        with patch.object(resilience.rss, 'source_pool', return_value=original), \
             patch.object(resilience.rss, 'enrich_evidence', side_effect=enrich) as enrichment, \
             patch.object(resilience.gdelt, 'source_pool') as gdelt, \
             patch.object(hf, 'structure', side_effect=structure):
            result = resilience.local_grounded('editorial')

        self.assertEqual([label for label, _ in calls], ['multi-publisher-rss', 'rss-article-context'])
        self.assertEqual(len(result[0]['candidates']), 2)
        self.assertEqual(result[-1], 'ollama_rss')
        self.assertEqual(original, snapshot)
        enrichment.assert_called_once()
        gdelt.assert_not_called()
        self.assertEqual(len(calls[-1][1]), len(original))
        updated = {record['url']: record for record in calls[-1][1]}
        for before in original:
            after = updated[before['url']]
            self.assertEqual({key: value for key, value in before.items() if key != 'context'},
                             {key: value for key, value in after.items() if key != 'context'})

    def test_missing_article_context_still_fails_without_model_or_duplicate_ranking(self):
        with patch.object(resilience.rss, 'source_pool', side_effect=self.records), \
             patch.object(resilience.rss, 'enrich_evidence', side_effect=lambda records: records), \
             patch.object(resilience.gdelt, 'source_pool', return_value=[]), \
             patch.object(hf, 'structure', wraps=hf.structure) as structure, \
             patch.object(hf.local, 'complete') as model:
            with self.assertRaisesRegex(RuntimeError, 'OLLAMA_SOURCE_MINIMUM_NOT_MET'):
                resilience.local_grounded('editorial')
        structure.assert_called_once()
        model.assert_not_called()

    def test_unrelated_original_article_context_does_not_bypass_real_source_gates(self):
        def enrich(records):
            return [{**record, 'context': record['context'] + ' Ein Museum zeigt eine Kunstausstellung.'}
                    for record in records]
        with patch.object(resilience.rss, 'source_pool', side_effect=self.records), \
             patch.object(resilience.rss, 'enrich_evidence', side_effect=enrich), \
             patch.object(resilience.gdelt, 'source_pool', return_value=[]), \
             patch.object(hf, 'structure', wraps=hf.structure) as structure, \
             patch.object(hf.local, 'complete') as model:
            with self.assertRaisesRegex(RuntimeError, 'OLLAMA_SOURCE_MINIMUM_NOT_MET'):
                resilience.local_grounded('editorial')
        self.assertEqual([call.args[3] for call in structure.call_args_list],
                         ['multi-publisher-rss', 'rss-article-context'])
        model.assert_not_called()

    def test_confirmed_rss_result_avoids_unnecessary_article_and_gdelt_requests(self):
        with patch.object(resilience.rss, 'source_pool', side_effect=self.records), \
             patch.object(hf, 'structure', return_value=({'candidates': []}, [], 'fixture')), \
             patch.object(resilience.rss, 'enrich_evidence') as enrichment, \
             patch.object(resilience.gdelt, 'source_pool') as gdelt:
            self.assertEqual(resilience.local_grounded('editorial')[-1], 'ollama_rss')
        enrichment.assert_not_called()
        gdelt.assert_not_called()

    def test_gdelt_context_search_uses_native_german_language_and_reports_non_json(self):
        article = {'title': 'Neue Tarifrunde in Stuttgart', 'url': 'https://example.org/tarif',
                   'language': 'German', 'snippet': 'Die Tarifrunde beginnt am Donnerstag.'}

        def response(request, *, timeout):
            params = parse_qs(urlsplit(request.full_url).query)
            self.assertEqual(params['searchlang'], ['german'])
            self.assertNotIn('sourcelang:', params['query'][0])
            self.assertEqual(params['format'], ['json'])
            reply = MagicMock()
            reply.__enter__.return_value = reply
            reply.status = 200
            reply.headers = Message()
            if 'Stuttgart' in params['query'][0]:
                self.assertIn('"Baden-Württemberg"', params['query'][0])
                reply.read.return_value = json.dumps({'articles': [article]}).encode()
            else:
                reply.headers['Content-Type'] = 'text/html; charset=utf-8'
                reply.read.return_value = b'<html>provider error details</html>'
            return reply

        with patch.object(resilience.gdelt.urllib.request, 'urlopen', side_effect=response) as request, \
             patch('builtins.print') as log:
            records = resilience.gdelt.source_pool()

        self.assertEqual(request.call_count, 4)
        self.assertEqual([(row['url'], row['context']) for row in records],
                         [(article['url'], article['snippet'])])
        events = [json.loads(call.args[0]) for call in log.call_args_list]
        failed = [row for row in events if row['event'] == 'gdelt_query_failed']
        self.assertEqual(len(failed), 3)
        for row in failed:
            self.assertEqual((row['error'], row['status'], row['content_type']),
                             ('NON_JSON_RESPONSE', 200, 'text/html'))
        self.assertNotIn('provider error details', str(events))


if __name__ == '__main__':
    unittest.main()
