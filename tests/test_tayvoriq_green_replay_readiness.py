import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class GreenReplayReadinessTests(unittest.TestCase):
    def test_live_workflow_accepts_verified_green_from_durable_binding_truth(self):
        workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/tayvoriq-deliver-video-now.yml').read_text()
        section = workflow.split('# A verified Production Green implementation revision', 1)[1]
        program = textwrap.dedent(section.split("<<'PY'\n", 1)[1].split('\n          PY', 1)[0])
        codefix = {
            'status': 'REPLAY_DISPATCHED',
            'request_substate': 'DISPATCHED',
            'failed_implementation_sha': 'a' * 40,
            'replay_implementation_sha': 'b' * 40,
            'replay_control_plane_sha': 'c' * 40,
            'replay_run_id': 42,
            'recovery_generation': 1,
            'same_generation_replay_required': True,
            'exact_source_request_required': True,
            'active_pointer_verified': True,
            'quality_gates_weakened': False,
        }
        request = {
            'request_id': 'exact',
            'status': 'DISPATCHED',
            'golden_path_run_id': 42,
            'recovery_generation': 1,
            'source_context_sha256': 'source-sha',
            'codefix_recovery': codefix,
        }
        manifest = {
            'implementation_sha': 'b' * 40,
            'control_plane_sha': 'd' * 40,
            'source_request_id': 'exact',
            'source_context_sha256': 'source-sha',
            'run_id': 42,
            'implementation_binding': 'production-green-immutable-sha',
            'autocodefix_overlay_applied': False,
            'lightweight_preflight_passed': True,
            'quality_gates_weakened': False,
        }
        green = {
            'implementation_sha': 'b' * 40,
            'full_preflight_passed': True,
            'quality_gates_weakened': False,
        }
        active = {
            'state': 'ACTIVE',
            'request_id': 'exact',
            'golden_path_run_id': 42,
            'recovery_generation': 1,
            'source_context_sha256': 'source-sha',
        }

        cases = [
            ({'codefix_detection_reason': reason}, {}, {}, {}, True)
            for reason in (
                'production-green-implementation-changed',
                'production-green-advanced-during-local-checkpoint-retry',
            )
        ]
        cases.extend([
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {'run_id': 43}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {'source_request_id': 'other'}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {'implementation_sha': 'e' * 40}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {'autocodefix_overlay_applied': True}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {'lightweight_preflight_passed': False}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {'quality_gates_weakened': True}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {}, {'implementation_sha': 'e' * 40}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {}, {'full_preflight_passed': False}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {}, {}, {'golden_path_run_id': 41}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed'}, {}, {}, {'source_context_sha256': 'other'}, False),
            ({'codefix_detection_reason': 'unverified-retry'}, {}, {}, {}, False),
            ({'codefix_detection_reason': 'production-green-implementation-changed', 'failed_implementation_sha': 'b' * 40}, {}, {}, {}, False),
        ])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for request_change, manifest_change, green_change, active_change, passed in cases:
                with self.subTest(
                    request_change=request_change,
                    manifest_change=manifest_change,
                    green_change=green_change,
                    active_change=active_change,
                ):
                    request_payload = dict(request)
                    request_payload['codefix_recovery'] = {**codefix, **request_change}
                    (root / 'request.json').write_text(json.dumps(request_payload))
                    (root / 'manifest.json').write_text(json.dumps({**manifest, **manifest_change}))
                    (root / 'green.json').write_text(json.dumps({**green, **green_change}))
                    (root / 'active.json').write_text(json.dumps({**active, **active_change}))
                    run = subprocess.run(
                        [
                            sys.executable,
                            '-c',
                            program,
                            'request.json',
                            'manifest.json',
                            'green.json',
                            'active.json',
                        ],
                        cwd=root,
                        capture_output=True,
                        text=True,
                    )
                    self.assertEqual(run.returncode == 0, passed, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
