from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import tayvoriq_telegram_generation_truth_guard as guard


def _request(bound_run: int, generation: int) -> str:
    return json.dumps(
        {
            "request_id": "telegram-test-trend-1",
            "source": "telegram_trend_approval",
            "status": "DISPATCHED",
            "golden_path_run_id": bound_run,
            "recovery_generation": generation,
            "quality_gates_weakened": False,
        },
        ensure_ascii=False,
    )


def test_stale_snapshot_never_reports_old_generation_as_current() -> None:
    data = json.loads(guard.sanitize_request_snapshot(_request(32565575910, 3), 32568385221))
    assert data["recovery_generation"] == 0
    evidence = data["telegram_generation_truth_guard"]
    assert evidence["status"] == "stale-snapshot-suppressed"
    assert evidence["snapshot_golden_path_run_id"] == 32565575910
    assert evidence["current_golden_path_run_id"] == 32568385221
    assert evidence["generation_was"] == 3
    assert evidence["generation_inferred"] is False
    assert evidence["quality_gates_changed"] is False


def test_current_snapshot_keeps_verified_generation() -> None:
    original = _request(32568385221, 4)
    assert guard.sanitize_request_snapshot(original, 32568385221) == original


def test_zero_or_non_recovery_generation_is_left_untouched() -> None:
    original = _request(32565575910, 0)
    assert guard.sanitize_request_snapshot(original, 32568385221) == original


def test_invalid_json_is_left_untouched() -> None:
    assert guard.sanitize_request_snapshot("not-json", 32568385221) == "not-json"


def test_sitecustomize_activates_only_for_telegram_progress_runtime() -> None:
    source = (TOOLS / "sitecustomize.py").read_text(encoding="utf-8")
    assert 'Path(sys.argv[0]).name == "tayvoriq_telegram_progress_v1.py"' in source
    assert "SOURCE_REQUEST_ID_PIN" in source
    assert "GITHUB_RUN_ID" in source
    assert "sanitize_request_snapshot" in source


def test_real_python_startup_suppresses_stale_generation_but_keeps_current() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        requests = root / "requests"
        requests.mkdir()
        request_path = requests / "telegram-test-trend-1.json"
        probe = root / "tayvoriq_telegram_progress_v1.py"
        probe.write_text(
            "import json\n"
            "from pathlib import Path\n"
            "data=json.loads(Path('requests/telegram-test-trend-1.json').read_text(encoding='utf-8'))\n"
            "print(data['recovery_generation'])\n",
            encoding="utf-8",
        )
        env = dict(os.environ)
        env.update(
            {
                "PYTHONPATH": str(TOOLS),
                "SOURCE_REQUEST_ID_PIN": "telegram-test-trend-1",
                "GITHUB_RUN_ID": "32568385221",
            }
        )

        request_path.write_text(_request(32565575910, 3), encoding="utf-8")
        stale = subprocess.run(
            [sys.executable, str(probe)],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert stale.stdout.strip() == "0"

        request_path.write_text(_request(32568385221, 4), encoding="utf-8")
        current = subprocess.run(
            [sys.executable, str(probe)],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert current.stdout.strip() == "4"
