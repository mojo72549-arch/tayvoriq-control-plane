import json
import sys
import subprocess
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
            variant = dict(text_package=dict(scenes=[dict(spoken_chunk='Test')]),
                           render=dict(final_duration_seconds=25, asset_report=[dict(scene=1, duration=25, subtitle_present=True)]))
            job = dict(job_id='fixture', github_run_id='42', variants={p: variant for p in bundle.PLATFORMS})
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

    def test_scene_and_caption_faults_identify_the_affected_variant(self):
        scene = dict(scene=1, duration=25, subtitle_present=True)
        for actual, reason in (([], 'COUNT'), ([{**scene, 'scene': 2}], 'SEQUENCE'),
                               ([{**scene, 'duration': 0}], 'DURATION'),
                               ([{**scene, 'duration': 22}], 'TIMELINE'),
                               ([{**scene, 'subtitle_present': False}], 'CAPTION')):
            v = dict(text_package=dict(scenes=[dict(spoken_chunk='Test')]),
                     render=dict(final_duration_seconds=25, asset_report=actual))
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                bundle.verify_scene_coverage(v, 'tiktok')

    def test_uploaded_revision_must_contain_every_file_and_match_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pub = root / 'runs/42'
            pub.mkdir(parents=True)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL, text=True).strip()
            git('init', '-q')
            for name in bundle.FILES:
                (pub/name).write_text(name)
            git('add', 'runs')
            git('reset', 'runs/42/index.html')
            def commit():
                git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
            commit()
            with self.assertRaisesRegex(ValueError, 'UNTRACKED'):
                bundle.committed_revision(root, 'runs/42', 'HEAD')
            git('add', 'runs')
            commit()
            self.assertEqual(bundle.committed_revision(root, 'runs/42', 'HEAD'), git('rev-parse', 'HEAD'))
            (pub/'short_youtube.mp4').write_text('other')
            with self.assertRaises(subprocess.CalledProcessError):
                bundle.committed_revision(root, 'runs/42', 'HEAD')
