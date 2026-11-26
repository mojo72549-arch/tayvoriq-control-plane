import io
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
    def test_completion_uses_the_installed_model_over_loopback(self):
        response = {'model': ollama.MODEL, 'done': True, 'message': {'content': '{"candidates":[]}'}}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(response).encode())
        result = ollama.complete({'messages': [{'role': 'user', 'content': 'test'}]}, opener=opener)
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'http://127.0.0.1:11434/api/chat')
        self.assertEqual(json.loads(req.data)['model'], ollama.MODEL)
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
