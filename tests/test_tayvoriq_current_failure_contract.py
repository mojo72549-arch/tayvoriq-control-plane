import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_current_failure_contract_v1 import bind_current_failure, recover_failure_contract, recover_production_manifest
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

    def legacy_log(self, **changes):
        payload = dict(schema='tayvoriq-failure-contract-v2',
                       state='PUBLISHABLE_OUTPUT_RETRY_REQUIRED',
                       failure_class='PUBLISHABLE_CHECKPOINT',
                       repair_target_stages=['RENDER'], quality_gates_weakened=False)
        payload.update(changes)
        return ('job 2026 ##[group]Run python - <<PY\n'
                'job 2026 control_plane_binding_failure = (condition)\n'
                'job 2026 ' + repr(payload) + '\n'
                'job 2026 ##[endgroup]\n'
                'job 2026 RuntimeError: CONTENT_REJECTED:verified-editorial-postcondition-drift:fields=action_now:body_words=46\n'
                'job 2026 ' + repr(payload))

    def test_legacy_console_contract_recovers_exact_terminal_failure(self):
        report = recover_failure_contract(self.legacy_log(), run_id=42,
                                          run_attempt=3, request_id='telegram-42-trend-1')
        self.assertEqual(report['state'], 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED')
        self.assertEqual(report['evidence_provenance'], 'exact-run-attempt-console')
        self.assertEqual(report['run_attempt'], 3)
        self.assertFalse(report['quality_gates_weakened'])
        decision = classify_failure(self.legacy_log(), run_attempt=3, structured_evidence=report)
        self.assertEqual(decision.state, report['state'])

    def test_uncolored_workflow_source_cannot_invent_a_binding_error(self):
        decision = classify_failure(self.legacy_log(), run_attempt=3)
        self.assertEqual(decision.state, 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED')

    def test_legacy_contract_with_wrong_identity_or_weakened_gates_is_rejected(self):
        for changes in ({'run_id': 41}, {'run_attempt': 2}, {'request_id': 'other'},
                        {'quality_gates_weakened': True}):
            with self.subTest(changes=changes):
                self.assertIsNone(recover_failure_contract(self.legacy_log(**changes),
                    run_id=42, run_attempt=3, request_id='telegram-42-trend-1'))

    def test_echoed_contract_without_runtime_proof_is_not_recovered(self):
        console = self.legacy_log().split('job 2026 ##[endgroup]', 1)[0] + 'job 2026 ##[endgroup]'
        self.assertIsNone(recover_failure_contract(console,run_id=42,run_attempt=3,
                                                 request_id='telegram-42-trend-1'))

    def test_failed_revision_comes_from_exact_bound_producer_manifest(self):
        import json
        manifest = dict(control_plane_schema='x-v3', implementation_binding='production-green-immutable-sha',
                        run_id='42', run_attempt='3', source_request_id='telegram-42-trend-1',
                        approved_trend_pinned=True, source_context_bound=True, source_request_pinned=True,
                        quality_gates_weakened=False, implementation_sha='a'*40,
                        control_plane_sha='b'*40, source_context_sha256='c'*64)
        console = json.dumps(manifest) + '\n' + self.legacy_log()
        proof = recover_failure_contract(console,run_id=42,run_attempt=3,request_id='telegram-42-trend-1')
        self.assertEqual(proof['failed_implementation_sha'], 'a'*40)
        self.assertEqual(proof['failed_control_plane_sha'], 'b'*40)
        self.assertEqual(proof['producer_source_context_sha256'], 'c'*64)
        for changes in ({'run_attempt': 2}, {'source_request_id': 'other'},
                        {'quality_gates_weakened': True}, {'source_request_pinned': False}):
            with self.subTest(changes=changes):
                self.assertIsNone(recover_production_manifest(json.dumps({**manifest,**changes}),
                    run_id=42,run_attempt=3,request_id='telegram-42-trend-1'))


if __name__ == '__main__':
    unittest.main()
