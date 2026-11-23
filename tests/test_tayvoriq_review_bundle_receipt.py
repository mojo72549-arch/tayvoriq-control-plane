import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import tayvoriq_review_bundle_receipt as bundle


class ReviewBundleTests(unittest.TestCase):
    def test_final_gate_and_actual_platform_files_must_match_review(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job_dir, staged = root / 'job', root / 'site'
            job = dict(job_id='fixture', github_run_id='42', variants={p: {} for p in bundle.PLATFORMS})
            gate = dict(job_id='fixture', passed=True, targets=list(bundle.PLATFORMS), quality_gates_weakened=False)
            for directory in (job_dir, staged):
                directory.mkdir()
                for name in bundle.FILES:
                    (directory / name).write_text(name)
                (directory / 'job.json').write_text(json.dumps(job))
                (directory / 'publication_quality_gate.json').write_text(json.dumps(gate))
            self.assertEqual(set(bundle.verify(job_dir, staged, '42')), bundle.FILES)
            with self.assertRaisesRegex(ValueError, 'JOB_OR_GATE'):
                bundle.verify(job_dir, staged, '41')
            gate_file = staged / 'publication_quality_gate.json'
            original = gate_file.read_bytes()
            gate_file.write_text('{}')
            with self.assertRaisesRegex(ValueError, 'GATE_DIFFERS'):
                bundle.verify(job_dir, staged, '42')
            gate_file.write_bytes(original)
            (staged / 'short_tiktok.mp4').write_bytes(b'stale')
            with self.assertRaisesRegex(ValueError, 'DIFFERS_FROM_QA:tiktok'):
                bundle.verify(job_dir, staged, '42')
            (staged / 'short_tiktok.mp4').unlink()
            with self.assertRaisesRegex(ValueError, 'FILE_MISSING'):
                bundle.verify(job_dir, staged, '42')
