"""Evidence-source regression: diverse, German-focused RSS without live API calls."""
from __future__ import annotations

import io
import json
import sys
import unittest
from email.message import Message
from unittest.mock import Mock, patch
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


def test_domestic_publisher_sections_survive_a_large_foreign_feed_pool(monkeypatch):
    monkeypatch.setattr(rss, "FEEDS", [
        ("national", "https://a.example/news"),
        ("regional", "https://a.example/local"),
        ("economy", "https://b.example/economy"),
        ("bbc-top", "https://bbc.example/news"),
    ])
    monkeypatch.setattr(rss, "_fetch_one", lambda name, url: [
        {"title":name, "context":"detail", "url":f"{url}/{index}", "domain":url.split("/")[2],
         "seen_date":"", "feed":name}
        for index in range(150)
    ])
    records = rss.source_pool()
    assert len(records) == 240
    assert sum(record["feed"] == "bbc-top" for record in records) == 30
    assert all(sum(record["feed"] == feed for record in records) >= 50 for feed in ("national","regional","economy"))


def test_rss_freshness_supports_rfc_and_atom_dates_but_rejects_undated_items(monkeypatch):
    from datetime import datetime

    now = datetime.fromisoformat("2026-11-07T13:00:00+01:00")
    monkeypatch.setattr(rss.time, "time", lambda: now.timestamp())
    assert rss._fresh("Thu, 05 Nov 2026 08:11:00 GMT")
    assert rss._fresh("2026-11-05T08:11:00+00:00")
    assert not rss._fresh("2026-11-04T08:11:00+00:00")
    assert not rss._fresh("2026-11-07T13:01:00+01:00")
    assert not rss._fresh("")


TITLE = "Mutmaßlicher Hackerangriff auf deutschen Softwarekonzern SAP"
DW_URL = (
    "https://www.dw.com/de/mutmaßlicher-hackerangriff-auf-deutschen-softwarekonzern-sap/"
    "a-80072576?maca=de-rss-de-all-1119-xml-mrss"
)
ENCODED_DW_URL = DW_URL.replace("ß", "%C3%9F")
ARTICLE_CONTEXT = "Der Konzern untersucht verdächtige Aktivitäten in seiner IT."


def record(url=DW_URL):
    return {
        "url": url, "title": TITLE, "context": "Erste Meldung zum Vorfall.",
        "domain": "dw.com", "feed": "dw-de",
        "seen_date": "Fri, 27 Nov 2026 10:41:00 GMT", "origin": "DW Redaktion",
        "source_hash": "unchanged-source-binding",
    }


def response():
    article = json.dumps({"@type": "NewsArticle", "headline": TITLE,
                          "description": ARTICLE_CONTEXT})
    stream = io.BytesIO(f'<script type="application/ld+json">{article}</script>'.encode())
    stream.headers = Message()
    stream.headers["Content-Type"] = "text/html; charset=utf-8"
    return stream


class ArticleRequestUrlTests(unittest.TestCase):
    def assert_preserved_provenance(self, before, after):
        self.assertEqual({k: v for k, v in after.items() if k != "context"},
                         {k: v for k, v in before.items() if k != "context"})
        self.assertIn(ARTICLE_CONTEXT, after["context"])

    def test_real_dw_unicode_path_and_unicode_query_reach_opener_encoded(self):
        cases = [
            (DW_URL, ENCODED_DW_URL),
            (DW_URL + "&suche=größer%2Fheute", ENCODED_DW_URL + "&suche=gr%C3%B6%C3%9Fer%2Fheute"),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                original = record(url)
                before = original.copy()
                opener = Mock()
                opener.open.return_value = response()
                with patch.object(rss.urllib.request, "build_opener", return_value=opener):
                    enriched = rss.enrich_article(original)
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, expected)
                request.selector.encode("ascii")
                self.assertEqual(opener.open.call_args.kwargs, {"timeout": 5})
                self.assertEqual(original, before)
                self.assert_preserved_provenance(before, enriched)

    def test_existing_percent_escapes_are_not_double_encoded(self):
        url = ENCODED_DW_URL + "&suche=gr%C3%B6%C3%9Fer%2Fheute#ref=rss"
        original = record(url)
        opener = Mock()
        opener.open.return_value = response()
        with patch.object(rss.urllib.request, "build_opener", return_value=opener):
            enriched = rss.enrich_article(original)
        self.assertEqual(opener.open.call_args.args[0].full_url, url)
        self.assert_preserved_provenance(original, enriched)

    def test_same_publisher_redirect_is_encoded_without_rebinding_source(self):
        original = record()
        redirect_url = "https://www.dw.com/de/aktualisiert-weiß/a-80072576?suche=größer%2Fheute"
        expected = "https://www.dw.com/de/aktualisiert-wei%C3%9F/a-80072576?suche=gr%C3%B6%C3%9Fer%2Fheute"
        redirected = []

        def build(handler):
            def open_article(request, timeout):
                redirected.append(handler.redirect_request(request, None, 302, "Found", {}, redirect_url))
                return response()
            return Mock(open=Mock(side_effect=open_article))

        with patch.object(rss.urllib.request, "build_opener", side_effect=build):
            enriched = rss.enrich_article(original)
        self.assertEqual(redirected[0].full_url, expected)
        redirected[0].selector.encode("ascii")
        self.assert_preserved_provenance(original, enriched)

    def test_encoding_does_not_allow_ineligible_sources_or_redirects(self):
        blocked = [
            "http://www.dw.com/de/weiß", "https://example.com/de/weiß",
            "https://user@www.dw.com/de/weiß", "https://www.dw.com:443/de/weiß",
        ]
        for url in blocked:
            with self.subTest(url=url), patch.object(rss.urllib.request, "build_opener") as build:
                original = record(url)
                self.assertIs(rss.enrich_article(original), original)
                build.assert_not_called()

            def build_redirect(handler):
                def open_article(request, timeout):
                    return handler.redirect_request(request, None, 302, "Found", {}, url)
                return Mock(open=Mock(side_effect=open_article))

            with self.subTest(redirect=url), \
                    patch.object(rss.urllib.request, "build_opener", side_effect=build_redirect), \
                    patch.object(rss, "article_context") as context:
                original = record()
                self.assertIs(rss.enrich_article(original), original)
                context.assert_not_called()
