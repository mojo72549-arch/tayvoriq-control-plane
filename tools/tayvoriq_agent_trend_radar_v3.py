#!/usr/bin/env python3
from __future__ import annotations

# Compatibility entrypoint: keep the existing workflow command stable while
# routing trend selection through Growth V2. The grounded provider itself is
# preserved in tayvoriq_agent_trend_provider_v3.py.
import tayvoriq_agent_trend_radar_v4 as growth

base = growth.base

if __name__ == "__main__":
    raise SystemExit(base.main())
