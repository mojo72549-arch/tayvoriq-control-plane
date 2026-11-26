import io
import base64
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

import tayvoriq_agent_research_resilience_v2 as resilience
import tayvoriq_contabo_research as transport
import tayvoriq_ollama_research as ollama


class OllamaResearchTests(unittest.TestCase):
    def test_receipt_uses_exact_selection_controller_and_attempt(self):
        binding = {'selection': '20261126-evening-agentv2', 'controller': '123', 'attempt': '2'}
        row = {'binding': binding, 'worker_run_id': 99, 'status': 'RUNNING'}
        response = {'content': base64.b64encode(json.dumps(row).encode()).decode(), 'sha': 'version'}
        with patch.object(transport, 'api', return_value=response) as call:
            self.assertEqual(transport.read_receipt(binding), (row, 'version'))
        self.assertTrue(call.call_args.args[0].endswith('20261126-evening-agentv2-123.2.json?ref=main'))

    def test_completion_uses_the_installed_model_over_loopback(self):
        chunks = [{'model': ollama.MODEL, 'done': False, 'message': {'content': '{"candidates":'}},
                  {'model': ollama.MODEL, 'done': True, 'message': {'content': '[]}'}}]
        opener = Mock()
        opener.open.return_value = io.BytesIO('\n'.join(json.dumps(chunk) for chunk in chunks).encode())
        result = ollama.complete({'messages': [{'role': 'user', 'content': 'test'}]}, opener=opener)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(json.loads(req.data)['model'], ollama.MODEL)
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
        fragment = {'model': ollama.MODEL, 'done': False, 'message': {'content': '{"candidates":[]}'}}
        opener.open.return_value = io.BytesIO(json.dumps(fragment).encode())
        with self.assertRaisesRegex(RuntimeError, 'RESPONSE_INCOMPLETE'):
            ollama.complete({'messages': []}, opener=opener)

    def test_verification_model_stays_on_loopback_and_checks_response_identity(self):
        opener = Mock()
        wrong_model = {'model': ollama.MODEL, 'done': True, 'message': {'content': '{"candidates":[]}'}}
        opener.open.return_value = io.BytesIO(json.dumps(wrong_model).encode())
        with patch.dict(os.environ, {'TAYVORIQ_RESEARCH_MODEL': ollama.COMPACT_MODEL}):
            with self.assertRaisesRegex(RuntimeError, 'RESPONSE_INVALID'):
                ollama.complete({'messages': []}, opener=opener)
        self.assertEqual(json.loads(opener.open.call_args.args[0].data)['model'], ollama.COMPACT_MODEL)

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
