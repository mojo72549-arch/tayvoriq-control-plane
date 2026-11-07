"""Keep German/regional publisher diversity in the bounded RSS fallback."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_agent_rss_v2 as rss


def test_rss_pool_does_not_drop_later_independent_publishers(monkeypatch):
    def fake_fetch(feed, url):
        if feed == "tagesschau":
            return [
                {"title": f"News {i}", "context": f"News details {i}",
                 "url": f"https://tagesschau.de/{i}", "domain": "tagesschau.de"}
                for i in range(40)
            ]
        if feed == "swr-bw":
            return [{"title": "Bosch Werk Baden-Württemberg",
                     "context": "Bosch reports an industrial update",
                     "url": "https://swr.de/regional", "domain": "swr.de"}]
        if feed == "deutschlandfunk-news":
            return [{"title": "Bosch Werk Baden-Württemberg",
                     "context": "Independent report about Bosch",
                     "url": "https://deutschlandfunk.de/news",
                     "domain": "deutschlandfunk.de"}]
        if feed.startswith("guardian") or feed.startswith("bbc"):
            return [{"title": f"{feed} update {i}", "context": "International news",
                     "url": f"https://{feed}.example/{i}", "domain": f"{feed}.example"}
                    for i in range(40)]
        return []
    monkeypatch.setattr(rss, "_fetch_one", fake_fetch)
    pool = rss.source_pool()
    hosts = {record["domain"] for record in pool}
    assert "swr.de" in hosts
    assert "deutschlandfunk.de" in hosts
    assert "tagesschau.de" in hosts
    assert len(pool) <= 240
    assert {feed for feed, _ in rss.FEEDS} >= {
        "swr-bw", "deutschlandfunk-news", "deutschlandfunk-economy"
    }


def test_rss_keeps_independent_domains_and_same_url_dedup(monkeypatch):
    def fake_fetch(feed, url):
        if feed in ("tagesschau", "tagesschau-bw"):
            return [{"title": "One article", "context": "One account",
                     "url": "https://tagesschau.de/shared", "domain": "tagesschau.de"}]
        return []
    monkeypatch.setattr(rss, "_fetch_one", fake_fetch)
    pool = rss.source_pool()
    assert [row["url"] for row in pool] == ["https://tagesschau.de/shared"]
