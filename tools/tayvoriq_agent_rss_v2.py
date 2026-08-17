from __future__ import annotations

import concurrent.futures
import html
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http

base = provider.base
FEEDS = [
    ("tagesschau", "https://www.tagesschau.de/index~rss2.xml"),
    ("tagesschau-bw", "https://www.tagesschau.de/inland/regional/badenwuerttemberg/index~rss2.xml"),
    ("tagesschau-wirtschaft", "https://www.tagesschau.de/wirtschaft/index~rss2.xml"),
    ("tagesschau-wissen", "https://www.tagesschau.de/wissen/index~rss2.xml"),
    ("guardian-world", "https://www.theguardian.com/world/rss"),
    ("guardian-tech", "https://www.theguardian.com/technology/rss"),
    ("guardian-business", "https://www.theguardian.com/business/rss"),
    ("guardian-sport", "https://www.theguardian.com/sport/rss"),
    ("bbc-top", "https://feeds.bbci.co.uk/news/rss.xml"),
    ("bbc-world", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("bbc-tech", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
    ("bbc-business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("bbc-sport", "https://feeds.bbci.co.uk/sport/rss.xml"),
    ("dw-de", "https://rss.dw.com/xml/rss-de-all"),
    ("dw-en", "https://rss.dw.com/xml/rss-en-all"),
    ("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
]
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def _domain(url: str) -> str:
    host = urlparse(url).netloc.casefold().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if host.endswith(("bbc.co.uk", "bbc.com")):
        return "bbc.com"
    if host.endswith("tagesschau.de"):
        return "tagesschau.de"
    if host.endswith("theguardian.com"):
        return "theguardian.com"
    if host.endswith("dw.com"):
        return "dw.com"
    if host.endswith("aljazeera.com"):
        return "aljazeera.com"
    return host


def _text(value: str | None, limit: int = 2200) -> str:
    cleaned = html.unescape(TAG_RE.sub(" ", value or ""))
    return SPACE_RE.sub(" ", cleaned).strip()[:limit]


def _first(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in node.iter():
        local = child.tag.rsplit("}", 1)[-1].casefold()
        if local in names and child.text:
            value = _text(child.text)
            if value:
                return value
    return ""


def _link(node: ET.Element) -> str:
    for child in node.iter():
        if child.tag.rsplit("}", 1)[-1].casefold() != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        if href.startswith(("https://", "http://")):
            return href
        text = _text(child.text, 2000)
        if text.startswith(("https://", "http://")):
            return text
    return ""


def _fresh(pub: str) -> bool:
    if not pub:
        return True
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            return True
        return (time.time() - dt.timestamp()) <= 60 * 60 * 48
    except Exception:
        return True


def _fetch_one(feed_name: str, url: str) -> list[dict[str, str]]:
    req = urllib.request.Request(url, headers={"User-Agent": "tayvoriq-agent-v3-rss"})
    with urllib.request.urlopen(req, timeout=8) as response:
        root = ET.fromstring(response.read())
    records: list[dict[str, str]] = []
    for node in root.iter():
        local = node.tag.rsplit("}", 1)[-1].casefold()
        if local not in {"item", "entry"}:
            continue
        title = _first(node, ("title",))
        context = _first(node, ("description", "summary", "content", "encoded"))
        pub = _first(node, ("pubdate", "published", "updated", "date"))
        link = _link(node)
        publisher = _domain(link)
        if not title or not context or not link or not publisher or not _fresh(pub):
            continue
        if any(marker in link.casefold() for marker in base.BLOCKED_SOURCE_MARKERS):
            continue
        records.append({"title": title, "context": context, "url": link, "domain": publisher, "seen_date": pub, "feed": feed_name})
    return records[:40]


def source_pool() -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    failures: list[dict[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(_fetch_one, name, url): (name, url) for name, url in FEEDS}
        for future, meta in list(futures.items()):
            name, url = meta
            try:
                records.extend(future.result(timeout=12))
            except Exception as exc:
                failures.append({"feed": name, "url": url, "error": http.summary(exc)})
    dedup: dict[str, dict[str, str]] = {}
    for record in records:
        dedup.setdefault(record["url"], record)
    out = list(dedup.values())[:240]
    print(json.dumps({"event": "rss_source_pool", "records": len(out), "independent_publishers": len({r['domain'] for r in out}), "publishers": sorted({r['domain'] for r in out}), "feed_failures": failures[:16]}, ensure_ascii=False))
    return out
