from __future__ import annotations

import concurrent.futures
from collections import defaultdict, deque
import html
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http

base = provider.base
FEEDS = [
    # Original German regional/national publishers first: less global filler and
    # more independently reported Germany/BW stories for strict two-source gates.
    ("ntv-wirtschaft", "https://www.n-tv.de/wirtschaft/rss"),
    ("ntv-auto", "https://www.n-tv.de/auto/rss"),
    ("land-bw-wirtschaft", "https://www.baden-wuerttemberg.de/de/service/rss/xml/rss-wirtschaft-arbeit-finanzen"),
    ("land-bw-verkehr", "https://www.baden-wuerttemberg.de/de/service/rss/xml/rss-energie-umwelt-verkehr"),
    ("swr-baden-wuerttemberg", "https://www.swr.de/~rss/swraktuell/swraktuell-bw-100.xml"),
    ("deutschlandfunk-nachrichten", "https://www.deutschlandfunk.de/nachrichten-100.rss"),
    ("deutschlandfunk-wirtschaft", "https://www.deutschlandfunk.de/wirtschaft-106.rss"),
    ("zdf-heute", "https://www.zdf.de/rss/zdf/nachrichten"),
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
    try:
        dt = parsedate_to_datetime(pub)
    except (ValueError, TypeError):
        try:
            dt = datetime.fromisoformat(pub)
        except (ValueError, TypeError):
            return False
    return bool(dt and dt.tzinfo and 0 <= time.time() - dt.timestamp() <= 72 * 3600)


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
        pub = _first(node, ("pubdate", "published", "issued", "date"))
        link = _link(node)
        publisher = _domain(link)
        if not title or not context or not link or not publisher or not _fresh(pub):
            continue
        if any(marker in link.casefold() for marker in base.BLOCKED_SOURCE_MARKERS):
            continue
        origin = _first(node, ("creator", "author", "source"))
        records.append({"title": title, "context": context, "url": link, "domain": publisher,
                        "seen_date": pub, "feed": feed_name, "origin": origin})
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
    # Previously the first 240 URLs starved later publishers (including DW).
    # Round-robin by publisher so source matching can find independent reports.
    by_publisher = defaultdict(deque)
    for record in dedup.values():
        by_publisher[record["domain"]].append(record)
    out = []
    active = list(by_publisher)
    while active and len(out) < 240:
        remaining = []
        for publisher in active:
            if len(out) >= 240:
                break
            if by_publisher[publisher]:
                out.append(by_publisher[publisher].popleft())
            if by_publisher[publisher]:
                remaining.append(publisher)
        active = remaining
    print(json.dumps({"event": "rss_source_pool", "records": len(out), "independent_publishers": len({r['domain'] for r in out}), "publishers": sorted({r['domain'] for r in out}), "feed_failures": failures[:16]}, ensure_ascii=False))
    return out
