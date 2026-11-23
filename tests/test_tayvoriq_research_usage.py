import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_research_usage import post


class ResearchUsageTests(unittest.TestCase):
    def test_counts_success_and_failure_once_and_keeps_prompts_and_keys_out(self):
        request = Request("https://example.invalid/", data=b"privateprompt", headers={"Authorization": "secret"})
        response = MagicMock(status=200, headers={})
        response.__enter__.return_value = response
        response.read.return_value = b'{"usageMetadata":{"promptTokenCount":3,"totalTokenCount":8}}'
        denied = HTTPError(request.full_url, 429, "privateprompt", {}, None)
        output = io.StringIO()
        with redirect_stdout(output), patch("urllib.request.urlopen", side_effect=[response, denied]):
            raw, _ = post(request, 10, "gemini", "fixture")
            self.assertIn("usageMetadata", raw)
            with self.assertRaises(HTTPError):
                post(request, 10, "gemini", "fixture")
        good, failed = map(json.loads, output.getvalue().splitlines())
        self.assertEqual((good["status"], good["input_tokens"], good["total_tokens"]), (200, 3, 8))
        self.assertIsNone(good["output_tokens"])
        self.assertEqual(failed["status"], 429)
        self.assertIsNone(failed["total_tokens"])
        self.assertNotIn("secret", output.getvalue())
        self.assertNotIn("privateprompt", output.getvalue())
