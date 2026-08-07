#!/usr/bin/env python3
"""Fail-closed orchestration contract for TAYVORIQ.

This module is intentionally dependency-free so the control-plane can validate
approval -> claim -> dispatch transitions before any media production starts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CLAIMABLE = {"APPROVED", "TREND_APPROVED", "READY_FOR_PRODUCTION"}
ALL_STATES = CLAIMABLE | {"DISPATCHING", "DISPATCHED", "DISPATCH_FAILED"}
SCOPES = {
    "auto_scope",
    "technology_ai",
    "business_economy",
    "world_society",
    "sports",
    "creator_media",
    "mobility_energy",
    "science_future",
}
EXECUTION_MODES = {"full", "quality_gate_only"}
TRANSITIONS = {
    "APPROVED": {"DISPATCHING"},
    "TREND_APPROVED": {"DISPATCHING"},
    "READY_FOR_PRODUCTION": {"DISPATCHING"},
    "DISPATCHING": {"DISPATCHED", "DISPATCH_FAILED"},
    "DISPATCH_FAILED": {"APPROVED"},
    "DISPATCHED": set(),
}
IMMUTABLE_FIELDS = (
    "request_id",
    "trend_id",
    "topic",
    "trend_scope",
    "language",
    "platform",
    "target_duration",
    "approval_required_before_youtube_publish",
    "approval_key",
    "mode",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_iso(value: str) -> None:
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def contract_hash(data: dict) -> str:
    payload = {k: data.get(k) for k in IMMUTABLE_FIELDS}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate(data: dict, *, require_claimable: bool = False) -> None:
    errors: list[str] = []
    request_id = str(data.get("request_id") or "").strip()
    status = str(data.get("status") or "").upper().strip()
    trend_id = str(data.get("trend_id") or "").strip()
    topic = str(data.get("topic") or "").strip()
    scope = str(data.get("trend_scope") or "").strip()
    language = str(data.get("language") or "").strip()
    platform = str(data.get("platform") or "").strip()
    approval_key = str(data.get("approval_key") or "").strip()
    mode = str(data.get("mode") or "").strip()

    if not request_id:
        errors.append("missing request_id")
    if status not in ALL_STATES:
        errors.append(f"invalid status={status!r}")
    if require_claimable and status not in CLAIMABLE:
        errors.append(f"status is not claimable: {status!r}")
    if trend_id not in {"1", "2", "3", "4", "5"}:
        errors.append(f"invalid trend_id={trend_id!r}")
    if not topic:
        errors.append("missing topic")
    if scope not in SCOPES:
        errors.append(f"invalid trend_scope={scope!r}")
    if language not in {"Deutsch", "de"}:
        errors.append(f"invalid language={language!r}")
    if platform != "youtube_tiktok":
        errors.append(f"invalid platform={platform!r}")
    if mode not in EXECUTION_MODES:
        errors.append(f"invalid mode={mode!r}")
    if data.get("approval_required_before_youtube_publish") is not True:
        errors.append("youtube approval gate must be true")
    try:
        duration = int(data.get("target_duration"))
        if duration < 35 or duration > 60:
            errors.append(f"target_duration out of range: {duration}")
    except Exception:
        errors.append("target_duration must be an integer")
    if not approval_key:
        errors.append("missing approval_key")
    approved_at = str(data.get("approved_at") or "").strip()
    if status in CLAIMABLE | {"DISPATCHING", "DISPATCHED"}:
        if not approved_at:
            errors.append("missing approved_at")
        else:
            try:
                parse_iso(approved_at)
            except Exception:
                errors.append(f"invalid approved_at={approved_at!r}")

    expected = contract_hash(data)
    actual = str(data.get("contract_sha256") or "").strip()
    if actual != expected:
        errors.append("contract_sha256 mismatch")

    history = data.get("state_history")
    if not isinstance(history, list) or not history:
        errors.append("missing state_history")
    elif str(history[-1].get("state") or "").upper() != status:
        errors.append("state_history does not end in current status")

    if errors:
        raise SystemExit("ORCHESTRATION_CONTRACT_FAILED: " + "; ".join(errors))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def create_from_telegram(args: argparse.Namespace) -> None:
    trend_id = str(args.trend_id).strip()
    message_id = str(args.message_id).strip()
    if trend_id not in {"1", "2", "3", "4", "5"}:
        raise SystemExit(f"invalid trend id: {trend_id!r}")
    if not message_id.isdigit():
        raise SystemExit("telegram message_id is required for idempotency")

    trend_request = read_json(Path(args.trend_request))
    selected = str(trend_request.get("selected_trend_id") or "").strip()
    if selected != trend_id:
        raise SystemExit(
            f"STALE_OR_WRONG_APPROVAL: callback trend {trend_id} != current selected trend {selected}"
        )
    trends = trend_request.get("trends") or []
    trend = next((t for t in trends if str(t.get("id")) == trend_id), None)
    if not trend:
        raise SystemExit(f"trend {trend_id} not present in canonical trend request")
    canonical_topic = str(trend.get("title") or "").strip()
    if not canonical_topic:
        raise SystemExit("canonical trend has no title")

    payload_topic = str(args.payload_topic or "").strip()
    if payload_topic and canonical_topic not in payload_topic and payload_topic not in canonical_topic:
        raise SystemExit("STALE_OR_WRONG_APPROVAL: Telegram topic does not match canonical selected trend")

    request_id = f"telegram-{message_id}-trend-{trend_id}"
    path = Path(args.out_dir) / f"{request_id}.json"
    if path.exists():
        existing = read_json(path)
        validate(existing)
        if str(existing.get("approval_key")) != f"telegram:{message_id}:trend:{trend_id}":
            raise SystemExit("idempotency collision for existing request")
        print(path)
        return

    approved_at = str(args.approved_at or "").strip() or utc_now()
    parse_iso(approved_at)
    scope = "technology_ai" if trend_id == "1" else "auto_scope"
    data = {
        "request_id": request_id,
        "status": "APPROVED",
        "source": "telegram_trend_approval",
        "trend_id": trend_id,
        "topic": canonical_topic,
        "trend_scope": scope,
        "language": "Deutsch",
        "platform": "youtube_tiktok",
        "target_duration": 35,
        "approval_required_before_youtube_publish": True,
        "tiktok_delivery": "telegram_manual",
        "approved_at": approved_at,
        "telegram_message_id": int(message_id),
        "approval_key": f"telegram:{message_id}:trend:{trend_id}",
        "mode": "full",
        "state_history": [
            {"state": "APPROVED", "at": approved_at, "actor": "telegram_callback"}
        ],
    }
    data["contract_sha256"] = contract_hash(data)
    validate(data, require_claimable=True)
    write_json(path, data)
    print(path)


def validate_file(args: argparse.Namespace) -> None:
    data = read_json(Path(args.path))
    validate(data, require_claimable=args.require_claimable)
    print(json.dumps({
        "contract": "passed",
        "request_id": data["request_id"],
        "status": data["status"],
        "mode": data["mode"],
        "contract_sha256": data["contract_sha256"],
    }))


def transition(args: argparse.Namespace) -> None:
    path = Path(args.path)
    data = read_json(path)
    validate(data)
    current = str(data["status"]).upper()
    target = str(args.to).upper()
    allowed = TRANSITIONS.get(current, set())
    if target not in allowed:
        raise SystemExit(f"ILLEGAL_STATE_TRANSITION: {current} -> {target}")
    at = utc_now()
    data["status"] = target
    data.setdefault("state_history", []).append({
        "state": target,
        "at": at,
        "actor": args.actor,
    })
    for item in args.meta or []:
        if "=" not in item:
            raise SystemExit(f"invalid --meta value: {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit("empty metadata key")
        if value.isdigit():
            data[key] = int(value)
        else:
            data[key] = value
    if data.get("contract_sha256") != contract_hash(data):
        raise SystemExit("immutable request fields changed during transition")
    validate(data)
    write_json(path, data)
    print(json.dumps({"transition": f"{current}->{target}", "request_id": data["request_id"]}))


def self_test(_: argparse.Namespace) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "request.json"
        now = utc_now()
        good = {
            "request_id": "selftest-1",
            "status": "APPROVED",
            "source": "self_test",
            "trend_id": "1",
            "topic": "Self-test topic",
            "trend_scope": "technology_ai",
            "language": "Deutsch",
            "platform": "youtube_tiktok",
            "target_duration": 35,
            "approval_required_before_youtube_publish": True,
            "approved_at": now,
            "approval_key": "selftest:1",
            "mode": "quality_gate_only",
            "state_history": [{"state": "APPROVED", "at": now, "actor": "self_test"}],
        }
        good["contract_sha256"] = contract_hash(good)
        write_json(p, good)
        validate(read_json(p), require_claimable=True)

        bad = dict(good)
        bad["topic"] = "tampered"
        try:
            validate(bad)
        except SystemExit:
            pass
        else:
            raise SystemExit("self-test failed: tamper was not detected")

        wrong_mode = dict(good)
        wrong_mode["mode"] = "full"
        try:
            validate(wrong_mode)
        except SystemExit:
            pass
        else:
            raise SystemExit("self-test failed: execution-mode tamper was not detected")

        if "DISPATCHING" not in TRANSITIONS["APPROVED"]:
            raise SystemExit("self-test failed: APPROVED cannot enter DISPATCHING")
        if "DISPATCHED" not in TRANSITIONS["DISPATCHING"]:
            raise SystemExit("self-test failed: DISPATCHING cannot enter DISPATCHED")
        if TRANSITIONS["DISPATCHED"]:
            raise SystemExit("self-test failed: DISPATCHED must be terminal")
        if "DISPATCHED" in TRANSITIONS["APPROVED"]:
            raise SystemExit("self-test failed: direct APPROVED->DISPATCHED must be forbidden")

    print("ORCHESTRATION_SELF_TEST_PASSED")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("self-test")
    s.set_defaults(func=self_test)

    v = sub.add_parser("validate")
    v.add_argument("path")
    v.add_argument("--require-claimable", action="store_true")
    v.set_defaults(func=validate_file)

    c = sub.add_parser("create-from-telegram")
    c.add_argument("--trend-request", required=True)
    c.add_argument("--trend-id", required=True)
    c.add_argument("--message-id", required=True)
    c.add_argument("--payload-topic", default="")
    c.add_argument("--approved-at", default="")
    c.add_argument("--out-dir", default="requests")
    c.set_defaults(func=create_from_telegram)

    t = sub.add_parser("transition")
    t.add_argument("path")
    t.add_argument("--to", required=True)
    t.add_argument("--actor", required=True)
    t.add_argument("--meta", action="append", default=[])
    t.set_defaults(func=transition)
    return p


if __name__ == "__main__":
    args = parser().parse_args()
    args.func(args)
