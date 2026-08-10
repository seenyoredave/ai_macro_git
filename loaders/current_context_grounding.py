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
    DOMAIN_NEWS_TERMS,
    DOMAIN_TOPIC_ANCHORS,
    assess_source,
    recent_development_copy_issues,
    term_present,
)
from loaders.current_context_news import NEWS_USER_AGENT, _valid_https_url


GROUNDING_VERSION = "2.1"
SOURCE_TIMEOUT = (4, 9)
SOURCE_MAX_BYTES = 2_500_000
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
        "User-Agent": NEWS_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
        "Accept-Language": "en-US,en;q=0.8",
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


def _sentence_score(sentence: str, *, domain: str, index: int) -> float:
    score = max(0.0, 6.0 - index * 0.18)
    score += sum(2.5 for term in DOMAIN_NEWS_TERMS.get(domain, ()) if term_present(sentence, str(term)))
    score += sum(1.8 for term in DOMAIN_TOPIC_ANCHORS.get(domain, ()) if term_present(sentence, str(term)))
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

    if not any(term_present(source_text, str(term)) for term in DOMAIN_NEWS_TERMS.get(domain, ())):
        return False, "source body does not establish the domain-relevant subject"
    if DOMAIN_TOPIC_ANCHORS.get(domain) and not any(term_present(source_text, str(term)) for term in DOMAIN_TOPIC_ANCHORS.get(domain, ())):
        # A few physical domains may qualify through a system-wide measured constraint.
        if domain == "grid_storage" and _has_number(source_text) and any(term in lower for term in _SYSTEM_GRID_TERMS):
            pass
        elif domain == "water" and _has_number(source_text) and any(term in lower for term in _SYSTEM_WATER_TERMS):
            pass
        else:
            return False, "source body does not establish the required AI/technology or system-wide anchor"

    if not _has_event_action(fact_sentence) and not _has_empirical_marker(fact_sentence):
        return False, "best source sentence is topical/commentary rather than a concrete development"

    if domain in {"workforce", "economic_impact", "adaptation"}:
        if not _has_number(fact_sentence):
            return False, "domain requires a quantified observed result; topic commentary or unquantified interpretation is not enough"

    if domain == "finance":
        monetary_policy = any(term in lower for term in (
            "federal reserve", "fomc", "monetary policy", "interest rate", "policy rate",
            "fed funds", "target range", "inflation", "pce", "cpi",
        ))
        if monetary_policy:
            concrete_policy_action = any(term in fact_lower for term in (
                "held", "maintained", "raised", "increased", "cut", "reduced", "lowered",
                "decided", "voted", "target range", "basis point", "bps", "rate hike",
                "rate cut", "policy rate", "federal funds rate",
            ))
            empirical_release = _has_empirical_marker(fact_sentence) and _has_number(fact_sentence)
            if not (concrete_policy_action or empirical_release):
                return False, "central-bank commentary without a policy action or new empirical release is not a Finance development"

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
        direct_ai_load = any(term in lower for term in ("data center", "datacenter", "ai", "hyperscaler", "cloud"))
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
    return value


def _compress_fact(sentence: str) -> str:
    text = _neutralize_journalistic_lead(_spaces(sentence))
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


def _specific_relevance(domain: str, fact: str, source_text: str) -> str:
    """Build one narrow analytical consequence from the grounded source fact.

    The result is deliberately fact-sensitive.  We do not append a universal
    domain sentence to a headline.  If the grounded fact does not support a
    specific consequence, the candidate is rejected rather than padded with
    generic AI language.
    """
    lower = _spaces(f"{fact} {source_text}").casefold()
    fact_lower = fact.casefold()

    if domain == "market":
        magnitude = _first_magnitude(fact)
        if "guidance" in lower and any(term in lower for term in ("raised", "increased", "boosted")):
            prefix = f"The {magnitude} change" if magnitude else "The higher guidance"
            return _sentence(f"{prefix} moves the AI-demand claim into management's expected operating results; the next test is whether reported revenue and margins catch up to that outlook")
        if any(term in lower for term in ("earnings", "revenue", "bookings")):
            return _sentence("Because the evidence is in reported operating results rather than a valuation narrative, it is a direct test of whether AI-linked demand is broadening into realized revenue and earnings")
        if any(term in lower for term in ("acquisition", "merger", "stake")):
            return _sentence("The transaction changes control of an AI-linked asset or capability, which can shift where future growth, pricing power, and investment returns accrue")
        if any(term in lower for term in ("downgrade", "upgrade", "valuation", "shares", "stock")):
            return _sentence("The repricing changes the return hurdle for AI-linked equities and therefore the amount of future execution already embedded in current valuations")
        return ""

    if domain == "finance":
        magnitude = _first_magnitude(fact) or _first_magnitude(source_text)
        if any(term in lower for term in ("uncommenced lease", "lease commitment", "contractual commitment", "purchase commitment", "lease obligation", "lease burden")):
            prefix = f"At {magnitude}, the obligation" if magnitude else "The obligation"
            return _sentence(f"{prefix} is a fixed claim on future cash flow, so it belongs beside funded debt when measuring how much financing capacity the infrastructure buildout is consuming")
        if any(term in lower for term in ("rating", "downgrade", "upgrade")):
            return _sentence("A ratings action converts AI-related spending from a capital-budget question into a borrowing-risk signal, with potential consequences for funding cost and balance-sheet flexibility")
        if "refinanc" in lower:
            return _sentence("The refinancing is a market test of whether a large AI-infrastructure exposure can still attract outside capital without eroding the economics through higher funding costs or shorter maturities")
        if any(term in lower for term in ("bond", "debt", "loan", "project finance", "financing")):
            prefix = f"The {magnitude} financing" if magnitude else "The financing"
            return _sentence(f"{prefix} moves part of the buildout from internally funded capex into an external capital claim, making borrowing cost and balance-sheet capacity part of the investment case")
        if any(term in lower for term in ("federal reserve", "fomc", "interest rate", "monetary policy", "policy rate", "target range")):
            if any(term in fact_lower for term in ("cut", "lowered", "reduced")):
                return _sentence("The actual rate cut lowers the marginal financing hurdle for long-duration infrastructure; commentary about possible future moves would not meet this standard")
            if any(term in fact_lower for term in ("raise", "raised", "increased", "hike")):
                return _sentence("The actual rate increase raises the financing and discount-rate hurdle for long-duration AI infrastructure and private-company investment")
            if any(term in fact_lower for term in ("held", "maintained", "target range")):
                return _sentence("Holding the policy rate preserves the current financing hurdle; the relevance is the implemented stance, not an official's speculation about what might happen next")
        if any(term in lower for term in ("credit spread", "yield", "liquidity")) and magnitude:
            return _sentence(f"The {magnitude} move is a measured change in the market price or availability of capital that finances long-duration AI infrastructure")
        return ""

    if domain == "compute":
        magnitude = _first_magnitude(fact) or _first_magnitude(source_text)
        if any(term in lower for term in ("export control", "restriction", "license", "ban")):
            return _sentence("The policy changes where advanced compute can legally be sold or deployed, shifting accessible demand and the geography of the AI hardware supply chain")
        if any(term in lower for term in ("fab", "foundry", "production", "capacity", "advanced packaging", "hbm")):
            prefix = f"The {magnitude} capacity change" if magnitude else "The capacity change"
            return _sentence(f"{prefix} affects physical supply rather than order demand alone, so it can change how quickly AI infrastructure is actually deployable")
        if any(term in lower for term in ("gpu", "accelerator", "shipment", "shipments")):
            return _sentence("The shipment change is a direct signal on accelerator availability and therefore on whether compute supply is loosening or remaining a deployment constraint")
        return ""

    if domain == "data_center":
        magnitude = _first_magnitude(fact) or _first_magnitude(source_text)
        if any(term in lower for term in ("permit", "zoning", "moratorium", "approved", "approval", "denied", "delay", "canceled", "cancelled")):
            return _sentence("The action changes whether announced capacity is actually buildable on the stated timetable, which is the relevant boundary between a pipeline headline and executable supply")
        if any(term in lower for term in ("opened", "commissioned", "construction", "began", "started", "capacity", "megawatt", "mw", "gw")):
            prefix = f"Moving {magnitude}" if magnitude else "Moving the project"
            return _sentence(f"{prefix} into construction or operation converts part of the development pipeline into physical capacity rather than an early-stage site claim")
        return ""

    if domain == "connectivity":
        support = _support_sentence(source_text, fact, terms=("data center", "cloud", "capacity", "route", "traffic", "landing"))
        magnitude = _first_magnitude(fact) or _first_magnitude(support)
        route = _route_phrase(fact) or _route_phrase(support)
        if any(term in lower for term in ("submarine cable", "cable landing", "fiber", "fibre", "backbone", "route")):
            if route and magnitude:
                return _sentence(f"The {route} path adds {magnitude} of transport on a route the source ties to compute traffic, increasing both headroom and physical-path diversity")
            if route:
                return _sentence(f"The {route} path matters only because the source ties that route to a major cloud or data-center market; the gain is a distinct physical path, not generic global cable growth")
            if magnitude:
                return _sentence(f"The {magnitude} addition is material because the source ties the capacity directly to a cloud or data-center market rather than to telecom traffic in general")
            return ""
        if any(term in lower for term in ("internet exchange", "peering")):
            return _sentence("The interconnection expansion shortens the physical path between major traffic sources in the named compute market, improving usable network depth rather than merely adding a new telecom announcement")
        return ""

    if domain == "power":
        support = _support_sentence(source_text, fact, terms=("contract", "data center", "supply", "capacity", "electricity", "generation"))
        magnitude = _first_magnitude(fact) or _first_magnitude(support)
        year = _first_year(support)
        if any(term in lower for term in ("power purchase agreement", "power contract", "ppa")):
            if magnitude and year:
                return _sentence(f"A {magnitude} contract beginning in {year} converts part of planned data-center load from a forecast into a dated supply commitment")
            if magnitude:
                return _sentence(f"A {magnitude} contract converts part of planned data-center load from a forecast into committed power supply")
            if year:
                return _sentence(f"Supply beginning in {year} gives the planned load a dated procurement path rather than an undated electricity assumption")
            return ""
        if any(term in lower for term in ("nuclear", "generation", "power plant", "gas turbine", "capacity")) and magnitude:
            return _sentence(f"The {magnitude} supply change alters the amount of firm generation available against large-load growth, directly affecting where additional AI infrastructure can be served")
        if any(term in lower for term in ("electricity price", "power price", "tariff")) and magnitude:
            return _sentence(f"The {magnitude} price or tariff change alters the operating-cost base for electricity-intensive compute in the affected market")
        return ""

    if domain == "grid_storage":
        support = _support_sentence(source_text, fact, terms=("transmission", "storage", "bottleneck", "curtail", "interconnection", "construction"))
        magnitude = _first_magnitude(fact) or _first_magnitude(support)
        if "curtail" in lower and magnitude:
            return _sentence(f"Curtailing {magnitude} despite available generation is direct evidence that deliverability—not nameplate supply—is binding when transmission and storage lag the buildout")
        if any(term in fact_lower for term in ("approved", "ordered", "adopted", "implemented")) and "interconnection" in lower:
            return _sentence("Because the action changes an implemented interconnection rule or process rather than merely recommending one, it can alter the path from queue position to construction and energization")
        if any(term in lower for term in ("transmission", "substation", "transformer", "congestion")) and magnitude:
            return _sentence(f"The {magnitude} constraint or upgrade changes physical deliverability between approved generation and load, which is the bottleneck the queue itself cannot solve")
        if "battery storage" in lower or "storage" in fact_lower:
            if magnitude:
                return _sentence(f"The {magnitude} storage change alters how much intermittent generation can be shifted into tight-demand periods, changing effective grid capacity rather than nominal supply")
            return ""
        return ""

    if domain == "water":
        magnitude = _first_magnitude(fact) or _first_magnitude(source_text)
        if any(term in lower for term in ("shortage", "restriction", "allocation", "drought", "river", "reservoir", "emergency")):
            if magnitude:
                return _sentence(f"A {magnitude} supply change is large enough to alter location-specific water exposure, raising the value of reuse capacity and lower-water cooling designs for new industrial load")
            return _sentence("The formal supply constraint changes the water envelope available to new industrial load, making location, reuse capacity, and cooling design part of the development decision")
        if any(term in lower for term in ("permit", "reuse", "wastewater", "cooling")):
            return _sentence("The permit or reuse action changes the local water/wastewater capacity that can actually support new industrial load, rather than merely describing regional scarcity")
        return ""

    if domain == "adaptation":
        magnitude = _first_magnitude(fact)
        if magnitude and any(term in lower for term in ("survey", "adoption", "business use", "deployment", "production use")):
            return _sentence(f"The {magnitude} observed-use measure helps distinguish broad experimentation from AI becoming embedded in normal business operations")
        return ""

    if domain == "workforce":
        magnitude = _first_magnitude(fact)
        if not magnitude:
            return ""
        if any(term in lower for term in ("hiring", "employment", "jobs", "layoff", "layoffs", "headcount")):
            return _sentence(f"The {magnitude} observed labor-market change is evidence of actual workforce demand, not a task-exposure estimate or an interview about what AI might eventually do")
        if any(term in lower for term in ("wage", "wages", "skills", "occupation", "training")):
            return _sentence(f"The {magnitude} measured shift shows where AI-related demand is changing the price or composition of labor rather than only the theoretical exposure of tasks")
        return ""

    if domain == "economic_impact":
        magnitude = _first_magnitude(fact)
        if not magnitude:
            return ""
        if any(term in lower for term in ("productivity", "unit labor cost")):
            return _sentence(f"The {magnitude} measured outcome is realized productivity or labor-cost evidence, not an AI spending proxy, so it bears directly on whether the investment boom is producing efficiency gains")
        if any(term in lower for term in ("gdp", "output", "value added", "income", "compensation")):
            return _sentence(f"The {magnitude} realized output or income measure is the appropriate test of whether large AI investment is translating into broader economic gains")
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
    if domain in {"workforce", "economic_impact", "adaptation"} and is_attributed_commentary_title(source_title):
        return None, GroundingResult(
            False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method,
            text_chars=doc.text_chars, reason="attributed commentary without a new empirical release is not a Current Context development",
        )

    ranked = _source_sentence_candidates(doc, domain=domain)
    if not ranked:
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="no substantive source sentences were extracted")

    chosen = ""
    similarity = 0.0
    gate_reason = ""
    for score, sentence_text in ranked[:16]:
        if score < 8.0:
            continue
        sim = _headline_similarity(headline, sentence_text)
        # A source sentence may resemble the headline, but it must add actual
        # evidence rather than simply restating the title.
        extra_tokens = _normalize_tokens(sentence_text) - _normalize_tokens(headline)
        extra_number = _has_number(sentence_text) and not _has_number(headline)
        if sim >= 0.88 and len(extra_tokens) < 4 and not extra_number:
            continue
        gate_ok, gate_reason = _domain_grounding_gate(domain, headline=headline, source_text=doc.body_text, fact_sentence=sentence_text)
        if not gate_ok:
            continue
        chosen = sentence_text
        similarity = sim
        break

    if not chosen:
        reason = gate_reason or "source text did not contain a concrete development beyond the headline"
        if is_commentary_style_title(source_title):
            reason = "source is commentary/topic framing without a source-grounded development"
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason=reason)

    fact = _sentence(_resolve_first_reference_identity(_compress_fact(chosen), headline, doc.body_text))
    relevance = _specific_relevance(domain, fact, doc.body_text)
    if not relevance:
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="source fact cleared evidence gates but did not support a specific analytical consequence")
    if recent_development_copy_issues(f"{fact} {relevance}"):
        return None, GroundingResult(False, resolved_url=doc.resolved_url, extraction_method=doc.extraction_method, text_chars=doc.text_chars, reason="source-grounded copy failed first-reference context rules")
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
        evidence_sentence_count=len(ranked),
        headline_similarity=similarity,
        source_published_date=doc.published_date,
        source_modified_date=doc.modified_date,
        reason="source body established the fact and a domain-specific analytical consequence",
    )
    return updated, result
