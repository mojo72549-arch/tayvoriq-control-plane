#!/usr/bin/env python3
from __future__ import annotations

# Compatibility entrypoint: keep the existing workflow command stable while
# routing trend selection through Growth V2, resilient research and source-cluster dedupe.
import tayvoriq_agent_trend_radar_v6 as growth

base = growth.base

if __name__ == "__main__":
    raise SystemExit(base.main())
