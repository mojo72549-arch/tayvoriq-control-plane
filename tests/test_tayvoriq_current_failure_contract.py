import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_current_failure_contract_v1 import bind_current_failure
from tayvoriq_recovery_policy_v1 import classify_failure


class CurrentFailureContractTests(unittest.TestCase):
    def contract(self, console):
        return bind_current_failure(
            {'state': 'LOCAL_VISUAL_REPAIR_REQUIRED', 'failure_class': 'LOCAL_VISUAL',
             'repair_target_stages': ['VISUALS'], 'master_reusable': True,
             'quality_gates_weakened': False}, console,
            run_id=42, run_attempt=3, request_id='telegram-42-trend-1')

    def test_current_editorial_error_supersedes_stale_visual_report(self):
        report = self.contract('RuntimeError: CONTENT_REJECTED:verified-editorial-postcondition-drift:fields=action_now:body_words=46')
        self.assertEqual(report['state'], 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED')
        self.assertEqual(report['repair_target_stages'], [])
        self.assertFalse(report['master_reusable'])
        decision = classify_failure('bounded localized repair exhausted', run_attempt=3,
                                    structured_evidence=report)
        self.assertEqual(decision.state, report['state'])
        self.assertEqual(decision.mode, 'deterministic')
        self.assertFalse(decision.retry_allowed)

    def test_echoed_policy_source_is_not_a_runtime_failure(self):
        echoed = '\x1b[36;1mif "CONTENT_REJECTED:verified-editorial-postcondition-drift" in text:\x1b[0m'
        report = self.contract(echoed)
        self.assertEqual(report['state'], 'LOCAL_VISUAL_REPAIR_REQUIRED')
        decision = classify_failure(echoed + '\nHTTP 503 temporarily unavailable')
        self.assertEqual(decision.mode, 'rerun')

    def test_previous_attempt_cannot_steal_current_failure(self):
        report = self.contract('')
        decision = classify_failure('HTTP 503', run_attempt=4, structured_evidence=report)
        self.assertEqual(decision.mode, 'stale')
        self.assertFalse(decision.retry_allowed)

    def test_current_visual_report_retains_its_checkpoint(self):
        report = self.contract('visual audit failed')
        self.assertTrue(report['master_reusable'])
        self.assertEqual(report['run_id'], 42)
        self.assertEqual(report['run_attempt'], 3)
        self.assertEqual(report['request_id'], 'telegram-42-trend-1')

    def test_later_local_failure_does_not_revive_an_earlier_editorial_error(self):
        report = self.contract(
            'RuntimeError: CONTENT_REJECTED:verified-editorial-postcondition-drift\n'
            'RuntimeError: LOCAL_VISUAL_REPAIR_REQUIRED')
        self.assertEqual(report['state'], 'LOCAL_VISUAL_REPAIR_REQUIRED')
        self.assertTrue(report['master_reusable'])


if __name__ == '__main__':
    unittest.main()
