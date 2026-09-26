import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class GreenReplayReadinessTests(unittest.TestCase):
    def test_live_workflow_accepts_both_verified_reasons_and_rejects_bad_bindings(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/tayvoriq-deliver-video-now.yml').read_text()
        section = workflow.split('# A verified Production Green implementation revision', 1)[1]
        program = textwrap.dedent(section.split("<<'PY'\n", 1)[1].split('\n          PY', 1)[0])
        codefix = {'status': 'REPLAY_DISPATCHED', 'request_substate': 'DISPATCHED',
                   'failed_implementation_sha': 'a' * 40, 'replay_implementation_sha': 'b' * 40,
                   'replay_control_plane_sha': 'c' * 40, 'replay_run_id': 42}
        manifest = {'implementation_sha': 'b' * 40, 'control_plane_sha': 'c' * 40,
                    'source_request_id': 'exact', 'run_id': 42,
                    'implementation_binding': 'production-green-immutable-sha',
                    'autocodefix_overlay_applied': False, 'lightweight_preflight_passed': True,
                    'quality_gates_weakened': False}
        cases = [({'codefix_detection_reason': reason}, {}, True) for reason in (
            'production-green-implementation-changed', 'production-green-advanced-during-local-checkpoint-retry')]
        for change in ({'run_id': 43}, {'source_request_id': 'other'}, {'implementation_sha': 'd' * 40},
                       {'autocodefix_overlay_applied': True}, {'lightweight_preflight_passed': False},
                       {'quality_gates_weakened': True}):
            cases.append(({'codefix_detection_reason': 'production-green-advanced-during-local-checkpoint-retry'}, change, False))
        cases.extend([({'codefix_detection_reason': 'unverified-retry'}, {}, False),
                      ({'codefix_detection_reason': 'production-green-implementation-changed', 'failed_implementation_sha': 'b' * 40}, {}, False)])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for request_change, manifest_change, passed in cases:
                with self.subTest(request_change=request_change, manifest_change=manifest_change):
                    (root / 'request.json').write_text(json.dumps({'request_id': 'exact', 'codefix_recovery': {**codefix, **request_change}}))
                    (root / 'manifest.json').write_text(json.dumps({**manifest, **manifest_change}))
                    run = subprocess.run([sys.executable, '-c', program, 'request.json', 'manifest.json'], cwd=root, capture_output=True, text=True)
                    self.assertEqual(run.returncode == 0, passed, run.stderr)


if __name__ == '__main__':
    unittest.main()
