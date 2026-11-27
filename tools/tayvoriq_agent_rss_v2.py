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
from urllib.parse import quote, urlparse

import tayvoriq_agent_trend_provider_v3 as provider
import tayvoriq_agent_research_http_v2 as http

base = provider.base
FEEDS = [
    # Original German regional/national publishers first: less global filler and
    # more independently reported Germany/BW stories for strict two-source gates.
    ("stuttgart-presse", "https://www.stuttgart.de/pressemitteilungen/?action=submit&sp%3Acmp=search-1-0-searchResult&sp%3Aout=rss"),
    ("lkz-stadt", "https://www.lkz.de/feed/6-RSS_Feed_Stadt_Ludwigsburg.xml"),
    ("lkz-kreis", "https://www.lkz.de/feed/7-RSS_Feed_Kreis_Ludwigsburg.xml"),
    ("zeit-nachrichten", "https://newsfeed.zeit.de/index"),
    ("faz-wirtschaft", "https://www.faz.net/rss/aktuell/wirtschaft/"),
    ("zeit-wirtschaft", "https://newsfeed.zeit.de/wirtschaft/index"),
    ("spiegel-schlagzeilen", "https://www.spiegel.de/schlagzeilen/index.rss"),
    ("ntv-wirtschaft", "https://www.n-tv.de/wirtschaft/rss"),
    ("ntv-auto", "https://www.n-tv.de/auto/rss"),
    ("ntv-politik", "https://www.n-tv.de/politik/rss"),
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
    ("sz-wirtschaft", "https://rss.sueddeutsche.de/rss/Wirtschaft"),
    ("sz-auto", "https://rss.sueddeutsche.de/rss/auto"),
    ("handelsblatt", "https://feeds.cms.handelsblatt.com/schlagzeilen"),
    ("manager-magazin", "https://www.manager-magazin.de/index.rss"),
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
ARTICLE_DATA_RE = re.compile(
    r'<script\b[^>]*\btype=["\']application/ld\+json["\'][^>]*>(.*?)</script\s*>',
    re.IGNORECASE | re.DOTALL,
)


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


def source_pool(*, expanded: bool = False) -> list[dict[str, str]]:
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
    domestic, other = defaultdict(lambda: defaultdict(deque)), defaultdict(lambda: defaultdict(deque))
    for record in dedup.values():
        foreign_feed = record["feed"].startswith(("bbc-", "guardian-", "aljazeera", "dw-en"))
        group = other if foreign_feed else domestic
        group[record["domain"]][record["feed"]].append(record)

    def balanced(group):
        # Alternate sections inside a publisher before advancing to another
        # publisher. A national feed must not crowd out its regional section.
        publishers = deque(deque(sections.values()) for sections in group.values())
        while publishers:
            sections = publishers.popleft()
            queue = sections.popleft()
            yield queue.popleft()
            if queue:
                sections.append(queue)
            if sections:
                publishers.append(sections)

    primary = list(balanced(domestic))
    domestic_limit, total_limit = (620, 660) if expanded else (210, 240)
    out = primary[:domestic_limit]
    out.extend(list(balanced(other))[:total_limit - len(out)])
    out.extend(primary[domestic_limit:domestic_limit + total_limit - len(out)])
    print(json.dumps({"event": "rss_source_pool", "records": len(out), "independent_publishers": len({r['domain'] for r in out}), "publishers": sorted({r['domain'] for r in out}), "feed_failures": failures[:16]}, ensure_ascii=False))
    return out


def article_context(page, original_title):
    """Read publisher-provided text for the same article, excluding paywalled bodies."""
    from tayvoriq_source_evidence_v1 import _words

    original = _words(original_title)
    for script in ARTICLE_DATA_RE.findall(page):
        try:
            data = json.loads(script)
        except ValueError:
            continue
        candidates = data.get("@graph", [data]) if isinstance(data, dict) else data
        if not isinstance(candidates, list):
            continue
        for item in candidates:
            if not isinstance(item, dict):
                continue
            kinds = item.get("@type") or []
            kinds = [kinds] if isinstance(kinds, str) else kinds
            if not isinstance(kinds, list) or not any(
                kind in ("Article", "NewsArticle", "ReportageNewsArticle") for kind in kinds
            ):
                continue
            headline = _words(str(item.get("headline") or ""))
            if len(original & headline) < max(3, (len(original) * 3 + 3) // 4):
                continue
            body = "" if str(item.get("isAccessibleForFree")).lower() == "false" else item.get("articleBody")
            description = _text(str(item.get("description") or ""), 300)
            excerpt = _text(str(body or ""), 850)
            return " ".join(part for part in (description, excerpt) if part).strip()
    return ""


def _article_request_url(url):
    """Encode the HTTP target without changing the original source identity."""
    parsed = urlparse(url)
    return parsed._replace(
        path=quote(parsed.path, safe="/%:@!$&'()*+,;="),
        params=quote(parsed.params, safe="%:@!$&'()*+,;="),
        query=quote(parsed.query, safe="/?%:@!$&'()*+,;="),
    ).geturl()


def enrich_article(record):
    url = record["url"]
    parsed = urlparse(url)
    publisher = _domain(url)
    feed_publishers = {_domain(feed_url) for _, feed_url in FEEDS} | {
        "handelsblatt.com", "sportschau.de", "sueddeutsche.de", "zdfheute.de",
    }
    if (parsed.scheme != "https" or parsed.username or parsed.password or publisher not in feed_publishers
            or parsed.netloc.casefold() not in {publisher, "www." + publisher}):
        return record

    class SamePublisherRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            target = urlparse(newurl)
            if target.scheme != "https" or target.netloc.casefold() not in {publisher, "www." + publisher}:
                raise ValueError("Article redirect leaves the original publisher")
            return super().redirect_request(req, fp, code, msg, headers, _article_request_url(newurl))

    request = urllib.request.Request(_article_request_url(url), headers={"User-Agent": "tayvoriq-agent-v3-rss", "Accept": "text/html"})
    try:
        opener = urllib.request.build_opener(SamePublisherRedirect())
        with opener.open(request, timeout=5) as response:
            if response.headers.get_content_type() != "text/html":
                return record
            document = response.read(650_000).decode(response.headers.get_content_charset() or "utf-8", "replace")
    except (OSError, ValueError, LookupError):
        return record
    context = article_context(document, record["title"])
    original = record.get("context") or ""
    if not context or context.casefold() in original.casefold():
        return record
    limit = max(0, 1350 - len(record["title"]) - len(original) - 1)
    if limit == 0:
        return record
    return {**record, "context": f"{original} {context[:limit]}".strip()}


def enrich_evidence(records):
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        return list(executor.map(enrich_article, records))
