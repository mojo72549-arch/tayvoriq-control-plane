"""Fail-closed, idempotent GitHub retry dispatch receipts."""
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from tayvoriq_recovery_attempt_ack_v1 import RetryDispatchError, dispatch_acknowledged


class RetryAckTests(unittest.TestCase):
    def run_info(self, attempt=2, status="completed", conclusion="failure", **changes):
        base = dict(
            id=42, run_attempt=attempt, status=status, conclusion=conclusion,
            name="TAYVORIQ-X Golden Path",
            path=".github/workflows/tayvoriq-deliver-video-now.yml@refs/heads/main",
        )
        return base | changes

    def test_one_dispatch_has_proof_of_exact_increment(self):
        records = [self.run_info(attempt=2), self.run_info(attempt=2),
                   self.run_info(attempt=3, status="queued", conclusion=None)]
        calls = []
        evidence = dispatch_acknowledged(
            42, 2, fetch=lambda _: records.pop(0),
            dispatch=lambda x: calls.append(x), pause=lambda _: None)
        self.assertEqual(evidence["acknowledged_attempt"], 3)
        self.assertEqual(evidence["mode"], "dispatched")
        self.assertEqual(calls, [42])

    def test_prior_ack_never_dispatches_again(self):
        receipt = dispatch_acknowledged(
            42, 2, fetch=lambda _: self.run_info(attempt=3),
            dispatch=lambda _: self.fail("duplicate"), pause=lambda _: None)
        self.assertEqual(receipt["mode"], "already_dispatched")

    def test_transport_timeout_after_github_acceptance_counts_only_with_proof(self):
        calls = []
        attempts = iter([self.run_info(attempt=1), self.run_info(attempt=2)])
        def dispatch(x):
            calls.append(x)
            raise subprocess.CalledProcessError(1, "gh run rerun")
        proof = dispatch_acknowledged(
            42, 1, fetch=lambda _: next(attempts),
            dispatch=dispatch, pause=lambda _: None)
        self.assertEqual(proof["dispatch_transport_error"], "CalledProcessError")
        self.assertEqual(calls, [42])

    def test_absent_ack_fails_without_duplicate_dispatch(self):
        calls = []
        with self.assertRaisesRegex(RetryDispatchError, "NOT_ACKNOWLEDGED"):
            dispatch_acknowledged(
                42, 1, fetch=lambda _: self.run_info(attempt=1),
                dispatch=lambda x: calls.append(x), pause=lambda _: None, polls=2)
        self.assertEqual(calls, [42])

    def test_wrong_owner_attempt_or_nonterminal_fail_before_dispatch(self):
        wrongs = [
            self.run_info(id=43),
            self.run_info(name="unrelated"),
            self.run_info(path=".github/workflows/unrelated.yml"),
            self.run_info(attempt=6),
            self.run_info(attempt=1, status="in_progress", conclusion=None),
            self.run_info(conclusion="success"),
        ]
        for wrong in wrongs:
            with self.subTest(wrong=wrong), self.assertRaises(RetryDispatchError):
                dispatch_acknowledged(
                    42, 2 if wrong.get("run_attempt") != 1 else 1,
                    fetch=lambda _: wrong,
                    dispatch=lambda _: self.fail("invalid dispatch"),
                    pause=lambda _: None)

    def test_unexpected_concurrent_later_attempt_fails_closed(self):
        states = iter([self.run_info(attempt=1), self.run_info(attempt=4)])
        with self.assertRaisesRegex(RetryDispatchError, "LATER_ATTEMPT"):
            dispatch_acknowledged(
                42, 1, fetch=lambda _: next(states),
                dispatch=lambda _: None, pause=lambda _: None)


if __name__ == "__main__":
    unittest.main()
