#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, re
from pathlib import Path

# Active series no longer bypass fresh research. If a series episode really
# earns a Top-5 position, preserve the historical -agentv2- series id contract.
import tayvoriq_agent_trend_radar_v4 as growth
base = growth.base


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--slot", choices=["morning", "evening"], required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    args, _ = parser.parse_known_args()
    result = base.main()
    if result != 0:
        return int(result)

    output = Path(args.output)
    audit_path = Path(args.audit_output)
    request = json.loads(output.read_text(encoding="utf-8"))
    series = None
    for trend in request.get("trends") or []:
        source = trend.get("source_context") if isinstance(trend, dict) else {}
        ctx = source.get("series_context") if isinstance(source, dict) else None
        if isinstance(ctx, dict) and ctx.get("series_id"):
            series = ctx
            break
    if not series:
        return 0

    token = re.sub(r"[^A-Za-z0-9_-]", "", str(series.get("series_id") or "series"))[:10] or "series"
    episode = int(series.get("episode") or 0)
    date_token = str(request.get("date") or "").replace("-", "")
    selection_id = f"{date_token}-{args.slot[0]}-agentv2-{token}-e{episode}"
    request["selection_id"] = selection_id
    request["series_competed_in_growth_ranking"] = True
    output.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if audit_path.is_file():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audit.update({
            "selection_id": selection_id,
            "series_candidate_injected": True,
            "series_bypassed_trend_radar": False,
            "series_competed_in_growth_ranking": True,
        })
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
