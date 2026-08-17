#!/usr/bin/env python3
from __future__ import annotations

# Compatibility adapter: an active series no longer bypasses fresh trend
# research. The current episode is injected as one candidate by Growth V2 and
# must earn its place against today's strongest stories.
import tayvoriq_agent_trend_radar_v4 as growth

base = growth.base

if __name__ == "__main__":
    raise SystemExit(base.main())
