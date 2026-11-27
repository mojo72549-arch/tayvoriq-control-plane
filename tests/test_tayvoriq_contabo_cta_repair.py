import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_contabo_cta_repair as recovery


def test_recovery_requires_the_exact_worker_and_reuses_one_validated_child(tmp_path):
    contract = recovery.contract
    source = {"sources": ["one", "two"]}
    shared = {
        "request_id": "telegram-1234-trend-1", "source_context_sha256": recovery.retention.json_sha256(source),
        "golden_path_run_id": 123,
    }
    owner = dict(shared, status="DISPATCHED", trend_id="1", topic="SAP prüft einen Stellenabbau",
                 trend_scope="business_economy", language="Deutsch", platform="youtube_tiktok", mode="full",
                 source="telegram_trend_approval", selection_id="20261127-morning-agentv2", telegram_message_id=1234,
                 approved_at="2026-11-27T06:00:00Z", approval_key="telegram:approval", source_context=source,
                 retention_contract_version="v5", approval_required_before_youtube_publish=True, target_duration=35,
                 cta_text="Entdecke mit TAYVORIQ, wie SAP den Umbau vorbereitet.", follow_reason="Wir prüfen die Folgen des konkreten Umbaus.",
                 cta_type="EXPERTISE", open_loop_status="NONE", golden_path_v5_history=[], contabo_handoff={"worker_run_id": 456})
    pointer = dict(shared, state="ACTIVE", execution_backend="contabo_private_runner", execution_run_id=456)
    receipt = dict(schema="tayvoriq-contabo-worker-v1", request_id=owner["request_id"],
                   source_context_sha256=owner["source_context_sha256"], controller_run_id=123, worker_run_id=456,
                   status="FAILED", failed_step="Assert publishable production output", failure_code="SHARED_CTA_INCOMPLETE")
    run = {"id": 123, "status": "completed", "conclusion": "failure", "head_branch": "main",
           "path": ".github/workflows/tayvoriq-deliver-video-now.yml"}
    for name, record in ((f'requests/{owner["request_id"]}.json', owner),
                         (".github/state/tayvoriq-active-production-request.json", pointer),
                         ("run-status/contabo/123.json", receipt)):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        contract.write_json(path, record)

    with patch.object(recovery, "github_json", return_value=run):
        assert recovery.stage(tmp_path, "repo", "token", "999") is None
        receipt_path = tmp_path / "run-status/contabo/123.json"
        contract.write_json(receipt_path, receipt | {"worker_run_id": 999})
        assert recovery.stage(tmp_path, "repo", "token", "123") is None
        contract.write_json(receipt_path, receipt)
        path = recovery.stage(tmp_path, "repo", "token", "123")
        repair = contract.read_json(path)
        assert repair["cta_text"] == "Folge TAYVORIQ und erfahre, wie SAP den Umbau vorbereitet."
        assert repair["source_context"] == source
        assert repair["telegram_message_id"] == owner["telegram_message_id"]
        assert recovery.stage(tmp_path, "repo", "token", "123") == path
        assert contract.read_json(path) == repair
        repair["status"] = "DISPATCHED"
        contract.write_json(path, repair)
        assert recovery.stage(tmp_path, "repo", "token", "123") is None
