"""Source-grounded qualification for AI Macro Current Context.

Discovery metadata may nominate a candidate, but Reader-facing prose may not be
built from a headline or RSS description.  A candidate must resolve to an
eligible publisher/primary page, yield substantive source text, contain a
concrete domain-relevant development, and support the factual sentence that is
published to the Reader.

Only compact derived facts/provenance are persisted.  Full article bodies are
used transiently during refresh and are never written to the retained ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import html as html_lib
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config.current_context_policy import (
    current_context_qualification_policy,
    current_context_qualification_tier,
    current_context_tier_index,
    domain_relevance_terms,
    domain_topic_anchors,
    domain_synthesis_terms,
    assess_source,
    assess_source_for_qualification,
    recent_development_copy_issues,
    term_present,
)
from loaders.current_context_news import NEWS_USER_AGENT, _valid_https_url
from loaders.current_context_composer import compose_development, strict_domain_fit


GROUNDING_VERSION = "4.0"
SOURCE_TIMEOUT = (4, 9)
SOURCE_MAX_BYTES = 2_500_000
# Publisher HTML is fetched as a normal browser navigation. The RSS/discovery
# client keeps AI Macro's identifying UA; source pages such as Reuters may
# reject non-browser HTML clients before returning any article text.
SOURCE_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)
MIN_SOURCE_TEXT_CHARS = 220
MIN_SOURCE_SENTENCES = 2
MAX_SOURCE_TEXT_CHARS = 28_000
PREFERRED_FACT_WORDS = 55
MAX_FACT_WORDS = 70

_PREVIEW_PATTERNS = (
    r"\bwall st(?:reet)? week ahead\b",
    r"\bweek ahead\b",
    r"\bwhat to watch\b",
    r"\bwhat investors should watch\b",
    r"\bpreview\b",
    r"\bcalendar:\b",
    r"\bwebinar\b",
    r"\bupcoming (?:event|session|webinar)\b",
)

_COMMENTARY_PATTERNS = (
    r"\bopinion\b",
    r"\bcommentary\b",
    r"\bcolumn\b",
    r"\binterview\b",
    r"\bq&a\b",
    r"\bquestions and answers\b",
    r"\bwhat .* means\b",
    r"\bwhy .* matters\b",
)

_TOPIC_ONLY_PATTERNS = (
    r"^ai['’]s impact on\b",
    r"^the impact of .+ on\b",
    r"^how .+ is changing\b",
    r"^what .+ means for\b",
    r"^the state of\b",
)

_POLICY_COMMENTARY_PATTERNS = (
    r"\bfed(?:eral reserve)?(?:['’]s)?\b.*\b(?:says|sees|expects|signals|warns|reiterates|keeps|wants|favors|backs|open mind|cautious|cautiously)\b",
    r"\b(?:fed|federal reserve)\b.*\b(?:outlook|view|views|remarks|speech|interview)\b",
)

_EVENT_VERBS = (
    # Past-tense/reporting forms.
    "acquired", "announced", "approved", "awarded", "began", "bought", "built", "closed", "commissioned",
    "completed", "cut", "decided", "delayed", "denied", "directed", "filed", "found", "grew", "held",
    "implemented", "increased", "invested", "issued", "launched", "maintained", "opened", "ordered",
    "planned", "priced", "proposed", "published", "purchased", "raised", "reached", "released", "reported", "secured", "signed",
    "started", "suspended", "terminated", "updated", "voted", "withdrew", "rose", "fell",
    "declined", "expanded", "refinanced", "downgraded", "upgraded", "curtailed", "added",
    "reduced", "adopted", "committed", "agreed", "entered", "lowered",
    "surged", "jumped", "rallied", "slid", "dropped", "plunged", "climbed", "beat", "blew", "forecast", "exceeded", "topped",
    "arranged", "marketed", "financed", "funded", "partnered", "stacked",
    # Headline-present forms. Publisher headlines are an eligible event frame
    # only when the body independently corroborates them, so present tense is
    # not by itself a weaker evidentiary form.
    "acquires", "announces", "approves", "awards", "begins", "buys", "closes", "commissions",
    "completes", "cuts", "decides", "delays", "denies", "directs", "files", "finds", "grows", "holds",
    "implements", "increases", "invests", "issues", "launches", "maintains", "opens", "orders",
    "plans", "prices", "proposes", "publishes", "purchases", "raises", "reaches", "releases", "reports", "secures", "signs",
    "starts", "suspends", "terminates", "updates", "votes", "withdraws",
    "declines", "expands", "refinances", "downgrades", "upgrades", "curtails", "adds",
    "reduces", "adopts", "commits", "agrees", "enters", "lowers",
    "surges", "jumps", "rallies", "slides", "drops", "plunges", "climbs", "beats", "forecasts", "exceeds", "tops",
    "arranges", "markets", "finances", "funds", "partners", "stacks",
)

_EMPIRICAL_MARKERS = (
    "data showed", "data show", "survey found", "survey showed", "study found",
    "study showed", "report found", "report showed", "researchers found",
    "the bureau reported", "the department reported", "the agency reported",
    "according to data", "estimate showed", "estimates showed",
)

_AI_INFRA_TERMS = (
    "ai", "artificial intelligence", "data center", "datacenter", "hyperscaler",
    "cloud", "gpu", "semiconductor", "compute", "nvidia", "microsoft", "amazon",
    "google", "alphabet", "meta", "oracle", "openai", "anthropic", "xai", "coreweave",
)

_US_STRATEGIC_CONNECTIVITY_TERMS = (
    "united states", "u.s.", "us ", "virginia", "northern virginia", "california",
    "oregon", "washington", "texas", "arizona", "ohio", "iowa", "nebraska",
    "new york", "new jersey", "florida", "georgia", "north carolina", "south carolina",
    "chicago", "atlanta", "dallas", "phoenix", "ashburn", "silicon valley", "guam",
    "hawaii",
)

_SYSTEM_GRID_TERMS = (
    "interconnection queue", "transmission", "curtailment", "grid", "substation",
    "transformer", "congestion", "battery storage", "regional transmission",
)

_SYSTEM_WATER_TERMS = (
    "colorado river", "lower basin", "upper basin", "drought", "water shortage",
    "water emergency", "water restriction", "aquifer", "reservoir", "water allocation",
)

_BOILERPLATE_RELEVANCE_PREFIXES = (
    "the development changes", "the change affects", "the release changes",
    "the action changes", "the project adds evidence", "the development is relevant",
)

# Reader prose reports what happened and what it implies.  It never explains
# why the selector admitted the item.  These phrases are selection-rationale
# leakage, not analysis.
_SELECTION_RATIONALE_PATTERNS = (
    r"\bbecause the evidence (?:is|comes from)\b",
    r"\bdirect test of whether\b",
    r"\bappropriate test of whether\b",
    r"\bmeets? (?:the )?(?:evidence|selection|materiality) (?:bar|threshold)\b",
    r"\bqualif(?:y|ies|ied) (?:because|for|under)\b",
    r"\brather than a valuation narrative\b",
    r"\bnot (?:an?|the) [^.]{0,50} proxy\b",
)

# Materiality precedes extraction.  A source must make a current development
# visible in its lead evidence; the engine is not allowed to mine a weak or
# commentary-first article for an isolated historical number that can justify
# inclusion after the fact.
MAX_DEVELOPMENT_LEAD_SENTENCES = 20
_MAJOR_MARKET_MOVE_PCT = 10.0
_MAJOR_MARKET_TRANSACTION_B = 10.0


_NOISE_PHRASES = (
    "sign up for", "subscribe", "newsletter", "all rights reserved", "cookie policy",
    "privacy policy", "terms of use", "advertisement", "read more", "related stories",
)


@dataclass(frozen=True)
class SourceDocument:
    requested_url: str
    resolved_url: str
    title: str
    description: str
    body_text: str
    extraction_method: str
    error: str = ""
    published_date: str = ""
    modified_date: str = ""

    @property
    def text_chars(self) -> int:
        return len(self.body_text or "")




_SYNTHETIC_ANALYSIS_TITLE_PATTERNS = (
    r"\bfuture of\b",
    r"\bunderstanding\b",
    r"\bfundamentals\b",
    r"\bwhat .* means for\b",
    r"\blimits of .* bankability\b",
    r"\bbuilding the .* stack\b",
    r"\bhow .* is evolving\b",
)

_SYNTHETIC_ANALYSIS_BODY_MARKERS = (
    "key takeaways",
    "in our previous article",
    "this article is part of",
    "thought leadership series",
    "explore our other articles",
    "in the next article",
    "looking for deeper insights",
    "deepen your understanding",
)


def source_content_quality_issues(doc: SourceDocument) -> list[str]:
    """Identify article formats that are poor Current Context evidence.

    Current Context is a development feed, not an opinion or explainer surface.
    Publisher reputation does not rescue an article whose form is analytical,
    promotional, or advisory rather than event-reporting.
    """
    title = _spaces(doc.title).casefold()
    body = _spaces(doc.body_text).casefold()
    try:
        path = urlparse(str(doc.resolved_url or doc.requested_url or "")).path.casefold()
    except ValueError:
        path = ""
    issues: list[str] = []
    title_hits = sum(bool(re.search(pattern, title, flags=re.I)) for pattern in _SYNTHETIC_ANALYSIS_TITLE_PATTERNS)
    body_hits = sum(marker in body for marker in _SYNTHETIC_ANALYSIS_BODY_MARKERS)
    if body_hits >= 2 or (title_hits >= 1 and body_hits >= 1):
        issues.append("source is a thematic/explainer series rather than a discrete current development")

    # Opinion/advice pages may contain useful domain facts, but they are not a
    # current development in their own right.  Event-specific professional
    # alerts remain eligible because they do not live on opinion/commentary
    # routes and still face the ordinary event-nucleus gate below.
    if re.search(r"/(?:opinion|opinions|commentary)(?:/|$)", path):
        issues.append("source is an opinion/commentary page rather than a reported development")

    lead = " ".join(_split_sentences(doc.body_text)[:8])
    if (title_hits or body_hits) and not (_has_event_action(lead) or _has_empirical_marker(lead)):
        issues.append("source lead is thematic analysis without a concrete reported event")
    return list(dict.fromkeys(issues))

@dataclass(frozen=True)
class GroundingResult:
    accepted: bool
    fact: str = ""
    relevance: str = ""
    resolved_url: str = ""
    extraction_method: str = ""
    text_chars: int = 0
    evidence_hash: str = ""
    evidence_sentence_count: int = 0
    headline_similarity: float = 0.0
    source_published_date: str = ""
    source_modified_date: str = ""
    reason: str = ""
    error: str = ""


def _spaces(value: object) -> str:
    text = html_lib.unescape(str(value or "")).replace("\xa0", " ")
    return " ".join(text.split()).strip()


def _sentence(value: object) -> str:
    text = _spaces(value)
    if not text:
        return ""
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text if text.endswith((".", "!", "?")) else text + "."


def is_preview_or_calendar_item(title: object) -> bool:
    value = _spaces(title).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _PREVIEW_PATTERNS)


def is_event_listing_page(doc: SourceDocument) -> bool:
    """Reject future event/webinar listings masquerading as current developments."""
    title = _spaces(doc.title).casefold()
    lead = _spaces(" ".join(_split_sentences(doc.body_text)[:6])).casefold()
    try:
        path = urlparse(str(doc.resolved_url or doc.requested_url or "")).path.casefold()
    except ValueError:
        path = ""
    event_path = bool(re.search(r"/(?:event|events|webinar|webinars)(?:/|$)", path))
    event_markers = (
        "webinar", "register", "registration", "this event will take place",
        "this call will focus", "session will", "conference", "workshop",
    )
    if event_path and any(marker in f"{title} {lead}" for marker in event_markers):
        return True
    if "webinar" in title and any(marker in lead for marker in ("register", "will take place", "session", "zoom")):
        return True
    return False


def is_commentary_style_title(title: object) -> bool:
    value = _spaces(title).casefold()
    if any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _COMMENTARY_PATTERNS):
        return True
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _TOPIC_ONLY_PATTERNS)


def is_policy_commentary_title(title: object) -> bool:
    value = _spaces(title).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _POLICY_COMMENTARY_PATTERNS)


def is_attributed_commentary_title(title: object) -> bool:
    value = _spaces(title).casefold()
    evidence_markers = ("study", "report", "data", "survey", "release", "results", "filing")
    if any(marker in value for marker in evidence_markers):
        return False
    return any(marker in value for marker in (
        " says ", " argues ", " believes ", " thinks ", " expects ", " sees ",
        "no evidence of", "in conversation", "interview", "q&a",
    ))


def strip_legacy_source_leadin(fact: object, source_name: object = "") -> str:
    """Recover the payload of machine-generated legacy prose for rejection/audit."""
    value = _spaces(fact)
    source = re.escape(_spaces(source_name)) if _spaces(source_name) else ""
    patterns = [r"^company statement via\s+[^:]+:\s*", r"^[^:]+\s+reports:\s*"]
    if source:
        patterns.extend([rf"^{source}\s+reports:\s*", rf"^{source}:\s*"])
    for pattern in patterns:
        updated = re.sub(pattern, "", value, flags=re.IGNORECASE)
        if updated != value:
            return updated.strip()
    return value.strip()


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _google_news_article_id(url: str) -> str:
    """Return the opaque Google News article identifier, if present."""
    try:
        parsed = urlparse(str(url or ""))
    except ValueError:
        return ""
    if (parsed.hostname or "").casefold() != "news.google.com":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2 or parts[-2] not in {"articles", "read"}:
        return ""
    return _spaces(parts[-1])


def _google_news_decode_params(html: str) -> tuple[str, str]:
    """Extract the signature/timestamp Google uses to resolve opaque RSS IDs."""
    soup = BeautifulSoup(html or "", "lxml")
    node = soup.select_one("[data-n-a-sg][data-n-a-ts]")
    if not node:
        return "", ""
    return _spaces(node.get("data-n-a-sg")), _spaces(node.get("data-n-a-ts"))


def _parse_google_news_decode_response(text: str) -> str:
    """Extract the canonical publisher URL from a Google batchexecute response."""
    value = str(text or "")
    # Google frames RPC responses after an anti-XSSI prefix and blank line.
    # Walk every JSON-looking frame rather than depending on one fixed index.
    frames = [part.strip() for part in value.split("\n\n") if part.strip()]
    for frame in frames:
        if frame.startswith(")]}'"):
            frame = frame.split("\n", 1)[-1].strip()
        try:
            payload = json.loads(frame)
        except Exception:
            continue
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, list) or len(row) < 3:
                continue
            inner = row[2]
            if not isinstance(inner, str):
                continue
            try:
                decoded = json.loads(inner)
            except Exception:
                continue
            if isinstance(decoded, list) and len(decoded) > 1 and _valid_https_url(decoded[1]):
                return _spaces(decoded[1])
    return ""


def _google_news_decode_rpc(article_id: str, signature: str, timestamp: str) -> tuple[str, str]:
    """Resolve a modern opaque Google News RSS identifier to the publisher URL."""
    if not article_id or not signature or not timestamp:
        return "", "missing Google News decode parameters"
    request_payload = [
        "Fbv4je",
        (
            '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
            'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
            f'"{article_id}",{timestamp},"{signature}"]'
        ),
    ]
    headers = {
        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        "User-Agent": NEWS_USER_AGENT,
    }
    try:
        response = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers=headers,
            data={"f.req": json.dumps([[request_payload]], separators=(",", ":"))},
            timeout=SOURCE_TIMEOUT,
        )
        response.raise_for_status()
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"
    decoded = _parse_google_news_decode_response(response.text)
    if not decoded:
        return "", "Google News decode response did not contain a publisher URL"
    return decoded, ""


def _decode_google_news_url(article_url: str, initial_html: str = "") -> tuple[str, str]:
    """Resolve both legacy and modern Google News RSS wrappers.

    Since mid-2024 many Google News RSS links contain only an opaque server-side
    identifier.  The publisher URL is recovered from the wrapper's decode
    signature/timestamp and Google's own batchexecute resolver.
    """
    article_id = _google_news_article_id(article_url)
    if not article_id:
        return "", "invalid Google News article identifier"

    signature, timestamp = _google_news_decode_params(initial_html)
    if not signature or not timestamp:
        # Current Google pages expose these attributes on /articles/<id>.  Keep
        # the RSS form as a fallback because deployments have varied over time.
        for candidate in (
            f"https://news.google.com/articles/{article_id}",
            f"https://news.google.com/rss/articles/{article_id}",
        ):
            html, _, error = _request_html(candidate)
            if error:
                continue
            signature, timestamp = _google_news_decode_params(html)
            if signature and timestamp:
                break
    if not signature or not timestamp:
        return "", "Google News wrapper did not expose decode parameters"
    return _google_news_decode_rpc(article_id, signature, timestamp)


def _publisher_candidate_urls(html: str, base_url: str, expected_host: str) -> list[str]:
    soup = BeautifulSoup(html or "", "lxml")
    candidates: list[str] = []

    for selector, attr in (
        ('meta[property="og:url"]', "content"),
        ('meta[name="twitter:url"]', "content"),
        ('link[rel="canonical"]', "href"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attr):
            candidates.append(urljoin(base_url, str(node.get(attr))))

    for node in soup.find_all("a", href=True):
        href = str(node.get("href") or "").strip()
        if not href:
            continue
        parsed = urlparse(href)
        if parsed.scheme in {"http", "https"}:
            candidates.append(href)
            continue
        query = parse_qs(parsed.query)
        for key in ("url", "u", "q"):
            for value in query.get(key, []):
                value = unquote(value)
                if value.startswith("https://"):
                    candidates.append(value)

    # Google wrapper pages sometimes embed the publisher URL only in script data.
    for match in re.findall(r'https:\\/\\/[^"\\\s<>]+|https://[^"\'\s<>]+', html or ""):
        candidates.append(unquote(match.replace("\\/", "/")))

    clean: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        url = _spaces(url).rstrip("),.;\"")
        if not _valid_https_url(url):
            continue
        host = _host(url)
        if not host or host.endswith("google.com") or host.endswith("googleusercontent.com"):
            continue
        if expected_host and not (host == expected_host or host.endswith("." + expected_host)):
            continue
        key = url.casefold()
        if key in seen:
            continue
        seen.add(key)
        clean.append(url)
    return clean


def _request_html(url: str) -> tuple[str, str, str]:
    headers = {
        "User-Agent": SOURCE_BROWSER_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
        "Cache-Control": "no-cache",
    }
    try:
        response = requests.get(url, headers=headers, timeout=SOURCE_TIMEOUT, allow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        return "", "", f"{type(exc).__name__}: {exc}"
    payload = response.content
    if len(payload) > SOURCE_MAX_BYTES:
        return "", str(response.url or url), "source page exceeded byte limit"
    content_type = str(response.headers.get("content-type") or "").casefold()
    if "html" not in content_type and "xml" not in content_type and "text" not in content_type:
        return "", str(response.url or url), f"unsupported source content type: {content_type or 'unknown'}"
    response.encoding = response.encoding or response.apparent_encoding or "utf-8"
    return response.text, str(response.url or url), ""


def _walk_jsonld(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_jsonld(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_jsonld(child)


def _clean_paragraph(value: object) -> str:
    raw = str(value or "")
    if "<" in raw and ">" in raw:
        text = BeautifulSoup(raw, "lxml").get_text(" ", strip=True)
    else:
        # JSON-LD fields are often already plain text. Passing a URL-shaped
        # value to BeautifulSoup raises MarkupResemblesLocatorWarning and does
        # no useful parsing, so decode entities without invoking an HTML parser.
        text = html_lib.unescape(raw)
    text = _spaces(text)
    if len(text) < 45:
        return ""
    lower = text.casefold()
    if any(phrase in lower for phrase in _NOISE_PHRASES):
        return ""
    if sum(ch.isalpha() for ch in text) < 25:
        return ""
    return text


def _date_only(value: object) -> str:
    text = _spaces(value)
    if not text:
        return ""
    try:
        import pandas as pd
        timezone_match = re.search(r"\b(EST|EDT|CST|CDT|MST|MDT|PST|PDT)\s*$", text, flags=re.IGNORECASE)
        if timezone_match:
            zone = {
                "EST": "America/New_York", "EDT": "America/New_York",
                "CST": "America/Chicago", "CDT": "America/Chicago",
                "MST": "America/Denver", "MDT": "America/Denver",
                "PST": "America/Los_Angeles", "PDT": "America/Los_Angeles",
            }[timezone_match.group(1).upper()]
            local_text = text[:timezone_match.start()].rstrip(" ,")
            if not re.search(r"\b20\d{2}\b", local_text):
                current_year = datetime.now(timezone.utc).year
                local_text = re.sub(
                    r"(,\s*\d{1,2}:\d{2}\s*[AP]M)\s*$",
                    rf", {current_year}\1",
                    local_text,
                    flags=re.IGNORECASE,
                )
            stamp = pd.Timestamp(local_text)
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize(zone)
            now_local = pd.Timestamp.now(tz=zone)
            if stamp > now_local + pd.Timedelta(days=2):
                stamp = stamp.replace(year=stamp.year - 1)
            return stamp.date().isoformat()
        stamp = pd.Timestamp(text)
        if stamp.tzinfo is not None:
            stamp = stamp.tz_convert("UTC").tz_localize(None)
        return stamp.date().isoformat()
    except Exception:
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        return match.group(1) if match else ""


def _visible_publication_date(soup: BeautifulSoup) -> str:
    """Recover a visible article date when metadata/JSON-LD omits one.

    Some trade publishers render only a human-facing age (for example
    ``9 months ago``). Current Context treats that as authoritative enough to
    reject stale material; it must not let a fresh RSS recrawl override the
    publisher's own visible age.
    """
    regions: list[str] = []
    for selector in (
        "time", "[class*='date']", "[class*='publish']", "[class*='time']",
        "[id*='date']", "[id*='publish']",
    ):
        for node in soup.select(selector)[:12]:
            text = _spaces(node.get_text(" ", strip=True))
            if text and text not in regions:
                regions.append(text)
    h1 = soup.find("h1")
    if h1 is not None:
        parent = h1.parent
        if parent is not None:
            text = _spaces(parent.get_text(" ", strip=True))[:1400]
            if text:
                regions.append(text)
        nearby: list[str] = []
        node = h1
        for _ in range(10):
            node = node.find_next() if node is not None else None
            if node is None:
                break
            if getattr(node, "name", None) in {"p", "article", "main"}:
                break
            text = _spaces(node.get_text(" ", strip=True))
            if text:
                nearby.append(text)
        if nearby:
            regions.append(" ".join(nearby)[:1000])

    month_names = (
        "January|February|March|April|May|June|July|August|September|October|November|December|"
        "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    )
    for text in regions:
        for pattern in (
            rf"\b(?:{month_names})\s+\d{{1,2}},\s+20\d{{2}}\b",
            rf"\b\d{{1,2}}\s+(?:{month_names})\s+20\d{{2}}\b",
        ):
            match = re.search(pattern, text, flags=re.I)
            if match:
                parsed = _date_only(match.group(0))
                if parsed:
                    return parsed
        relative = re.search(r"\b(\d{1,3})\s+(day|week|month|year)s?\s+ago\b", text, flags=re.I)
        if relative:
            count = int(relative.group(1))
            unit = relative.group(2).casefold()
            days = count * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]
            stamp = datetime.now(timezone.utc).date() - timedelta(days=days)
            return stamp.isoformat()
    return ""


def _page_dates(soup: BeautifulSoup) -> tuple[str, str]:
    published = ""
    modified = ""
    for selector, attr, target in (
        ('meta[property="article:published_time"]', "content", "published"),
        ('meta[name="date"]', "content", "published"),
        ('meta[name="datePublished"]', "content", "published"),
        ('meta[property="article:modified_time"]', "content", "modified"),
        ('meta[name="dateModified"]', "content", "modified"),
    ):
        node = soup.select_one(selector)
        if not node or not node.get(attr):
            continue
        value = _date_only(node.get(attr))
        if target == "published" and value and not published:
            published = value
        if target == "modified" and value and not modified:
            modified = value
    if not published:
        node = soup.find("time", attrs={"datetime": True})
        if node:
            published = _date_only(node.get("datetime"))
    if not published:
        published = _visible_publication_date(soup)
    return published, modified


def _extract_article(html: str, resolved_url: str) -> SourceDocument:
    soup = BeautifulSoup(html or "", "lxml")
    published_date, modified_date = _page_dates(soup)
    title = ""
    for selector, attr in (
        ('meta[property="og:title"]', "content"),
        ('meta[name="twitter:title"]', "content"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attr):
            title = _spaces(node.get(attr))
            break
    if not title and soup.find("h1"):
        title = _spaces(soup.find("h1").get_text(" ", strip=True))
    if not title and soup.title:
        title = _spaces(soup.title.get_text(" ", strip=True))

    description = ""
    for selector, attr in (
        ('meta[property="og:description"]', "content"),
        ('meta[name="description"]', "content"),
        ('meta[name="twitter:description"]', "content"),
    ):
        node = soup.select_one(selector)
        if node and node.get(attr):
            description = _spaces(node.get(attr))
            break

    article_bodies: list[str] = []
    for node in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = node.string or node.get_text() or ""
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        for obj in _walk_jsonld(parsed):
            body = obj.get("articleBody")
            if body:
                clean = _clean_paragraph(body)
                if clean:
                    article_bodies.append(clean)
            if not title and obj.get("headline"):
                title = _spaces(obj.get("headline"))
            if not description and obj.get("description"):
                description = _spaces(obj.get("description"))
            if not published_date and obj.get("datePublished"):
                published_date = _date_only(obj.get("datePublished"))
            if not modified_date and obj.get("dateModified"):
                modified_date = _date_only(obj.get("dateModified"))

    if article_bodies:
        body_text = max(article_bodies, key=len)[:MAX_SOURCE_TEXT_CHARS]
        return SourceDocument("", resolved_url, title, description, body_text, "jsonld_article_body", published_date=published_date, modified_date=modified_date)

    # Remove navigation/recommendation furniture before paragraph fallback.
    # Several publisher pages place ``Related News`` or recommended cards inside
    # ``main``; allowing those paragraphs into the article body can splice an
    # unrelated development onto the current story.
    for node in soup.select(
        "nav, footer, aside, [class*='related'], [id*='related'], "
        "[class*='recommend'], [id*='recommend'], [class*='promo'], "
        "[class*='newsletter'], [class*='sidebar']"
    ):
        try:
            node.decompose()
        except Exception:
            pass

    selectors = ("article p", "main article p", "main p", "[role='main'] p", "p")
    best: list[str] = []
    for selector in selectors:
        paragraphs: list[str] = []
        seen: set[str] = set()
        for node in soup.select(selector):
            text = _clean_paragraph(node.get_text(" ", strip=True))
            if not text or text.casefold() in seen:
                continue
            seen.add(text.casefold())
            paragraphs.append(text)
        if sum(len(p) for p in paragraphs) > sum(len(p) for p in best):
            best = paragraphs
        if len(paragraphs) >= 3 and sum(len(p) for p in paragraphs) >= MIN_SOURCE_TEXT_CHARS:
            break
    body_text = "\n".join(best)[:MAX_SOURCE_TEXT_CHARS]
    return SourceDocument("", resolved_url, title, description, body_text, "html_paragraphs", published_date=published_date, modified_date=modified_date)


def fetch_source_document(
    article_url: str,
    *,
    publisher_url: str = "",
    source_name: str = "",
    qualification_tier: str = "A",
    discovery_provider: str = "",
) -> SourceDocument:
    """Resolve an eligible source page and extract transient article/release text."""
    requested = _spaces(article_url)
    if not _valid_https_url(requested):
        return SourceDocument(requested, "", "", "", "", "", "invalid HTTPS source URL")

    expected_host = _host(publisher_url)
    html, resolved, error = _request_html(requested)
    if error:
        return SourceDocument(requested, resolved, "", "", "", "", error)

    host = _host(resolved)
    if host.endswith("news.google.com") or host == "news.google.com":
        # Legacy wrappers sometimes expose a direct publisher link in HTML.
        # Modern RSS links often contain only an opaque Google identifier, so
        # fall through to the canonical decode handshake when no direct link is
        # available.  In either case Reader citations must end at the publisher.
        candidates = _publisher_candidate_urls(html, resolved, expected_host)
        decode_error = ""
        if not candidates:
            decoded_url, decode_error = _decode_google_news_url(requested, initial_html=html)
            if decoded_url:
                candidates = [decoded_url]
        publisher_html = ""
        publisher_resolved = ""
        publisher_error = ""
        for candidate in candidates[:5]:
            candidate_host = _host(candidate)
            if expected_host and not (candidate_host == expected_host or candidate_host.endswith("." + expected_host)):
                publisher_error = f"decoded publisher host {candidate_host or 'unknown'} did not match expected host {expected_host}"
                continue
            publisher_html, publisher_resolved, publisher_error = _request_html(candidate)
            if not publisher_error and publisher_html:
                resolved = publisher_resolved or candidate
                html = publisher_html
                break
        else:
            detail = publisher_error or decode_error or "Google News wrapper did not resolve to the publisher page"
            return SourceDocument(requested, resolved, "", "", "", "", detail)

    # Re-assess the page that was actually fetched.  Discovery metadata can
    # nominate a publisher, but a trusted source name must not bless a redirect
    # onto an unrelated host.
    assessment = assess_source_for_qualification(
        "", "", resolved, provider=discovery_provider, tier_key=qualification_tier
    )
    if not assessment.auto_eligible:
        return SourceDocument(requested, resolved, "", "", "", "", f"resolved page is not eligible evidence: {assessment.reason}")

    doc = _extract_article(html, resolved)
    doc = SourceDocument(
        requested, doc.resolved_url, doc.title, doc.description, doc.body_text,
        doc.extraction_method, doc.error, doc.published_date, doc.modified_date,
    )
    minimum_chars = max(80, int(current_context_qualification_tier(qualification_tier).minimum_source_text_chars))
    if doc.text_chars < minimum_chars or len(_split_sentences(doc.body_text)) < MIN_SOURCE_SENTENCES:
        return SourceDocument(
            requested, doc.resolved_url, doc.title, doc.description, doc.body_text,
            doc.extraction_method, "insufficient source body text", doc.published_date, doc.modified_date,
        )
    return doc


_SENTENCE_PERIOD_TOKEN = "∯"
_SENTENCE_ABBREVIATIONS = (
    "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.", "Sept.", "Oct.", "Nov.", "Dec.",
    "Gov.", "Sen.", "Rep.", "Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Gen.", "Lt.", "St.", "No.",
)


def _protect_sentence_abbreviations(text: str) -> str:
    """Protect periods that are not sentence boundaries.

    v7.5 exposed a classic splitter failure: ``Aug. 3 letter`` became
    ``3 letter`` because the date abbreviation was treated as a sentence end.
    Initialisms such as ``U.S.`` and common title/month abbreviations are
    shielded during segmentation and restored afterward.
    """
    value = str(text or "")
    for abbreviation in _SENTENCE_ABBREVIATIONS:
        protected = abbreviation.replace(".", _SENTENCE_PERIOD_TOKEN)
        value = re.sub(re.escape(abbreviation), protected, value, flags=re.I)
    value = re.sub(
        r"\b(?:[A-Z]\.){2,}",
        lambda match: match.group(0).replace(".", _SENTENCE_PERIOD_TOKEN),
        value,
    )
    return value



def _strip_wire_dateline(text: str) -> str:
    """Remove wire-service datelines while retaining the reported event."""
    value = _spaces(text)
    if not value:
        return ""
    # Examples:
    #   RIYADH, Saudi Arabia, Aug. 3, 2026 /PRNewswire/ -- HUMAIN ...
    #   Aug. 3, 2026 /PRNewswire/ -- HUMAIN ...
    month = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    pattern = re.compile(
        rf"^(?:(?:[A-Z][A-Za-z .’'\-]+,\s*){{0,2}})?{month}\s+\d{{1,2}},\s+20\d{{2}}\s*/(?:PRNewswire|Business\s+Wire|GlobeNewswire)/\s*(?:--|[-—–])?\s*",
        flags=re.I,
    )
    value = pattern.sub("", value)
    # Reuters-style city/dateline furniture.
    value = re.sub(r"^[A-Z][A-Z .’'\-]{2,40},\s+(?:Aug|Sep|Sept|Oct|Nov|Dec|Jan|Feb|Mar|Apr|May|Jun|Jul)\.\s+\d{1,2}\s*[-—–]\s*", "", value)
    return _spaces(value)


def _strip_market_widget_furniture(text: str) -> str:
    """Remove ticker widgets embedded in article text without losing the actor."""
    value = _spaces(text)
    if not value:
        return ""
    # WSJ-like: ``Nvidia NVDA -2.86 % decrease; down pointing triangle reached deals ...``
    value = re.sub(
        r"^(?P<actor>[A-Z][A-Za-z0-9.&’'\-]*(?:\s+[A-Z][A-Za-z0-9.&’'\-]*){0,4})\s+"
        r"[A-Z]{1,6}\s+[+\-−]?\d+(?:\.\d+)?\s*%\s+(?:increase|decrease)\s*;?\s*"
        r"(?:up|down)\s+pointing\s+triangle\s+",
        lambda m: m.group('actor') + " ", value, flags=re.I,
    )
    return _spaces(value)


def _strip_inline_page_furniture(text: str) -> str:
    """Remove URLs, inline navigation labels, wire datelines and market widgets."""
    value = _spaces(text)
    if not value:
        return ""
    value = re.sub(r"https?://\S+", " ", value, flags=re.I)
    value = _strip_wire_dateline(value)
    value = _strip_market_widget_furniture(value)
    # Inline recommendation/navigation blocks are ambiguous by construction:
    # there is no reliable deterministic boundary between the linked headline
    # and the article sentence that follows.  Reject the contaminated sentence
    # and let another clean body sentence/candidate carry the event.
    if re.match(r"^(?:also\s+read|read\s+also|related|recommended)\s*[|:—–-]", value, flags=re.I):
        return ""
    # Standalone utility labels do not belong in evidence sentences.
    value = re.sub(r"^(?:here'?s\s+how|here\s+is\s+how)\b[^:]{0,140}:\s*", "", value, flags=re.I)
    return _spaces(value)


def _split_sentences(text: str) -> list[str]:
    clean = re.sub(r"[\t\r ]+", " ", str(text or "")).strip()
    clean = re.sub(r"\n{2,}", "\n", clean)
    # Some publisher extractors concatenate paragraph/sentence boundaries
    # without whitespace (``year.However``). Repair only common discourse
    # starts; broad punctuation splitting would damage abbreviations/initials.
    clean = re.sub(
        r"(?<=[A-Za-z0-9%”’])\.(?=(?:However|Overall|Meanwhile|Separately|The|Technology|Among|In|At|On)\b)",
        ". ", clean,
    )
    if not clean:
        return []
    protected = _protect_sentence_abbreviations(clean)
    pieces = re.split(r"(?<=[.!?])\s+(?=(?:[\"'“‘(]*[A-Z0-9]))", protected)
    output: list[str] = []
    for piece in pieces:
        sentence = _spaces(piece.replace(_SENTENCE_PERIOD_TOKEN, "."))
        sentence = _strip_inline_page_furniture(sentence)
        if 45 <= len(sentence) <= 650:
            output.append(sentence)
    return output

def _normalize_tokens(text: str) -> set[str]:
    stop = {
        "about", "after", "against", "among", "been", "being", "could", "from", "have",
        "into", "more", "over", "said", "says", "than", "that", "their", "there", "these",
        "they", "this", "through", "under", "were", "which", "with", "would", "year", "years",
    }
    return {token for token in re.findall(r"[a-z0-9]+", str(text or "").casefold()) if len(token) >= 4 and token not in stop}


def _headline_similarity(headline: str, sentence: str) -> float:
    left = " ".join(sorted(_normalize_tokens(headline)))
    right = " ".join(sorted(_normalize_tokens(sentence)))
    if not left or not right:
        return 0.0
    return float(SequenceMatcher(None, left, right).ratio())


_QUANTIFIED_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    r"\$\d[\d,]*(?:\.\d+)?(?:\s*(?:million|billion|trillion))?"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:%|percent|percentage points?|basis points?|bps)"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:million|billion|trillion)\s*(?:MWh|GWh|TWh|Tbps|Gbps|MW|GW|acre-feet|gallons?|jobs?|workers?|employees?|people|customers?|clients?|companies|firms|sites?|projects?)"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:MWh|GWh|TWh|Tbps|Gbps|MW|GW|acre-feet|gallons?|jobs?|workers?|employees?|people|customers?|clients?|companies|firms|sites?|projects?)"
    r")",
    flags=re.I,
)


def _has_number(text: str) -> bool:
    # Calendar years alone are not quantitative evidence.  This deliberately
    # requires a unit, percentage, money amount, or counted economic object.
    return bool(_QUANTIFIED_RE.search(str(text or "")))


def _has_event_action(text: str) -> bool:
    lower = str(text or "").casefold()
    return any(re.search(rf"(?<![a-z]){re.escape(verb)}(?![a-z])", lower) for verb in _EVENT_VERBS)


def _has_empirical_marker(text: str) -> bool:
    lower = str(text or "").casefold()
    return any(marker in lower for marker in _EMPIRICAL_MARKERS)


def reader_copy_has_selection_rationale(text: object) -> bool:
    """Return True when Reader prose explains the selector instead of the event."""
    value = _spaces(text).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _SELECTION_RATIONALE_PATTERNS)


def fact_is_current_development(text: object, *, reference_date: object, lookback_days: int = 7) -> bool:
    """Reject historical-context sentences from the Recent Developments anchor slot.

    A current article may cite 1989, 1999, 2021, or any other historical period
    as context.  That context can support synthesis after a current anchor fact
    qualifies, but it may not become the development merely because it contains
    a clean number.
    """
    value = _spaces(text)
    if not value:
        return False
    match = re.search(r"(20\d{2}|19\d{2})", str(reference_date or ""))
    if not match:
        return True
    reference_year = int(match.group(1))
    years = [int(year) for year in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", value)]
    if not years:
        return True

    # Explicit historical ranges ending before the current year are context.
    range_like = bool(re.search(
        r"\b(?:from|between)\b[^.]{0,80}?(?:19|20)\d{2}[^.]{0,40}?(?:to|and|through|until|-|–|—)[^.]{0,40}?(?:19|20)\d{2}",
        value, flags=re.IGNORECASE,
    ))
    if range_like and max(years) < reference_year:
        return False

    # A sentence whose newest explicit year is at least two calendar years old
    # cannot be the current anchor.  Prior-year comparisons remain allowed only
    # when the sentence also states a current-year observation.
    if max(years) <= reference_year - 2:
        return False
    if max(years) == reference_year - 1 and reference_year not in years:
        current_markers = (
            "now", "currently", "today", "this week", "this month", "this quarter",
            "this year", "latest", "recently", "has risen", "have risen",
            "has fallen", "have fallen", "has increased", "have increased",
            "has declined", "have declined", "is up", "is down", "are up", "are down",
        )
        if not any(marker in value.casefold() for marker in current_markers):
            return False
    return True


def _market_percent_move(text: object) -> float:
    """Return a percent explicitly attached to a stock/share-price move."""
    value = _spaces(text).casefold()
    move = r"(?:rose|surged|jumped|gained|rallied|fell|dropped|slid|tumbled|plunged|declined|advanced|climbed)"
    security = r"(?:shares?|stock)"
    patterns = (
        rf"{security}[^.;:]{{0,45}}?{move}[^.;:]{{0,20}}?(\d{{1,3}}(?:\.\d+)?)\s*%",
        rf"{security}[^.;:]{{0,35}}?(?:up|down)[^.;:]{{0,12}}?(\d{{1,3}}(?:\.\d+)?)\s*%",
        rf"{move}[^.;:]{{0,20}}?(\d{{1,3}}(?:\.\d+)?)\s*%[^.;:]{{0,35}}?{security}",
        rf"(?:up|down)[^.;:]{{0,12}}?(\d{{1,3}}(?:\.\d+)?)\s*%[^.;:]{{0,35}}?{security}",
    )
    values: list[float] = []
    for pattern in patterns:
        for match in re.findall(pattern, value, flags=re.IGNORECASE):
            try:
                values.append(float(match))
            except ValueError:
                continue
    return max(values, default=0.0)


def _money_magnitude_billions(text: object) -> float:
    value = _spaces(text).casefold()
    matches = re.findall(r"\$\s*(\d[\d,]*(?:\.\d+)?)\s*(million|billion|trillion)\b", value)
    amounts: list[float] = []
    for raw, unit in matches:
        try:
            amount = float(raw.replace(",", ""))
        except ValueError:
            continue
        factor = {"million": 0.001, "billion": 1.0, "trillion": 1000.0}[unit]
        amounts.append(amount * factor)
    return max(amounts, default=0.0)


def market_event_is_significant(fact: object, context: object = "") -> bool:
    """Separate AI relevance from Market-level significance.

    Company-specific AI news is not automatically a Market development.  A
    Market item must have broad read-through, involve a systemically important
    AI/technology issuer, produce an unusually large public-market repricing,
    or represent a major transaction.  This intentionally lets valid but small
    company evidence fall through rather than consuming scarce Market slots.
    """
    fact_text = _spaces(fact)
    combined = _spaces(f"{fact_text} {context}")
    lower = combined.casefold()

    broad_terms = domain_synthesis_terms("market", "broad_market")
    broad_market_action = any(term_present(lower, term) for term in broad_terms) and any(
        token in lower for token in (
            "rose", "fell", "gained", "declined", "rallied", "sold off",
            "breadth", "concentration", "weight", "valuation", "multiple",
            "entered the index", "added to the index", "removed from the index",
        )
    )
    benchmark_names = "|".join(re.escape(term) for term in domain_synthesis_terms("market", "benchmark_index"))
    benchmark_action = bool(benchmark_names) and bool(re.search(
        rf"(?:{benchmark_names})(?:\s+index)?\s+(?:rose|fell|gained|declined|rallied|dropped|slid|advanced|closed|ended)\b",
        lower, flags=re.IGNORECASE,
    ))
    if broad_market_action or benchmark_action:
        return True

    systemic = any(term_present(lower, term) for term in domain_synthesis_terms("market", "systemic_company"))
    operating_or_market_event = any(term_present(fact_text, term) for term in (
        "earnings", "revenue", "guidance", "bookings", "margin", "capex",
        "acquisition", "merger", "downgrade", "upgrade", "valuation",
    ))
    if systemic and operating_or_market_event:
        return True

    if _market_percent_move(combined) >= _MAJOR_MARKET_MOVE_PCT:
        return True

    major_transaction = any(term_present(fact_text, term) for term in domain_synthesis_terms("market", "major_transaction"))
    if major_transaction and _money_magnitude_billions(fact_text) >= _MAJOR_MARKET_TRANSACTION_B:
        return True

    return False


def reader_development_event_frame_issues(text: object) -> list[str]:
    """Require Reader copy to state a discrete event rather than a loose detail."""
    value = _spaces(text)
    lower = value.casefold()
    issues: list[str] = []
    if not value:
        return ["development is empty"]
    if re.match(r'^[\"“]', value):
        issues.append("development opens with a quotation instead of the event frame")
    if re.match(r"^over the past\b", lower):
        issues.append("development opens with a retrospective summary instead of a current event")
    if _CONTEXT_DEPENDENT_OPENING_RE.search(value):
        issues.append("development opens with context-dependent wording instead of naming the event")
    if re.search(r"\bcited\b.{0,100}\bas an example\b", lower):
        issues.append("development presents a subordinate example without the governing action")
    if re.search(r"\b(?:this segment|this sector|this market)\b", lower):
        issues.append("development relies on unresolved thematic context")
    if not (_has_event_action(value) or _headline_actor(value) or _has_empirical_marker(value) or _finance_transaction_in_motion(value)):
        issues.append("development does not state a concrete event or empirical release")
    return list(dict.fromkeys(issues))


def retained_reader_quality_gate(
    domain: str,
    fact: object,
    relevance: object,
    *,
    event_date: object,
    lookback_days: int = 7,
) -> tuple[bool, str]:
    """Content-based durable gate for already-vetted retained rows.

    Engine version never expires a grounded row.  Universal Reader-quality
    invariants still apply: a historical-context sentence cannot masquerade as
    the current event, selection rationale cannot leak into prose, and Market
    retains its separate significance boundary.
    """
    fact_text = _spaces(fact)
    relevance_text = _spaces(relevance)
    if not fact_is_current_development(fact_text, reference_date=event_date, lookback_days=lookback_days):
        return False, "retained fact is historical context rather than a current development"
    if len(_spaces(f"{fact_text} {relevance_text}").split()) > MAX_FACT_WORDS:
        return False, f"retained Reader copy exceeds the {MAX_FACT_WORDS}-word ceiling"
    copy_issues = recent_development_copy_issues(f"{fact_text} {relevance_text}")
    if copy_issues:
        return False, f"retained Reader copy failed hygiene: {copy_issues[0]}"
    frame_issues = reader_development_event_frame_issues(fact_text)
    if frame_issues:
        return False, f"retained Reader copy lacks event framing: {frame_issues[0]}"
    if reader_copy_has_selection_rationale(relevance_text):
        return False, "retained Reader prose contains selection-rationale language"
    if str(domain or "").strip().casefold() == "market" and not market_event_is_significant(fact_text, relevance_text):
        return False, "retained Market item is AI-relevant but not market-significant"
    return True, "retained source-grounded event remains Reader-eligible"


def _finance_transaction_in_motion(text: str) -> bool:
    """Recognize a concrete, quantified financing process before final pricing.

    Finance often becomes material while a debt sale/refinancing is being
    marketed, prepared, sought, or arranged. That is an active capital-markets
    development, not generic outlook commentary, when the chosen source fact
    itself contains a financing instrument, magnitude, and transaction action.
    """
    value = str(text or "").casefold()
    if not _has_number(value):
        return False
    finance_noun = any(term_present(value, term) for term in (
        "bond", "bonds", "debt", "loan", "loans", "financing", "refinancing",
        "notes", "lease", "leases", "credit facility",
    ))
    action = any(phrase in value for phrase in (
        "preparing to offload", "prepare to offload", "preparing to sell",
        "plans to sell", "planning to sell", "seeks to sell", "looking to sell",
        "preparing to raise", "plans to raise", "planning to raise",
        "seeks to raise", "looking to raise", "aims to raise",
        "preparing to issue", "plans to issue", "planning to issue",
        "seeks to issue", "looking to issue", "set to issue",
        "set to be refinanced", "will be refinanced", "plans to refinance",
        "planning to refinance", "seeks to refinance", "looking to refinance",
        "marketing", "arranging", "syndicating", "offload",
    ))
    return finance_noun and action


def _sentence_score(sentence: str, *, domain: str, index: int) -> float:
    score = max(0.0, 6.0 - index * 0.18)
    score += sum(2.5 for term in domain_relevance_terms(domain) if term_present(sentence, str(term)))
    score += sum(1.8 for term in domain_topic_anchors(domain) if term_present(sentence, str(term)))
    if _has_event_action(sentence):
        score += 7.0
    if _has_number(sentence):
        # Concrete magnitudes usually carry more evidentiary value than a
        # generic explanatory sentence that merely names several domain terms.
        score += 12.0
    if _has_empirical_marker(sentence):
        score += 8.0
    if sentence.count('"') >= 2 or sentence.count("“") >= 1:
        score -= 5.0
    lower = sentence.casefold()
    if any(term in lower for term in ("believes", "thinks", "argues", "opinion", "could eventually", "may someday")):
        score -= 4.0
    # Prefer event-framing sentences over subordinate examples or quotations.
    if any(term in lower for term in (
        " approved ", " ordered ", " signed ", " launched ", " released ",
        " reported ", " completed ", " announced ", " filed ", " awarded ",
    )):
        score += 4.0
    if re.match(r'^[\"“]', sentence.strip()):
        score -= 8.0
    if re.search(r"\bcited\b.{0,80}\bas an example\b", lower):
        score -= 5.0
    if re.match(r"^(?:over the past|during (?:a|the) )", lower):
        score -= 2.0
    return score


def _source_sentence_candidates(doc: SourceDocument, *, domain: str) -> list[tuple[float, str]]:
    candidates = _split_sentences(doc.body_text)
    scored = [(_sentence_score(sentence, domain=domain, index=index), sentence) for index, sentence in enumerate(candidates[:100])]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _domain_grounding_gate(
    domain: str,
    *,
    headline: str,
    source_text: str,
    fact_sentence: str,
    qualification_tier: str = "A",
) -> tuple[bool, str]:
    combined = _spaces(f"{headline} {source_text}")
    lower = combined.casefold()
    fact_lower = fact_sentence.casefold()
    tier_index = current_context_tier_index(qualification_tier)
    broad_coverage = tier_index >= current_context_tier_index("C")
    floor_coverage = tier_index >= current_context_tier_index("D")

    relevance_terms = tuple(domain_relevance_terms(domain))
    if not any(term_present(source_text, str(term)) for term in relevance_terms):
        return False, "source body does not establish the domain-relevant subject"
    if not any(term_present(fact_sentence, str(term)) for term in relevance_terms):
        return False, "selected source fact does not itself establish the domain-relevant subject"
    tier_policy = current_context_qualification_policy(domain, qualification_tier)
    if bool(tier_policy.get("require_topic_anchor", True)) and domain_topic_anchors(domain) and not any(term_present(source_text, str(term)) for term in domain_topic_anchors(domain)):
        # A few physical domains may qualify through a system-wide measured constraint.
        if domain == "grid_storage" and _has_number(source_text) and any(term in lower for term in _SYSTEM_GRID_TERMS):
            pass
        elif domain == "water" and _has_number(source_text) and any(term in lower for term in _SYSTEM_WATER_TERMS):
            pass
        else:
            return False, "source body does not establish the required AI/technology or system-wide anchor"

    finance_transaction_action = domain == "finance" and _finance_transaction_in_motion(fact_sentence)
    finance_offering_action = (
        domain == "finance"
        and _has_number(fact_sentence)
        and any(term in fact_lower for term in ("bond offering", "bond sale", "debt offering", "notes offering", "offering"))
        and any(term in fact_lower for term in ("raise", "raising", "raised", "launch", "launched", "priced", "price", "sell", "sale", "sold", "offered", "marketed"))
    )
    if (
        not _has_event_action(fact_sentence)
        and not _has_empirical_marker(fact_sentence)
        and not finance_offering_action
        and not finance_transaction_action
    ):
        return False, "best source sentence is topical/commentary rather than a concrete development"

    if domain in {"workforce", "economic_impact", "adoption"}:
        if not broad_coverage and not _has_number(fact_sentence):
            return False, "domain requires a quantified observed result; topic commentary or unquantified interpretation is not enough"

    if domain == "finance":
        finance_fact_terms = domain_relevance_terms("finance")
        monetary_policy = _synthesis_match("finance", "monetary_policy", fact_sentence)
        concrete_policy_action = any(term in fact_lower for term in (
            "held", "maintained", "raised", "increased", "cut", "reduced", "lowered",
            "decided", "voted", "target range", "basis point", "bps", "rate hike",
            "rate cut", "policy rate", "federal funds rate",
        ))
        empirical_release = _has_empirical_marker(fact_sentence) and _has_number(fact_sentence)
        offering_action = (
            _has_number(fact_sentence)
            and any(term in fact_lower for term in ("bond offering", "bond sale", "debt offering", "notes offering", "offering"))
            and any(term in fact_lower for term in ("raise", "raising", "raised", "launch", "launched", "priced", "price", "sell", "sale", "sold", "offered", "marketed"))
        )
        if monetary_policy:
            if not (concrete_policy_action or empirical_release):
                return False, "central-bank commentary without a policy action or new empirical release is not a Finance development"
        elif not any(term in fact_lower for term in finance_fact_terms):
            return False, "selected source fact is not itself a financing, credit, lease, or capital-markets development"
        if not (
            _has_event_action(fact_sentence)
            or _has_empirical_marker(fact_sentence)
            or offering_action
            or _finance_transaction_in_motion(fact_sentence)
        ):
            return False, "Finance fact names a financing topic but does not establish a concrete transaction, obligation, ratings action, or measured market change"

    if domain == "connectivity":
        # Connectivity is especially prone to globally interesting but platform-
        # irrelevant cable headlines.  The *fact itself* must tie the event to
        # AI/cloud/data-center demand, unless the route is clearly a strategic
        # U.S. compute-market path.  A stray mention elsewhere in the article is
        # not enough.
        relevant_stack = any(term in fact_lower for term in _AI_INFRA_TERMS)
        strategic_us = any(term in fact_lower for term in _US_STRATEGIC_CONNECTIVITY_TERMS)
        if not floor_coverage and not (relevant_stack or strategic_us):
            return False, "connectivity fact is not tied to an AI/cloud compute market or strategic U.S. route"
        if not any(term in fact_lower for term in ("fiber", "fibre", "cable", "landing", "backbone", "internet exchange", "peering", "route")):
            return False, "source fact does not establish a connectivity capacity/route event"

    if domain == "power":
        direct_ai_load = any(term in fact_lower for term in ("data center", "datacenter", "ai", "hyperscaler", "cloud"))
        quantified_system = _has_number(fact_sentence) and any(term in fact_lower for term in ("electricity", "power", "generation", "load", "capacity", "nuclear", "gas"))
        operational_action = any(term in fact_lower for term in (
            "signed", "secured", "approved", "commissioned", "opened", "began", "started",
            "awarded", "contract", "power purchase agreement", "ppa", "tariff", "rate case",
            "retired", "closed", "added", "increased", "reduced", "held",
        ))
        if not broad_coverage and not (direct_ai_load or quantified_system):
            return False, "power item lacks a concrete AI-load connection or quantified system-wide change"
        if broad_coverage and not (direct_ai_load or quantified_system or operational_action):
            return False, "power item lacks an operational, measured, or AI-load development"
        if any(term in fact_lower for term in ("published", "released", "resource", "guide", "overview")) and not (quantified_system or operational_action):
            return False, "informational power publication does not establish a new operational or measured development"

    if domain == "grid_storage":
        binding_action = any(term in fact_lower for term in (
            "approved", "ordered", "adopted", "implemented", "rule", "standard", "tariff",
            "construction", "commissioned", "energized", "curtail", "curtailed", "transmission",
            "substation", "transformer",
        ))
        broader_action = any(term in fact_lower for term in (
            "proposed", "filed", "requested", "announced", "selected", "awarded", "planned",
            "interconnection", "storage", "battery", "queue", "grid",
        ))
        if not (_has_number(fact_sentence) or binding_action or (broad_coverage and broader_action)):
            return False, "grid item lacks a concrete measured constraint or binding/physical system action"
        if (
            not floor_coverage
            and any(term in fact_lower for term in ("roadmap", "recommendation", "guide", "framework"))
            and not (_has_number(fact_sentence) or any(term in fact_lower for term in ("adopted", "implemented", "approved", "ordered")))
        ):
            return False, "nonbinding grid roadmap or guidance is context, not a material development"

    if domain == "water":
        formal_action = any(term in fact_lower for term in (
            "approved", "proposed", "ordered", "restriction", "emergency", "permit", "allocation",
        ))
        broader_action = any(term in fact_lower for term in (
            "announced", "funding", "construction", "project", "expansion", "reuse", "treatment",
            "groundwater", "withdrawal", "drought", "cooling",
        ))
        if not (_has_number(fact_sentence) or formal_action or (broad_coverage and broader_action)):
            return False, "water item lacks a concrete measured constraint or formal action"

    return True, "source body establishes a concrete, domain-relevant development"


def _development_anchor_candidates(
    doc: SourceDocument,
    *,
    candidate: dict,
    domain: str,
    headline: str,
) -> tuple[list[tuple[float, str]], str]:
    """Identify a clear current development before extracting Reader prose.

    This is intentionally lead-bounded.  If the article's title/lead evidence
    does not establish a material development, AI Macro rejects the candidate
    instead of searching deep in the page for a technically true sentence that
    can be used to rationalize inclusion.
    """
    sentences = _split_sentences(doc.body_text)[:MAX_DEVELOPMENT_LEAD_SENTENCES]
    if not sentences:
        return [], "source lead did not contain substantive sentences"

    lead_text = _spaces(" ".join(sentences))
    reference_date = candidate.get("event_date") or doc.published_date or doc.modified_date
    lookback_days = max(int(candidate.get("lookback_days", 7) or 7), 1)
    accepted: list[tuple[float, str]] = []
    rejection_reasons: list[str] = []

    tier_policy = current_context_qualification_policy(
        domain, str(candidate.get("qualification_tier") or "A")
    )
    minimum_anchor_score = float(tier_policy.get("minimum_anchor_score", 8.0) or 8.0)

    for index, sentence in enumerate(sentences):
        score = _sentence_score(sentence, domain=domain, index=index)
        if score < minimum_anchor_score:
            continue
        if not fact_is_current_development(sentence, reference_date=reference_date, lookback_days=lookback_days):
            rejection_reasons.append("lead fact was historical context rather than a current development")
            continue
        gate_ok, gate_reason = _domain_grounding_gate(
            domain,
            headline=headline,
            source_text=lead_text,
            fact_sentence=sentence,
            qualification_tier=str(candidate.get("qualification_tier") or "A"),
        )
        if not gate_ok:
            rejection_reasons.append(gate_reason)
            continue
        if domain == "market" and not market_event_is_significant(sentence, lead_text):
            rejection_reasons.append("AI-relevant company news lacked Market-level significance")
            continue
        accepted.append((score, sentence))

    accepted.sort(key=lambda item: item[0], reverse=True)
    if accepted:
        return accepted, "lead evidence establishes a current, material development"

    # Prefer the most informative repeated failure reason for auditability.
    if rejection_reasons:
        from collections import Counter
        reason = Counter(rejection_reasons).most_common(1)[0][0]
        return [], reason
    return [], "source lead did not establish a clear current material development"


def _first_magnitude(text: str) -> str:
    match = _QUANTIFIED_RE.search(str(text or ""))
    return _spaces(match.group(0)) if match else ""


def _first_year(text: str) -> str:
    match = re.search(r"\b(20\d{2})\b", str(text or ""))
    return match.group(1) if match else ""


def _route_phrase(text: str) -> str:
    value = _spaces(text)
    for pattern in (
        r"\b(?:connecting|linking)\s+([^.;,]{2,70}?)\s+(?:to|with)\s+([^.;,]{2,70}?)(?=\s+(?:for|serving|to serve|that|which)\b|[.;,]|$)",
        r"\bbetween\s+([^.;,]{2,70}?)\s+and\s+([^.;,]{2,70}?)(?=\s+(?:for|serving|to serve|that|which)\b|[.;,]|$)",
    ):
        match = re.search(pattern, value, flags=re.I)
        if match:
            return _spaces(f"{match.group(1)}–{match.group(2)}")
    return ""


def _support_sentence(source_text: str, fact: str, *, terms: tuple[str, ...] = ()) -> str:
    fact_tokens = _normalize_tokens(fact)
    best: tuple[float, str] | None = None
    for index, sentence in enumerate(_split_sentences(source_text)[:80]):
        if _headline_similarity(fact, sentence) >= 0.90:
            continue
        lower = sentence.casefold()
        score = 0.0
        score += 4.0 if _has_number(sentence) else 0.0
        score += sum(2.0 for term in terms if term.casefold() in lower)
        score += 2.5 if any(marker in lower for marker in (
            "because", "due to", "contributed", "driven by", "will supply", "will serve",
            "begin", "cover", "expected", "capacity", "constraint", "shortage", "bottleneck",
            "customers", "sites", "campuses", "route", "market",
        )) else 0.0
        overlap = len(fact_tokens.intersection(_normalize_tokens(sentence)))
        score += min(3.0, overlap * 0.6)
        score -= index * 0.05
        if best is None or score > best[0]:
            best = (score, sentence)
    return _spaces(best[1]) if best and best[0] >= 3.0 else ""


def _neutralize_journalistic_lead(text: str) -> str:
    """Remove narrow attribution/appositive furniture from an explicit event."""
    value = _spaces(text)
    # ``Company said on Tuesday it signed ...`` -> ``Company signed ...``
    match = re.match(
        r"^(.{2,90}?)\s+said(?:\s+on\s+[A-Z][a-z]+)?\s+(?:that\s+)?it\s+(?:has\s+|had\s+)?(.+)$",
        value,
        flags=re.I,
    )
    if match:
        actor, action = _spaces(match.group(1)), _spaces(match.group(2))
        if actor and action and len(actor.split()) <= 14:
            value = f"{actor} {action}"

    # ``HUMAIN, a PIF company delivering ..., today announced ...`` and
    # ``CoreWeave, an AI infrastructure provider, reported ...`` carry useful
    # background but bury the event.  Remove only one bounded appositive when a
    # recognized event verb immediately follows it.
    verbs = "|".join(sorted((re.escape(v) for v in _EVENT_VERBS), key=len, reverse=True))
    appositive = re.match(
        rf"^(?P<actor>[A-Z][A-Za-z0-9.&’'\-]*(?:\s+[A-Z][A-Za-z0-9.&’'\-]*){{0,5}}),\s+"
        rf"(?:(?:an?|the)\s+)?[^,]{{4,120}},\s+(?:today\s+|on\s+[A-Z][a-z]+\s+)?(?P<verb>{verbs})\b(?P<rest>.+)$",
        value,
        flags=re.I,
    )
    if appositive:
        value = _spaces(f"{appositive.group('actor')} {appositive.group('verb')}{appositive.group('rest')}")

    value = re.sub(r",?\s+the company said(?:\s+on\s+[A-Z][a-z]+)?\.?$", "", value, flags=re.I)
    value = re.sub(r",?\s+the agency said(?:\s+on\s+[A-Z][a-z]+)?\.?$", "", value, flags=re.I)
    return _spaces(value)


_INSTITUTION_SURNAME_RE = re.compile(
    r"\b(?:Fed(?:eral Reserve)?|Treasury|SEC|Commerce|DOE|Energy Department|FERC|ECB|Bank of England)(?:['’]s)?\s+([A-Z][A-Za-z'’-]+)\b"
)


def _identity_for_surname(source_text: str, surname: str) -> str:
    """Resolve headline shorthand to the source's first full identity.

    This is intentionally conservative: a surname is expanded only when the
    source body contains one unique first+last name ending in that surname.
    For common policy roles we preserve the institutional title when the source
    provides it, so Reader copy cannot turn ``Fed's Paulson`` into a mystery.
    """
    surname = _spaces(surname)
    if not surname:
        return ""
    names = re.findall(
        rf"\b([A-Z][A-Za-z'’\-]+\s+{re.escape(surname)})\b",
        str(source_text or ""),
    )
    cleaned = []
    for value in names:
        value = _spaces(value)
        if len(value.split()) < 2 or value.casefold().endswith(("bank " + surname).casefold()):
            continue
        if value not in cleaned:
            cleaned.append(value)
    if len(cleaned) != 1:
        return ""
    full_name = cleaned[0]
    role_patterns = (
        rf"Federal Reserve Bank of [A-Z][A-Za-z .'-]+ President\s+{re.escape(full_name)}",
        rf"Federal Reserve Governor\s+{re.escape(full_name)}",
        rf"Federal Reserve Chair(?:man)?\s+{re.escape(full_name)}",
        rf"U\.S\. Treasury Secretary\s+{re.escape(full_name)}",
        rf"Treasury Secretary\s+{re.escape(full_name)}",
        rf"U\.S\. Commerce Secretary\s+{re.escape(full_name)}",
        rf"Energy Secretary\s+{re.escape(full_name)}",
    )
    for pattern in role_patterns:
        match = re.search(pattern, str(source_text or ""))
        if match:
            return _spaces(match.group(0))
    return full_name


def _public_identity_for_bare_surname(source_text: str, surname: str) -> str:
    """Resolve a bare public-official surname from the source body."""
    surname = _spaces(surname)
    if not surname or not re.fullmatch(r"[A-Z][A-Za-z'’\-]+", surname):
        return ""
    roles = r"(?:Governor|Gov\.|President|Chair(?:man|woman)?|Senator|Sen\.|Secretary|Commissioner|Mayor)"
    patterns = (
        rf"\b([A-Z][A-Za-z.'’\-]+\s+{roles}\s+[A-Z][A-Za-z'’\-]+\s+{re.escape(surname)})\b",
        rf"\b({roles}\s+[A-Z][A-Za-z'’\-]+\s+{re.escape(surname)})\b",
    )
    matches: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, str(source_text or "")):
            identity = _spaces(match.group(1))
            if identity and identity not in matches:
                matches.append(identity)
    if not matches:
        return ""
    # Overlapping role forms (``Texas Governor Greg Abbott`` and
    # ``Governor Greg Abbott``) describe the same identity; prefer the fuller
    # source form rather than treating that overlap as ambiguity.
    return max(matches, key=lambda item: (len(item.split()), len(item)))


_DANGLING_FACT_OPENING_RE = re.compile(
    r"^(?:"
    r"(?:the\s+)?(?:company|firm|chipmaker|manufacturer|operator|developer|utility|regulator|agency|commission|provider|vendor|lender|borrower|venture)\b"
    r"|(?:they|their|it|its)\b"
    r"|leading\s+up\s+to\s+their\b"
    r")",
    flags=re.IGNORECASE,
)

_CONTEXT_DEPENDENT_OPENING_RE = re.compile(
    r"^(?:"
    r"if\s+(?:built|approved|completed|implemented|constructed|developed)\b"
    r"|(?:most\s+of\s+)?(?:this|the)\s+(?:capacity|funding|investment|increase|decline|growth)\b"
    r"|management\s+(?:expects?|said|says|plans?|believes?)\b"
    r"|the\s+(?:(?:january|february|march|april|may|june|july|august|september|october|november|december|latest|monthly|quarterly)\s+)?(?:financing\s+push|move|deal|transaction|project|proposal|plan|measure|"
    r"proposed\s+legislation|legislation|figures|results|letter|directive|order|announcement)\b"
    r"|these\s+(?:figures|results|plans|measures)\b"
    r")",
    flags=re.IGNORECASE,
)


def _explicit_actor_action(text: str) -> bool:
    """Return True when the opening clause names an actor and an event action."""
    value = _spaces(text)
    if not value or _DANGLING_FACT_OPENING_RE.search(value) or _CONTEXT_DEPENDENT_OPENING_RE.search(value):
        return False
    words = value.split()[:22]
    prefix = " ".join(words)
    for verb in _EVENT_VERBS:
        match = re.search(rf"(?<![A-Za-z]){re.escape(verb)}(?![A-Za-z])", prefix, flags=re.I)
        if not match:
            continue
        actor = prefix[:match.start()].strip(" ,:;-—–")
        if not (1 <= len(actor.split()) <= 14 and re.search(r"[A-Za-z]", actor)):
            continue
        # Page fragments such as ``of respondents ... team cuts`` must not be
        # mistaken for an actor merely because a later noun matches an event
        # verb.  Real event frames normally open with a named/proper actor.
        if re.match(r"^(?:of|in|on|for|from|with|by|at|as|to|and|or|while|after|before|during)\b", actor, flags=re.I):
            continue
        if not re.match(r"^(?:[A-Z]|[0-9]+[A-Za-z]|[a-z][A-Z])", actor):
            continue
        return True
    return False

def _strip_embedded_heading_prefix(text: str, *, headline: str = "") -> str:
    """Strip page furniture concatenated immediately ahead of event prose.

    The old implementation only recognized question-style headings.  Real
    publisher pages also splice subtitles such as ``Follows growing scrutiny
    from state regulators`` directly onto the first paragraph.  A prefix may
    be removed only when a complete actor/action event sentence remains.
    """
    value = _spaces(text)
    words = value.split()
    if len(words) < 14:
        return value
    # Obvious heading shapes get a wider search window.  For other prefixes the
    # cut is kept short so a genuine introductory clause is not casually lost.
    heading_like = bool(re.match(
        r"^(?:why|how|what|when|where|follows?|following|inside|analysis|update|exclusive|breaking)\b",
        value, flags=re.I,
    ))
    if not heading_like:
        return value
    max_cut = min(14, len(words) - 10)
    candidates: list[tuple[float, int, str]] = []
    headline_tokens = _normalize_tokens(headline) if headline else set()
    for cut in range(2, max_cut + 1):
        prefix = _spaces(" ".join(words[:cut]))
        tail = _spaces(" ".join(words[cut:]))
        if len(tail.split()) < 10 or not re.match(r"^[A-Z][A-Za-z0-9&.'’\-]*\b", tail) or not _explicit_actor_action(tail):
            continue
        # Do not strip a normal comma-delimited introductory clause unless it
        # has a strong page-heading signature.
        if prefix.endswith(",") and not heading_like:
            continue
        score = -float(cut) * 0.05
        if headline:
            score = float(cut) * 0.02
            score += _headline_similarity(headline, tail) * 12.0
            score += min(4.0, len(headline_tokens.intersection(_normalize_tokens(tail))) * 0.8)
        candidates.append((score, cut, tail))
    if candidates:
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]
    return value

_HEADLINE_ACTOR_RE = re.compile(
    r"^(.{2,80}?)\s+(?:"
    r"announces?|announced|approves?|approved|backs?|backed|begins?|began|commits?|committed|"
    r"cuts?|cut|delays?|delayed|files?|filed|launches?|launched|lines\s+up|opens?|opened|"
    r"orders?|ordered|plans?|planned|proposes?|proposed|raises?|raised|refinances?|refinanced|"
    r"reports?|reported|secures?|secured|signs?|signed|starts?|started|unveils?|unveiled|"
    r"reaches?|reached|invests?|invested|partners?|partnered|deploys?|deployed|directs?|directed|stacks?|stacked|beats?|forecast(?:s|ed)?|exceeds?|tops?|"
    r"develops?|developed|conducts?|conducted|establishes?|established|makes?\s+(?:an?\s+)?investment|"
    r"will\s+(?:build|buy|invest|open|sell|spend|supply)"
    r")\b",
    flags=re.IGNORECASE,
)


def _source_defined_acronym_expansion(source_text: str, acronym: str) -> str:
    """Return a source-body expansion for a specialized acronym, if explicit."""
    acronym = _spaces(acronym).upper()
    if not acronym:
        return ""
    pattern = re.compile(
        rf"\b([A-Z][A-Za-z&.'’\-]*(?:\s+(?:[A-Z][A-Za-z&.'’\-]*|of|the|and|for|to|&)){{1,8}})\s*\(\s*{re.escape(acronym)}\s*\)",
    )
    matches = []
    for match in pattern.finditer(str(source_text or "")):
        expansion = re.sub(r"^The\s+", "", _spaces(match.group(1)), flags=re.I)
        if expansion and expansion not in matches:
            matches.append(expansion)
    return matches[0] if len(matches) == 1 else ""


def _headline_actor(headline: str) -> str:
    """Extract a bounded explicit actor from an event-style headline."""
    value = _spaces(headline)
    match = _HEADLINE_ACTOR_RE.match(value)
    if not match:
        return ""
    actor = _spaces(match.group(1)).strip(" ,:;-—–")
    if not actor or len(actor.split()) > 8:
        return ""
    if re.match(r"^(?:how|why|what|when|where|the\s+(?:company|firm|chipmaker|market))\b", actor, flags=re.I):
        return ""
    return actor


def _resolve_generic_actor(value: str, headline: str) -> str:
    """Replace a generic first-reference noun/pronoun only when headline identity is explicit."""
    actor = _headline_actor(headline)
    if not actor:
        return value
    generic = re.match(
        r"^(?:the\s+)?(?:company|firm|chipmaker|manufacturer|operator|developer|utility|regulator|agency|commission|provider|vendor|lender|borrower|venture)\b",
        value,
        flags=re.I,
    )
    if generic:
        return actor + value[generic.end():]
    management = re.match(r"^management\s+", value, flags=re.I)
    if management:
        return actor + " management " + value[management.end():]
    match = re.match(r"^(?:they|it)\s+", value, flags=re.I)
    if match:
        return actor + " " + value[match.end():]
    # Resolve a generic actor that appears after a short introductory phrase,
    # e.g. ``During a hearing, they approved ...``.
    match = re.match(r"^(.{1,90}?,\s*)(?:they|it)\s+", value, flags=re.I)
    if match:
        return match.group(1) + actor + " " + value[match.end():]
    match = re.match(r"^(?:their|its)\s+", value, flags=re.I)
    if match:
        return actor + "'s " + value[match.end():]
    match = re.match(r"^Leading\s+up\s+to\s+their\s+(.+?),\s*they\s+(.+)$", value, flags=re.I)
    if match:
        return f"{actor}, leading up to its {_spaces(match.group(1))}, {_spaces(match.group(2))}"
    return value


_DUPLICATE_ACRONYM_EXPANSION_RE = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z&.'’\-]*(?:\s+(?:[A-Z][A-Za-z&.'’\-]*|of|the|and|for|to|&)){1,8})"
    r"\s*\(\s*(?P=name)\s*\(\s*(?P<acronym>[A-Z]{2,6})\s*\)\s*\)"
)


def _collapse_duplicate_acronym_expansions(text: str) -> str:
    value = _spaces(text)
    for _ in range(4):
        updated = _DUPLICATE_ACRONYM_EXPANSION_RE.sub(
            lambda match: f"{match.group('name')} ({match.group('acronym')})", value
        )
        if updated == value:
            break
        value = updated
    return _spaces(value)


def _resolve_first_reference_identity(fact: str, headline: str, source_text: str) -> str:
    value = _collapse_duplicate_acronym_expansions(fact)
    identity_matches = list(_INSTITUTION_SURNAME_RE.finditer(str(headline or "")))
    seen_surnames: set[str] = set()
    for match in identity_matches:
        surname = _spaces(match.group(1))
        if not surname or surname in seen_surnames:
            continue
        seen_surnames.add(surname)
        identity = _identity_for_surname(source_text, surname)
        if not identity or identity.casefold() in value.casefold():
            continue
        shorthand = _spaces(match.group(0))
        updated = value
        if shorthand and re.search(re.escape(shorthand), value, flags=re.I):
            updated = re.sub(re.escape(shorthand), identity, value, count=1, flags=re.I)
        else:
            updated = re.sub(rf"\b{re.escape(surname)}\b", identity, value, count=1)
        if updated != value:
            value = updated

    headline_actor = _headline_actor(headline)
    if headline_actor and len(headline_actor.split()) == 1:
        identity = _public_identity_for_bare_surname(source_text, headline_actor)
        if identity and re.match(rf"^{re.escape(headline_actor)}\b", value, flags=re.I):
            value = re.sub(rf"^{re.escape(headline_actor)}\b", identity, value, count=1, flags=re.I)

    # Expand an acronym only when the source itself defines it.  The source
    # body remains the authority; the headline may contribute jurisdiction.
    for acronym in re.findall(r"\b[A-Z]{2,6}\b", value):
        if acronym in {"AI", "US", "USA", "CEO", "CFO", "IPO"}:
            continue
        expansion = _source_defined_acronym_expansion(source_text, acronym)
        if acronym == "SCC" and expansion and "virginia" in headline.casefold() and "virginia" not in expansion.casefold():
            expansion = "Virginia " + expansion
        if not expansion:
            continue
        # Do not expand an acronym again when the sentence already supplies
        # the source-defined full name. This prevents nested artifacts such as
        # ``Electric Reliability Council of Texas (Electric Reliability Council
        # of Texas (ERCOT))``.
        if expansion.casefold() in value.casefold():
            continue
        value = re.sub(rf"\b{re.escape(acronym)}\b", f"{expansion} ({acronym})", value, count=1)

    value = _resolve_generic_actor(value, headline)
    return _spaces(value)


def _compress_fact(sentence: str, *, headline: str = "") -> str:
    """Normalize one source sentence without inventing or mechanically chopping.

    Cleanup removes page furniture first.  A sentence that remains malformed or
    context-dependent is not repaired into eligibility; the caller must choose a
    different event frame/candidate.
    """
    text = _strip_inline_page_furniture(sentence)
    text = _strip_embedded_heading_prefix(_neutralize_journalistic_lead(text), headline=headline)
    # Remove a short scene-setting temporal clause when the remaining sentence
    # already names the actor/action. This preserves the event while avoiding
    # weak openings such as ``During a public hearing yesterday, ...``.
    intro = re.match(r"^(?:During|At|On|After|Before)\b[^,]{2,90},\s+(.+)$", text, flags=re.I)
    if intro and _explicit_actor_action(_spaces(intro.group(1))):
        text = _spaces(intro.group(1))
    if ":" in text:
        lead, tail = (_spaces(part) for part in text.split(":", 1))
        if _DANGLING_FACT_OPENING_RE.search(lead) and tail and not _DANGLING_FACT_OPENING_RE.search(tail):
            text = tail
    text = re.sub(r"^[A-Z][A-Z .,'-]{2,45}\s+[—–-]\s+", "", text)
    text = re.sub(r"^\([^)]*Reuters\)\s*[-—–]?\s*", "", text, flags=re.I)
    text = re.sub(r"\s+according to (?:the|a) [^.]{0,80}$", "", text, flags=re.I)
    text = re.sub(r",?\s+(?:he|she|they)\s+said\.?$", "", text, flags=re.I)
    text = _spaces(text)
    if not text:
        return ""
    if len(text.split()) <= MAX_FACT_WORDS:
        return _sentence(text)

    boundaries = re.split(
        r"(?<=;)\s+|\s+[—–]\s+|\s+(?:while|although|but|whereas)\s+",
        text,
        maxsplit=3,
        flags=re.I,
    )
    running: list[str] = []
    candidates: list[str] = []
    for part in boundaries:
        running.append(_spaces(part))
        candidate = _spaces(" ".join(running))
        words = len(candidate.split())
        if 12 <= words <= MAX_FACT_WORDS and (_explicit_actor_action(candidate) or _has_empirical_marker(candidate)):
            candidates.append(candidate)
        if words > MAX_FACT_WORDS:
            break
    if candidates:
        return _sentence(max(candidates, key=lambda item: len(item.split())))
    return ""

def _presentation_score(text: str) -> float:
    """Prefer copy that frames the event before details or quotations."""
    value = _spaces(text)
    lower = value.casefold()
    words = len(value.split())
    score = 0.0
    score += 7.0 if _has_event_action(value) else 0.0
    score += 3.0 if _has_number(value) else 0.0
    score += min(4.0, max(0, words - 18) * 0.12)
    if 25 <= words <= PREFERRED_FACT_WORDS:
        score += 3.0
    if words < 18:
        score -= 5.0
    if re.match(r'^[\"“]', value):
        score -= 10.0
    if re.match(r"^(?:over the past|during (?:a|the) )", lower):
        score -= 2.0
    if re.search(r"\bcited\b.{0,80}\bas an example\b", lower):
        score -= 5.0
    if re.search(r"\b(?:this segment|the segment|the sector|the market)\b", lower) and words < 30:
        score -= 6.0
    return score


def _format_source_sentence(sentence: str, *, headline: str, source_text: str) -> str:
    compressed = _compress_fact(sentence, headline=headline)
    if not compressed:
        return ""
    fact = _sentence(_resolve_first_reference_identity(compressed, headline, source_text))
    if not fact or len(fact.split()) > MAX_FACT_WORDS:
        return ""
    if recent_development_copy_issues(fact):
        return ""
    if reader_development_event_frame_issues(fact):
        return ""
    return fact


def _format_support_sentence(sentence: str, *, headline: str, source_text: str) -> str:
    """Normalize one grounded context/detail sentence without requiring a second event."""
    compressed = _compress_fact(sentence, headline=headline)
    if not compressed:
        return ""
    value = _sentence(_resolve_first_reference_identity(compressed, headline, source_text))
    if not value or len(value.split()) > MAX_FACT_WORDS:
        return ""
    if recent_development_copy_issues(value) or reader_copy_has_selection_rationale(value):
        return ""
    if re.match(r'^[\"“]', value):
        return ""
    return value


def _event_identity_tokens(text: str, domain: str) -> set[str]:
    tokens = _normalize_tokens(text)
    generic: set[str] = {
        "artificial", "intelligence", "company", "companies", "market", "markets",
        "project", "projects", "development", "developments", "reported", "announced",
        "approved", "signed", "plans", "planned", "data", "center", "centers",
    }
    for term in domain_relevance_terms(domain):
        generic.update(_normalize_tokens(str(term)))
    return {token for token in tokens if token not in generic}


def _same_event_context(frame: str, support: str, *, domain: str, distance: int) -> bool:
    """Require a support sentence to remain attached to the same event."""
    left = _event_identity_tokens(frame, domain)
    right = _event_identity_tokens(support, domain)
    overlap = left.intersection(right)
    if len(overlap) >= (1 if distance <= 1 else 2):
        return True
    if _headline_similarity(frame, support) >= (0.28 if distance <= 1 else 0.38):
        return True
    return False


def _numeric_identity_tokens(text: str) -> set[str]:
    return {token.replace(",", "") for token in re.findall(r"\b\d[\d,]*(?:\.\d+)?\b", str(text or ""))}


def _clean_source_title(title: str) -> str:
    """Normalize a publisher title without rewriting its factual content."""
    value = _spaces(title)
    if not value:
        return ""
    value = re.sub(r"^(?:breaking|exclusive|update)\s*:\s*", "", value, flags=re.I)
    value = re.sub(r"\bmakes? (?:an? )?investment in\b", "invests in", value, flags=re.I)
    # Publisher suffixes appear with inconsistent spacing around pipes/dashes.
    pipe_parts = re.split(r"\s*\|\s*", value)
    if len(pipe_parts) > 1:
        tail = _spaces(pipe_parts[-1])
        if 1 <= len(tail.split()) <= 6 and not _has_event_action(tail):
            value = _spaces(" | ".join(pipe_parts[:-1]))
    for separator in (" — ", " – ", " - "):
        if separator not in value:
            continue
        lead, tail = value.rsplit(separator, 1)
        if 1 <= len(tail.split()) <= 5 and not _has_event_action(tail):
            value = _spaces(lead)
            break
    return value.strip(" -—–|")

def _source_identity_coherence_issue(
    discovery_headline: str, source_title: str, source_text: str, *, domain: str
) -> str:
    """Reject resolved pages whose identity does not match the discovered story.

    This catches a subtle but serious extraction class: a URL can resolve to one
    article while page furniture/related cards donate prose from another.  The
    discovery headline, publisher title, and article lead do not need identical
    wording, but they must share a distinctive event identity.
    """
    discovered = _clean_source_title(discovery_headline)
    published = _clean_source_title(source_title)
    lead_sentences = _split_sentences(source_text)[:10]
    lead = _spaces(" ".join(lead_sentences))

    if discovered and published:
        left = _event_identity_tokens(discovered, domain)
        right = _event_identity_tokens(published, domain)
        overlap = left.intersection(right)
        if len(left) >= 2 and len(right) >= 2 and not overlap:
            return "resolved publisher title does not match the discovered article identity"

    if published and lead_sentences and (_has_event_action(published) or _has_empirical_marker(published)):
        title_tokens = _event_identity_tokens(published, domain)
        if len(title_tokens) >= 2:
            best_overlap = 0
            best_similarity = 0.0
            for sentence in lead_sentences:
                best_overlap = max(best_overlap, len(title_tokens.intersection(_event_identity_tokens(sentence, domain))))
                best_similarity = max(best_similarity, _headline_similarity(published, sentence))
            # One shared distinctive identity plus ordinary topical overlap is
            # enough. Zero identity and near-zero textual similarity is not.
            if best_overlap == 0 and best_similarity < 0.12:
                return "publisher title is not corroborated by the extracted article lead"
    return ""


def _title_body_corroborated(title_fact: str, source_text: str, *, domain: str) -> bool:
    title_tokens = _event_identity_tokens(title_fact, domain)
    title_numbers = _numeric_identity_tokens(title_fact)
    for sentence in _split_sentences(source_text)[:12]:
        sentence_tokens = _event_identity_tokens(sentence, domain)
        overlap = title_tokens.intersection(sentence_tokens)
        if len(overlap) >= 2:
            return True
        if overlap and title_numbers.intersection(_numeric_identity_tokens(sentence)):
            return True
        if _headline_similarity(title_fact, sentence) >= 0.24:
            return True
    return False


def _body_event_frame_candidates(
    source_text: str,
    *,
    headline: str,
    domain: str,
    qualification_tier: str,
    anchors: list[tuple[float, str]],
) -> list[tuple[float, str, str]]:
    """Return body sentences that independently state the article's event.

    The body is preferred over the headline because publisher prose normally
    has natural sentence case and fuller context.  Titles are a fallback when
    no clean body event frame survives.
    """
    anchor_scores = {_spaces(raw): float(score) for score, raw in anchors}
    options: list[tuple[float, str, str]] = []
    for index, raw in enumerate(_split_sentences(source_text)[:MAX_DEVELOPMENT_LEAD_SENTENCES]):
        fact = _format_source_sentence(raw, headline=headline, source_text=source_text)
        if not fact:
            continue
        if not (_explicit_actor_action(fact) or _has_empirical_marker(fact) or _finance_transaction_in_motion(fact)):
            continue
        gate_ok, _ = _domain_grounding_gate(
            domain,
            headline=headline,
            source_text=source_text,
            fact_sentence=fact,
            qualification_tier=qualification_tier,
        )
        if not gate_ok:
            continue
        score = _presentation_score(fact)
        score += min(7.0, _headline_similarity(headline, fact) * 9.0)
        identity_overlap = _event_identity_tokens(headline, domain).intersection(_event_identity_tokens(fact, domain))
        score += min(9.0, len(identity_overlap) * 3.0)
        headline_numbers = _numeric_identity_tokens(headline)
        if headline_numbers and headline_numbers.intersection(_numeric_identity_tokens(fact)):
            score += 5.0
        score += max(0.0, 5.0 - index * 0.45)
        score += min(4.0, anchor_scores.get(_spaces(raw), 0.0) * 0.16)
        if _explicit_actor_action(fact):
            score += 5.0
        if _has_empirical_marker(fact):
            score += 3.0
        options.append((score, fact, raw))
    options.sort(key=lambda item: item[0], reverse=True)
    return options


def _support_adds_information(frame: str, support: str, *, domain: str) -> bool:
    """Require support to contribute scale/context rather than restating frame."""
    if not support or _headline_similarity(frame, support) >= 0.74:
        return False
    if _has_number(support) and not _has_number(frame):
        return True
    new_tokens = _event_identity_tokens(support, domain) - _event_identity_tokens(frame, domain)
    if len(new_tokens) >= 3 and any(marker in support.casefold() for marker in (
        "revenue", "capacity", "queue", "investment", "funding", "guidance", "forecast",
        "customers", "sites", "jobs", "layoffs", "demand", "route", "cost", "costs",
    )):
        return True
    return False


def _source_title_event_frame(
    source_title: str, *, source_text: str, domain: str, qualification_tier: str
) -> str:
    """Use the publisher title only as a corroborated fallback event frame."""
    value = _clean_source_title(source_title)
    words = len(value.split())
    if not value or words < 5 or words > 34:
        return ""
    if is_preview_or_calendar_item(value) or is_commentary_style_title(value):
        return ""
    if not (_has_event_action(value) or _headline_actor(value) or _has_empirical_marker(value) or _finance_transaction_in_motion(value)):
        return ""
    fact = _sentence(_resolve_first_reference_identity(value, value, source_text))
    if recent_development_copy_issues(fact) or reader_development_event_frame_issues(fact):
        return ""
    if not _title_body_corroborated(fact, source_text, domain=domain):
        return ""
    return fact

def _best_title_support(
    title_fact: str, *, source_text: str, headline: str, domain: str
) -> tuple[str, str]:
    """Choose one nearby body detail that materially adds to a title fallback."""
    options: list[tuple[float, str, str]] = []
    for index, raw in enumerate(_split_sentences(source_text)[:10]):
        support = _format_support_sentence(raw, headline=headline, source_text=source_text)
        if not support or not _support_adds_information(title_fact, support, domain=domain):
            continue
        if not _same_event_context(title_fact, support, domain=domain, distance=1 if index < 4 else 2):
            continue
        combined = _spaces(f"{title_fact} {support}")
        if len(combined.split()) > MAX_FACT_WORDS or recent_development_copy_issues(combined):
            continue
        score = _presentation_score(support)
        score += 5.0 if _has_number(support) else 0.0
        score += max(0.0, 3.0 - index * 0.35)
        options.append((score, support, raw))
    if not options:
        return "", ""
    options.sort(key=lambda item: item[0], reverse=True)
    _, support, raw = options[0]
    return support, raw

def _sentence_index(sentences: list[str], raw: str) -> int:
    target = _spaces(raw)
    for index, sentence in enumerate(sentences):
        if _spaces(sentence) == target:
            return index
    return -1


def _assemble_reader_development(
    anchors: list[tuple[float, str]],
    *,
    headline: str,
    source_text: str,
    domain: str,
    qualification_tier: str = "A",
    source_title: str = "",
) -> tuple[str, str]:
    """Compose Reader copy from a deterministic semantic event frame.

    v7.9 stops treating source sentences as the presentation model.  The
    article is first reduced to cleaned factual clauses, then the deterministic
    composer identifies an actor/action event nucleus, assigns supporting facts
    to that event, and realizes the event before any supporting metric/context.

    The publisher title may participate only as corroborated evidence; it is
    never concatenated verbatim ahead of body prose.  If the semantic composer
    cannot establish a complete domain-specific event, the candidate is
    rejected and discovery proceeds to the next source.
    """
    cleaned_body: list[str] = []
    for raw in _split_sentences(source_text)[:24]:
        value = _format_support_sentence(raw, headline=headline or source_title, source_text=source_text)
        if value:
            cleaned_body.append(value)

    # Anchors can contain a fact that the page splitter omitted because of a
    # malformed boundary.  They are evidence-only additions, deduplicated
    # against the cleaned body, not privileged presentation candidates.
    for _, raw in anchors:
        value = _format_support_sentence(raw, headline=headline or source_title, source_text=source_text)
        if value and all(_headline_similarity(value, existing) < 0.94 for existing in cleaned_body):
            cleaned_body.append(value)

    clean_title = _clean_source_title(source_title or headline)
    composed = compose_development(
        domain=domain,
        source_title=clean_title,
        body_sentences=cleaned_body,
    )
    if composed is None:
        return "", ""

    fact = _spaces(composed.text)
    if not fact or len(fact.split()) > MAX_FACT_WORDS:
        return "", ""
    if recent_development_copy_issues(fact):
        return "", ""
    if reader_development_event_frame_issues(fact):
        return "", ""
    if not strict_domain_fit(domain, fact):
        return "", ""
    return fact, _spaces(composed.evidence_text)


def _synthesis_match(domain: str, category: str, text: str) -> bool:
    """Match a synthesis category from the canonical per-domain vocabulary."""
    return any(term_present(text, term) for term in domain_synthesis_terms(domain, category))


def ground_candidate(
    candidate: dict,
    *,
    domain: str,
    fetcher: Callable[..., SourceDocument] = fetch_source_document,
) -> tuple[dict | None, GroundingResult]:
    """Ground one metadata-qualified candidate in the underlying source text."""
    headline = _spaces(candidate.get("discovery_title") or candidate.get("verified_fact"))
    publisher_url = _spaces(candidate.get("publisher_url"))
    source_name = _spaces(candidate.get("source_name"))
    article_url = _spaces(candidate.get("source_url"))

    doc = fetcher(
        article_url,
        publisher_url=publisher_url,
        source_name=source_name,
        qualification_tier=str(candidate.get("qualification_tier") or "A"),
        discovery_provider=str(candidate.get("discovery_provider") or ""),
    )
    if doc.error:
        return None, GroundingResult(
            False,
            resolved_url=doc.resolved_url,
            extraction_method=doc.extraction_method,
            text_chars=doc.text_chars,
            reason="underlying source could not be established",
            error=doc.error,
        )

    # Google News can resurface/reindex old pages with a fresh feed timestamp.
    # If the publisher exposes its own publication/update date, that date—not
    # the RSS crawl date—must be inside the domain lookback window.
    # Publisher publication date is authoritative when exposed.  A recent
    # ``modified`` timestamp on an old article is not enough to turn a recrawl
    # into a new development.  Modified date is used only when publication date
    # is unavailable.
    freshness_date = doc.published_date or doc.modified_date
    if freshness_date:
        try:
            import pandas as pd
            discovered_on = pd.Timestamp(candidate.get("event_date")).normalize()
            days = max(int(candidate.get("lookback_days", 7) or 7), 1)
            source_stamp = pd.Timestamp(freshness_date).normalize()
            source_age = int((discovered_on - source_stamp).days)
            if source_age < 0 or source_age >= days:
                return None, GroundingResult(
                    False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
                    text_chars=doc.text_chars, source_published_date=doc.published_date,
                    source_modified_date=doc.modified_date,
                    reason="publisher page predates the Current Context window; discovery appears to be a recrawl/reindex",
                )
        except Exception:
            pass

    source_title = doc.title or headline
    coherence_issue = _source_identity_coherence_issue(
        headline, doc.title, doc.body_text, domain=domain
    )
    if coherence_issue:
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason=coherence_issue,
        )
    source_quality_issues = source_content_quality_issues(doc)
    if source_quality_issues:
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason=source_quality_issues[0],
        )
    if is_event_listing_page(doc):
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason="source is an event/webinar listing rather than a reported development",
        )
    if is_preview_or_calendar_item(source_title):
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="source is a preview/calendar item")
    if domain == "finance" and is_policy_commentary_title(source_title):
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason="central-bank commentary or outlook is not a completed Finance development",
        )
    if domain in {"workforce", "economic_impact", "adoption"} and is_attributed_commentary_title(source_title):
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason="attributed commentary without a new empirical release is not a Current Context development",
        )

    # Materiality precedes extraction: first establish that the title/lead body
    # contains a clear current development.  Only then choose the factual anchor
    # for Reader prose.  This prevents a recent commentary article from donating
    # an isolated historical statistic simply because the number scores well.
    anchors, salience_reason = _development_anchor_candidates(
        doc, candidate=candidate, domain=domain, headline=headline
    )

    usable_anchors: list[tuple[float, str]] = []
    best_similarity = 0.0
    for score, sentence_text in anchors:
        sim = _headline_similarity(headline, sentence_text)
        extra_tokens = _normalize_tokens(sentence_text) - _normalize_tokens(headline)
        extra_number = _has_number(sentence_text) and not _has_number(headline)
        if sim >= 0.88 and len(extra_tokens) < 4 and not extra_number:
            continue
        usable_anchors.append((score, sentence_text))
        best_similarity = max(best_similarity, sim)

    # Semantic composition is the publication gate. A clean, corroborated
    # publisher-title event may survive even when no individual body sentence
    # is independently strong enough for the old sentence-anchor scorer. This
    # is important for pages whose body begins with consequences/details rather
    # than restating the headline event.
    fact, evidence_text = _assemble_reader_development(
        usable_anchors, headline=headline, source_text=doc.body_text, domain=domain,
        qualification_tier=str(candidate.get("qualification_tier") or "A"),
        source_title=source_title,
    )
    if not fact and not anchors:
        reason = salience_reason
        if is_commentary_style_title(source_title) and "Market-level significance" not in reason:
            reason = "source is commentary/topic framing without a clear current material development"
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason=reason,
        )
    if not fact:
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars,
            reason="source established a development but no complete self-contained Reader copy fit the 70-word ceiling",
        )
    final_gate_ok, final_gate_reason = _domain_grounding_gate(
        domain, headline=source_title, source_text=doc.body_text, fact_sentence=fact,
        qualification_tier=str(candidate.get("qualification_tier") or "A"),
    )
    if not final_gate_ok:
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars,
            reason=f"final Reader development failed domain fit: {final_gate_reason}",
        )
    if domain == "market" and not market_event_is_significant(fact, doc.body_text):
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars,
            reason="Market-level significance gate rejected the final Reader development",
        )
    final_frame_issues = reader_development_event_frame_issues(fact)
    if final_frame_issues:
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars,
            reason=f"final Reader development lacks event framing: {final_frame_issues[0]}",
        )

    # Current Context uses deterministic language repair only to preserve source
    # context and readability; it does not generate analytical implications.
    relevance = ""
    similarity = best_similarity
    evidence_hash = hashlib.sha256(_spaces(evidence_text).encode("utf-8")).hexdigest()[:16]
    updated = dict(candidate)
    source_event_date = ""
    if freshness_date:
        try:
            import pandas as pd
            discovered_on = pd.Timestamp(candidate.get("event_date")).normalize()
            days = max(int(candidate.get("lookback_days", 7) or 7), 1)
            source_stamp = pd.Timestamp(freshness_date).normalize()
            if 0 <= int((discovered_on - source_stamp).days) < days:
                source_event_date = source_stamp.date().isoformat()
        except Exception:
            source_event_date = ""
    updated.update({
        "event_date": source_event_date or candidate.get("event_date", ""),
        "verified_fact": fact,
        "platform_relevance": relevance,
        "display": f"{fact} {relevance}".strip(),
        "source_url": doc.resolved_url,
        "grounding_version": GROUNDING_VERSION,
        "grounding_status": "grounded",
        "source_text_method": doc.extraction_method,
        "source_text_chars": doc.text_chars,
        "source_evidence_hash": evidence_hash,
        "source_title": source_title,
        "source_published_date": doc.published_date,
        "source_modified_date": doc.modified_date,
    })
    result = GroundingResult(
        True,
        fact=fact,
        relevance=relevance,
        resolved_url=doc.resolved_url,
        extraction_method=doc.extraction_method,
        text_chars=doc.text_chars,
        evidence_hash=evidence_hash,
        evidence_sentence_count=len(anchors),
        headline_similarity=similarity,
        source_published_date=doc.published_date,
        source_modified_date=doc.modified_date,
        reason="source body established a current, domain-relevant factual development",
    )
    return updated, result
