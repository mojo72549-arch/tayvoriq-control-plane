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

    def test_retiring_a_request_keeps_original_archive_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            publication=root/'.automation/tayvoriq-publications/123.json'
            publication.parent.mkdir(parents=True)
            publication.write_text(json.dumps(self.receipt()))
            request=root/'requests/request-123.json'
            request.parent.mkdir()
            request.write_text(json.dumps({'request_id':'request-123','golden_path_run_id':123,
                'topic':'Geprüftes Originalthema','source_context':{'sources':[{'url':'https://source.example/'}]},
                'state_history':[{'state':'APPROVED','at':'2026-11-25T10:00:00Z'}]}))
            first=build(root)
            archive=root/ARCHIVE;archive.parent.mkdir(parents=True)
            archive.write_text(json.dumps(first))
            request.unlink()
            self.assertEqual(build(root),first)
            publication.unlink()
            self.assertEqual(build(root),first)

    def test_historical_platform_receipt_is_retained_without_a_separate_ledger(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            path=root/'.automation/tayvoriq-reviews/123.json'
            path.parent.mkdir(parents=True)
            review={'review_id':'123','status':'APPROVED','platform_upload_performed':True,
                'publication_pending':False,'upload_status':'PUBLISHED_YOUTUBE','youtube_privacy':'public',
                'published_at':'2026-08-16T07:16:00Z','approved_at':'2026-08-16T07:15:00Z',
                'tiktok_status':'MANUAL_UPLOAD_REQUIRED','published_payload':{'title':'Historisches Original'},
                'youtube':{'video_id':'12345678901','url':'https://www.youtube.com/shorts/12345678901'}}
            path.write_text(json.dumps(review))
            records=build(root)['records']
            self.assertEqual(len(records),1)
            self.assertEqual(records[0]['topic'],'Historisches Original')
            self.assertFalse(records[0]['fully_published'])
            self.assertEqual(records[0]['platforms']['youtube']['receipt_kind'],'legacy_review_publication_result')
            review['platform_upload_performed']=False
            path.write_text(json.dumps(review))
            self.assertEqual(build(root)['records'],[])
