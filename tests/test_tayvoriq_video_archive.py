import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_video_archive import ARCHIVE, build, platform_receipts


class ArchiveTest(unittest.TestCase):
    def receipt(self):
        return {'review_id': '123', 'platform': 'youtube', 'privacy': 'public',
                'video_id': '12345678901', 'url': 'https://www.youtube.com/shorts/12345678901',
                'published_at': '2026-11-25T10:26:23Z', 'idempotency_lock': True}

    def test_claim_or_approval_does_not_count_as_publication(self):
        for state in ('UPLOAD_STARTED', 'APPROVED', 'PENDING'):
            self.assertIsNone(platform_receipts({'review_id': '123', 'state': state}, {}, '123'))
        for key, value in [('privacy', 'private'), ('review_id', '124'),
                           ('idempotency_lock', False), ('url', 'https://evil.example/video'),
                           ('published_at', None)]:
            self.assertIsNone(platform_receipts({**self.receipt(), key: value}, {}, '123'))

    def test_youtube_success_and_tiktok_package_remain_partial(self):
        receipt = {**self.receipt(), 'tiktok_status': 'MANUAL_UPLOAD_REQUIRED'}
        result = platform_receipts(receipt, {}, '123')
        self.assertEqual(result['youtube']['status'], 'PUBLISHED')
        self.assertEqual(result['tiktok']['status'], 'MANUAL_UPLOAD_REQUIRED')
        receipt['tiktok'] = {'status': 'PUBLISHED', 'verified': True,
                             'url': 'https://www.tiktok.com/@tayvoriqofficial/video/123',
                             'published_at': '2026-11-25T11:00:00Z'}
        self.assertEqual(platform_receipts(receipt, {}, '123')['tiktok']['status'], 'PUBLISHED')
        receipt['tiktok']['verified'] = False
        self.assertEqual(platform_receipts(receipt, {}, '123')['tiktok']['status'], 'MANUAL_UPLOAD_REQUIRED')

    def test_archive_survives_queue_changes_and_repeated_builds(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / '.automation/tayvoriq-publications/123.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(self.receipt()))
            first = build(root)
            self.assertFalse(first['records'][0]['fully_published'])
            self.assertFalse(first['records'][0]['publication_offered'])
            self.assertIsNone(first['records'][0]['quality'])
            target = root / ARCHIVE
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(first))
            self.assertEqual(build(root), first)
            path.unlink()
            self.assertEqual(build(root), first)
