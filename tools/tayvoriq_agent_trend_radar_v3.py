#!/usr/bin/env python3
from __future__ import annotations

# Compatibility entrypoint: keep the existing workflow command stable while
# routing trend selection through audience-growth scoring, resilient research,
# source-cluster dedupe, brand-safety and the existing fail-closed editorial gates.
import tayvoriq_agent_trend_radar_v8 as growth

base = growth.base

if __name__ == "__main__":
    raise SystemExit(base.main())
