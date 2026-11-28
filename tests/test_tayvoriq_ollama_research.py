import io
import base64
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import tayvoriq_agent_research_resilience_v2 as resilience
import tayvoriq_contabo_research as transport
import tayvoriq_ollama_research as ollama


class ContaboWakeupTests(unittest.TestCase):
    binding = {'selection': '20261127-morning-agentv2-c12345678', 'slot': 'morning',
               'controller': '123', 'attempt': '1', 'origin': 'control_center',
               'revision': 'a' * 40, 'topic': ''}

    def test_wakeup_is_bound_private_contents_write_and_idempotent(self):
        written = {}
        def api(path, **kwargs):
            self.assertIn('/shorts-agent-studio/contents/.automation/contabo-research-wakeup.json', path)
            self.assertFalse(kwargs.get('public_write', False))
            if kwargs.get('body'):
                written.update(kwargs['body'])
                return {}
            return {'content': written['content'], 'sha': 'version'} if written else None
        with patch.object(transport, 'queue_current', return_value=True), patch.object(transport, 'api', side_effect=api) as call:
            transport.wake_worker(self.binding)
            self.assertEqual(json.loads(base64.b64decode(written['content'])),
                             {'binding': self.binding, 'wake_attempt': 1})
            transport.wake_worker(self.binding)
            self.assertEqual(sum('body' in c.kwargs for c in call.call_args_list), 1)
            transport.wake_worker(self.binding, 2)
            transport.wake_worker(self.binding, 1)
            self.assertEqual(sum('body' in c.kwargs for c in call.call_args_list), 2)
            self.assertEqual(json.loads(base64.b64decode(written['content']))['wake_attempt'], 2)

    def test_expired_or_replaced_queue_cannot_wake_or_claim_worker(self):
        for binding, expires in [(self.binding, 999), ({**self.binding, 'attempt': '2'}, 2000)]:
            response = {'content': base64.b64encode(json.dumps({'binding': binding, 'expires_at': expires}).encode()).decode()}
            with patch.object(transport.time, 'time', return_value=1000), patch.object(transport, 'api', return_value=response) as call:
                with self.assertRaisesRegex(RuntimeError, 'EXPIRED_OR_SUPERSEDED'):
                    transport.wake_worker(self.binding)
                with self.assertRaisesRegex(RuntimeError, 'EXPIRED_OR_SUPERSEDED'):
                    transport.write_receipt(self.binding, 99, 'RUNNING', Path('/unused'))
                self.assertFalse(any('body' in c.kwargs for c in call.call_args_list))

    def wait(self, receipt, seconds=100, wake_error=None, binding=None):
        now = [0]
        def pause(value):
            now[0] += value
        with patch.object(transport.time, 'monotonic', side_effect=lambda: now[0]), \
             patch.object(transport.time, 'time', side_effect=lambda: 1000 + now[0]), \
             patch.object(transport.time, 'sleep', side_effect=pause), \
             patch.object(transport, 'read_receipt', side_effect=lambda b: (receipt(now[0]), None)), \
             patch.object(transport, 'wake_worker', side_effect=wake_error) as wake, patch.object(transport, 'event') as events:
            result = transport.wait_for_result(binding or self.binding, seconds)
        return result, wake, events

    def test_denied_wakeup_preserves_existing_consumer_and_records_unconfirmed_attempt(self):
        succeeded = {'worker_run_id': 99, 'status': 'SUCCEEDED'}
        result, wake, events = self.wait(lambda now: succeeded if now >= 10 else None,
                                        wake_error=RuntimeError('CONTABO_RESEARCH_GITHUB: HTTP 403'))
        self.assertEqual(result, (succeeded, 0))
        wake.assert_called_once_with(self.binding, 1)
        failure = next(c for c in events.call_args_list if c.args[0] == 'contabo_worker_failure')
        self.assertIs(failure.kwargs['terminal'], False)
        attempt = next(c for c in events.call_args_list if c.args[0] == 'contabo_worker_wakeup')
        self.assertIs(attempt.kwargs['confirmed'], False)

    def test_same_queue_binding_preserves_original_expiry(self):
        previous = {'binding': self.binding, 'expires_at': 1010}
        response = {'content': base64.b64encode(json.dumps(previous).encode()).decode(), 'sha': 'version'}
        with patch.object(transport, 'api', return_value=response) as call:
            self.assertEqual(transport.enqueue(self.binding, 760), 1010)
            call.assert_called_once()

    def test_missing_worker_gets_one_same_binding_rewake_then_truthful_stop(self):
        result, wake, events = self.wait(lambda _: None)
        self.assertEqual(result, (None, transport.WORKER_START_TIMEOUT))
        self.assertEqual(wake.call_args_list, [unittest.mock.call(self.binding, 1), unittest.mock.call(self.binding, 2)])
        self.assertEqual(events.call_args_list[0].kwargs['next_check_epoch'], 1090)
        self.assertIsNone(events.call_args_list[1].kwargs['next_check_epoch'])
        self.assertEqual(events.call_args.kwargs['code'], 'WORKER_START_TIMEOUT')

    def test_running_or_completed_worker_never_restarts(self):
        running = {'worker_run_id': 99, 'status': 'RUNNING'}
        result, wake, events = self.wait(lambda _: running)
        self.assertEqual(result, (None, transport.WORKER_RESULT_TIMEOUT))
        wake.assert_not_called()
        self.assertEqual(events.call_args.kwargs['code'], 'WORKER_RESULT_TIMEOUT')
        succeeded = {**running, 'status': 'SUCCEEDED'}
        result, wake, events = self.wait(lambda now: succeeded if now >= 10 else None)
        self.assertEqual(result, (succeeded, 0))
        wake.assert_called_once_with(self.binding, 1)
        self.assertFalse(any(c.args[0] == 'contabo_worker_failure' for c in events.call_args_list))

    def test_all_entrypoints_report_denied_start_without_repeating_a_denied_write(self):
        for origin, slot, selection in [
            ('control_center', 'morning', '20261127-morning-agentv2-c12345678'),
            ('telegram_command', 'evening', '20261127-evening-agentv2-r1'),
            ('scheduled', 'morning', '20261127-morning-agentv2'),
            ('scheduled', 'evening', '20261127-evening-agentv2'),
            ('review', 'evening', 'review-evening-123'),
        ]:
            with self.subTest(origin=origin, slot=slot):
                binding = {**self.binding, 'origin': origin, 'slot': slot, 'selection': selection}
                result, wake, events = self.wait(lambda _: None, binding=binding,
                    wake_error=RuntimeError('CONTABO_RESEARCH_GITHUB: HTTP 403'))
                self.assertEqual(result, (None, transport.WAKEUP_ACCESS_DENIED))
                wake.assert_called_once_with(binding, 1)
                self.assertEqual(events.call_args_list[0].kwargs['cause'], 'ACCESS')
                self.assertIsNone(events.call_args_list[1].kwargs['next_check_epoch'])
                self.assertEqual(events.call_args.kwargs['code'], 'WORKER_START_TIMEOUT')

    def test_transient_wake_failure_still_gets_a_bounded_second_attempt(self):
        result, wake, _ = self.wait(lambda _: None, wake_error=RuntimeError('CONTABO_RESEARCH_GITHUB: HTTP 503'))
        self.assertEqual(result, (None, transport.WORKER_START_TIMEOUT))
        self.assertEqual(wake.call_count, 2)

    def test_push_selects_its_bound_lane_and_the_consumer_skips_cancelled_items(self):
        explicit = self.binding
        morning = {**explicit, 'origin': 'scheduled', 'selection': '20261127-morning-agentv2',
                   'controller': '124'}
        evening = {**morning, 'slot': 'evening', 'selection': '20261127-evening-agentv2',
                   'controller': '125'}
        queues = {'explicit': explicit, 'morning': morning, 'evening': evening}
        revision = 'b' * 40
        with TemporaryDirectory() as directory, patch.object(transport.time, 'time', return_value=1000), \
                patch.object(transport, 'read_receipt', return_value=(None, None)), \
                patch.object(transport, 'queue_current', side_effect=lambda binding: binding != explicit):
            root = Path(directory)
            queue = root / transport.QUEUE
            queue.mkdir(parents=True)
            for lane, binding in queues.items():
                (queue / f'{lane}.json').write_text(json.dumps({'binding': binding, 'expires_at': 1100}))
            self.assertEqual(transport.resolve_queue(root)['binding'], morning)
            wake = {'content': base64.b64encode(json.dumps({'binding': evening}).encode()).decode()}
            with patch.object(transport, 'api', return_value=wake) as api:
                self.assertEqual(transport.resolve_queue(root, wake_revision=revision)['binding'], evening)
                api.assert_called_once_with(f'repos/{transport.STUDIO}/contents/{transport.WAKEUP}?ref={revision}',
                                            missing=True)
            cancelled_wake = {'content': base64.b64encode(json.dumps({'binding': explicit}).encode()).decode()}
            with patch.object(transport, 'api', return_value=cancelled_wake):
                self.assertEqual(transport.resolve_queue(root, wake_revision=revision)['binding'], morning)


class OllamaResearchTests(unittest.TestCase):
    def test_verified_worker_failure_preserves_the_actual_model_timeout(self):
        timeout = {'event': 'provider_attempt_failed', 'provider': 'ollama', 'error': 'Model timeout'}
        preflight = {'event': 'source_headline_preflight', 'corroborated_headlines': 2}
        editorial = {'event': 'candidate_editorial_rejection'}
        self.assertEqual(transport.worker_failure_code([preflight, timeout, timeout]), transport.OLLAMA_MODEL_TIMEOUT)
        self.assertEqual(transport.worker_failure_code([preflight, timeout, editorial]), 65)
        self.assertEqual(transport.worker_failure_code([preflight]), 1)

    def test_scheduled_slots_and_review_do_not_replace_queued_explicit_search(self):
        with patch.object(transport, 'api', return_value=None) as api, patch.object(transport.time, 'time', return_value=1000):
            for origin, slot, lane in [('scheduled', 'morning', 'morning'), ('scheduled', 'evening', 'evening'),
                                       ('review', 'morning', 'review'), ('telegram_command', 'evening', 'explicit')]:
                binding = {'origin': origin, 'slot': slot, 'controller': '123'}
                transport.enqueue(binding, wait_seconds=420)
                path = api.call_args.args[0]
                payload = api.call_args.kwargs['body']
                self.assertTrue(path.endswith(f'/{lane}.json'))
                self.assertEqual(json.loads(base64.b64decode(payload['content'])),
                                 {'binding': binding, 'expires_at': 1430})

    def test_receipt_uses_exact_selection_controller_and_attempt(self):
        binding = {'selection': '20261126-evening-agentv2', 'controller': '123', 'attempt': '2'}
        row = {'binding': binding, 'worker_run_id': 99, 'status': 'RUNNING'}
        response = {'content': base64.b64encode(json.dumps(row).encode()).decode(), 'sha': 'version'}
        with patch.object(transport, 'api', return_value=response) as call:
            self.assertEqual(transport.read_receipt(binding), (row, 'version'))
        self.assertTrue(call.call_args.args[0].endswith('20261126-evening-agentv2-123.2.json?ref=main'))

    def test_completion_uses_the_installed_model_over_loopback(self):
        chunks = [{'model': ollama.COMPACT_MODEL, 'done': False, 'message': {'content': '{"candidates":'}},
                  {'model': ollama.COMPACT_MODEL, 'done': True, 'message': {'content': '[]}'}}]
        opener = Mock()
        opener.open.return_value = io.BytesIO('\n'.join(json.dumps(chunk) for chunk in chunks).encode())
        result = ollama.complete({'messages': [{'role': 'user', 'content': 'test'}]}, opener=opener)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(json.loads(req.data)['model'], ollama.COMPACT_MODEL)
        self.assertEqual(json.loads(req.data)['keep_alive'], '4m')
        self.assertIs(json.loads(req.data)['stream'], True)
        self.assertEqual(result['choices'][0]['message']['content'], '{"candidates":[]}')

    def test_local_mode_never_calls_cloud_providers_even_with_configured_credentials(self):
        source = {'url': 'https://example.invalid/news'}
        with patch.dict(os.environ, {'TAYVORIQ_LOCAL_RESEARCH': 'true', 'HF_TOKEN': 'fixture'}), \
                patch.object(resilience.rss, 'source_pool', return_value=[source]), \
                patch.object(resilience.hf, 'structure', side_effect=ConnectionRefusedError) as local, \
                patch.object(resilience.http, 'gemini_grounded') as cloud:
            with self.assertRaises(ConnectionRefusedError):
                resilience.grounded('test', 'fixture', 'fixture')
        local.assert_called_once_with('test', '', [source], 'multi-publisher-rss', provider_kind='ollama')
        cloud.assert_not_called()

    def test_truncated_ollama_stream_never_reaches_quality_gates(self):
        opener = Mock()
        fragment = {'model': ollama.COMPACT_MODEL, 'done': False, 'message': {'content': '{"candidates":[]}'}}
        opener.open.return_value = io.BytesIO(json.dumps(fragment).encode())
        with self.assertRaisesRegex(RuntimeError, 'RESPONSE_INCOMPLETE'):
            ollama.complete({'messages': []}, opener=opener)

    def test_optional_model_repairs_reserve_time_for_validation(self):
        with patch.object(ollama.time, 'time', return_value=1000):
            with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_DEADLINE_EPOCH': '1029'}):
                self.assertEqual(ollama.repair_budget(), 0)
            with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_DEADLINE_EPOCH': '1055'}):
                self.assertEqual(ollama.repair_budget(), 35)

    def test_candidate_budget_preserves_time_for_other_pairs_and_validation(self):
        with patch.object(ollama.time, 'time', return_value=1000):
            with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_DEADLINE_EPOCH': '1410'}):
                self.assertEqual(ollama.candidate_budget(2), 195)
                self.assertEqual(ollama.candidate_budget(1), 210)
            with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_DEADLINE_EPOCH': '1030'}):
                self.assertEqual(ollama.candidate_budget(2), 5)
            with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_DEADLINE_EPOCH': '1010'}):
                helper = Mock()
                with self.assertRaises(TimeoutError):
                    ollama.complete({'messages': []}, opener=helper, time_limit=ollama.candidate_budget(1))
                helper.open.assert_not_called()

    def test_verification_model_stays_on_loopback_and_checks_response_identity(self):
        opener = Mock()
        wrong_model = {'model': ollama.MODEL, 'done': True, 'message': {'content': '{"candidates":[]}'}}
        opener.open.return_value = io.BytesIO(json.dumps(wrong_model).encode())
        with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_MODEL': ollama.COMPACT_MODEL}):
            with self.assertRaisesRegex(RuntimeError, 'RESPONSE_INVALID'):
                ollama.complete({'messages': []}, opener=opener)
        self.assertEqual(json.loads(opener.open.call_args.args[0].data)['model'], ollama.COMPACT_MODEL)

    def test_wire_schema_requires_one_decision_per_pair_and_one_literal_scope(self):
        example = '''{"candidates":[{"source_pair_id":"<listed source_pair_id>",
            "trend_scope":"technology_ai|business_economy","regional_relevance":"local|germany",
            "viral_potential":<integer 0-100>,"regional_scorecard":{"evidence":{"<source>":"<claim>"},
            "ratings":{"consequence":[<YouTube integer 0-5>,<TikTok integer 0-5>,"reason"]}}}]}'''
        pairs = [('S001', 'S002'), ('S003', 'S004')]
        schema = ollama.research_format(example, pairs, {'business_economy', 'mobility_energy', 'auto_scope'})
        self.assertEqual(schema['required'], ['S001+S002', 'S003+S004'])
        fields = schema['properties']['S001+S002']['anyOf'][0]['properties']
        self.assertEqual(fields['trend_scope']['enum'], ['business_economy', 'mobility_energy'])
        self.assertEqual(fields['regional_scorecard']['properties']['evidence']['required'], ['S001', 'S002'])
        rating = fields['regional_scorecard']['properties']['ratings']['properties']['consequence']
        self.assertEqual(rating['required'], ['y', 't', 'why'])
        self.assertEqual(rating['properties']['t']['maximum'], 5)
        with self.assertRaisesRegex(RuntimeError, 'PAIR_DECISIONS_INCOMPLETE'):
            ollama.read_candidates({'S001+S002': None}, pairs)
        row = {'trend_scope': 'business_economy'}
        self.assertEqual(ollama.read_candidates({'S001+S002': row, 'S003+S004': None}, pairs),
                         {'candidates': [{**row, 'source_pair_id': 'S001+S002'}]})
        compact = ollama.research_format(example, pairs, {'business_economy'}, compact=True)
        short_shape = compact['properties']['S001+S002']['anyOf'][0]
        self.assertEqual(set(short_shape['required']), {'scope', 'region', 'viral', 'card'})
        self.assertEqual(short_shape['properties']['card'], fields['regional_scorecard'])
        self.assertEqual(ollama.read_candidates({'S001+S002': {'scope': 'business_economy'}, 'S003+S004': None},
                                               pairs, compact=True),
                         {'candidates': [{**row, 'source_pair_id': 'S001+S002'}]})

    def test_local_platform_scores_are_mapped_to_the_existing_rubric_contract(self):
        reason = 'Zwei Streiktage betreffen die Zustellung.'
        row = {'regional_scorecard': {'ratings': {'consequence': {'y': 4, 't': 3, 'why': reason}}}}
        result = ollama.read_candidates({'S001+S002': row}, [('S001', 'S002')])
        self.assertEqual(result['candidates'][0]['regional_scorecard']['ratings']['consequence'], [4, 3, reason])

    def test_result_rejects_a_different_attempt_or_provider(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            binding = {'attempt': '2'}
            (root / 'receipt.json').write_text(json.dumps({'binding': binding, 'worker_run_id': 12}))
            with self.assertRaisesRegex(RuntimeError, 'BINDING_MISMATCH'):
                transport.check_result(root, {'attempt': '1'}, 12)
            (root / 'audit.json').write_text(json.dumps({'provider': 'ollama_rss+gemini', 'quality_gates_weakened': False}))
            with self.assertRaisesRegex(RuntimeError, 'PROVIDER_UNVERIFIED'):
                transport.check_result(root, binding, 12)
