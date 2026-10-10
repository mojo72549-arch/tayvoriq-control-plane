import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from tayvoriq_lifecycle_dispatch_v1 import dispatch_verified

KEY = 'a' * 64


class DispatchReceiptTests(unittest.TestCase):
    def run_dispatch(self, lists, dispatch):
        return dispatch_verified('DELIVERY_WATCH', 'approved-request', '42', KEY,
                                 list_runs=lists, dispatch=dispatch, pause=lambda _: None, polls=3)

    def executor(self, **changes):
        return dict(id=71, display_title='TAYVORIQ lifecycle ' + KEY,
                    event='workflow_dispatch', head_branch='main', **changes)

    def test_acceptance_without_executor_is_not_success(self):
        calls = []
        with self.assertRaisesRegex(RuntimeError, 'NOT_ACKNOWLEDGED'):
            self.run_dispatch(lambda _: [], lambda *args: calls.append(args))
        self.assertEqual(len(calls), 1)

    def test_lost_transport_response_reuses_observed_executor(self):
        created = []
        def dispatch(*args):
            created.append(self.executor())
            raise subprocess.CalledProcessError(1, 'gh')
        self.assertEqual(self.run_dispatch(lambda _: created, dispatch)['id'], 71)

    def test_repeat_never_dispatches_same_decision_twice(self):
        self.assertEqual(self.run_dispatch(lambda _: [self.executor()],
                                          lambda *args: self.fail('duplicate dispatch'))['id'], 71)

    def test_unrelated_or_wrong_branch_executor_cannot_acknowledge(self):
        for field, value in [('display_title', 'unrelated'), ('head_branch', 'feature'), ('event', 'push')]:
            with self.subTest(field=field):
                wrong = self.executor()
                wrong[field] = value
                with self.assertRaisesRegex(RuntimeError, 'NOT_ACKNOWLEDGED'):
                    self.run_dispatch(lambda _: [wrong], lambda *args: None)

    def test_duplicate_correlated_executors_are_a_contract_failure(self):
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_EXECUTORS'):
            self.run_dispatch(lambda _: [self.executor(), self.executor()], lambda *args: None)

    def test_invalid_identity_fails_before_api_or_dispatch(self):
        with self.assertRaises(ValueError):
            dispatch_verified('DELIVERY_WATCH', 'approved-request', '42', 'bad-key',
                              list_runs=lambda _: self.fail('api'), dispatch=lambda *args: self.fail('dispatch'))


if __name__ == '__main__':
    unittest.main()
