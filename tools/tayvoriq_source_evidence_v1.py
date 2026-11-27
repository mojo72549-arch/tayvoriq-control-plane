"""Conservative source-record checks before model output becomes evidence.

This is a rejection gate, not a claim of semantic fact verification. Ambiguous
or translated pairs without enough shared anchors must use another research
path. Downstream editorial/factual gates still run against original excerpts.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from decimal import Decimal
from urllib.parse import urlparse

_STOP = set("der die das den dem des ein eine einer einem einen eines und oder aber mit von vom zur zum für auf aus bei nach vor über ist sind wird werden hat haben heute jetzt neu neue neuen neuer meldet berichtet laut sagt the a an and or of to in on for with from as is are was were new says said report reports latest update updates live news current event bestätigt bestätigte meldung quelle unabhängig independently confirmed source sources coverage".split())
_SHORT_ANCHORS = {"eu", "uk", "us", "vw", "db", "bw", "ki"}
_RULE_CHANGE = r"\bstrengere?\s+([\wäöüß]+)[ -]regeln\b"
# Replace only the complete reflexive merger expression. A closure elsewhere
# in the same report remains a separate event.
_MERGER = re.compile(r"\b(?:schlie(?:ß|ss)(?:en|t)\s+sich\s+zusammen|fusionier(?:t|en|te|ten))\b")
_POLITICAL_ROLE = r"\b\w*(?:minister(?:präsident)?(?:in)?|staatssekretär(?:in)?)\b"
_APPOINTMENT_SUBJECT = re.compile(
    r"\b([A-ZÄÖÜ][\w-]{2,})\s+"
    r"(?i:folgt\b|rückt\s+an\s+die\s+spitze\b|wird\s+(?:nachfolger(?:in)?\b|"
    r"(?:(?:neue[rs]?|bayerische[rs]?)\s+)?" + _POLITICAL_ROLE + r"))"
)
_PRICE = r"\b(?:[a-zäöüß-]*preis(?:e[ns]?|en|es)?|kosten)\b"
_PRICE_DOWN = r"\b(?:senk\w*|gesenkt\w*|sink\w*|sank\w*|gesunken\w*|fällt|fallen|fiel)\b"
_PRICE_UP = r"\b(?:steig\w*|stieg\w*|gestiegen\w*|erhöh\w*|erhoeh\w*|erhöht\w*)\b"
_QUARTER_STEMS = {"1": "erst", "2": "zweit", "3": "dritt", "4": "viert"}
_QUARTER = re.compile(r"\b(?:([1-4])\.\s*|(erst|zweit|dritt|viert)(?:e|en|em|es)\s+)quartal\b")
_REAL_WAGE_RISE = re.compile(
    r"(\breallöhne\s+(?:(?:sind|waren)\s+)?"
    r"(?:im\s+(?:(?:erstes|zweites|drittes|viertes)\s+quartal(?:\s+\d{4})?|sommer)\s+)?"
    r"(?:(?:weiter|leicht|langsamer|deutlich)\s+)?(?:um\s+\d+(?:[.,]\d+)?\s*(?:%|prozent)\s+)?)"
    r"(steigen|stiegen|gestiegen|wachsen|wuchsen|gewachsen|höher)\b"
)

# Explicitly bounded event vocabulary: unknown or ambiguous actions defer to
# another research path. Shared actors/places alone never prove one event.
_EVENTS = {
    "merger": r"\b(?:firmenfusion|fusion|zusammenschluss)\b",
    "investment": r"\b(?:invest\w*|finanzier\w*)\b",
    "closure": r"\b(?:schließ\w*|schliess\w*|stillleg\w*|clos(?:e|es|ing|ure)|shuts?)\b",
    "job_cuts": r"\b(?:stellenabbau|personalabbau|jobabbau|entlass\w*|layoffs?|streicht|streichen|stellenstreich\w*)\b",
    "opening": r"\b(?:eröffn\w*|eroeffn\w*|opens?|opening)\b",
    "hiring": r"\b(?:neueinstellungen|hires?|hiring)\b",
    "strike": r"\b(?:warnstreik\w*|streik\w*|strikes?)\b",
    "price_rise": r"\b(?:preisanstieg|preiserhöhung\w*|preiserhoehung\w*|verteuer\w*|teurer)\b",
    "price_fall": r"\b(?:preissenkung\w*|preisrückgang|preisrueckgang|verbillig\w*|billiger)\b",
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
    # Common work, money and mobility events must be discoverable too. Each
    # family still needs the same action in BOTH headlines, exact support,
    # matching certainty, matching numbers and independent reporting origins.
    "trade_tariffs": r"\b(?:zölle|zoelle|zöllen|zoellen|zollpolitik|einfuhrzölle|einfuhrzoelle)\b",
    "ticket_distribution": r"\b(?:tickets?|fahrkarten)\b.{0,90}\b(?:buchbar|verkauf\w*|verkauft|buchung\w*)\b|\b(?:verkauf\w*|verkauft)\b.{0,90}\b(?:tickets?|fahrkarten)\b",
    "economic_growth": r"\b(?:wirtschaft|bip|bruttoinlandsprodukt)\b.{0,65}\b(?:wächst|wuchs|gewachsen|wachstum)\b|\bwirtschaftswachstum\b",
    "economic_contraction": r"\b(?:wirtschaft|bip|bruttoinlandsprodukt)\b.{0,65}\b(?:schrumpf\w*|gesunken|rückgang|rueckgang)\b",
    "wage_negotiation": r"\b(?:tarifrunde\w*|tarifverhandlung\w*|tarifgespräch\w*|tarifgespraech\w*)\b",
    "policy_reform": r"\b(?:\w*reform\w*|gesetzesänder\w*)\b",
    "sale": r"\b(?:verkauf|verkauft|verkaufen|firmenverkauf|unternehmensverkauf)\b",
}


def _normalize_quarters(text: str) -> str:
    return _QUARTER.sub(lambda match: (match[2] or _QUARTER_STEMS[match[1]]) + "es quartal", text)


def _events(text: str) -> set[str]:
    text = _MERGER.sub("firmenfusion", text.casefold())
    events = {name for name, pattern in _EVENTS.items() if re.search(pattern, text)}
    if "reallöhne" in text and _REAL_WAGE_RISE.search(_normalize_quarters(text)):
        events.add("real_wage_rise")
    for name, direction in (("price_fall", _PRICE_DOWN), ("price_rise", _PRICE_UP)):
        if re.search(_PRICE + r".{0,45}" + direction + "|" + direction + r".{0,45}" + _PRICE, text):
            events.add(name)
    if "ticket_distribution" in events:
        events.discard("sale")  # Ticket distribution is not a company disposal.
    if re.search(r"\b(?:stellen|jobs|arbeitsplätze)\b", text) and re.search(
        r"\b(?:abbau\w*|wegfall\w*|baut.{0,65}\bab|fallen.{0,40}\bweg)\b", text
    ):
        events.add("job_cuts")
    if re.search(_RULE_CHANGE, text):
        events.add("policy_reform")
    role_change = re.search(r"\b(?:folgt|nachfolg\w*|übernimmt)\b", text)
    appointed = re.search(r"\bwird\s+(?:(?:neue[rs]?|bayerische[rs]?)\s+)?" + _POLITICAL_ROLE, text)
    if appointed or (role_change and re.search(_POLITICAL_ROLE, text)):
        events.add("government_appointment")
    return events


def _status(text: str) -> tuple[bool, bool]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    # Match bounded stems so ordinary inflections (for example planen/plante,
    # dementieren/dementierte) cannot turn tentative or denied reporting into
    # a confirmed candidate headline.
    negative = bool(re.search(
        r"\b(?:nicht|kein\w*|dementier\w*|vernein\w*|not|no|den(?:y|ies|ied|ying))\b",
        normalized,
    ))
    proposed = bool(re.search(
        r"\b(?:plan(?:t|en|te|ten|end\w*|ung\w*)|plän\w*|plaen\w*|geplant\w*|"
        r"beabsichtig\w*|erwäg\w*|erwaeg\w*|könn\w*|koenn\w*|"
        r"soll\w*|woll\w*|will|bald|demnächst|künftig|zukünftig|dürft\w*|voraussichtlich|erwart(?:et|en)|vermutlich|forder\w*|vorschl\w*|vorschlag\w*|plans?|planned|planning|"
        r"propos\w*|could|may|might|intends?|consider\w*)\b",
        normalized,
    ))
    return negative, proposed


def _text(record: dict) -> str:
    # Source provenance is always reconstructed, never model-generated supports.
    return " ".join(str(record.get(k) or "").strip() for k in ("title", "context")).strip()


def _words(value: str) -> set[str]:
    value = unicodedata.normalize("NFKC", value).casefold()
    return {w for w in re.findall(r"[^\W_]+", value) if (len(w) >= 3 or w in _SHORT_ANCHORS) and not w.isdigit() and w not in _STOP}


def claim_terms(value: str) -> set[str]:
    # Normalize a small set of equivalent surface forms without erasing
    # subjects, numbers, disputed facts, or the distinction between plans and outcomes.
    value = re.sub(_RULE_CHANGE, r"\1 reform", value.casefold())
    if _MERGER.search(value):
        value = _MERGER.sub("firmenfusion", value)
        # In a report on named merging chains these are equivalent industry
        # labels. Preserve every company name, modal, location and number.
        value = re.sub(r"\b(?:baumarktketten|baumärkte)\b", "baumarkt", value)
    if re.search(_POLITICAL_ROLE, value):
        value = re.sub(r"\b(?:folgt|folgen|nachfolg\w*)\b", "nachfolge", value)
        value = re.sub(r"\brückt an die spitze des (?:[\w]+\s+){0,2}(\w+minister)iums\b",
                       r"nachfolge \1", value)
        value = re.sub(r"\bals\s+(?=" + _POLITICAL_ROLE + ")", "", value)
    forms = {"fiskus":"staat", "staatskasse":"staat", "könnten":"könnte",
             "discountern":"discounter", "deutschen":"deutsche", "deutscher":"deutsche",
             "bald":"zukünftig", "demnächst":"zukünftig", "künftig":"zukünftig"}
    events = _events(value)
    if "real_wage_rise" in events:
        value = _REAL_WAGE_RISE.sub(r"\1reallohnanstieg", _normalize_quarters(value))
    if "price_fall" in events:
        value = re.sub(_PRICE_DOWN, "preissenkung", value)
    if "price_rise" in events:
        value = re.sub(_PRICE_UP, "preiserhöhung", value)
    if "ticket_distribution" in events:
        value = re.sub(r"\b(?:buchbar|buchen|gebucht|verkauft|verkaufen)\b", "ticketkauf", value)
    return {forms.get(word, word) for word in _words(value)}


def record_events(record: dict) -> set[str]:
    """Discovery may find a price change in the original lead, not just its headline."""
    return _events(str(record.get("title") or "")) | (_events(str(record.get("context") or "")) & {"price_fall", "price_rise"})


def _supports_event(record: dict, headline: str) -> bool:
    wanted = _events(headline)
    present = _events(str(record.get("title") or ""))
    if wanted.issubset(present):
        return True
    # Only a bounded price-change lead can supply a missing headline action.
    # Its object, amount/unit and direction must occur together in one original
    # sentence. An unrelated event elsewhere in the story is not corroboration.
    if not (wanted - present) <= {"price_fall", "price_rise"}:
        return False
    anchors = claim_terms(headline) - {"preissenkung", "preiserhöhung", "discounter"}
    if len(anchors) < 2:
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", str(record.get("context") or "")):
        if (wanted <= _events(sentence) and _status(sentence) == _status(headline)
                and anchors <= claim_terms(sentence)):
            return True
    return False


def _numbers(value: str) -> set[str]:
    numbers = set()
    for token in re.findall(r"[+-]?\d+(?:[.,]\d+)*", value):
        if '.' in token and ',' in token:
            decimal = '.' if token.rfind('.') > token.rfind(',') else ','
            grouping = ',' if decimal == '.' else '.'
            whole, fraction = token.rsplit(decimal, 1)
            if not re.fullmatch(r'[+-]?\d{1,3}(?:' + re.escape(grouping) + r'\d{3})+', whole):
                numbers.add('ambiguous:' + token)
                continue
            token = whole.replace(grouping, '') + '.' + fraction
        elif '.' in token or ',' in token:
            separator = '.' if '.' in token else ','
            if token.count(separator) > 1:
                if re.fullmatch(r'[+-]?\d{1,3}(?:' + re.escape(separator) + r'\d{3})+', token):
                    token = token.replace(separator, '')
                else:
                    numbers.add('ambiguous:' + token)
                    continue
            elif len(token.rsplit(separator, 1)[1]) == 3:
                # Without a source locale, 1.000 may mean 1000 or 1 exactly.
                # Preserve ambiguity rather than silently choosing either.
                numbers.add('ambiguous:' + token)
                continue
            else:
                token = token.replace(separator, '.')
        numbers.add(str(Decimal(token).normalize()))
    return numbers


def _publisher(record: dict) -> str:
    parsed = urlparse(str(record.get("url") or ""))
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if host == "tagesschau.de":
        affiliate = re.match(r"^/inland/regional/[^/]+/(swr|ndr|wdr|br|hr|mdr|rbb|sr)-", parsed.path)
        if affiliate:
            return affiliate.group(1) + ".de"
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
    terms = [claim_terms(t) for t in texts]
    title_terms = [claim_terms(str(r.get("title") or "")) for r in records]
    common = terms[0] & terms[1]
    reasons = []
    if len(common) < 3 or not (title_terms[0] & title_terms[1]):
        reasons.append("source_records_do_not_establish_same_story")
    headline = str(candidate.get("title") or "")
    event = _events(headline)
    if not event or not all(_supports_event(record, headline) for record in records):
        reasons.append("shared_headline_event_anchor_required")
    if any(_status(str(r.get("title") or "")) != _status(headline) for r in records):
        reasons.append("headline_event_status_not_correlated")
    if "government_appointment" in event:
        appointees = {name.casefold() for name in _APPOINTMENT_SUBJECT.findall(headline)}
        if not appointees or any(
            not appointees.issubset({name.casefold() for name in _APPOINTMENT_SUBJECT.findall(text)})
            for text in texts
        ):
            reasons.append("appointment_subject_not_independently_confirmed")
    headline_terms = claim_terms(headline)
    for index, (text, source_terms) in enumerate(zip(texts, terms), 1):
        overlap = headline_terms & source_terms
        if len(overlap) < 2 or not headline_terms.issubset(source_terms):
            reasons.append(f"source_{index}_does_not_support_headline")
        if not _numbers(headline).issubset(_numbers(text)):
            reasons.append(f"source_{index}_missing_headline_number")
    origins = []
    for record, text in zip(records, texts):
        declared = str(record.get("origin") or record.get("source_origin") or record.get("wire_agency") or "").strip().casefold()
        agencies = set(re.findall(r"\b(?:dpa|reuters|afp|associated press)\b", f"{declared} {text.casefold()}"))
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
