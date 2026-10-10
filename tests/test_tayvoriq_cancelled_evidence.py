import os
import subprocess
import tempfile
import unittest
from pathlib import Path


class CancelledEvidenceTests(unittest.TestCase):
    def test_real_capture_step_handles_empty_failed_logs(self):
        source = (Path(__file__).resolve().parents[1] / '.github/workflows/tayvoriq-delivery-watch.yml').read_text()
        block = source.split('      - name: Capture failed-run evidence', 1)[1].split('      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in block.split('        run: |\n', 1)[1].splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gh = root / 'gh'
            gh.write_text('#!/bin/bash\nif [[ "$*" == *--log-failed* ]]; then exit 0; fi\nif [[ "$*" == *--log* ]]; then echo REAL_CANCELLED_RUN_LOG; exit 0; fi\nexit 1\n')
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'RUN_ID': '123', 'RUN_ATTEMPT': '1', 'REQUEST_ID': 'telegram-123-trend-1'}
            result = subprocess.run(['bash', '-c', script.replace('/tmp/', tmp + '/')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('REAL_CANCELLED_RUN_LOG', (root / 'tayvoriq-failed.log').read_text())
            gh.write_text('#!/bin/bash\nexit 0\n')
            result = subprocess.run(['bash', '-c', script.replace('/tmp/', tmp + '/')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('DELIVERY_WATCH_FAILED_LOG_MISSING', result.stdout)

    def test_real_capture_recovers_legacy_contract_for_the_exact_attempt(self):
        import json
        source = (Path(__file__).resolve().parents[1] / '.github/workflows/tayvoriq-delivery-watch.yml').read_text()
        block = source.split('      - name: Capture failed-run evidence', 1)[1].split('      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in block.split('        run: |\n', 1)[1].splitlines())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = dict(schema='tayvoriq-failure-contract-v2', state='PUBLISHABLE_OUTPUT_RETRY_REQUIRED',
                           repair_target_stages=['RENDER'], quality_gates_weakened=False)
            log = root / 'producer.log'
            log.write_text('RuntimeError: CONTENT_REJECTED:verified-editorial-postcondition-drift:fields=action_now:body_words=46\n' + repr(payload))
            gh = root / 'gh'
            gh.write_text('#!/bin/bash\nif [[ "$*" == *"--attempt 3 --log"* ]]; then cat "' + str(log) + '"; exit 0; fi\nexit 1\n')
            gh.chmod(0o755)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'RUN_ID': '123', 'RUN_ATTEMPT': '3', 'REQUEST_ID': 'telegram-123-trend-1'}
            result = subprocess.run(['bash', '-c', script.replace('/tmp/', tmp + '/')], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            proof = json.loads((root / 'tayvoriq-structured-failure.json').read_text())
            self.assertEqual(proof['state'], 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED')
            self.assertEqual((proof['run_id'], proof['run_attempt'], proof['request_id']),
                             (123, 3, 'telegram-123-trend-1'))
            self.assertFalse(proof['quality_gates_weakened'])


if __name__ == '__main__':
    unittest.main()

