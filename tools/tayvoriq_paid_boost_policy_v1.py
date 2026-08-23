#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("config/tayvoriq_growth_runtime_v2.json")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return value


def evaluate(metrics: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    promo = ((config.get("audience_growth") or {}).get("promotion_test") or {})
    target = float(promo.get("requested_total_budget_eur") or 0)
    hard_cap = float(promo.get("hard_max_total_budget_eur") or 0)
    if target <= 0 or hard_cap <= 0 or target > hard_cap:
        raise SystemExit("Invalid paid boost budget policy")

    reasons: list[str] = []
    if str(metrics.get("platform") or "") != str(promo.get("platform") or "youtube_shorts"):
        reasons.append("wrong_platform")

    checkpoint = float(promo.get("evaluation_checkpoint_hours_after_publish") or 2)
    if float(metrics.get("hours_since_publish") or 0) < checkpoint:
        reasons.append("too_early")

    observed = metrics.get("observed") if isinstance(metrics.get("observed"), dict) else {}
    baseline = metrics.get("rolling_baseline") if isinstance(metrics.get("rolling_baseline"), dict) else {}
    comparable = (
        "engaged_or_qualified_views",
        "retention_or_completion",
        "subscriber_conversion_per_1000",
    )
    for key in comparable:
        if key not in observed or key not in baseline:
            reasons.append(f"missing_{key}")
            continue
        if float(observed[key]) < float(baseline[key]):
            reasons.append(f"below_baseline_{key}")

    if bool(metrics.get("policy_restriction")):
        reasons.append("policy_restriction")
    if not bool(metrics.get("publishable", True)):
        reasons.append("not_publishable")

    max_tests = int(promo.get("max_tests_per_week") or 0)
    weekly_cap = float(promo.get("max_weekly_spend_eur") or 0)
    monthly_cap = float(promo.get("max_monthly_spend_eur") or 0)
    tests_week = int(metrics.get("tests_started_this_week") or 0)
    spend_week = float(metrics.get("spend_eur_this_week") or 0)
    spend_month = float(metrics.get("spend_eur_this_month") or 0)

    if max_tests and tests_week >= max_tests:
        reasons.append("weekly_test_limit")
    if weekly_cap and spend_week + target > weekly_cap + 1e-9:
        reasons.append("weekly_spend_cap")
    if monthly_cap and spend_month + target > monthly_cap + 1e-9:
        reasons.append("monthly_spend_cap")

    eligible = not reasons
    credentials = bool(metrics.get("ads_credentials_present"))
    auto_requested = bool(promo.get("auto_spend_requested"))
    auto_enabled = bool(promo.get("auto_spend_enabled"))

    if not eligible:
        action = "NO_BOOST"
    elif not credentials:
        action = "BOOST_CANDIDATE_NO_CREDENTIALS"
    elif auto_requested and auto_enabled:
        action = "READY_TO_AUTO_BOOST"
    else:
        action = "BOOST_CANDIDATE_AUTOSPEND_DISABLED"

    return {
        "eligible": eligible,
        "action": action,
        "platform": promo.get("platform", "youtube_shorts"),
        "currency": promo.get("currency", "EUR"),
        "requested_total_budget_eur": target,
        "hard_max_total_budget_eur": hard_cap,
        "must_never_exceed_hard_cap": True,
        "actual_spend_may_be_lower_due_to_auction_delivery": True,
        "reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", required=True)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output")
    args = parser.parse_args()

    result = evaluate(_load(Path(args.metrics)), _load(Path(args.config)))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
