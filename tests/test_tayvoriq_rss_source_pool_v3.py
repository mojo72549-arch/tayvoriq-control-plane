"""Evidence-source regression: diverse, German-focused RSS without live API calls."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import tayvoriq_agent_rss_v2 as rss


def test_regional_and_german_independent_feeds_are_configured():
    entries = dict(rss.FEEDS)
    assert entries["swr-baden-wuerttemberg"].startswith("https://www.swr.de/")
    assert entries["deutschlandfunk-nachrichten"].startswith("https://www.deutschlandfunk.de/")
    assert entries["deutschlandfunk-wirtschaft"].startswith("https://www.deutschlandfunk.de/")
    assert entries["zdf-heute"].startswith("https://www.zdf.de/")
    assert "tagesschau" in entries


def test_large_early_feed_does_not_starve_independent_publishers(monkeypatch):
    # No network calls; make the earliest feed yield far more than the cap.
    monkeypatch.setattr(rss, "FEEDS", [
        ("one", "https://one.example/feed"),
        ("two", "https://two.example/feed"),
        ("three", "https://three.example/feed"),
    ])

    def fake_fetch(name, url):
        domain = url.split("/")[2]
        return [
            {"title": f"{name} {i}", "context": f"Detail {i}",
             "url": f"https://{domain}/{i}", "domain": domain,
             "seen_date": "", "feed": name}
            for i in range(150)
        ]

    monkeypatch.setattr(rss, "_fetch_one", fake_fetch)
    records = rss.source_pool()
    assert len(records) == 240
    domains = [r["domain"] for r in records]
    assert set(domains) == {"one.example", "two.example", "three.example"}
    assert all(domains.count(name) == 80 for name in set(domains))
    assert len({r["url"] for r in records}) == len(records)


def test_source_pool_keeps_article_urls_and_does_not_invent_cross_source_claims(monkeypatch):
    monkeypatch.setattr(rss, "FEEDS", [("one", "https://one.example/feed"), ("two", "https://two.example/feed")])
    monkeypatch.setattr(rss, "_fetch_one", lambda name, url: [
        {"title": name, "context": "Original source snippet",
         "url": f"https://{name}.example/article", "domain": f"{name}.example",
         "seen_date": "", "feed": name}
    ])
    records = rss.source_pool()
    assert len(records) == 2
    assert all(x["context"] == "Original source snippet" for x in records)
    assert {r["url"] for r in records} == {
        "https://one.example/article", "https://two.example/article",
    }
