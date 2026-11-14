import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_artifact_approval import FILES, verify_package


class ArtifactApprovalTest(unittest.TestCase):
    def test_only_the_exact_approved_pair_can_be_published(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in FILES:
                (root / name).write_bytes(b'fixture')
            (root / 'job.json').write_text(json.dumps({'github_run_id': '100', 'render_status': 'DONE',
                                                       'quality_report': {'passed': True}}))
            (root / 'publication_quality_gate.json').write_text(json.dumps(
                {'passed': True, 'quality_gates_weakened': False, 'targets': ['youtube_shorts', 'tiktok']}))
            hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in FILES}
            decision = dict(schema='tayvoriq-artifact-approval', review_id='100', state='APPROVED',
                            decided_via='telegram_callback', decision_id='approved-callback',
                            telegram_message_id=120, studio_sha='a'*40, files_sha256=hashes)
            verify_package(root, decision, '100')
            for status in ('PENDING', 'REJECTED'):
                with self.assertRaisesRegex(ValueError, 'TELEGRAM_BOUND_APPROVAL_REQUIRED'):
                    verify_package(root, {**decision, 'state': status}, '100')
            (root / 'short_tiktok.mp4').write_bytes(b'exchanged video')
            with self.assertRaisesRegex(ValueError, 'APPROVED_REVIEW_FILE_CHANGED'):
                verify_package(root, decision, '100')
