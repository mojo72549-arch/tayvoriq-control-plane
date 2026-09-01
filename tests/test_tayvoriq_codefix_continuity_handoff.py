from __future__ import annotations

import unittest
from pathlib import Path


GOLDEN = Path(".github/workflows/tayvoriq-deliver-video-now.yml")
CONTINUITY = Path(".github/workflows/tayvoriq-deterministic-codefix-continuity.yml")
PROMOTER = Path(".github/workflows/tayvoriq-production-green-promoter.yml")
HARDENER = Path("tools/tayvoriq_harden_failure_finalizer_v1.py")


def _step(text: str, name: str) -> str:
    marker = f"      - name: {name}"
    start = text.index(marker)
    end = text.find("\n      - name:", start + len(marker))
    return text[start:] if end < 0 else text[start:end]


class CodefixContinuityHandoffTests(unittest.TestCase):
    def test_failure_finalizer_verifies_the_latest_committed_owner(self) -> None:
        golden = GOLDEN.read_text(encoding="utf-8")
        step = _step(golden, "Dispatch exact deterministic failure finalizer")
        required = (
            "CODEFIX_FINALIZER_REQUEST_ID_INVALID",
            "git fetch --no-tags --prune origin main --quiet",
            "git show origin/main:.github/state/tayvoriq-active-production-request.json",
            'git show "origin/main:${request_rel}"',
            "pointer_path=Path(sys.argv[3]); request_path=Path(sys.argv[4])",
            "CODEFIX_FINALIZER_ACTIVE_OWNER_CHANGED",
            "CODEFIX_FINALIZER_REQUEST_OWNER_CHANGED",
        )
        for marker in required:
            self.assertIn(marker, step, marker)
        self.assertNotIn(
            "pointer_path=Path('.github/state/tayvoriq-active-production-request.json')",
            step,
        )

    def test_failure_finalizer_hardener_preserves_fresh_owner_verification(
        self,
    ) -> None:
        hardener = HARDENER.read_text(encoding="utf-8")
        for marker in (
            "git fetch --no-tags --prune origin main --quiet",
            "git show origin/main:.github/state/tayvoriq-active-production-request.json",
            'git show "origin/main:${request_rel}"',
            "pointer_path=Path(sys.argv[3]); request_path=Path(sys.argv[4])",
        ):
            self.assertIn(marker, hardener, marker)

    def test_armed_codefix_requests_event_driven_green_reconciliation_once(
        self,
    ) -> None:
        continuity = CONTINUITY.read_text(encoding="utf-8")
        step = _step(
            continuity,
            "Request Production Green reconciliation for armed codefix",
        )
        required = (
            "steps.pending.outputs.found == 'true'",
            "steps.revision.outputs.detected != 'true'",
            "github.event_name != 'schedule'",
            "github.event.workflow_run.name != 'TAYVORIQ Production Green Promoter'",
            "gh workflow run tayvoriq-production-green-promoter.yml --ref main",
            "CODEFIX_PRODUCTION_GREEN_RECONCILIATION_DISPATCHED",
        )
        for marker in required:
            self.assertIn(marker, step, marker)
        self.assertNotIn("quality_gates_weakened: true", continuity.casefold())

    def test_successful_green_promotion_explicitly_resumes_continuity(self) -> None:
        promoter = PROMOTER.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  actions: write\n  contents: write", promoter)
        step = _step(
            promoter,
            "Resume deterministic codefix continuity after promotion",
        )
        for marker in (
            "steps.refs.outputs.changed == 'true'",
            "GH_TOKEN: ${{ github.token }}",
            "gh workflow run tayvoriq-deterministic-codefix-continuity.yml --ref main",
            "TAYVORIQ_PRODUCTION_GREEN_CONTINUITY_RESUMED",
        ):
            self.assertIn(marker, step, marker)
        self.assertNotIn("quality_gates_weakened: true", promoter.casefold())


if __name__ == "__main__":
    unittest.main()
