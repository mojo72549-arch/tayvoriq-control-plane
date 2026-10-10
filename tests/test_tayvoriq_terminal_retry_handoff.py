import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_codefix_orphan_reconcile_v1 import _replay_status_allows_rearm
from tayvoriq_lifecycle_controller_v1 import decide


class TerminalRetryHandoffTests(unittest.TestCase):
    def fixture(self):
        codefix = dict(status='LOCAL_RETRY_DISPATCHED', local_retry_run_id=42,
                       local_retry_run_attempt=3, local_retry_dispatched_at='2026-10-06T00:58:54Z')
        run = dict(id=42, run_attempt=3, status='completed', conclusion='failure',
                   updated_at='2026-10-06T01:01:28Z')
        evidence = dict(run_id=42, run_attempt=3, state='EDITORIAL_VALIDATOR_CODEFIX_REQUIRED',
                        quality_gates_weakened=False)
        return codefix, run, evidence

    def test_completed_retry_can_release_ownership_for_current_deterministic_failure(self):
        codefix, run, evidence = self.fixture()
        self.assertTrue(_replay_status_allows_rearm(codefix, 42, run, evidence))

    def test_live_old_or_local_failure_cannot_release_owner(self):
        codefix, run, evidence = self.fixture()
        cases = [({**run, 'status': 'in_progress'}, evidence),
                 ({**run, 'run_attempt': 2}, {**evidence, 'run_attempt': 2}),
                 (run, {**evidence, 'run_id': 41}),
                 (run, {**evidence, 'state': 'LOCAL_VISUAL_REPAIR_REQUIRED'}),
                 (run, {**evidence, 'quality_gates_weakened': True}),
                 (run, {}),
                 ({**run, 'updated_at': '2026-10-06T00:58:00Z'}, evidence)]
        for metadata, proof in cases:
            with self.subTest(metadata=metadata, proof=proof):
                self.assertFalse(_replay_status_allows_rearm(codefix, 42, metadata, proof))

    def test_classifier_completion_unlocks_continuity_but_never_repeats_a_handoff(self):
        pointer = dict(schema='tayvoriq-active-production-request-v1', state='ACTIVE',
                       request_id='telegram-42-trend-1', golden_path_run_id=42,
                       approval_key='approved', source_context_sha256='sources',
                       contract_sha256='contract', recovery_generation=1)
        request = {**pointer, 'source': 'telegram_trend_approval', 'status': 'DISPATCHED',
                   'codefix_recovery': {'status': 'LOCAL_RETRY_DISPATCHED'}}
        _, run, _ = self.fixture()
        classified = decide(pointer, request, run, revision='fixed', green='green')
        self.assertEqual(classified['action'], 'DELIVERY_WATCH')
        receipt = {**classified, 'dispatch_verified': True}
        request['codefix_recovery'] = dict(status='ARMED', request_substate='AWAITING_CODEFIX',
                                         failed_run_id=42, failure_state='EDITORIAL_VALIDATOR_CODEFIX_REQUIRED')
        next_step = decide(pointer, request, run, revision='fixed', green='green', previous=receipt)
        self.assertEqual(next_step['action'], 'CODEFIX_CONTINUITY')
        self.assertNotEqual(next_step['decision_key'], receipt['decision_key'])
        for _ in range(20):
            repeated = decide(pointer, request, run, revision='fixed', green='green',
                              previous={**next_step, 'dispatch_verified': True})
            self.assertEqual(repeated['action'], 'NONE')


if __name__ == '__main__':
    unittest.main()
