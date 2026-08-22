from __future__ import annotations

import ast
from pathlib import Path


DISPATCH = Path(".github/workflows/tayvoriq-request-dispatch.yml")
REPLAY_GUARD = Path(".github/workflows/tayvoriq-x-replay-start-guard.yml")
PROGRESS = Path("tools/tayvoriq_telegram_progress_v1.py")


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            value = node.value
            if isinstance(target, ast.Name) and target.id == name and value is not None:
                return ast.literal_eval(value)
    raise AssertionError(f"assignment {name} not found in {path}")


def test_normal_dispatch_pins_the_exact_telegram_request():
    text = DISPATCH.read_text(encoding="utf-8")
    assert 'REQUEST_ID: ${{ steps.request.outputs.request_id }}' in text
    assert '-f source_request_id="$REQUEST_ID"' in text
    assert 'Golden Path accepted request ${REQUEST_ID}' in text


def test_replay_push_is_verified_and_has_an_exact_request_fallback():
    text = REPLAY_GUARD.read_text(encoding="utf-8")
    required = (
        '.github/run-now/tayvoriq-x-request.json',
        "approved_trend_pinned",
        "telegram_trend_approval",
        "REPLAY_TOPIC_MISMATCH",
        "REPLAY_TREND_MISMATCH",
        "--event push",
        'headSha == \\"$GITHUB_SHA\\"'.replace('\\\\"', '\\"'),
        'gh workflow run tayvoriq-deliver-video-now.yml',
        '-f source_request_id="$REQUEST_ID"',
        "REPLAY_START_NOT_VERIFIED",
        "golden_path_run_id",
        "REPLAY_REQUEST_BINDING_VERIFIED",
        "tayvoriq-delivery-watch",
    )
    for marker in required:
        assert marker in text, marker


def test_same_run_retry_does_not_repeat_early_progress_milestones():
    suppressed = _literal_assignment(PROGRESS, "REPLAY_SUPPRESSED_STAGES")
    assert {"sources_locked", "environment_active", "production_active"}.issubset(
        set(suppressed)
    )


def test_hardening_never_weakens_quality_gates():
    dispatch = DISPATCH.read_text(encoding="utf-8")
    replay = REPLAY_GUARD.read_text(encoding="utf-8")
    assert "quality_gates_weakened: true" not in replay.casefold()
    assert "source_request_id" in dispatch
