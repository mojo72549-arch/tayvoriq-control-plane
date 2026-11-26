import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))

from tayvoriq_artifact_approval import FILES
from tayvoriq_contabo_review_binding import pending
from tayvoriq_restore_contabo_review import restore


class TestRestoreContaboReview(unittest.TestCase):
    def test_restores_an_older_exact_review_and_rejects_changed_media(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'original'
            original.mkdir()
            request = {
                'execution_backend': 'contabo_private_runner', 'request_id': 'request-123',
                'source_context_sha256': 'a'*64, 'golden_path_run_id': 123,
                'contabo_handoff': {'worker_run_id': 122},
                'production_completion': {'golden_path_run_id': 123, 'state': 'REVIEW_READY',
                                          'quality_gates_weakened': False, 'telegram_message_id': 500},
            }
            job = {'github_run_id': 122, 'render_status': 'DONE', 'quality_report': {'passed': True}}
            audit = {'passed': True, 'quality_gates_weakened': False, 'targets': ['youtube_shorts', 'tiktok']}
            for name in FILES:
                (original / name).write_text(name)
            (original / 'job.json').write_text(json.dumps(job))
            (original / 'publication_quality_gate.json').write_text(json.dumps(audit))
            decision = pending(original, request, '123', 456, 'b'*40)
            decision.update(state='APPROVED', decision_id='checked-123', decided_via='control_center')

            for tampered in (False, True):
                archive = root / 'result.zip'
                with ZipFile(archive, 'w') as bundle:
                    bundle.writestr('out/control-plane/production-manifest.json',
                                    json.dumps({'implementation_sha': decision['studio_sha']}))
                    bundle.writestr('out/control-plane/contabo-result.json', json.dumps({
                        'request_id': request['request_id'], 'run_id': 123,
                        'source_context_sha256': request['source_context_sha256'],
                        'quality_passed': True, 'quality_gates_weakened': False,
                    }))
                    for name in FILES:
                        value = (original / name).read_text()
                        if name == 'job.json':
                            value = json.dumps(job)
                        if tampered and name == 'short_tiktok.mp4':
                            value = 'changed media'
                        bundle.writestr(f'site/tayvoriq/runs/123/{name}', value)
                destination = root / f'destination-{tampered}'
                if tampered:
                    with self.assertRaisesRegex(ValueError, 'CONTABO|APPROVED_REVIEW_FILE_CHANGED'):
                        restore(archive, decision, request, '123', destination)
                    self.assertFalse(destination.exists())
                else:
                    restore(archive, decision, request, '123', destination)
                    self.assertEqual((destination / 'job.json').read_bytes(), (original / 'job.json').read_bytes())
