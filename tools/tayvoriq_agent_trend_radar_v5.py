#!/usr/bin/env python3
from __future__ import annotations
import tayvoriq_agent_trend_radar_v4 as growth
import tayvoriq_agent_research_resilience_v2 as resilience
base=growth.base
resilience.install()
if __name__=='__main__': raise SystemExit(base.main())
