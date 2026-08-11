"""Source-grounded qualification and synthesis for AI Macro Current Context.

Discovery metadata may nominate a candidate, but Reader-facing prose may not be
built from a headline or RSS description.  A candidate must resolve to an
eligible publisher/primary page, yield substantive source text, contain a
concrete domain-relevant development, and support an analytical implication
specific enough to state without generic boilerplate.

Only compact derived facts/provenance are persisted.  Full article bodies are
used transiently during refresh and are never written to the retained ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import hashlib
import json
import re
from typing import Callable
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from config.current_context_policy import (
    domain_relevance_terms,
    domain_topic_anchors,
    domain_synthesis_terms,
    assess_source,
    recent_development_copy_issues,
    term_present,
)
from loaders.current_context_news import NEWS_USER_AGENT, _valid_https_url


GROUNDING_VERSION = "2.8"
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
MAX_FACT_WORDS = 36

_PREVIEW_PATTERNS = (
    r"\bwall st(?:reet)? week ahead\b",
    r"\bweek ahead\b",
    r"\bwhat to watch\b",
    r"\bwhat investors should watch\b",
    r"\bpreview\b",
    r"\bcalendar:\b",
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
    "announced", "approved", "awarded", "began", "built", "closed", "commissioned",
    "completed", "cut", "decided", "delayed", "denied", "filed", "found", "grew", "held",
    "implemented", "increased", "issued", "launched", "maintained", "opened", "ordered",
    "priced", "proposed", "published", "raised", "released", "reported", "secured", "signed",
    "started", "suspended", "terminated", "updated", "voted", "withdrew", "rose", "fell",
    "declined", "expanded", "refinanced", "downgraded", "upgraded", "curtailed", "added",
    "reduced", "adopted", "committed", "agreed", "entered", "lowered", "lowering",
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
    return " ".join(str(value or "").replace("\xa0", " ").split()).strip()


def _sentence(value: object) -> str:
    text = _spaces(value)
    if not text:
        return ""
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text if text.endswith((".", "!", "?")) else text + "."


def is_preview_or_calendar_item(title: object) -> bool:
    value = _spaces(title).casefold()
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in _PREVIEW_PATTERNS)


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
    text = _spaces(BeautifulSoup(str(value or ""), "lxml").get_text(" ", strip=True))
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
        stamp = pd.Timestamp(text)
        if stamp.tzinfo is not None:
            stamp = stamp.tz_convert("UTC").tz_localize(None)
        return stamp.date().isoformat()
    except Exception:
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        return match.group(1) if match else ""


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
    assessment = assess_source("", "", resolved)
    if not assessment.auto_eligible:
        return SourceDocument(requested, resolved, "", "", "", "", f"resolved page is not eligible evidence: {assessment.reason}")

    doc = _extract_article(html, resolved)
    doc = SourceDocument(
        requested, doc.resolved_url, doc.title, doc.description, doc.body_text,
        doc.extraction_method, doc.error, doc.published_date, doc.modified_date,
    )
    if doc.text_chars < MIN_SOURCE_TEXT_CHARS or len(_split_sentences(doc.body_text)) < MIN_SOURCE_SENTENCES:
        return SourceDocument(
            requested, doc.resolved_url, doc.title, doc.description, doc.body_text,
            doc.extraction_method, "insufficient source body text", doc.published_date, doc.modified_date,
        )
    return doc


def _split_sentences(text: str) -> list[str]:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()
    if not clean:
        return []
    pieces = re.split(r"(?<=[.!?])\s+(?=(?:[\"'“‘(]*[A-Z0-9]))", clean)
    output: list[str] = []
    for piece in pieces:
        sentence = _spaces(piece)
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
    r"|\d[\d,]*(?:\.\d+)?\s*(?:million|billion|trillion)\s*(?:MWh|GWh|TWh|Tbps|Gbps|MW|GW|acre-feet|gallons?|jobs?|workers?|employees?|people|companies|firms|sites?|projects?)"
    r"|\d[\d,]*(?:\.\d+)?\s*(?:MWh|GWh|TWh|Tbps|Gbps|MW|GW|acre-feet|gallons?|jobs?|workers?|employees?|people|companies|firms|sites?|projects?)"
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
    copy_issues = recent_development_copy_issues(f"{fact_text} {relevance_text}")
    if copy_issues:
        return False, f"retained Reader copy failed hygiene: {copy_issues[0]}"
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
        score -= 3.0
    lower = sentence.casefold()
    if any(term in lower for term in ("believes", "thinks", "argues", "opinion", "could eventually", "may someday")):
        score -= 4.0
    return score


def _source_sentence_candidates(doc: SourceDocument, *, domain: str) -> list[tuple[float, str]]:
    candidates = _split_sentences(doc.body_text)
    scored = [(_sentence_score(sentence, domain=domain, index=index), sentence) for index, sentence in enumerate(candidates[:100])]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _domain_grounding_gate(domain: str, *, headline: str, source_text: str, fact_sentence: str) -> tuple[bool, str]:
    combined = _spaces(f"{headline} {source_text}")
    lower = combined.casefold()
    fact_lower = fact_sentence.casefold()

    if not any(term_present(source_text, str(term)) for term in domain_relevance_terms(domain)):
        return False, "source body does not establish the domain-relevant subject"
    if domain_topic_anchors(domain) and not any(term_present(source_text, str(term)) for term in domain_topic_anchors(domain)):
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
        if not _has_number(fact_sentence):
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
        if not (relevant_stack or strategic_us):
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
        if not (direct_ai_load or quantified_system):
            return False, "power item lacks a concrete AI-load connection or quantified system-wide change"
        if any(term in fact_lower for term in ("published", "released", "resource", "guide", "overview")) and not (quantified_system or operational_action):
            return False, "informational power publication does not establish a new operational or measured development"

    if domain == "grid_storage":
        binding_action = any(term in fact_lower for term in (
            "approved", "ordered", "adopted", "implemented", "rule", "standard", "tariff",
            "construction", "commissioned", "energized", "curtail", "curtailed", "transmission",
            "substation", "transformer",
        ))
        if not (_has_number(fact_sentence) or binding_action):
            return False, "grid item lacks a concrete measured constraint or binding/physical system action"
        if any(term in fact_lower for term in ("roadmap", "recommendation", "guide", "framework")) and not (_has_number(fact_sentence) or any(term in fact_lower for term in ("adopted", "implemented", "approved", "ordered"))):
            return False, "nonbinding grid roadmap or guidance is context, not a material development"

    if domain == "water":
        if not (_has_number(fact_sentence) or any(term in fact_lower for term in ("approved", "proposed", "ordered", "restriction", "emergency", "permit", "allocation"))):
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

    for index, sentence in enumerate(sentences):
        score = _sentence_score(sentence, domain=domain, index=index)
        if score < 8.0:
            continue
        if not fact_is_current_development(sentence, reference_date=reference_date, lookback_days=lookback_days):
            rejection_reasons.append("lead fact was historical context rather than a current development")
            continue
        gate_ok, gate_reason = _domain_grounding_gate(
            domain, headline=headline, source_text=lead_text, fact_sentence=sentence
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
    """Turn common article-lead furniture into a compact neutral fact.

    This is deliberately narrow: it removes attribution syntax when the actor
    and action are already explicit, but it does not invent actors, values, or
    causal claims.  If a sentence cannot be safely normalized, it is returned
    unchanged and the later evidence gates still control eligibility.
    """
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


_DANGLING_FACT_OPENING_RE = re.compile(
    r"^(?:"
    r"(?:the\s+)?(?:company|firm|chipmaker|manufacturer|operator|developer|utility|regulator|agency|commission|provider|vendor|lender|borrower)\b"
    r"|(?:they|their|it|its)\b"
    r"|leading\s+up\s+to\s+their\b"
    r")",
    flags=re.IGNORECASE,
)

_HEADLINE_ACTOR_RE = re.compile(
    r"^(.{2,80}?)\s+(?:"
    r"announces?|announced|approves?|approved|backs?|backed|begins?|began|commits?|committed|"
    r"cuts?|cut|delays?|delayed|files?|filed|launches?|launched|lines\s+up|opens?|opened|"
    r"orders?|ordered|plans?|planned|proposes?|proposed|raises?|raised|refinances?|refinanced|"
    r"reports?|reported|secures?|secured|signs?|signed|starts?|started|unveils?|unveiled|"
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
        r"^(?:the\s+)?(?:company|firm|chipmaker|manufacturer|operator|developer|utility|regulator|agency|commission|provider|vendor|lender|borrower)\b",
        value,
        flags=re.I,
    )
    if generic:
        return actor + value[generic.end():]
    match = re.match(r"^(?:they|it)\s+", value, flags=re.I)
    if match:
        return actor + " " + value[match.end():]
    match = re.match(r"^(?:their|its)\s+", value, flags=re.I)
    if match:
        return actor + "'s " + value[match.end():]
    match = re.match(r"^Leading\s+up\s+to\s+their\s+(.+?),\s*they\s+(.+)$", value, flags=re.I)
    if match:
        return f"{actor}, leading up to its {_spaces(match.group(1))}, {_spaces(match.group(2))}"
    return value


def _resolve_first_reference_identity(fact: str, headline: str, source_text: str) -> str:
    value = _spaces(fact)
    surnames = []
    for match in _INSTITUTION_SURNAME_RE.finditer(str(headline or "")):
        surname = _spaces(match.group(1))
        if surname and surname not in surnames:
            surnames.append(surname)
    for surname in surnames:
        identity = _identity_for_surname(source_text, surname)
        if not identity or identity.casefold() in value.casefold():
            continue
        updated = re.sub(rf"\b{re.escape(surname)}\b", identity, value, count=1)
        if updated != value:
            value = updated

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
        value = re.sub(rf"\b{re.escape(acronym)}\b", f"{expansion} ({acronym})", value, count=1)

    value = _resolve_generic_actor(value, headline)
    return _spaces(value)


def _compress_fact(sentence: str) -> str:
    text = _neutralize_journalistic_lead(_spaces(sentence))
    # If a dangling introductory clause is followed by a self-contained event
    # after a colon, preserve the event rather than publishing the orphaned lead.
    if ":" in text:
        lead, tail = (_spaces(part) for part in text.split(":", 1))
        if _DANGLING_FACT_OPENING_RE.search(lead) and tail and not _DANGLING_FACT_OPENING_RE.search(tail):
            text = tail
    # Remove common dateline/publisher furniture while keeping the actor and fact.
    text = re.sub(r"^[A-Z][A-Z .,'-]{2,45}\s*[—–-]\s*", "", text)
    text = re.sub(r"^\([^)]*Reuters\)\s*[-—–]?\s*", "", text, flags=re.I)
    text = re.sub(r"\s+according to (?:the|a) [^.]{0,80}$", "", text, flags=re.I)
    words = text.split()
    if len(words) > MAX_FACT_WORDS:
        # Prefer a complete first clause over a chopped article sentence.
        clauses = re.split(r"(?<=[,;])\s+|\s+(?:while|although|but|which)\s+", text, maxsplit=2, flags=re.I)
        candidate = _spaces(clauses[0])
        if 10 <= len(candidate.split()) <= MAX_FACT_WORDS:
            text = candidate
        else:
            text = " ".join(words[:MAX_FACT_WORDS]).rstrip(",;:")
    return _sentence(text)


def _synthesis_match(domain: str, category: str, text: str) -> bool:
    """Match a synthesis category from the canonical per-domain vocabulary."""
    return any(term_present(text, term) for term in domain_synthesis_terms(domain, category))


def _specific_relevance(domain: str, fact: str, source_text: str) -> str:
    """Write one bounded, source-grounded analytical consequence.

    Current Context remains deterministic on purpose: once the source body has
    established a material development, this function maps that fact to one of
    the platform's explicit economic mechanisms.  The factual first sentence is
    already carried separately, so these consequences avoid repeating numbers
    unless the magnitude itself changes the meaning.
    """
    lower = _spaces(f"{fact} {source_text}").casefold()
    fact_lower = fact.casefold()

    if domain == "market":
        if _synthesis_match("market", "guidance_down", fact_lower):
            return _sentence("The weaker outlook lowers near-term growth expectations and raises the execution hurdle already reflected in the company's valuation")
        if _synthesis_match("market", "guidance_up", fact_lower):
            return _sentence("The stronger outlook raises expected revenue and earnings from AI-linked demand and increases the growth investors can reasonably price into the company")
        if _synthesis_match("market", "demand_signals", fact_lower):
            return _sentence("The order or backlog signal adds visibility into future demand before it reaches reported revenue")
        if _synthesis_match("market", "margin_profitability", fact_lower):
            return _sentence("The margin or profitability change shows whether AI-linked growth is improving the economics of the business or being offset by the cost of delivering it")
        if _synthesis_match("market", "capex_investment", fact_lower):
            return _sentence("The spending plan expands the capacity available for future growth but also raises the amount of execution required before that investment produces a return")
        if _synthesis_match("market", "operating_results", fact_lower):
            return _sentence("The reported results show whether AI-linked demand is turning into realized revenue and profit rather than remaining an expectation")
        if _synthesis_match("market", "ipo_equity_raise", fact_lower):
            return _sentence("The equity raise adds funding without new debt and establishes a fresh public-market price for the company's growth expectations")
        if _synthesis_match("market", "antitrust_regulatory", fact_lower):
            return _sentence("The regulatory action can change the timing, strategic freedom, or economic value of an AI-linked transaction or business line")
        if _synthesis_match("market", "transaction", fact_lower):
            return _sentence("The transaction shifts ownership of an AI-linked asset or capability and can redirect future growth, pricing power, and investment returns")
        if _synthesis_match("market", "concentration_breadth", fact_lower):
            return _sentence("The breadth or concentration change shows whether AI-linked market gains are spreading across more companies or becoming more dependent on a small group of leaders")
        if _synthesis_match("market", "analyst_revision", fact_lower):
            return _sentence("The estimate revision changes the earnings or revenue expectations investors are using to value the company, even though it does not change the underlying operations by itself")
        if _synthesis_match("market", "share_repurchase", fact_lower):
            return _sentence("The repurchase directs cash toward shareholders and reduces share count, while also competing with other uses of capital such as investment and acquisitions")
        if _synthesis_match("market", "dividend_capital_return", fact_lower):
            return _sentence("The capital-return decision changes how much cash is being distributed to shareholders rather than retained for future investment")
        if _synthesis_match("market", "repricing", fact_lower):
            return _sentence("The repricing resets the valuation investors are assigning to AI-linked growth and the execution already embedded in the stock")
        # Market is expected to remain populated when a genuinely material,
        # source-grounded event survives the evidence gates.  This fallback is
        # intentionally broad but still bounded to Market ownership.
        return _sentence("The development gives investors new information about the growth, risk, or strategic position of an AI-linked company and can change how that business is valued")

    if domain == "finance":
        if _synthesis_match("finance", "financing_platform", fact_lower):
            return _sentence("The financing partnership creates a repeatable outside-capital channel for the AI buildout, reducing how much funding must come directly from the customer's own balance sheet")
        if _synthesis_match("finance", "project_finance", fact_lower):
            return _sentence("The project financing ties repayment more closely to the economics of the specific infrastructure asset, helping fund construction while putting more weight on the project's own cash flows")
        if _synthesis_match("finance", "private_credit", fact_lower):
            return _sentence("The private-credit funding adds another source of capital outside public bonds and traditional bank lending, with its own pricing and covenant tradeoffs")
        if _synthesis_match("finance", "venture_funding", fact_lower):
            return _sentence("The funding round extends the company's runway and its ability to invest before the business has to finance growth entirely from its own cash flow")
        if _synthesis_match("finance", "private_equity", fact_lower):
            return _sentence("The sponsor investment changes the ownership and financing structure around the business and raises the importance of leverage and eventual exit returns")
        if _synthesis_match("finance", "securitization", fact_lower):
            return _sentence("The securitization turns contracted cash flows or infrastructure assets into investable debt, broadening the funding base while adding another layer of financing claims")
        if _synthesis_match("finance", "restructuring", fact_lower):
            return _sentence("The restructuring is evidence that the existing financing structure is under strain and can shift both ownership and repayment claims")
        if _synthesis_match("finance", "secondaries", fact_lower):
            return _sentence("The secondary transaction creates liquidity and price discovery for an otherwise illiquid private investment without requiring the underlying company to go public")
        if _synthesis_match("finance", "fund_distributions", fact_lower):
            return _sentence("The distribution turns private-fund value into realized cash, increasing the capital investors can recycle into new technology investments")
        if _synthesis_match("finance", "lease_obligation", fact_lower) or ("committed" in fact_lower and "lease" in fact_lower):
            return _sentence("The commitments add fixed future cash claims alongside funded debt, increasing the share of future cash flow already spoken for by the infrastructure buildout")
        if _synthesis_match("finance", "ratings", fact_lower):
            return _sentence("The ratings action changes borrowing-cost pressure and balance-sheet flexibility as AI-related capital spending expands")
        if _synthesis_match("finance", "covenant", fact_lower):
            return _sentence("The covenant change alters how much financial flexibility the borrower has before lenders can demand concessions or restrict additional borrowing")
        if _synthesis_match("finance", "maturity", fact_lower):
            return _sentence("The maturity change shifts when the borrower must refinance or repay debt, which can move financing risk into or out of the current rate environment")
        if _synthesis_match("finance", "refinancing", fact_lower):
            return _sentence("The refinancing puts a current market price on a large AI-infrastructure exposure and shows the terms on which outside investors are willing to keep funding it")
        if _synthesis_match("finance", "liquidity", fact_lower):
            return _sentence("The liquidity change alters how much near-term spending the company can fund or absorb before it needs to raise additional capital")
        if _synthesis_match("finance", "monetary_policy", fact_lower):
            if any(term in fact_lower for term in ("cut", "lowered", "reduced", "easing")):
                return _sentence("The rate cut lowers the financing hurdle for long-duration infrastructure and private-company investment")
            if any(term in fact_lower for term in ("raise", "raised", "increased", "hike", "tightening")):
                return _sentence("The rate increase raises borrowing costs and the return investors require from long-duration AI investment")
            return _sentence("The policy decision leaves the prevailing financing hurdle largely in place for long-duration AI infrastructure")
        if _synthesis_match("finance", "capital_conditions", fact_lower):
            return _sentence("The change in yields, spreads, or lending conditions alters the cost and availability of capital for long-duration AI investment")
        if _synthesis_match("finance", "external_financing", fact_lower):
            return _sentence("The financing shifts part of the buildout onto external capital, making borrowing cost and balance-sheet capacity more important to the economics of the project")
        return _sentence("The development changes the amount, timing, cost, or source of capital available to support AI investment")

    if domain == "compute":
        if _synthesis_match("compute", "compute_leasing", fact_lower):
            return _sentence("Making existing compute capacity available to outside customers increases effective near-term supply without waiting for new fabrication or data-center construction")
        if _synthesis_match("compute", "policy_constraint", fact_lower):
            return _sentence("The policy changes where advanced compute can be sold or deployed, shifting accessible demand and the geography of the AI hardware supply chain")
        if _synthesis_match("compute", "advanced_packaging", fact_lower):
            return _sentence("The packaging change affects one of the steps that turns leading-edge chips and memory into usable AI accelerators, so it can raise or relieve a bottleneck even when wafer supply is available")
        if _synthesis_match("compute", "memory_supply", fact_lower):
            return _sentence("The memory-supply change affects how many high-end accelerators can be completed, because advanced AI chips depend on high-bandwidth memory as well as processor capacity")
        if _synthesis_match("compute", "fab_investment", fact_lower):
            return _sentence("The fab investment expands future domestic manufacturing capacity, but the added supply arrives only after construction, equipment installation, and production ramp-up")
        if _synthesis_match("compute", "foundry_capacity", fact_lower):
            return _sentence("The foundry-capacity change affects how much leading-edge silicon can be produced before packaging, memory, and system assembly become the next constraints")
        if _synthesis_match("compute", "supply_agreement", fact_lower):
            return _sentence("The supply agreement reserves future manufacturing or component capacity for a specific buyer, improving that customer's access while reducing the uncommitted supply available elsewhere")
        if _synthesis_match("compute", "accelerator_shipments", fact_lower):
            return _sentence("The shipment change alters accelerator availability and the pace at which new compute capacity can come online")
        if _synthesis_match("compute", "supply_capacity", fact_lower):
            return _sentence("The capacity change alters the amount of chip supply available to support new AI systems and therefore how quickly compute can expand")
        return ""

    if domain == "data_center":
        if _synthesis_match("data_center", "cancellation", fact_lower):
            return _sentence("The cancellation removes planned capacity from the development pipeline and is a direct sign that announced projects do not all convert into operating infrastructure")
        if _synthesis_match("data_center", "power_readiness", fact_lower):
            return _sentence("The power agreement improves the project's path to energization, which is often a separate constraint from securing land and completing the building")
        if _synthesis_match("data_center", "commissioning", fact_lower):
            return _sentence("Commissioning or energization moves the project from construction toward usable operating capacity rather than simply adding another announced site")
        if _synthesis_match("data_center", "construction_start", fact_lower):
            return _sentence("Starting construction moves the project beyond planning and into physical execution, although completion and power delivery still remain ahead")
        if _synthesis_match("data_center", "prelease", fact_lower):
            return _sentence("The customer commitment gives the planned capacity a clearer demand base before the site is fully built or energized")
        if _synthesis_match("data_center", "land_site", fact_lower):
            return _sentence("Securing the site expands the developer's option to build, but land control alone does not establish construction, power availability, or operating capacity")
        if _synthesis_match("data_center", "tax_incentive", fact_lower):
            return _sentence("The incentive lowers part of the local cost of developing the project and can influence where new capacity is economically attractive to build")
        if _synthesis_match("data_center", "execution_gate", fact_lower):
            return _sentence("The permitting or approval action changes whether announced capacity can move onto its stated construction or energization timetable")
        if _synthesis_match("data_center", "physical_capacity", fact_lower):
            return _sentence("The project milestone converts part of the announced development pipeline into physical or operating capacity")
        return ""

    if domain == "connectivity":
        if _synthesis_match("connectivity", "outage_resilience", fact_lower):
            return _sentence("The outage or route-diversity change affects how much network traffic can keep moving when a cable or path fails")
        if _synthesis_match("connectivity", "permit_right_of_way", fact_lower):
            return _sentence("The permit or right-of-way action changes how quickly new fiber can be built along the planned route")
        if _synthesis_match("connectivity", "landing_station", fact_lower):
            return _sentence("The landing-station development creates the onshore connection needed for new subsea capacity to reach domestic networks and data-center markets")
        if _synthesis_match("connectivity", "peering_expansion", fact_lower):
            return _sentence("The peering expansion gives more networks a local place to exchange traffic directly, reducing dependence on longer indirect routes")
        if _synthesis_match("connectivity", "fiber_build", fact_lower):
            return _sentence("The fiber build adds a new physical path for moving cloud and data-center traffic between the markets named in the source")
        if _synthesis_match("connectivity", "capacity_upgrade", fact_lower):
            return _sentence("The network upgrade increases the amount of traffic the existing route can carry without requiring an entirely new path")
        if _synthesis_match("connectivity", "interconnection", fact_lower):
            return _sentence("The interconnection expansion adds network depth between major traffic sources in the named compute market")
        if _synthesis_match("connectivity", "physical_route", fact_lower):
            return _sentence("The new route adds transport capacity and physical-path diversity for cloud and data-center traffic")
        return ""

    if domain == "power":
        if _synthesis_match("power", "nuclear_restart", fact_lower):
            return _sentence("Restarting the nuclear unit can add firm generation without waiting for an entirely new plant to be built, although the unit still has to clear its restart and operating milestones")
        if _synthesis_match("power", "generation_retirement", fact_lower):
            return _sentence("The retirement removes firm generation from the supply stack and can tighten the amount of dependable power available against rising large-load demand")
        if _synthesis_match("power", "generation_addition", fact_lower):
            return _sentence("The generation addition expands future electricity supply, but it becomes useful to large loads only after construction and grid delivery are in place")
        if _synthesis_match("power", "fuel_supply", fact_lower):
            return _sentence("The fuel-supply change affects how reliably gas-fired generation can run when electricity demand is high")
        if _synthesis_match("power", "demand_response", fact_lower):
            return _sentence("The demand-response arrangement gives the grid a way to reduce or shift large-load demand during tight periods instead of meeting every peak with new generation")
        if _synthesis_match("power", "utility_capex", fact_lower):
            return _sentence("The utility investment plan expands the spending committed to serving future load, but the benefits depend on the projects being completed on time")
        if _synthesis_match("power", "load_forecast", fact_lower):
            return _sentence("The load forecast changes the amount of future electricity demand utilities must plan to serve, affecting both generation needs and grid investment")
        if _synthesis_match("power", "supply_contract", fact_lower):
            support = _support_sentence(source_text, fact, terms=("contract", "supply", "electricity", "generation", "data center"))
            magnitude = _first_magnitude(fact) or _first_magnitude(support)
            year = _first_year(support)
            if magnitude and year:
                return _sentence(f"The {magnitude} contract beginning in {year} gives the planned data-center load a dated supply commitment")
            if year:
                return _sentence(f"Supply beginning in {year} gives the planned load a dated supply commitment")
            return _sentence("The contract gives planned large-load demand a defined power-supply path rather than leaving the project dependent on uncommitted future generation")
        if _synthesis_match("power", "cost", fact_lower):
            return _sentence("The price or tariff change alters the operating-cost base for electricity-intensive compute in the affected market")
        if _synthesis_match("power", "firm_supply", fact_lower):
            return _sentence("The supply change alters the amount of dependable generation available against large-load growth")
        return ""

    if domain == "grid_storage":
        magnitude = _first_magnitude(fact) or _first_magnitude(source_text)
        if _synthesis_match("grid_storage", "curtailment", fact_lower):
            if magnitude:
                return _sentence(f"Curtailing {magnitude} despite available generation shows that transmission and storage are limiting deliverability even as nameplate supply expands")
            return _sentence("Renewable curtailment shows that available generation is exceeding the grid's ability to move or store it when and where it is needed")
        if _synthesis_match("grid_storage", "cost_allocation", fact_lower):
            return _sentence("Assigning transmission costs directly to large-load customers changes who pays for the grid expansion needed to serve data-center growth and can materially alter project economics")
        if _synthesis_match("grid_storage", "queue_reform", fact_lower):
            return _sentence("The queue reform changes how projects advance through grid studies and approvals, which can shorten or lengthen the path from application to construction")
        if _synthesis_match("grid_storage", "transformer_substation", fact_lower):
            return _sentence("The transformer or substation change affects the equipment needed to connect new generation and large loads, making hardware availability part of the delivery schedule")
        if _synthesis_match("grid_storage", "transmission_build", fact_lower):
            return _sentence("The transmission project expands the physical network available to move power from generation to load, which can relieve constraints that new generation alone cannot solve")
        if _synthesis_match("grid_storage", "congestion", fact_lower):
            return _sentence("The congestion signal shows that parts of the grid are already running into transfer limits, raising the value of transmission upgrades, storage, or more flexible load")
        if _synthesis_match("grid_storage", "reliability", fact_lower):
            return _sentence("The reliability finding shows how much dependable supply is available under stressed conditions rather than under an average-demand scenario")
        if _synthesis_match("grid_storage", "interconnection_action", fact_lower):
            return _sentence("The interconnection action changes the path from queue position to construction and energization for projects waiting to connect")
        if _synthesis_match("grid_storage", "storage", fact_lower):
            return _sentence("The storage change increases the amount of electricity that can be shifted from periods of surplus generation into tighter-demand hours")
        if _synthesis_match("grid_storage", "deliverability", fact_lower):
            return _sentence("The transmission or equipment change affects how much approved generation can physically reach the customers that need it")
        return ""

    if domain == "water":
        magnitude = _first_magnitude(fact) or _first_magnitude(source_text)
        if _synthesis_match("water", "allocation_policy", fact_lower):
            return _sentence("The allocation rule changes how much water can be delivered to competing users, making location-specific supply rights more important for new industrial development")
        if _synthesis_match("water", "drought_emergency", fact_lower):
            return _sentence("The drought emergency raises the risk that industrial users face tighter restrictions during dry conditions even when average water supply appears adequate")
        if _synthesis_match("water", "groundwater", fact_lower):
            return _sentence("The groundwater action changes how much local supply can be pumped over time and therefore how dependable that source is for new industrial load")
        if _synthesis_match("water", "cooling_technology", fact_lower):
            return _sentence("The cooling change alters how much water the facility needs to operate, which can reduce or increase its exposure to local water constraints")
        if _synthesis_match("water", "wastewater_capacity", fact_lower):
            return _sentence("The wastewater-capacity change affects how much new industrial load the local system can support after water has been used")
        if _synthesis_match("water", "infrastructure_expansion", fact_lower):
            return _sentence("The water-infrastructure project increases the physical supply or treatment capacity available to support additional industrial development")
        if _synthesis_match("water", "permit_reuse", fact_lower):
            return _sentence("The permit or reuse action changes the local water or wastewater capacity available to support new industrial load")
        if _synthesis_match("water", "supply_constraint", fact_lower):
            if magnitude:
                return _sentence(f"The {magnitude} supply change increases location-specific water exposure and the value of reuse capacity and lower-water cooling designs")
            return _sentence("The formal supply constraint tightens the water available to new industrial load and raises the importance of location, reuse capacity, and lower-water cooling")
        return ""

    if domain == "adoption":
        if _synthesis_match("adoption", "governance_constraint", fact_lower):
            return _sentence("The policy limits where or how employees can use AI tools, showing that governance and security can slow adoption even when the technology is available")
        if _synthesis_match("adoption", "production_integration", fact_lower):
            return _sentence("Moving AI into production workflows is stronger evidence of business adoption than trials or stated plans because the tools are being used in day-to-day operations")
        if _synthesis_match("adoption", "agent_deployment", fact_lower):
            return _sentence("The agent deployment moves AI from answering individual prompts toward carrying out multi-step work inside business processes")
        if _synthesis_match("adoption", "workflow_automation", fact_lower):
            return _sentence("The automation rollout shows AI being attached to specific work rather than remaining a general-purpose tool available to employees")
        if _synthesis_match("adoption", "enterprise_rollout", fact_lower):
            return _sentence("The broader rollout expands access across the organization and moves adoption beyond a small pilot group")
        if _synthesis_match("adoption", "paid_usage", fact_lower):
            return _sentence("The paid-user or seat count shows demand that has converted into a recurring commercial relationship rather than free experimentation")
        if _synthesis_match("adoption", "observed_adoption", fact_lower):
            return _sentence("The observed-use measure shows how far AI has moved from experimentation into normal business operations")
        return ""

    if domain == "workforce":
        if _synthesis_match("workforce", "layoffs", fact_lower):
            return _sentence("The job cuts show where employers are reducing labor demand, but the event alone does not establish how much of that reduction was caused by AI")
        if _synthesis_match("workforce", "job_postings", fact_lower):
            return _sentence("The change in job openings shows where employers are trying to add labor before those plans appear in actual employment")
        if _synthesis_match("workforce", "wage_compensation", fact_lower):
            return _sentence("The pay change shows whether demand for the affected work is translating into stronger or weaker compensation")
        if _synthesis_match("workforce", "skills_training", fact_lower):
            return _sentence("The training effort shows employers investing in worker adjustment rather than relying only on hiring new people with different skills")
        if _synthesis_match("workforce", "automation_task_change", fact_lower):
            return _sentence("The task change shows AI altering the content of work, which can happen before any clear change appears in total employment")
        if _synthesis_match("workforce", "union_bargaining", fact_lower):
            return _sentence("The labor agreement shows AI-related work rules becoming a bargaining issue over how technology is introduced and how its effects are shared")
        if _synthesis_match("workforce", "occupational_shift", fact_lower):
            return _sentence("The occupational shift shows workers moving between types of jobs as the mix of tasks and employer demand changes")
        if _synthesis_match("workforce", "labor_composition", fact_lower):
            return _sentence("The shift shows where AI-related demand is changing the skills or mix of work rather than simply changing the total number of jobs")
        if _synthesis_match("workforce", "labor_demand", fact_lower):
            return _sentence("The labor-market change shows where AI-related demand is appearing in hiring, employment, or headcount")
        return ""

    if domain == "economic_impact":
        if _synthesis_match("economic_impact", "gdp_revision", fact_lower):
            return _sentence("The revision changes the measured size or growth of the economy without necessarily representing a new change in underlying activity")
        if _synthesis_match("economic_impact", "labor_share_distribution", fact_lower):
            return _sentence("The distribution change shows whether gains in output are reaching workers' compensation or accruing more heavily elsewhere in the economy")
        if _synthesis_match("economic_impact", "unit_labor_cost", fact_lower):
            return _sentence("The labor-cost result shows how pay and productivity are combining to change the cost of producing each unit of output")
        if _synthesis_match("economic_impact", "inflation_prices", fact_lower):
            return _sentence("The price change shows whether broader cost pressure is easing or rising while AI investment and productivity are expanding")
        if _synthesis_match("economic_impact", "consumer_spending", fact_lower):
            return _sentence("The spending result shows whether household demand is reinforcing or offsetting the investment-led part of economic growth")
        if _synthesis_match("economic_impact", "sector_output", fact_lower):
            return _sentence("The industry-output change shows where measured economic growth is actually appearing rather than assuming the gains are economy-wide")
        if _synthesis_match("economic_impact", "investment", fact_lower):
            return _sentence("The investment change shows how much capital is being committed to future productive capacity before the resulting gains appear in measured output or productivity")
        if _synthesis_match("economic_impact", "productivity", fact_lower):
            return _sentence("The productivity result shows whether the economy is producing more output from the labor and capital already in use")
        if _synthesis_match("economic_impact", "output_income", fact_lower):
            return _sentence("The output or income result shows how much of the investment cycle is reaching broader economic activity and household earnings")
        return ""

    return ""

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

    doc = fetcher(article_url, publisher_url=publisher_url, source_name=source_name)
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
    if not anchors:
        reason = salience_reason
        if is_commentary_style_title(source_title) and "Market-level significance" not in reason:
            reason = "source is commentary/topic framing without a clear current material development"
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason=reason,
        )

    chosen = ""
    similarity = 0.0
    for score, sentence_text in anchors:
        sim = _headline_similarity(headline, sentence_text)
        # A source sentence may resemble the headline, but it must add actual
        # evidence rather than simply restating the title.
        extra_tokens = _normalize_tokens(sentence_text) - _normalize_tokens(headline)
        extra_number = _has_number(sentence_text) and not _has_number(headline)
        if sim >= 0.88 and len(extra_tokens) < 4 and not extra_number:
            continue
        chosen = sentence_text
        similarity = sim
        break

    if not chosen:
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason="clear development existed, but source text added no evidence beyond the headline",
        )

    fact = _sentence(_resolve_first_reference_identity(_compress_fact(chosen), headline, doc.body_text))
    relevance = _specific_relevance(domain, fact, doc.body_text)
    if not relevance:
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="source fact cleared evidence gates but did not support a specific analytical consequence")
    if recent_development_copy_issues(f"{fact} {relevance}"):
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="source-grounded copy failed first-reference context rules")
    if reader_copy_has_selection_rationale(relevance):
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="Reader prose leaked selection-rationale language")
    if any(relevance.casefold().startswith(prefix) for prefix in _BOILERPLATE_RELEVANCE_PREFIXES):
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="generic consequence boilerplate is prohibited")

    evidence_hash = hashlib.sha256(_spaces(chosen).encode("utf-8")).hexdigest()[:16]
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
        reason="source body established the fact and a domain-specific analytical consequence",
    )
    return updated, result
