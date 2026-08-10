"""Shared Current Context parsing, deduplication, and ownership utilities.

Network discovery lives only in ``current_context_discovery``.  This module is
intentionally provider-free so the retained registry loader cannot accidentally
create a second live-news path.
"""

from __future__ import annotations

from email.utils import parsedate_to_datetime
import html as html_lib
import re
from urllib.parse import quote_plus, urlparse
import xml.etree.ElementTree as ET

import pandas as pd

from config.current_context_policy import DOMAIN_NEWS_QUERIES, DOMAIN_OWNER_TERMS


DOMAIN_KEYS = tuple(DOMAIN_NEWS_QUERIES)

NEWS_RSS_ENDPOINT = "https://news.google.com/rss/search"
NEWS_TIMEOUT_SECONDS = 4
NEWS_MAX_BYTES = 1_500_000
NEWS_USER_AGENT = "AI-Macro/6.10.19 (+source-grounded-current-context; business-research-source-policy)"

_EVENT_STOPWORDS = {
    "about", "after", "again", "against", "also", "amid", "among", "announced",
    "company", "development", "from", "into", "million", "billion", "reports",
    "reported", "says", "said", "that", "their", "this", "through", "under",
    "with", "year", "years", "would", "could", "will", "reuters", "associated",
    "press", "news", "office", "department", "current", "context",
}


def _clean_sentence(value) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _valid_https_url(value) -> bool:
    try:
        parsed = urlparse(str(value).strip())
    except ValueError:
        return False
    return parsed.scheme == "https" and bool(parsed.netloc)


def _bool(value, default=False) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "y", "on"}


def _strip_source_suffix(title: str, source: str) -> str:
    title = " ".join(html_lib.unescape(str(title or "")).split()).strip()
    source = " ".join(html_lib.unescape(str(source or "")).split()).strip()
    if source and title.casefold().endswith((" - " + source).casefold()):
        title = title[: -(len(source) + 3)].rstrip()
    return title


def _parse_news_date(value) -> pd.Timestamp | None:
    try:
        parsed = parsedate_to_datetime(str(value or ""))
    except (TypeError, ValueError, OverflowError):
        return None
    stamp = pd.Timestamp(parsed)
    if stamp.tzinfo is not None:
        stamp = stamp.tz_convert("UTC").tz_localize(None)
    return stamp.normalize()


def _parse_google_news_rss(payload: bytes) -> list[dict]:
    if not payload:
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    items: list[dict] = []
    for node in root.findall("./channel/item"):
        source_node = node.find("source")
        source_name = " ".join(str(source_node.text or "").split()).strip() if source_node is not None else ""
        source_url = str(source_node.attrib.get("url") or "").strip() if source_node is not None else ""
        title = " ".join(str(node.findtext("title") or "").split()).strip()
        link = str(node.findtext("link") or "").strip()
        published = _parse_news_date(node.findtext("pubDate"))
        description = re.sub(r"<[^>]+>", " ", str(node.findtext("description") or ""))
        description = " ".join(html_lib.unescape(description).split()).strip()
        if title and _valid_https_url(link) and published is not None:
            items.append({
                "title": title,
                "link": link,
                "published": published,
                "source_name": source_name or "News source",
                "source_url": source_url,
                "description": description,
            })
    return items


def _feed_url(query: str, *, days=7) -> str:
    encoded = quote_plus(f"({query}) when:{max(int(days), 1)}d")
    return f"{NEWS_RSS_ENDPOINT}?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def _domain_fit_score(text: str, domain: str) -> float:
    haystack = " ".join(str(text or "").split()).casefold()
    matches = sum(1 for term in DOMAIN_OWNER_TERMS.get(domain, ()) if str(term).casefold() in haystack)
    return min(24.0, matches * 4.0)


def _canonical_event_key(event: dict) -> str:
    url = str(event.get("source_url") or "").strip().casefold()
    if _valid_https_url(url):
        return f"url::{url}"
    fact = re.sub(r"[^a-z0-9 ]+", " ", str(event.get("verified_fact") or "").casefold())
    return "text::" + " ".join(fact.split()[:18])


def _event_tokens(event: dict) -> set[str]:
    text = f"{event.get('verified_fact', '')} {event.get('event_type', '')}".casefold()
    tokens = re.findall(r"[a-z0-9]+", text)
    return {token for token in tokens if len(token) >= 4 and token not in _EVENT_STOPWORDS}


def _same_development(left: dict, right: dict) -> bool:
    if _canonical_event_key(left) == _canonical_event_key(right):
        return True
    try:
        left_date = pd.Timestamp(left.get("event_date"))
        right_date = pd.Timestamp(right.get("event_date"))
        if pd.isna(left_date) or pd.isna(right_date) or abs((left_date - right_date).days) > 1:
            return False
    except (TypeError, ValueError):
        return False
    left_tokens = _event_tokens(left)
    right_tokens = _event_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    overlap = len(left_tokens.intersection(right_tokens)) / max(1, min(len(left_tokens), len(right_tokens)))
    return overlap >= 0.62


def _assign_event_owners(candidates_by_domain: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Assign each discovered development to exactly one visible domain tab."""
    clusters: list[list[dict]] = []
    for domain, candidates in candidates_by_domain.items():
        for candidate in candidates:
            item = dict(candidate)
            item["owner_domain"] = domain
            cluster = next(
                (group for group in clusters if any(_same_development(item, member) for member in group)),
                None,
            )
            if cluster is None:
                clusters.append([item])
            else:
                cluster.append(item)

    assigned: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    for cluster in clusters:
        winner = max(
            cluster,
            key=lambda item: (
                float(item.get("owner_score", 0) or 0),
                float(item.get("rank_score", 0) or 0),
                str(item.get("event_date", "")),
            ),
        )
        owner = str(winner.get("owner_domain") or winner.get("domain") or "").strip().lower()
        if owner in assigned:
            winner["domain"] = owner
            winner["secondary_domains"] = sorted({
                str(item.get("owner_domain") or item.get("domain") or "").strip().lower()
                for item in cluster
                if str(item.get("owner_domain") or item.get("domain") or "").strip().lower() not in {"", owner}
            })
            assigned[owner].append(winner)
    return assigned
