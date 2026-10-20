"""Conservative source-record checks before model output becomes evidence.

This is a rejection gate, not a claim of semantic fact verification. Ambiguous
or translated pairs without enough shared anchors must use another research
path. Downstream editorial/factual gates still run against original excerpts.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import urlparse

_STOP = set("der die das den dem des ein eine einer einem einen eines und oder aber mit von vom zur zum für auf aus bei nach vor über ist sind wird werden hat haben heute jetzt neu neue neuen neuer meldet berichtet laut sagt the a an and or of to in on for with from as is are was were new says said report reports latest update updates live news current event bestätigt bestätigte meldung quelle unabhängig independently confirmed source sources coverage".split())

# Explicitly bounded event vocabulary: unknown or ambiguous actions defer to
# another research path. Shared actors/places alone never prove one event.
_EVENTS = {
    "investment": r"\b(?:invest\w*|finanzier\w*)\b",
    "closure": r"\b(?:schließ\w*|schliess\w*|stillleg\w*|clos(?:e|es|ing|ure)|shuts?)\b",
    "job_cuts": r"\b(?:stellenabbau|personalabbau|jobabbau|entlass\w*|layoffs?|streicht|streichen)\b",
    "opening": r"\b(?:eröffn\w*|eroeffn\w*|opens?|opening)\b",
    "hiring": r"\b(?:einstell\w*|neueinstellungen|hires?|hiring)\b",
    "strike": r"\b(?:streik\w*|strikes?)\b",
    "announcement": r"\b(?:kündigt|kuendigt|informiert|announc\w*|informs?)\b",
    "price_rise": r"\b(?:preisanstieg|preiserhöhung\w*|preiserhoehung\w*|verteuer\w*)\b",
    "price_fall": r"\b(?:preissenkung\w*|preisrückgang|preisrueckgang|verbillig\w*)\b",
    "recall": r"\b(?:rückruf\w*|rueckruf\w*|recalls?)\b",
    "delay": r"\b(?:verspät\w*|verspaet\w*|verzöger\w*|verzoeger\w*|delays?|delayed)\b",
    "cancellation": r"\b(?:abgesagt|absage\w*|cancel\w*)\b",
    "launch": r"\b(?:startet|starten|einführung\w*|einfuehrung\w*|launch\w*|release\w*)\b",
    "cyberattack": r"\b(?:cyberangriff\w*|hackerangriff\w*|datenleck\w*|cyberattack\w*)\b",
    "outage": r"\b(?:ausfall\w*|störung\w*|stoerung\w*|outage\w*)\b",
    "win": r"\b(?:gewinnt|gewann|sieg\w*|wins?|won)\b",
    "loss": r"\b(?:verliert|verlor|niederlage\w*|loses?|lost)\b",
    "flood": r"\b(?:hochwasser|überschwemm\w*|ueberschwemm\w*|flood\w*)\b",
    "earthquake": r"\b(?:erdbeben|earthquake\w*)\b",
    "fire": r"\b(?:waldbrand\w*|großbrand\w*|wildfire\w*)\b",
}


def _events(text: str) -> set[str]:
    return {name for name, pattern in _EVENTS.items() if re.search(pattern, text.casefold())}


def _status(text: str) -> tuple[bool, bool]:
    words = set(re.findall(r"[^\W_]+", text.casefold()))
    negative = bool(words & {"nicht", "kein", "keine", "keinen", "dementiert", "not", "denies", "no"})
    proposed = bool(words & {"plant", "geplant", "will", "soll", "sollen", "könnte", "könnten", "fordert", "vorschlag", "plans", "planned", "proposes", "could", "may"})
    return negative, proposed


def _text(record: dict) -> str:
    # Source provenance is always reconstructed, never model-generated supports.
    return " ".join(str(record.get(k) or "").strip() for k in ("title", "context")).strip()


def _words(value: str) -> set[str]:
    value = unicodedata.normalize("NFKC", value).casefold()
    return {w for w in re.findall(r"[^\W_]+", value) if len(w) >= 3 and not w.isdigit() and w not in _STOP}


def _numbers(value: str) -> set[str]:
    return {re.sub(r"[.,]", "", n) for n in re.findall(r"\d+(?:[.,]\d+)*", value)}


def _publisher(record: dict) -> str:
    host = (urlparse(str(record.get("url") or "")).hostname or "").casefold()
    host = host.removeprefix("www.")
    if host in {"bbc.com", "bbc.co.uk"} or host.endswith((".bbc.com", ".bbc.co.uk")):
        return "bbc.com"
    for publisher in ("tagesschau.de", "dw.com", "theguardian.com", "aljazeera.com"):
        if host == publisher or host.endswith("." + publisher):
            return publisher
    return host


def validate_pair(candidate: dict, records: list[dict]) -> list[str]:
    """Reject unrelated IDs, unsupported headline numbers and known mirrors."""
    if len(records) != 2:
        return ["requires_two_source_records"]
    a, b = records
    publishers = [_publisher(r) for r in records]
    if not all(publishers) or len(set(publishers)) != 2:
        return ["requires_two_independent_publishers"]
    texts = [_text(r) for r in records]
    terms = [_words(t) for t in texts]
    title_terms = [_words(str(r.get("title") or "")) for r in records]
    common = terms[0] & terms[1]
    reasons = []
    if len(common) < 3 or not (title_terms[0] & title_terms[1]):
        reasons.append("source_records_do_not_establish_same_story")
    headline = str(candidate.get("title") or "")
    event = _events(headline)
    if not event or not event.issubset(_events(str(a.get("title") or "")) & _events(str(b.get("title") or ""))):
        reasons.append("shared_headline_event_anchor_required")
    if any(_status(str(r.get("title") or "")) != _status(headline) for r in records):
        reasons.append("headline_event_status_not_correlated")
    headline_terms = _words(headline)
    for index, (text, source_terms) in enumerate(zip(texts, terms), 1):
        overlap = headline_terms & source_terms
        if len(overlap) < 2 or not headline_terms.issubset(source_terms):
            reasons.append(f"source_{index}_does_not_support_headline")
        if not _numbers(headline).issubset(_numbers(text)):
            reasons.append(f"source_{index}_missing_headline_number")
    origins = []
    for record, text in zip(records, texts):
        declared = str(record.get("origin") or record.get("source_origin") or record.get("wire_agency") or "").strip().casefold()
        agencies = set(re.findall(r"\b(?:dpa|reuters|afp|associated press)\b", text.casefold()))
        origins.append(agencies | ({declared} if declared else set()))
    if origins[0] & origins[1]:
        reasons.append("same_declared_reporting_origin")
    contexts = [" ".join(str(r.get("context") or "").casefold().split()) for r in records]
    if len(contexts[0]) >= 80 and contexts[0] == contexts[1]:
        reasons.append("identical_source_context_is_not_independent_confirmation")
    return reasons


def source_support(record: dict) -> tuple[str, str]:
    text = _text(record)
    return text[:1400], hashlib.sha256(text.encode("utf-8")).hexdigest()
