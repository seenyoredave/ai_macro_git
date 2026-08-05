from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
import hashlib
import html as html_lib
import re
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_FALLBACK,
    DOMAIN_CONTEXT_POLICY,
    DOMAIN_LIVE_RELEVANCE,
    DOMAIN_NEWS_QUERIES,
    DOMAIN_NEWS_TERMS,
    DOMAIN_OWNER_TERMS,
    assess_source,
    materiality_score,
)
from config.sector_config import SECTOR_CONFIG, SECTOR_DISPLAY_NAMES

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENT_PATH = ROOT / "data" / "weekly_context_events.csv"
WEEKLY_CONTEXT_VERSION = "2.1"
DOMAIN_KEYS = tuple(DOMAIN_NEWS_QUERIES)
REQUIRED_COLUMNS = {
    "event_id",
    "event_date",
    "domain",
    "event_type",
    "priority",
    "verified_fact",
    "platform_relevance",
    "source_name",
    "source_label",
    "source_url",
    "source_type",
    "verification_status",
    "expires_after_days",
}

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
NEWS_USER_AGENT = "AI-Macro/6.5.1 (+single-owner-current-context; academic-source-policy)"
NO_QUALIFYING_NEWS = "No qualifying sector-specific headline was identified in the last seven days."


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


_EVENT_STOPWORDS = {
    "about", "after", "again", "against", "also", "amid", "among", "announced",
    "company", "development", "from", "into", "million", "billion", "reports",
    "reported", "says", "said", "that", "their", "this", "through", "under",
    "with", "year", "years", "would", "could", "will", "reuters", "associated",
    "press", "news", "office", "department", "current", "context",
}


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


def _fallback_domain_event(domain: str, current: pd.Timestamp) -> dict:
    text = DOMAIN_CONTEXT_FALLBACK.get(
        domain,
        "No material domain-specific development met the platform's evidence threshold this period.",
    )
    return {
        "event_id": f"no-context-{domain}-{current.date().isoformat()}",
        "event_date": current.date().isoformat(),
        "domain": domain,
        "owner_domain": domain,
        "event_type": "context_status",
        "priority": 0.0,
        "verified_fact": text,
        "platform_relevance": "",
        "display": text,
        "reference_number": None,
        "source_name": "",
        "source_label": "",
        "source_url": "",
        "source_type": "status",
        "source_tier": "status",
        "evidence_role": "none",
        "verification_status": "no_match",
        "status": "No qualifying event",
        "legal_status": "",
        "resolution_status": "recent",
        "surface": "domain",
        "sectors": [],
        "tickers": [],
        "owner_score": 0.0,
        "rank_score": 0.0,
    }

def _read_registry(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    frame = pd.read_csv(path)
    missing = REQUIRED_COLUMNS.difference(frame.columns)
    if missing:
        raise ValueError(f"Current-context registry is missing columns: {sorted(missing)}")
    defaults = {
        "surface": "macro",
        "sectors": "",
        "tickers": "",
        "status": "Confirmed",
        "legal_status": "",
        "resolution_status": "recent",
        "resolved_date": "",
        "source_tier": "",
        "evidence_role": "",
        "persistent": "",
        "secondary_domains": "",
        "record_origin": "",
        "retrieved_at": "",
        "discovery_provider": "",
        "discovery_query": "",
    }
    for column, default in defaults.items():
        if column not in frame.columns:
            frame[column] = default
        else:
            frame[column] = frame[column].fillna(default)
    frame = frame.copy()
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.normalize()
    frame["resolved_date"] = pd.to_datetime(frame["resolved_date"], errors="coerce").dt.normalize()
    frame["priority"] = pd.to_numeric(frame["priority"], errors="coerce")
    frame["expires_after_days"] = pd.to_numeric(frame["expires_after_days"], errors="coerce")
    for column in ("source_type", "verification_status", "surface", "resolution_status"):
        frame[column] = frame[column].fillna("").astype(str).str.strip().str.lower()
    return frame


def _curated_source_allowed(row: dict) -> tuple[bool, str, str]:
    source_name = str(row.get("source_name") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    assessment = assess_source(source_name, source_url, source_url)
    source_type = str(row.get("source_type") or "").strip().lower()
    verification = str(row.get("verification_status") or "").strip().lower()
    if assessment.tier == "blocked":
        return False, assessment.tier, assessment.evidence_role
    if assessment.tier == "manual_review" and verification != "corroborated":
        return False, assessment.tier, assessment.evidence_role
    # Curated primary records may include official corporate investor releases
    # not present on the unattended-news allowlist.
    if source_type == "primary" and verification in {"confirmed", "corroborated"}:
        return True, str(row.get("source_tier") or assessment.tier or "primary"), str(row.get("evidence_role") or assessment.evidence_role or "official_statement")
    if source_type == "news" and verification in {"confirmed", "corroborated"} and assessment.auto_eligible:
        return True, str(row.get("source_tier") or assessment.tier), str(row.get("evidence_role") or assessment.evidence_role)
    return False, assessment.tier, assessment.evidence_role


def _row_is_temporally_valid(row: dict, current: pd.Timestamp) -> bool:
    date = row.get("event_date")
    if pd.isna(date) or date > current:
        return False
    resolution = str(row.get("resolution_status") or "").strip().lower()
    persistent = _bool(row.get("persistent"), default=False) or resolution in {"unresolved", "active", "pending"}
    if persistent:
        return True
    expiration = pd.to_numeric(row.get("expires_after_days"), errors="coerce")
    if pd.isna(expiration):
        expiration = 7
    age = int((current - pd.Timestamp(date)).days)
    return 0 <= age <= int(expiration)


def _curated_events(frame: pd.DataFrame, current: pd.Timestamp) -> list[dict]:
    events: list[dict] = []
    if frame.empty:
        return events
    for row in frame.to_dict("records"):
        if pd.isna(row.get("priority")) or not _row_is_temporally_valid(row, current):
            continue
        if not _valid_https_url(row.get("source_url")):
            continue
        allowed, tier, evidence_role = _curated_source_allowed(row)
        if not allowed:
            continue
        fact = _clean_sentence(row.get("verified_fact"))
        relevance = _clean_sentence(row.get("platform_relevance"))
        source_name = " ".join(str(row.get("source_name") or "").split()).strip()
        source_label = " ".join(str(row.get("source_label") or source_name).split()).strip()
        if not fact or not source_name or not source_label:
            continue
        event_date = pd.Timestamp(row["event_date"])
        age = max(0, int((current - event_date).days))
        freshness = max(0.0, 12.0 - min(age, 12))
        resolution = str(row.get("resolution_status") or "recent").strip().lower()
        persistent_bonus = 4.0 if resolution in {"unresolved", "active", "pending"} else 0.0
        priority = float(row["priority"])
        events.append({
            "event_id": str(row["event_id"]),
            "event_date": event_date.date().isoformat(),
            "domain": str(row.get("domain") or "").strip().lower(),
            "owner_domain": str(row.get("domain") or "").strip().lower(),
            "event_type": str(row.get("event_type") or "").strip(),
            "priority": priority,
            "verified_fact": fact,
            "platform_relevance": relevance,
            "display": f"{fact} {relevance}".strip(),
            "reference_number": 0,
            "source_name": source_name,
            "source_label": source_label,
            "source_url": str(row.get("source_url") or "").strip(),
            "source_type": str(row.get("source_type") or "primary").strip().lower(),
            "source_tier": tier,
            "evidence_role": evidence_role,
            "verification_status": str(row.get("verification_status") or "confirmed").strip().lower(),
            "status": str(row.get("status") or "Confirmed").strip(),
            "legal_status": str(row.get("legal_status") or "").strip(),
            "resolution_status": resolution,
            "surface": str(row.get("surface") or "macro").strip().lower(),
            "secondary_domains": [item.strip() for item in str(row.get("secondary_domains") or "").split("|") if item.strip()],
            "sectors": [item.strip() for item in str(row.get("sectors") or "").split("|") if item.strip()],
            "tickers": [item.strip().upper() for item in str(row.get("tickers") or "").split("|") if item.strip()],
            "rank_score": priority + freshness + persistent_bonus,
            "record_origin": str(row.get("record_origin") or "").strip(),
            "retrieved_at": str(row.get("retrieved_at") or "").strip(),
            "discovery_provider": str(row.get("discovery_provider") or "").strip(),
            "discovery_query": str(row.get("discovery_query") or "").strip(),
        })
    return events


def _event_valid_for_sector(event: dict, sector: str) -> bool:
    sectors = {str(value) for value in event.get("sectors", [])}
    if str(sector) not in sectors:
        return False
    event_tickers = {str(value).upper() for value in event.get("tickers", []) if str(value).strip()}
    if not event_tickers:
        return True
    basket = {str(value).upper() for value in (SECTOR_CONFIG.get(sector, {}) or {}).get("basket", [])}
    return bool(event_tickers.intersection(basket))


def _fallback_sector_event(sector: str, current: pd.Timestamp) -> dict:
    return {
        "event_id": f"no-news-{sector.lower()}-{current.date().isoformat()}",
        "event_date": current.date().isoformat(),
        "domain": "market",
        "event_type": "sector_news_status",
        "priority": 0.0,
        "verified_fact": NO_QUALIFYING_NEWS,
        "platform_relevance": "",
        "display": NO_QUALIFYING_NEWS,
        "reference_number": None,
        "source_name": "",
        "source_label": "",
        "source_url": "",
        "source_type": "status",
        "source_tier": "status",
        "evidence_role": "none",
        "verification_status": "no_match",
        "status": "No match",
        "legal_status": "",
        "resolution_status": "recent",
        "surface": "sector",
        "sectors": [sector],
        "tickers": [],
        "rank_score": 0.0,
    }


def _dedupe_events(events: list[dict]) -> list[dict]:
    chosen: list[dict] = []
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for event in sorted(
        events,
        key=lambda item: (float(item.get("rank_score", item.get("priority", 0)) or 0), str(item.get("event_date", ""))),
        reverse=True,
    ):
        event_id = str(event.get("event_id") or "")
        normalized = re.sub(r"[^a-z0-9 ]+", " ", str(event.get("verified_fact") or "").casefold())
        title_key = " ".join(normalized.split()[:14])
        if event_id in seen_ids or (title_key and title_key in seen_titles):
            continue
        chosen.append(dict(event))
        if event_id:
            seen_ids.add(event_id)
        if title_key:
            seen_titles.add(title_key)
    return chosen


def _renumber_context(events: list[dict], current: pd.Timestamp, *, source: str) -> dict:
    references: list[dict] = []
    numbered_events: list[dict] = []
    reference_keys: dict[tuple[str, str], int] = {}
    for event in events:
        item = dict(event)
        url = str(item.get("source_url") or "").strip()
        source_label = str(item.get("source_label") or item.get("source_name") or "Source").strip()
        key = (source_label, url)
        number = None
        if _valid_https_url(url):
            number = reference_keys.get(key)
            if number is None:
                number = len(references) + 1
                reference_keys[key] = number
                references.append({
                    "reference_number": number,
                    "event_id": item.get("event_id", ""),
                    "source_name": item.get("source_name", ""),
                    "source_label": source_label,
                    "source_url": url,
                    "event_date": item.get("event_date", ""),
                    "source_tier": item.get("source_tier", ""),
                    "evidence_role": item.get("evidence_role", ""),
                })
        item["reference_number"] = number
        numbered_events.append(item)
    return {
        "events": numbered_events,
        "references": references,
        "as_of": current.date().isoformat(),
        "window_start": (current - pd.Timedelta(days=6)).date().isoformat(),
        "source": source,
        "version": WEEKLY_CONTEXT_VERSION,
    }


def _complete_sector_context(base_events: list[dict], current: pd.Timestamp, *, include_live: bool) -> dict:
    chosen: dict[str, dict] = {}
    for sector in SECTOR_CONFIG:
        candidates = [event for event in base_events if _event_valid_for_sector(event, sector)]
        candidates = _dedupe_events(candidates)
        if candidates:
            chosen[sector] = dict(candidates[0])

    missing = [sector for sector in SECTOR_CONFIG if sector not in chosen]
    if include_live and missing:
        workers = min(8, len(missing))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_fetch_live_sector_event, sector, current.date().isoformat()): sector
                for sector in missing
            }
            for future in as_completed(futures):
                sector = futures[future]
                try:
                    event = future.result()
                except Exception:
                    event = None
                if event is not None:
                    chosen[sector] = event

    for sector in SECTOR_CONFIG:
        chosen.setdefault(sector, _fallback_sector_event(sector, current))
    ordered = [chosen[sector] for sector in SECTOR_CONFIG]
    return _renumber_context(ordered, current, source="curated registry + approved live sector feeds")


def load_current_context(*, as_of=None, path=None, limit_per_domain=1, include_live=True) -> dict:
    """Return one or two source-controlled developments for every domain.

    Each event has exactly one visible tab owner.  Unresolved curated events may
    remain beyond the normal freshness window, but fresher and more material
    events can displace them.  When no source clears the evidence threshold, a
    restrained status row preserves the read's visual symmetry without
    inventing a headline.
    """
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    frame = _read_registry(Path(path or DEFAULT_EVENT_PATH))
    curated = _curated_events(frame, current)
    domain_events: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    for event in curated:
        domain = str(event.get("owner_domain") or event.get("domain") or "").strip().lower()
        surface = str(event.get("surface") or "").strip().lower()
        if domain in domain_events and surface in {"domain", "tab", "macro", "both", "all"}:
            item = dict(event)
            item["domain"] = domain
            item["owner_domain"] = domain
            # Curated ownership is explicit and outranks accidental live-query overlap.
            item["owner_score"] = float(item.get("rank_score", item.get("priority", 0)) or 0) + 1000.0
            domain_events[domain].append(item)

    if include_live:
        live_candidates: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
        with ThreadPoolExecutor(max_workers=min(8, len(DOMAIN_KEYS))) as executor:
            futures = {
                executor.submit(_fetch_live_domain_candidates, domain, current.date().isoformat()): domain
                for domain in DOMAIN_KEYS
            }
            for future in as_completed(futures):
                domain = futures[future]
                try:
                    candidates = list(future.result())
                except Exception:
                    candidates = []
                live_candidates[domain].extend(candidates)
        assigned = _assign_live_event_owners(live_candidates)
        for domain, events in assigned.items():
            domain_events[domain].extend(events)

    # A single source URL or canonical event may appear in only one subordinate
    # read.  Explicit curated ownership wins; otherwise the strongest fit wins.
    curated_or_live = {domain: [dict(event) for event in events] for domain, events in domain_events.items()}
    owned_events = _assign_live_event_owners(curated_or_live)

    by_domain: dict[str, dict] = {}
    all_events: list[dict] = []
    all_references: list[dict] = []
    limit = max(1, min(int(limit_per_domain), 2))
    for domain in DOMAIN_KEYS:
        selected = _dedupe_events(owned_events.get(domain, []))[:limit]
        if not selected:
            selected = [_fallback_domain_event(domain, current)]
        context = _renumber_context(selected, current, source="curated event ledger + approved live feeds")
        by_domain[domain] = context
        all_events.extend(context["events"])
        for reference in context["references"]:
            all_references.append({**reference, "domain": domain})

    macro_only = [
        event for event in curated
        if str(event.get("surface") or "").strip().lower() in {"macro", "both", "all"}
        and str(event.get("domain") or "").strip().lower() not in DOMAIN_KEYS
    ]
    return {
        "by_domain": by_domain,
        "events": _dedupe_events(all_events + macro_only),
        "references": all_references,
        "as_of": current.date().isoformat(),
        "window_start": (current - pd.Timedelta(days=6)).date().isoformat(),
        "source": "curated event ledger + approved live feeds",
        "version": WEEKLY_CONTEXT_VERSION,
    }


def load_weekly_context(*, as_of=None, path=None, limit=3, surface="macro", include_live=True):
    """Compatibility loader for the macro archive and Sector Dossier."""
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    frame = _read_registry(Path(path or DEFAULT_EVENT_PATH))
    curated = _curated_events(frame, current)
    surface_value = str(surface or "macro").strip().lower()

    if surface_value == "sector":
        base = [
            event for event in curated
            if str(event.get("surface") or "").strip().lower() in {"sector", "both", "all"}
        ]
        return _complete_sector_context(base, current, include_live=include_live)

    if surface_value == "domain":
        return load_current_context(
            as_of=current,
            path=path,
            limit_per_domain=min(max(int(limit), 1), 2),
            include_live=include_live,
        )

    candidates = [
        event for event in curated
        if str(event.get("surface") or "").strip().lower() in {surface_value, "both", "all"}
    ]
    selected = _dedupe_events(candidates)[: max(0, int(limit))]
    return _renumber_context(selected, current, source="curated primary-source registry")
