from __future__ import annotations

from email.utils import parsedate_to_datetime
from functools import lru_cache
import hashlib
import html as html_lib
import re
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    DOMAIN_LIVE_RELEVANCE,
    DOMAIN_NEWS_QUERIES,
    DOMAIN_NEWS_TERMS,
    DOMAIN_OWNER_TERMS,
    assess_source,
    materiality_score,
)
from config.sector_config import SECTOR_DISPLAY_NAMES

DOMAIN_KEYS = tuple(DOMAIN_NEWS_QUERIES)


SECTOR_NEWS_QUERIES = {
    "COMPUTE": 'Nvidia OR AMD OR Broadcom OR Micron OR "AI chips"',
    "SEMICAP_EQUIPMENT": 'ASML OR "Applied Materials" OR "Lam Research" OR KLA OR "semiconductor equipment"',
    "CLOUD_HYPERSCALERS": 'Microsoft OR Amazon OR AWS OR "Google Cloud" OR Meta OR Oracle cloud AI',
    "DATA_AI_INFRASTRUCTURE": 'Snowflake OR Datadog OR MongoDB OR Cloudflare OR "AI data infrastructure"',
    "DATA_CENTER_INFRASTRUCTURE": 'Vertiv OR Equinix OR "Digital Realty" OR Arista OR Dell "data center"',
    "POWER_GRID": 'Constellation OR Vistra OR Eaton OR "GE Vernova" OR "power grid" data center',
    "ENTERPRISE_AI_SOFTWARE": 'Salesforce OR ServiceNow OR Adobe OR SAP OR "enterprise AI software"',
    "CYBERSECURITY_AI_TRUST": 'CrowdStrike OR "Palo Alto Networks" OR Fortinet OR Okta OR cybersecurity AI',
    "INDUSTRIAL_AUTOMATION": 'Rockwell OR ABB OR Honeywell OR Emerson OR "industrial automation" AI',
    "ROBOTICS": 'robotics OR autonomy OR "Intuitive Surgical" OR Tesla robot OR autonomous systems',
    "DEFENSE_NATIONAL_SECURITY": 'Palantir OR Lockheed OR RTX OR Northrop OR "defense AI"',
    "CONSUMER_AI": 'Apple OR Spotify OR Reddit OR Netflix OR "consumer AI"',
    "HEALTHCARE_LIFE_SCIENCES_AI": 'Tempus OR Natera OR "GE HealthCare" OR "healthcare AI"',
    "TRANSPORTATION_LOGISTICS": 'Uber OR Lyft OR Aurora OR UPS OR "transportation logistics" AI',
    "INSURANCE_RISK": 'Progressive OR Allstate OR Chubb OR UnitedHealth OR "insurance AI" risk',
}


SECTOR_NEWS_TERMS = {
    "COMPUTE": ("nvidia", "amd", "broadcom", "micron", "semiconductor", "chip", "gpu"),
    "SEMICAP_EQUIPMENT": ("asml", "applied materials", "lam research", "kla", "semiconductor equipment", "eda"),
    "CLOUD_HYPERSCALERS": ("microsoft", "amazon", "aws", "google cloud", "meta", "oracle", "cloud"),
    "DATA_AI_INFRASTRUCTURE": ("snowflake", "datadog", "mongodb", "cloudflare", "data infrastructure", "data platform"),
    "DATA_CENTER_INFRASTRUCTURE": ("vertiv", "equinix", "digital realty", "arista", "dell", "data center", "datacenter"),
    "POWER_GRID": ("constellation", "vistra", "eaton", "ge vernova", "grid", "power demand", "electricity"),
    "ENTERPRISE_AI_SOFTWARE": ("salesforce", "servicenow", "adobe", "sap", "enterprise software", "agentic"),
    "CYBERSECURITY_AI_TRUST": ("crowdstrike", "palo alto", "fortinet", "okta", "cybersecurity", "security"),
    "INDUSTRIAL_AUTOMATION": ("rockwell", "abb", "honeywell", "emerson", "industrial automation", "factory automation"),
    "ROBOTICS": ("robot", "robotics", "autonomy", "autonomous", "intuitive surgical"),
    "DEFENSE_NATIONAL_SECURITY": ("palantir", "lockheed", "rtx", "northrop", "defense", "national security"),
    "CONSUMER_AI": ("apple", "spotify", "reddit", "netflix", "consumer ai", "siri"),
    "HEALTHCARE_LIFE_SCIENCES_AI": ("tempus", "natera", "ge healthcare", "healthcare ai", "life sciences ai", "diagnostic"),
    "TRANSPORTATION_LOGISTICS": ("uber", "lyft", "aurora", "ups", "transportation", "logistics", "autonomous vehicle"),
    "INSURANCE_RISK": ("progressive", "allstate", "chubb", "unitedhealth", "insurance", "underwriting", "risk"),
}


NEWS_RSS_ENDPOINT = "https://news.google.com/rss/search"


NEWS_TIMEOUT_SECONDS = 4


NEWS_MAX_BYTES = 1_500_000


NEWS_USER_AGENT = "AI-Macro/6.5.2 (+single-owner-current-context; academic-source-policy)"


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


def _news_item_matches(item: dict, sector: str) -> bool:
    """Compatibility helper used by the sector regression suite."""
    return _text_matches(item, SECTOR_NEWS_TERMS.get(sector, ()))


def _feed_url(query: str, *, days=7) -> str:
    encoded = quote_plus(f"({query}) when:{max(int(days), 1)}d")
    return f"{NEWS_RSS_ENDPOINT}?q={encoded}&hl=en-US&gl=US&ceid=US:en"


def _fetch_feed(query: str, *, days=7) -> list[dict]:
    request = Request(_feed_url(query, days=days), headers={"User-Agent": NEWS_USER_AGENT})
    try:
        with urlopen(request, timeout=NEWS_TIMEOUT_SECONDS) as response:
            payload = response.read(NEWS_MAX_BYTES + 1)
    except Exception:
        return []
    if len(payload) > NEWS_MAX_BYTES:
        return []
    return _parse_google_news_rss(payload)


def _text_matches(item: dict, terms) -> bool:
    haystack = f"{item.get('title', '')} {item.get('description', '')}".casefold()
    return any(str(term).casefold() in haystack for term in terms)


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


def _live_candidate(
    item: dict,
    *,
    key: str,
    terms,
    current: pd.Timestamp,
    surface: str,
    lookback_days: int = 7,
) -> dict | None:
    window_start = current - pd.Timedelta(days=max(int(lookback_days), 1) - 1)
    published = item.get("published")
    if published is None or not (window_start <= published <= current):
        return None
    if not _text_matches(item, terms):
        return None

    source_name = str(item.get("source_name") or "News source").strip()
    assessment = assess_source(source_name, item.get("source_url", ""), item.get("link", ""))
    if not assessment.auto_eligible:
        return None

    headline = _strip_source_suffix(item.get("title", ""), source_name)
    source_text = f"{headline} {item.get('description', '')}"
    action_score = materiality_score(source_text)
    if not headline or action_score <= 0:
        return None

    age = max(0, int((current - published).days))
    freshness = max(0.0, float(lookback_days) - age)
    fit_score = _domain_fit_score(source_text, key) if surface == "domain" else 0.0
    score = assessment.score + action_score + freshness
    if surface == "domain":
        minimum = float((DOMAIN_CONTEXT_POLICY.get(key, {}) or {}).get("minimum_score", 106.0))
        if score + fit_score < minimum:
            return None
        relevance = DOMAIN_LIVE_RELEVANCE.get(key, "The development may change the interpretation of the retained data.")
        domain = key
        sectors = []
    else:
        relevance = ""
        domain = "market"
        sectors = [key]

    digest = hashlib.sha1(headline.casefold().encode("utf-8")).hexdigest()[:10]
    event_id = (
        f"live-{surface}-{published.date().isoformat()}-{digest}"
        if surface == "domain"
        else f"live-{surface}-{key.lower()}-{published.date().isoformat()}-{digest}"
    )
    return {
        "event_id": event_id,
        "event_date": published.date().isoformat(),
        "domain": domain,
        "owner_domain": domain,
        "event_type": "reported_development",
        "priority": float(score),
        "verified_fact": _clean_sentence(f"{source_name} reports: {headline}"),
        "platform_relevance": _clean_sentence(relevance),
        "display": _clean_sentence(f"{source_name} reports: {headline}") + (f" {_clean_sentence(relevance)}" if relevance else ""),
        "reference_number": 0,
        "source_name": source_name,
        "source_label": source_name,
        "source_url": str(item.get("link") or "").strip(),
        "publisher_url": str(item.get("source_url") or "").strip(),
        "source_type": "news",
        "source_tier": assessment.tier,
        "evidence_role": assessment.evidence_role,
        "verification_status": "reported",
        "status": "Reported",
        "legal_status": "",
        "resolution_status": "recent",
        "surface": surface,
        "sectors": sectors,
        "tickers": [],
        "owner_score": float(score + fit_score),
        "rank_score": float(score + fit_score),
    }


@lru_cache(maxsize=64)
def _fetch_live_sector_event(sector: str, as_of_iso: str) -> dict | None:
    current = pd.Timestamp(as_of_iso).normalize()
    items = _fetch_feed(SECTOR_NEWS_QUERIES.get(sector, SECTOR_DISPLAY_NAMES.get(sector, sector)), days=7)
    candidates = [
        candidate for item in items
        if (candidate := _live_candidate(
            item,
            key=sector,
            terms=SECTOR_NEWS_TERMS.get(sector, ()),
            current=current,
            surface="sector",
            lookback_days=7,
        )) is not None
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item.get("rank_score", 0), item.get("event_date", "")), reverse=True)
    return candidates[0]


@lru_cache(maxsize=32)
def _fetch_live_domain_candidates(domain: str, as_of_iso: str) -> tuple[dict, ...]:
    current = pd.Timestamp(as_of_iso).normalize()
    policy = DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}
    days = max(int(policy.get("lookback_days", 7)), 1)
    items = _fetch_feed(DOMAIN_NEWS_QUERIES.get(domain, domain.replace("_", " ")), days=days)
    candidates = [
        candidate for item in items
        if (candidate := _live_candidate(
            item,
            key=domain,
            terms=DOMAIN_NEWS_TERMS.get(domain, ()),
            current=current,
            surface="domain",
            lookback_days=days,
        )) is not None
    ]
    candidates.sort(key=lambda item: (item.get("rank_score", 0), item.get("event_date", "")), reverse=True)
    return tuple(candidates[:5])


def _assign_live_event_owners(candidates_by_domain: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Assign each discovered development to exactly one visible tab.

    Several searches and publishers may describe the same underlying event.
    Candidates are clustered by URL or high token overlap, then assigned to the
    domain with the strongest relevance and materiality score.
    """
    clusters: list[list[dict]] = []
    for domain, candidates in candidates_by_domain.items():
        for candidate in candidates:
            item = dict(candidate)
            item["owner_domain"] = domain
            cluster = next((group for group in clusters if any(_same_development(item, member) for member in group)), None)
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
