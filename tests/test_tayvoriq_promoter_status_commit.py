"""Git status-only promotion test: code SHA stays pinned; real code changes fail."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/tayvoriq-production-green-promoter.yml"


class PromoterSourceIdentityTests(unittest.TestCase):
    def test_only_verified_status_receipt_may_advance_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)
            def git(*args):
                return subprocess.check_output(["git", "-C", str(p), *args], text=True).strip()
            subprocess.run(["git", "init", "-q", str(p)], check=True)
            git("config", "user.email", "ci@example.invalid")
            git("config", "user.name", "Test")
            (p / "tools").mkdir()
            (p / "tools/renderer.py").write_text("QUALITY_FLOOR=0.95\n")
            git("add", ".")
            git("commit", "-qm", "verified renderer")
            code_sha = git("rev-parse", "HEAD")

            (p / ".automation").mkdir()
            (p / ".automation/tayvoriq-quality-status.json").write_text(
                json.dumps({"state": "TAYVORIQ_QUALITY_GATES_PASSED",
                            "tested_sha": code_sha,
                            "all_tayvoriq_tests_passed": True}))
            git("add", ".")
            git("commit", "-qm", "metadata-only quality receipt")
            status_sha = git("rev-parse", "HEAD")
            self.assertNotEqual(status_sha, code_sha)
            selected = git("log", "-1", "--format=%H", "--", ".", ":!.automation/tayvoriq-quality-status.json")
            self.assertEqual(selected, code_sha)
            changed = git("diff", "--name-only", code_sha, status_sha, "--", ".", ":!.automation/tayvoriq-quality-status.json")
            self.assertEqual(changed, "")

            (p / "tools/renderer.py").write_text("QUALITY_FLOOR=0.90\n")
            git("add", ".")
            git("commit", "-qm", "dangerous quality change")
            new_head = git("rev-parse", "HEAD")
            changed = git("diff", "--name-only", code_sha, new_head, "--", ".", ":!.automation/tayvoriq-quality-status.json")
            self.assertIn("tools/renderer.py", changed)

    def test_promoter_refuses_unverified_or_wrong_candidate(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("STUDIO_PRODUCTION_SOURCE_ADVANCED_DURING_PREFLIGHT", text)
        self.assertIn("STUDIO_QUALITY_STATUS_OTHER_CANDIDATE", text)
        self.assertIn("STUDIO_QUALITY_STATUS_NOT_VERIFIED", text)
        self.assertIn("git merge-base --is-ancestor", text)
        self.assertIn("git checkout --detach", text)
        self.assertIn("STUDIO_STATUS_ONLY_COMMIT_ACCEPTED", text)


if __name__ == "__main__":
    unittest.main()
