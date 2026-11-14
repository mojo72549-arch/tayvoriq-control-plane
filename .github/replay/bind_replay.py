import json
import os
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path("tools").resolve()))
from tayvoriq_orchestration_contract import validate
from tayvoriq_global_duplicate_gate_v1 import run_gate

rid = os.environ["REPLAY_REQUEST_ID"]
if not re.fullmatch(r"telegram-[0-9]+-trend-[0-9]+", rid):
    raise SystemExit("REPLAY_REQUEST_ID_INVALID")
request_file = Path("requests") / f"{rid}.json"
request = json.loads(request_file.read_text(encoding="utf-8"))
history = request.get("state_history") or []
substate = request.get("codefix_recovery") or {}
if history and history[-1].get("state") == "AWAITING_CODEFIX":
    if (substate.get("status") != "ARMED" or substate.get("request_substate") != "AWAITING_CODEFIX"
            or substate.get("failed_run_id") != request.get("golden_path_run_id")
            or history[-1].get("meta", {}).get("failed_run_id") != request.get("golden_path_run_id")):
        raise SystemExit("REPLAY_REQUEST_HISTORY_UNBOUND")
    validate({**request, "state_history": [*history, {"state": request["status"]}]})
else:
    validate(request)
if (request["request_id"] != rid or request["source"] != "telegram_trend_approval"
        or request["status"] != "DISPATCHED" or request.get("production_completion")
        or request.get("publication")):
    raise SystemExit("REPLAY_REQUEST_NOT_ELIGIBLE")
source = request["source_context"]
if source.get("independent_news_count", 0) < 2:
    raise SystemExit("REPLAY_REQUEST_SOURCE_EVIDENCE_MISSING")
duplicate = run_gate(requests_dir=Path("requests"), source_request_id=rid,
                     topic=request["topic"], source_context=source)
if not duplicate.get("passed"):
    raise SystemExit("REPLAY_REQUEST_DUPLICATE")
out = Path("replay")
out.mkdir(exist_ok=True)
(out / "source.json").write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
(out / "binding.json").write_text(json.dumps({
    "request_id": rid, "source_context_sha256": request["source_context_sha256"],
    "contract_sha256": request["contract_sha256"], "content_angle": request["content_angle"],
    "run_id": os.environ["GITHUB_RUN_ID"], "studio_sha": os.environ["STUDIO_SHA"],
}, ensure_ascii=False), encoding="utf-8")
