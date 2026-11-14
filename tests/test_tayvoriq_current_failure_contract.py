import json
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

    def test_repeated_missing_visual_search_fallback_requires_code(self):
        log = ("RuntimeError: REAL_VIDEO_SCENE_REQUIRED:scene=6:query=example:"
               "bounded_real_video_queries_exhausted=['example']:attempted_queries=[]:"
               "no usable moving clip was downloaded; generated/static fallback is forbidden")
        for attempt in (1, 2):
            report = bind_current_failure({'state': 'TRANSIENT_RENDER_FAILURE'}, log,
                                          run_id=42, run_attempt=attempt, request_id='telegram-42-trend-1')
            expected = 'TRANSIENT_RENDER_FAILURE' if attempt == 1 else 'LOCAL_VISUAL_CODEFIX_REQUIRED'
            self.assertEqual(report['state'], expected)
        decision = classify_failure('', run_attempt=2, structured_evidence=report)
        self.assertEqual(decision.mode, 'deterministic')
        self.assertFalse(decision.retry_allowed)

    def test_repeated_generic_editorial_queries_require_a_studio_revision(self):
        log = "RuntimeError: CONTENT_REJECTED:tayvoriq-editorial-visual-standard-v1:generic_visual_query_detected"
        report = self.contract(log)
        self.assertEqual(report['state'], 'LOCAL_VISUAL_CODEFIX_REQUIRED')
        decision = classify_failure('', run_attempt=3, structured_evidence=report)
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

    def test_exact_dhl_alias_proof_blocks_audio_regeneration(self):
        expected = 'Deh Hah Ell: vor dem Versand Filialpreis und Onlinepreis vergleichen.'
        heard = 'DHL: vor dem Versand-Filialpreis und Online-Preis vergleichen.'
        proof = dict(passed=False, segment_min_similarity=0.95, missing_critical_terms=[],
                     hallucinated_tail=False, terminal_token_match=True, contract_expected=expected)
        terminal = 'RuntimeError: POST_AUDIO_QUALITY_GATE_BLOCKED:pre-render-transcript-contract-failed'

        def evidence(transcript):
            return json.dumps({'quality_gates_weakened': False, 'pre_render_voice_attempt': {
                'stage': 'pre-render-transcript', 'cta_morphology_passed': True,
                'strict_audio_validation': {**proof, 'raw_transcript': transcript},
            }}) + '\n' + terminal

        report = self.contract(evidence(heard))
        self.assertEqual(report['state'], 'TRANSCRIPT_NORMALIZATION_DEFECT')
        self.assertFalse(report['audio_regeneration_allowed'])
        decision = classify_failure('', run_attempt=3, structured_evidence=report)
        self.assertEqual(decision.retry_kind, 'verified-codefix-replay')
        self.assertFalse(decision.retry_allowed)
        for altered in ('DPD: vor dem Versand Filialpreis und Online-Preis vergleichen.',
                        heard.replace('Online-Preis', 'Online-Preise')):
            self.assertNotEqual(self.contract(evidence(altered))['state'], report['state'])

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

    def broken_writer_log(self, **changes):
        import json
        manifest = dict(control_plane_schema='x-v3', implementation_binding='production-green-immutable-sha',
                        run_id='42', run_attempt='3', source_request_id='telegram-42-trend-1',
                        approved_trend_pinned=True, source_context_bound=True, source_request_pinned=True,
                        quality_gates_weakened=False, implementation_sha='a'*40,
                        control_plane_sha='b'*40, source_context_sha256='c'*64)
        return (json.dumps({**manifest, **changes}) + '\n'
                'RuntimeError: TAYVORIQ V20 Quality-Gate blockiert das Video: script_too_short:47:min=51\n'
                'Controller handoff: state=PUBLISHABLE_OUTPUT_RETRY_REQUIRED reusable_master=false process_exit=1\n'
                "ModuleNotFoundError: No module named 'tools.tayvoriq_current_failure_contract_v1'")

    def test_broken_historical_writer_recovers_only_bound_native_failure(self):
        proof = recover_failure_contract(self.broken_writer_log(), run_id=42,
                    run_attempt=3, request_id='telegram-42-trend-1')
        self.assertEqual(proof['state'], 'EDITORIAL_VALIDATOR_CODEFIX_REQUIRED')
        self.assertEqual(proof['failed_implementation_sha'], 'a'*40)
        self.assertEqual(proof['evidence_provenance'], 'exact-run-attempt-console')
        self.assertFalse(proof['master_reusable'])
        self.assertFalse(proof['quality_gates_weakened'])

    def test_broken_writer_recovery_requires_all_provenance_and_terminal_evidence(self):
        for changes in ({'run_id': '41'}, {'run_attempt': '2'}, {'source_request_id': 'other'},
                        {'source_context_bound': False}, {'quality_gates_weakened': True}):
            with self.subTest(changes=changes):
                self.assertIsNone(recover_failure_contract(self.broken_writer_log(**changes),
                    run_id=42, run_attempt=3, request_id='telegram-42-trend-1'))
        for marker in ('RuntimeError:', 'Controller handoff:', 'ModuleNotFoundError:'):
            log = '\n'.join(line for line in self.broken_writer_log().splitlines() if marker not in line)
            self.assertIsNone(recover_failure_contract(log, run_id=42,
                    run_attempt=3, request_id='telegram-42-trend-1'))
        log = self.broken_writer_log() + '\nRuntimeError: LOCAL_VISUAL_REPAIR_REQUIRED'
        self.assertIsNone(recover_failure_contract(log, run_id=42,
                    run_attempt=3, request_id='telegram-42-trend-1'))


if __name__ == '__main__':
    unittest.main()
