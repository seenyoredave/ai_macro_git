"""Auditable discovery pipeline for AI Macro Current Context.

This module is deliberately separate from rendering.  It discovers candidate
articles, records every acceptance/rejection decision, assigns each development
to one visible tab owner, and can merge selected records into the retained event
ledger.  The application therefore has a reproducible evidence trail rather
than an opaque "latest headline" call at render time.
"""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
import argparse
import hashlib
import html as html_lib
import json
import re
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    CURRENT_CONTEXT_COVERAGE_TARGET,
    CURRENT_CONTEXT_PREFERRED_WINDOW_DAYS,
    CURRENT_CONTEXT_HARD_WINDOW_DAYS,
    CURRENT_CONTEXT_QUALIFICATION_TIERS,
    current_context_max_lookback_days,
    current_context_qualification_policy,
    current_context_qualification_tier,
    current_context_tier_index,
    domain_relevance_terms,
    domain_topic_anchors,
    DISCOVERY_ONLY_DOMAINS,
    assess_source,
    assess_source_for_qualification,
    domain_news_queries,
    materiality_score,
    term_present,
)
from helpers.atomic_io import atomic_write_bundle, atomic_write_csv, synchronized_path
from loaders.current_context_grounding import GROUNDING_VERSION, GroundingResult, ground_candidate, is_preview_or_calendar_item
from loaders.current_context_news import (
    DOMAIN_KEYS,
    NEWS_MAX_BYTES,
    NEWS_TIMEOUT_SECONDS,
    NEWS_USER_AGENT,
    _assign_event_owners,
    _domain_fit_score,
    _feed_url,
    _parse_google_news_rss,
    _parse_news_date,
    _same_development,
    _strip_source_suffix,
    _valid_https_url,
)
from loaders.current_context_registry import DEFAULT_EVENT_PATH, _automated_row_still_qualifies, _curated_events

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = ROOT / "data" / "current_context_candidate_audit.csv"
DEFAULT_MANIFEST_PATH = ROOT / "data" / "current_context_refresh_manifest.json"
DEFAULT_RETROSPECTIVE_REGISTRY_PATH = ROOT / "audit" / "current_context_retrospective" / "retired_unproven_registry_rows_v730.csv"
DISCOVERY_VERSION = "3.1"

# Free second-layer sources are lead generators only.  The adapter harvests
# outbound evidence links and discards the intermediary prose for selection.
TIER2_DISCOVERY_FEEDS = {
    "market": (
        ("Techmeme", "https://www.techmeme.com/feed.xml"),
        ("Abnormal Returns", "https://abnormalreturns.com/feed"),
    ),
    "finance": (
        ("Abnormal Returns", "https://abnormalreturns.com/feed"),
        ("Data Center Richness", "https://datacenterrichness.substack.com/feed"),
    ),
}

# Direct primary feeds add an independent path that does not depend on a news
# index or curator.  Domain filters still decide whether an item is relevant.
PRIMARY_DISCOVERY_FEEDS = {
    "market": (
        ("U.S. Securities and Exchange Commission", "https://www.sec.gov/news/pressreleases.rss"),
    ),
    "finance": (
        ("Federal Reserve Board", "https://www.federalreserve.gov/feeds/press_monetary.xml"),
        ("U.S. Securities and Exchange Commission", "https://www.sec.gov/news/pressreleases.rss"),
    ),
}

_CANONICAL_SOURCE_NAMES = {
    "wsj.com": "The Wall Street Journal",
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "bloomberg.com": "Bloomberg",
    "ft.com": "Financial Times",
    "barrons.com": "Barron's",
    "investors.com": "Investor's Business Daily",
    "morningstar.com": "Morningstar",
    "cnbc.com": "CNBC",
    "businesswire.com": "Business Wire",
    "utilitydive.com": "Utility Dive",
    "datacenterdynamics.com": "Data Center Dynamics",
    "rtoinsider.com": "RTO Insider",
    "spglobal.com": "S&P Global",
    "constructiondive.com": "Construction Dive",
    "semiengineering.com": "Semiconductor Engineering",
    "eetimes.com": "EE Times",
    "texastribune.org": "The Texas Tribune",
    "houstonchronicle.com": "Houston Chronicle",
    "dallasnews.com": "Dallas Morning News",
    "statesman.com": "Austin American-Statesman",
    "expressnews.com": "San Antonio Express-News",
}


class _AnchorExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.casefold() != "a":
            return
        self._href = dict(attrs).get("href", "") or ""
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "a" or not self._href:
            return
        text = " ".join(" ".join(self._text).split()).strip()
        self.links.append((self._href, text))
        self._href = ""
        self._text = []


def _fetch_bytes(url: str) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": NEWS_USER_AGENT})
    try:
        with urlopen(request, timeout=max(NEWS_TIMEOUT_SECONDS, 6)) as response:
            payload = response.read(NEWS_MAX_BYTES + 1)
    except Exception as exc:
        return b"", f"{type(exc).__name__}: {exc}"
    if len(payload) > NEWS_MAX_BYTES:
        return b"", "response exceeded byte limit"
    return payload, ""


def _node_text(node: ET.Element, names: tuple[str, ...]) -> str:
    for child in list(node):
        local = child.tag.rsplit("}", 1)[-1].casefold()
        if local in names:
            return str(child.text or "").strip()
    return ""


def _generic_rss_items(payload: bytes, *, provider: str, source_name: str = "") -> list[dict]:
    if not payload:
        return []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return []
    nodes = root.findall("./channel/item")
    if not nodes:
        nodes = [node for node in root.iter() if node.tag.rsplit("}", 1)[-1].casefold() == "entry"]
    items: list[dict] = []
    for node in nodes:
        title = " ".join(html_lib.unescape(_node_text(node, ("title",))).split()).strip()
        link = _node_text(node, ("link",))
        if not link:
            for child in list(node):
                if child.tag.rsplit("}", 1)[-1].casefold() == "link":
                    link = str(child.attrib.get("href") or "").strip()
                    if link:
                        break
        date_text = _node_text(node, ("pubdate", "published", "updated", "date"))
        published = _parse_news_date(date_text)
        if published is None:
            try:
                published = pd.Timestamp(date_text).tz_localize(None).normalize() if date_text else None
            except (TypeError, ValueError):
                published = None
        parts = []
        for child in list(node):
            if child.tag.rsplit("}", 1)[-1].casefold() in {"description", "summary", "content", "encoded"}:
                parts.append(str(child.text or ""))
        description_html = " ".join(parts)
        description = re.sub(r"<[^>]+>", " ", description_html)
        description = " ".join(html_lib.unescape(description).split()).strip()
        if title and published is not None:
            items.append({
                "title": title,
                "link": link,
                "published": published,
                "source_name": source_name or _canonical_source_name(link),
                "source_url": f"https://{_host(link)}" if _host(link) else "",
                "description": description,
                "description_html": description_html,
                "provider": provider,
            })
    return items




def fetch_google_news(query: str, *, days: int) -> tuple[list[dict], str]:
    """Fetch Google News RSS while preserving transport failures in the audit.

    Transport failures remain explicit audit data so an unreachable provider
    cannot be mistaken for a valid zero-result query.
    """
    payload, error = _fetch_bytes(_feed_url(query, days=days))
    if error:
        return [], error
    return _parse_google_news_rss(payload), ""

def fetch_primary_feed(source_name: str, feed_url: str) -> tuple[list[dict], str]:
    payload, error = _fetch_bytes(feed_url)
    if error:
        return [], error
    items = _generic_rss_items(payload, provider="primary_feed", source_name=source_name)
    for item in items:
        item["source_name"] = source_name
        item["source_url"] = f"https://{_host(item.get('link', ''))}" if _host(item.get("link", "")) else ""
        item["discovered_via"] = source_name
        item["discovery_source_url"] = feed_url
    return items, ""


def fetch_tier2_outbound(source_name: str, feed_url: str, *, max_links: int = 60) -> tuple[list[dict], str]:
    payload, error = _fetch_bytes(feed_url)
    if error:
        return [], error
    feed_items = _generic_rss_items(payload, provider="tier2_feed", source_name=source_name)
    outbound: list[dict] = []
    for parent in feed_items:
        extractor = _AnchorExtractor()
        try:
            extractor.feed(str(parent.get("description_html") or ""))
        except Exception:
            pass
        candidates = list(extractor.links)
        parent_link = str(parent.get("link") or "").strip()
        if parent_link:
            candidates.append((parent_link, str(parent.get("title") or "")))
        for href, anchor_text in candidates:
            url = urljoin(feed_url, str(href or "").strip())
            if not _valid_https_url(url):
                continue
            host = _host(url)
            if any(host == domain or host.endswith("." + domain) for domain in DISCOVERY_ONLY_DOMAINS):
                continue
            evidence = assess_source(_canonical_source_name(url), f"https://{host}" if host else "", url)
            if not evidence.auto_eligible:
                continue
            title = " ".join(str(anchor_text or parent.get("title") or "").split()).strip()
            if len(title) < 8:
                title = str(parent.get("title") or "").strip()
            outbound.append({
                "title": title,
                "link": url,
                "published": parent.get("published"),
                "source_name": _canonical_source_name(url),
                "source_url": f"https://{host}" if host else "",
                "description": str(parent.get("title") or ""),
                "provider": "tier2_outbound",
                "discovered_via": source_name,
                "discovery_source_url": parent_link or feed_url,
            })
            if len(outbound) >= max_links:
                return _dedupe_items(outbound), ""
    return _dedupe_items(outbound), ""


@dataclass
class FetchStatus:
    domain: str
    provider: str
    query: str
    lookback_days: int
    status: str
    item_count: int
    error: str = ""


def _host(url: str) -> str:
    try:
        return (urlparse(str(url or "")).hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _canonical_source_name(url: str) -> str:
    host = _host(url)
    for domain, name in _CANONICAL_SOURCE_NAMES.items():
        if host == domain or host.endswith("." + domain):
            return name
    if host.endswith(".gov"):
        return host
    return host or "News source"


def _item_key(item: dict) -> str:
    url = str(item.get("link") or "").strip().casefold()
    if url:
        return "url::" + url
    title = re.sub(r"[^a-z0-9 ]+", " ", str(item.get("title") or "").casefold())
    return "title::" + " ".join(title.split()[:18])


def _dedupe_items(items: list[dict]) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()
    for item in items:
        key = _item_key(item)
        if key in seen:
            continue
        seen.add(key)
        selected.append(dict(item))
    return selected


def evaluate_item(
    item: dict,
    *,
    domain: str,
    current: pd.Timestamp,
    provider: str,
    qualification_tier: str | None = None,
) -> tuple[dict | None, dict]:
    """Evaluate one discovery item through the progressive coverage ladder.

    When ``qualification_tier`` is omitted, the item is assigned to the first
    tier A→E whose metadata gates it clears.  The audit row therefore records
    the least-relaxed standard required for that candidate.
    """
    tiers = (
        [tier for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS if tier.key == str(qualification_tier).upper()]
        if qualification_tier
        else list(CURRENT_CONTEXT_QUALIFICATION_TIERS)
    )
    if not tiers:
        tiers = [CURRENT_CONTEXT_QUALIFICATION_TIERS[0]]

    title = " ".join(str(item.get("title") or "").split()).strip()
    source_name = " ".join(str(item.get("source_name") or "News source").split()).strip()
    article_url = str(item.get("link") or "").strip()
    publisher_url = str(item.get("source_url") or "").strip()
    published_raw = item.get("published")
    text = f"{title} {item.get('description', '')}".strip()
    materiality = float(materiality_score(text, domain))
    relevance_matches = [term for term in domain_relevance_terms(domain) if term_present(text, str(term))]
    topic_anchor_matches = [term for term in domain_topic_anchors(domain) if term_present(text, str(term))]
    fit = float(_domain_fit_score(text, domain))
    tier_failures: list[str] = []
    final_audit: dict = {}

    for tier in tiers:
        policy = current_context_qualification_policy(domain, tier.key)
        days = max(int(policy.get("lookback_days", 7)), 1)
        assessment = assess_source_for_qualification(
            source_name, publisher_url, article_url, provider=provider, tier_key=tier.key
        )
        source_score = float(assessment.score)
        freshness = 0.0
        score = source_score + (materiality * 2.5) + (fit * 1.5)
        age_days = None
        decision = "rejected"
        reason = ""
        published = None

        if published_raw is None:
            reason = "missing publication date"
        else:
            published = pd.Timestamp(published_raw).normalize()
            age_days = int((current - published).days)
            freshness = max(0.0, float(days - max(age_days, 0)))
            score += freshness
            if age_days < 0 or age_days >= days:
                reason = "outside tier lookback window"
            elif not assessment.auto_eligible:
                reason = assessment.reason
            elif is_preview_or_calendar_item(title):
                reason = "preview/calendar item is not a completed development"
            elif not relevance_matches:
                reason = "no domain relevance term"
            elif bool(policy.get("require_topic_anchor", True)) and domain_topic_anchors(domain) and not topic_anchor_matches:
                reason = "no AI/technology or system-wide domain anchor"
            elif materiality < float(policy.get("minimum_materiality", 0.0001)):
                reason = "insufficient domain materiality"
            elif not _valid_https_url(article_url):
                reason = "missing traceable HTTPS article URL"
            else:
                decision = "metadata_qualified"
                reason = "cleared progressive discovery-metadata gates; underlying source grounding required before selection"

        final_audit = {
            "audit_version": DISCOVERY_VERSION,
            "as_of": current.date().isoformat(),
            "domain_query": domain,
            "provider": provider,
            "query": " || ".join(domain_news_queries(domain)),
            "lookback_days": days,
            "qualification_tier": tier.key,
            "qualification_tier_label": tier.label,
            "effective_minimum_materiality": round(float(policy.get("minimum_materiality", 0.0)), 4),
            "topic_anchor_required": bool(policy.get("require_topic_anchor", True)),
            "source_policy": str(policy.get("source_policy") or "strict"),
            "title": title,
            "published": published.date().isoformat() if published is not None else "",
            "age_days": age_days if age_days is not None else "",
            "source_name": source_name,
            "publisher_url": publisher_url,
            "article_url": article_url,
            "source_tier": assessment.tier,
            "source_score": source_score,
            "source_role": assessment.evidence_role,
            "materiality_score": materiality,
            "domain_fit_score": fit,
            "rank_score": score,
            "relevance_terms": "|".join(relevance_matches),
            "topic_anchor_terms": "|".join(topic_anchor_matches),
            "decision": decision,
            "reason": reason,
            "event_id": "",
            "owner_domain": "",
            "selected": False,
            "discovered_via": str(item.get("discovered_via") or provider),
            "discovery_source_url": str(item.get("discovery_source_url") or ""),
            "evidence_path": "progressive_eligible_source" if assessment.auto_eligible else "",
            "grounding_version": GROUNDING_VERSION,
            "grounding_status": "not_attempted",
            "source_resolved_url": "",
            "source_text_method": "",
            "source_text_chars": 0,
            "source_evidence_hash": "",
            "headline_similarity": "",
            "source_published_date": "",
            "source_modified_date": "",
            "grounding_reason": "",
            "grounding_error": "",
            "tier_failures": " | ".join(tier_failures),
        }
        if decision != "metadata_qualified":
            tier_failures.append(f"{tier.key}:{reason}")
            continue

        headline = _strip_source_suffix(title, source_name)
        digest = hashlib.sha1(f"{headline}|{article_url}".casefold().encode("utf-8")).hexdigest()[:12]
        event_id = f"auto-{published.date().isoformat()}-{digest}"
        if assessment.evidence_role == "official_statement":
            source_type = "official_statement"
            verification_status = "primary"
            status = "Primary record"
        elif assessment.evidence_role == "company_statement":
            source_type = "company_statement"
            verification_status = "company_statement"
            status = "Company statement"
        else:
            source_type = "news"
            verification_status = "reported"
            status = "Reported"
        candidate = {
            "event_id": event_id,
            "event_date": published.date().isoformat(),
            "domain": domain,
            "owner_domain": domain,
            "event_type": "reported_development",
            "priority": score,
            "verified_fact": headline,
            "platform_relevance": "",
            "display": headline,
            "reference_number": 0,
            "source_name": source_name,
            "source_label": source_name,
            "source_url": article_url,
            "publisher_url": publisher_url,
            "source_type": source_type,
            "source_tier": assessment.tier,
            "evidence_role": assessment.evidence_role,
            "verification_status": verification_status,
            "status": status,
            "legal_status": "",
            "resolution_status": "recent",
            "surface": "domain",
            "sectors": [],
            "tickers": [],
            "owner_score": fit,
            "rank_score": score,
            "discovery_provider": provider,
            "discovery_query": str(item.get("discovery_query") or " || ".join(domain_news_queries(domain))),
            "discovered_via": str(item.get("discovered_via") or provider),
            "discovery_source_url": str(item.get("discovery_source_url") or ""),
            "discovery_title": headline,
            "discovery_description": str(item.get("description") or ""),
            "grounding_version": GROUNDING_VERSION,
            "grounding_status": "pending",
            "lookback_days": days,
            "qualification_tier": tier.key,
            "qualification_tier_label": tier.label,
            "effective_minimum_materiality": float(policy.get("minimum_materiality", 0.0)),
            "topic_anchor_required": bool(policy.get("require_topic_anchor", True)),
            "minimum_source_text_chars": int(policy.get("minimum_source_text_chars", 220)),
        }
        final_audit["event_id"] = event_id
        final_audit["tier_failures"] = " | ".join(tier_failures)
        return candidate, final_audit

    if final_audit:
        final_audit["tier_failures"] = " | ".join(tier_failures)
    return None, final_audit


def _enforce_tier2_evidence_boundary(evaluated: list[tuple[dict, dict]]) -> list[dict]:
    """Require independent retrieval for Tier-2 leads that resolve only to secondary reporting.

    A curator may point directly to a primary record or company statement; that
    underlying record can establish the claim on its own.  If the curator points
    to secondary journalism, however, the same development must also have been
    found through an independent non-Tier-2 discovery path before it is eligible
    for unattended selection.  This breaks the curator's bibliography boundary
    without pretending repeated publication is independent evidence.
    """
    independent = [
        candidate for candidate, audit in evaluated
        if candidate is not None and str(audit.get("provider") or "") != "tier2_outbound"
    ]
    accepted: list[dict] = []
    for candidate, audit in evaluated:
        if candidate is None:
            continue
        if str(audit.get("provider") or "") != "tier2_outbound":
            accepted.append(candidate)
            continue
        role = str(candidate.get("evidence_role") or "")
        discovered_via = str(candidate.get("discovered_via") or "Tier-2 source")
        source_name = str(candidate.get("source_name") or "evidence source")
        if role in {"official_statement", "company_statement"}:
            audit["evidence_path"] = f"{discovered_via} -> {source_name} ({role})"
            accepted.append(candidate)
            continue
        corroborator = next((other for other in independent if _same_development(candidate, other)), None)
        if corroborator is None:
            audit["decision"] = "rejected_tier2_unverified"
            audit["reason"] = "Tier-2 lead lacked independent retrieval beyond the curator bibliography"
            audit["evidence_path"] = f"{discovered_via} -> {source_name} -> independent retrieval not found"
            continue
        independent_source = str(corroborator.get("source_name") or "independent source")
        audit["evidence_path"] = f"{discovered_via} -> {source_name} -> independently retrieved via {independent_source}"
        candidate["verification_status"] = "independently_retrieved"
        candidate["status"] = "Independently reported"
        candidate["independent_source_name"] = independent_source
        accepted.append(candidate)
    return accepted



_EVENT_EVIDENCE_STOPWORDS = {
    "about", "after", "against", "amid", "among", "article", "builds", "company",
    "development", "from", "into", "more", "news", "reports", "reported", "says",
    "said", "than", "that", "their", "this", "through", "under", "week", "with",
    "year", "years", "would", "could", "will", "reuters", "bloomberg", "journal",
    "times", "market", "markets", "business", "finance", "financial", "latest",
}


def _event_evidence_text(candidate: dict) -> str:
    return " ".join(
        str(candidate.get(key) or "")
        for key in ("discovery_title", "discovery_description", "verified_fact")
    ).strip()


def _event_evidence_tokens(text: object) -> set[str]:
    value = str(text or "").casefold().replace("data-centre", "data center").replace("data-centre", "data center")
    tokens = re.findall(r"[a-z0-9]+", value)
    return {
        token for token in tokens
        if len(token) >= 3 and token not in _EVENT_EVIDENCE_STOPWORDS
    }


def _event_numeric_tokens(text: object) -> set[str]:
    """Return coarse numeric signatures so $15bn and $15 billion can match."""
    value = str(text or "").casefold().replace(",", "")
    matches: set[str] = set()
    pattern = re.compile(
        r"\$?\s*(\d+(?:\.\d+)?)\s*(trillion|billion|million|tn|bn|mn|%|percent|gw|mw|gbps|tbps|bps)?",
        re.I,
    )
    scale = {"tn": "trillion", "bn": "billion", "mn": "million", "percent": "%"}
    for number, unit in pattern.findall(value):
        try:
            canonical_number = f"{float(number):g}"
        except ValueError:
            canonical_number = number
        canonical_unit = scale.get(unit.casefold(), unit.casefold()) if unit else ""
        if canonical_unit or float(number) >= 10:
            matches.add(f"{canonical_number}:{canonical_unit}")
    return matches


def _event_evidence_similarity(seed: dict, item: dict, *, domain: str) -> float:
    """Score whether an alternate search result is about the nominated event.

    This is deliberately an evidence-routing score, not a qualification score.
    The alternate source still has to pass the normal source-body grounding gate.
    """
    seed_text = _event_evidence_text(seed)
    item_text = f"{item.get('title', '')} {item.get('description', '')}".strip()
    left = _event_evidence_tokens(seed_text)
    right = _event_evidence_tokens(item_text)
    if not left or not right:
        return 0.0
    overlap = len(left.intersection(right)) / max(1, min(len(left), len(right)))
    seq = SequenceMatcher(None, " ".join(sorted(left)), " ".join(sorted(right))).ratio()
    seed_numbers = _event_numeric_tokens(seed_text)
    item_numbers = _event_numeric_tokens(item_text)
    number_bonus = 0.22 if seed_numbers and item_numbers and seed_numbers.intersection(item_numbers) else 0.0

    anchor_matches = sum(
        1 for term in domain_topic_anchors(domain)
        if term_present(seed_text, str(term)) and term_present(item_text, str(term))
    )
    relevance_matches = sum(
        1 for term in domain_relevance_terms(domain)
        if term_present(seed_text, str(term)) and term_present(item_text, str(term))
    )
    signal_bonus = min(0.22, anchor_matches * 0.04 + relevance_matches * 0.03)
    return min(1.0, overlap * 0.55 + seq * 0.23 + number_bonus + signal_bonus)


def _event_resolution_queries(candidate: dict, *, domain: str) -> tuple[str, ...]:
    """Build a tiny source-independent search set for one nominated event."""
    headline = _strip_source_suffix(
        str(candidate.get("discovery_title") or candidate.get("verified_fact") or ""),
        str(candidate.get("source_name") or ""),
    )
    headline = " ".join(headline.split()).strip()
    combined = _event_evidence_text(candidate)
    queries: list[str] = []
    if headline:
        queries.append(headline[:220])

    anchors = [str(term) for term in domain_topic_anchors(domain) if term_present(combined, str(term))]
    relevance = [str(term) for term in domain_relevance_terms(domain) if term_present(combined, str(term))]
    numbers = sorted(_event_numeric_tokens(combined))
    number_words = []
    for value in numbers[:2]:
        number, unit = value.split(":", 1)
        number_words.append(" ".join(part for part in (number, unit) if part))
    signal_query = " ".join(dict.fromkeys([*anchors[:6], *relevance[:4], *number_words]))
    if signal_query and signal_query.casefold() != headline.casefold():
        queries.append(signal_query[:220])
    return tuple(dict.fromkeys(query for query in queries if query))[:2]


def _alternate_evidence_candidate(
    seed: dict,
    item: dict,
    *,
    domain: str,
    current: pd.Timestamp,
    resolution_query: str,
) -> dict | None:
    source_name = " ".join(str(item.get("source_name") or "News source").split()).strip()
    article_url = str(item.get("link") or "").strip()
    publisher_url = str(item.get("source_url") or "").strip()
    assessment = assess_source(source_name, publisher_url, article_url)
    if not assessment.auto_eligible or not _valid_https_url(article_url):
        return None

    # An alternate-evidence lookup exists to escape one inaccessible publisher.
    # Retrying the same host under a different headline is not independent evidence.
    alternate_host = _host(publisher_url) or _host(article_url)
    seed_host = _host(str(seed.get("publisher_url") or "")) or _host(str(seed.get("source_url") or ""))
    if alternate_host and seed_host and alternate_host == seed_host:
        return None

    published = item.get("published")
    if published is None:
        return None
    try:
        published = pd.Timestamp(published).normalize()
        lookback = max(int(seed.get("lookback_days", 7) or 7), 1)
        age = int((current - published).days)
        seed_date = pd.Timestamp(seed.get("event_date")).normalize()
        if age < 0 or age >= lookback or abs(int((published - seed_date).days)) > 4:
            return None
    except Exception:
        return None

    similarity = _event_evidence_similarity(seed, item, domain=domain)
    if similarity < 0.42:
        return None

    alternate = dict(seed)
    alternate.update({
        "source_name": source_name,
        "source_label": source_name,
        "source_url": article_url,
        "publisher_url": publisher_url,
        "source_tier": assessment.tier,
        "evidence_role": assessment.evidence_role,
        "evidence_resolution_similarity": round(float(similarity), 4),
        "evidence_resolution_query": resolution_query,
        "evidence_resolution_mode": "alternate_source",
        "evidence_seed_source_name": str(seed.get("source_name") or ""),
        "evidence_seed_source_url": str(seed.get("source_url") or ""),
    })
    if assessment.evidence_role == "official_statement":
        alternate.update({"source_type": "official_statement", "verification_status": "primary", "status": "Primary record"})
    elif assessment.evidence_role == "company_statement":
        alternate.update({"source_type": "company_statement", "verification_status": "company_statement", "status": "Company statement"})
    else:
        alternate.update({"source_type": "news", "verification_status": "reported", "status": "Reported"})
    return alternate


def _known_event_evidence_alternatives(
    seed: dict,
    items: list[dict],
    *,
    domain: str,
    current: pd.Timestamp,
) -> list[dict]:
    alternatives: list[tuple[float, dict]] = []
    seen_urls: set[str] = set()
    for item in items:
        candidate = _alternate_evidence_candidate(
            seed, item, domain=domain, current=current, resolution_query="existing discovery pool"
        )
        if candidate is None:
            continue
        url = str(candidate.get("source_url") or "").casefold()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        alternatives.append((float(candidate.get("evidence_resolution_similarity", 0)), candidate))
    alternatives.sort(key=lambda pair: pair[0], reverse=True)
    return [candidate for _, candidate in alternatives]


def _should_seek_alternate_evidence(result: GroundingResult) -> bool:
    reason = str(result.reason or "").casefold()
    # Explicitly disqualifying event types should remain dead. Everything else
    # that failed because one URL was inaccessible or insufficient may be
    # researched through another eligible evidence path.
    disqualifying = (
        "preview/calendar",
        "central-bank commentary",
        "attributed commentary",
        "publisher page predates",
        "commentary/topic framing",
    )
    return not any(marker in reason for marker in disqualifying)

def _ground_domain_candidates(
    candidates: list[dict],
    audit_rows: list[dict],
    *,
    domain: str,
    target_grounded: int,
    max_attempts: int,
    current: pd.Timestamp | None = None,
    discovery_items: list[dict] | None = None,
    statuses: list[FetchStatus] | None = None,
    grounder=None,
    event_searcher=None,
) -> list[dict]:
    """Ground events, not URLs.

    A discovery URL nominates an event.  The URL gets the first chance because
    it is the shortest evidence path, but an inaccessible/paywalled publisher is
    not allowed to veto an otherwise material event.  When direct grounding
    fails for a non-disqualifying reason, the same event is researched through
    other eligible evidence already in the discovery pool and then through a
    small source-independent Google News event search.  Every alternate source
    still has to pass the exact same source-body grounding contract.
    """
    current = pd.Timestamp(current or pd.Timestamp.now()).normalize()
    discovery_items = list(discovery_items or [])
    statuses = statuses if statuses is not None else []
    grounder = grounder or ground_candidate
    event_searcher = event_searcher or fetch_google_news
    by_event = {str(row.get("event_id") or ""): row for row in audit_rows if row.get("event_id")}
    grounded: list[dict] = []
    attempted: set[str] = set()
    target = max(1, int(target_grounded))
    budget = max(target, int(max_attempts))
    event_search_budget = 6 if domain == "finance" else (4 if domain == "market" else 2)
    alternate_fetch_budget = 10 if domain == "finance" else (7 if domain == "market" else 4)
    event_search_cache: dict[str, tuple[list[dict], str]] = {}
    tried_evidence_urls: set[str] = set()

    # Do not let one inaccessible publisher consume the entire grounding budget.
    # First try the highest-ranked candidate from each source, then return to the
    # remaining ranked queue. This changes transport resilience, not the evidence bar.
    first_by_source: list[dict] = []
    deferred: list[dict] = []
    seen_sources: set[str] = set()
    for candidate in candidates:
        source_key = str(candidate.get("source_name") or candidate.get("publisher_url") or candidate.get("source_url") or "unknown").strip().casefold()
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            first_by_source.append(candidate)
        else:
            deferred.append(candidate)
    attempt_queue = first_by_source + deferred

    for candidate in attempt_queue:
        if len(attempted) >= budget or len(grounded) >= target:
            break
        event_id = str(candidate.get("event_id") or "")
        attempted.add(event_id)
        row = by_event.get(event_id)

        result_candidate, result = grounder(candidate, domain=domain)
        seed_reason = result.reason or result.error or "underlying source did not establish the development"
        evidence_attempts = 0
        alternate_errors: list[str] = []

        # The discovered URL is a nomination, not a mandatory endpoint. If that
        # route fails, search for the same event through another eligible source.
        if result_candidate is None and _should_seek_alternate_evidence(result) and alternate_fetch_budget > 0:
            alternatives = _known_event_evidence_alternatives(
                candidate, discovery_items, domain=domain, current=current
            )

            if event_search_budget > 0:
                queries = _event_resolution_queries(candidate, domain=domain)
                allowed_queries = min(len(queries), event_search_budget)
                searched: list[dict] = []
                for query in queries[:allowed_queries]:
                    event_search_budget -= 1
                    if query not in event_search_cache:
                        found, error = event_searcher(query, days=max(int(candidate.get("lookback_days", 7) or 7), 1))
                        event_search_cache[query] = (found, error)
                        statuses.append(FetchStatus(
                            domain,
                            "event_evidence_search",
                            query,
                            max(int(candidate.get("lookback_days", 7) or 7), 1),
                            "ok" if not error else "error",
                            len(found),
                            error,
                        ))
                    found, error = event_search_cache[query]
                    if error:
                        alternate_errors.append(f"event search {query!r}: {error}")
                        continue
                    for item in found:
                        alternate = _alternate_evidence_candidate(
                            candidate, item, domain=domain, current=current, resolution_query=query
                        )
                        if alternate is not None:
                            searched.append(alternate)
                alternatives.extend(searched)

            deduped_alternatives: list[dict] = []
            local_seen: set[str] = set()
            for alternate in sorted(
                alternatives,
                key=lambda item: float(item.get("evidence_resolution_similarity", 0)),
                reverse=True,
            ):
                alt_url = str(alternate.get("source_url") or "").strip().casefold()
                if not alt_url or alt_url in local_seen or alt_url in tried_evidence_urls:
                    continue
                local_seen.add(alt_url)
                deduped_alternatives.append(alternate)

            for alternate in deduped_alternatives[:4]:
                if alternate_fetch_budget <= 0:
                    break
                alternate_fetch_budget -= 1
                evidence_attempts += 1
                tried_evidence_urls.add(str(alternate.get("source_url") or "").strip().casefold())
                alt_candidate, alt_result = grounder(alternate, domain=domain)
                if alt_candidate is None:
                    alternate_errors.append(
                        f"{alternate.get('source_name', 'alternate source')}: "
                        f"{alt_result.reason or alt_result.error or 'grounding rejected'}"
                    )
                    continue

                # Preserve the event's discovery/ranking identity while replacing
                # the evidentiary endpoint with the source that actually grounded it.
                for key in (
                    "event_id", "domain", "owner_domain", "priority", "owner_score",
                    "rank_score", "event_type", "lookback_days", "discovery_provider",
                    "discovery_query", "discovered_via", "discovery_source_url",
                    "qualification_tier", "qualification_tier_label",
                    "effective_minimum_materiality", "topic_anchor_required",
                    "minimum_source_text_chars",
                ):
                    if key in candidate:
                        alt_candidate[key] = candidate[key]
                alt_candidate.update({
                    "evidence_resolution_mode": "alternate_source",
                    "evidence_seed_source_name": str(candidate.get("source_name") or ""),
                    "evidence_seed_source_url": str(candidate.get("source_url") or ""),
                    "evidence_resolution_query": str(alternate.get("evidence_resolution_query") or ""),
                    "evidence_resolution_similarity": alternate.get("evidence_resolution_similarity", ""),
                })
                result_candidate = alt_candidate
                result = alt_result
                break

        if row is not None:
            row.update({
                "grounding_status": "grounded" if result_candidate is not None else "rejected",
                "source_resolved_url": result.resolved_url,
                "source_text_method": result.extraction_method,
                "source_text_chars": result.text_chars,
                "source_evidence_hash": result.evidence_hash,
                "headline_similarity": result.headline_similarity,
                "source_published_date": result.source_published_date,
                "source_modified_date": result.source_modified_date,
                "grounding_reason": result.reason,
                "grounding_error": result.error,
                "evidence_resolution_status": (
                    "alternate_source_grounded"
                    if result_candidate is not None and str(result_candidate.get("evidence_resolution_mode") or "") == "alternate_source"
                    else ("direct_source_grounded" if result_candidate is not None else "exhausted")
                ),
                "evidence_resolution_attempts": evidence_attempts,
                "evidence_seed_grounding_reason": seed_reason if evidence_attempts else "",
                "evidence_source_name": str(result_candidate.get("source_name") or "") if result_candidate is not None else "",
                "evidence_resolution_query": str(result_candidate.get("evidence_resolution_query") or "") if result_candidate is not None else "",
                "evidence_resolution_error": " | ".join(alternate_errors[:4]),
            })

        if result_candidate is None:
            if row is not None:
                row["decision"] = "rejected_source_grounding"
                row["reason"] = seed_reason
                if evidence_attempts or alternate_errors:
                    row["grounding_reason"] = (
                        f"{seed_reason}; alternate eligible evidence did not establish the event"
                    )
            continue

        if row is not None:
            row["decision"] = "accepted"
            if str(result_candidate.get("evidence_resolution_mode") or "") == "alternate_source":
                row["reason"] = "event established through alternate eligible evidence"
                row["article_url"] = result.resolved_url or result_candidate.get("source_url", "")
                row["evidence_path"] = (
                    f"{row.get('source_name') or 'discovery source'} nominated event -> "
                    f"{result_candidate.get('source_name') or 'alternate eligible source'} established event"
                )
                row["source_resolved_url"] = result.resolved_url or result_candidate.get("source_url", "")
            else:
                row["reason"] = result.reason
                row["article_url"] = result.resolved_url or row.get("article_url", "")
                row["evidence_path"] = f"{row.get('evidence_path') or 'eligible source'} -> source body grounded"
        grounded.append(result_candidate)

    for candidate in candidates:
        event_id = str(candidate.get("event_id") or "")
        if event_id in attempted:
            continue
        row = by_event.get(event_id)
        if row is not None and row.get("decision") == "metadata_qualified":
            row["decision"] = "metadata_qualified_not_grounded"
            row["reason"] = "source-grounding request budget reached after higher-ranked candidates"
    return grounded

def _select_ranked_domain_events(ranked: list[dict], max_items: int) -> list[dict]:
    """Select at most two events and prevent a Tier-2 discovery source from monopolizing the surface."""
    limit = max(1, min(int(max_items), 2))
    selected: list[dict] = []
    tier2_count = 0
    for event in ranked:
        is_tier2 = str(event.get("discovery_provider") or "") == "tier2_outbound"
        if is_tier2 and tier2_count >= 1:
            continue
        selected.append(event)
        if is_tier2:
            tier2_count += 1
        if len(selected) >= limit:
            break
    return selected


def _rank_progressive_events(events: list[dict]) -> list[dict]:
    """Rank quality tier before within-tier materiality/freshness score."""
    return sorted(
        events,
        key=lambda item: (
            -current_context_tier_index(item.get("qualification_tier", "A")),
            float(item.get("rank_score", item.get("priority", 0)) or 0),
            str(item.get("event_date", "")),
        ),
        reverse=True,
    )


def _event_survives_reader_contract(event: dict, *, current: pd.Timestamp, retrieved_at: str) -> bool:
    """Apply the exact retained Reader gate before an event can count toward coverage.

    Discovery and rendering must share one eligibility contract.  A grounded
    candidate that would disappear on registry reload is not a qualifying
    Current Context event and may not satisfy the six-domain floor.
    """
    row = _registry_row(event, retrieved_at=retrieved_at)
    frame = pd.DataFrame([row])
    frame["event_date"] = pd.to_datetime(frame["event_date"], errors="coerce").dt.normalize()
    frame["priority"] = pd.to_numeric(frame["priority"], errors="coerce")
    frame["expires_after_days"] = pd.to_numeric(frame["expires_after_days"], errors="coerce")
    return bool(_curated_events(frame, current))


def _reader_renderable_assigned(
    assigned: dict[str, list[dict]], *, current: pd.Timestamp, retrieved_at: str, audit_rows: list[dict] | None = None
) -> dict[str, list[dict]]:
    audit_by_event = {str(row.get("event_id") or ""): row for row in (audit_rows or []) if row.get("event_id")}
    renderable: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    for domain in DOMAIN_KEYS:
        for event in assigned.get(domain, []) or []:
            item = dict(event)
            item["domain"] = domain
            item["owner_domain"] = domain
            if _event_survives_reader_contract(item, current=current, retrieved_at=retrieved_at):
                renderable[domain].append(item)
                continue
            row = audit_by_event.get(str(item.get("event_id") or ""))
            if row is not None:
                row["decision"] = "rejected_reader_contract"
                row["reason"] = "grounded event failed the final retained Reader eligibility contract"
    return renderable


def _normalize_reader_registry_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize a raw/prospective registry frame before applying Reader rules.

    ``_curated_events`` normally receives the normalized output of the retained
    registry loader.  Coverage commissioning also evaluates raw CSV/prospective
    frames directly, so normalize the date/numeric fields here rather than
    depending on the caller's storage representation.
    """
    normalized = frame.copy()
    if normalized.empty:
        return normalized
    if "event_date" in normalized.columns:
        normalized["event_date"] = pd.to_datetime(normalized["event_date"], errors="coerce").dt.normalize()
    if "resolved_date" in normalized.columns:
        normalized["resolved_date"] = pd.to_datetime(normalized["resolved_date"], errors="coerce").dt.normalize()
    for column in ("priority", "expires_after_days"):
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    return normalized


def _reader_visible_domains_from_frame(frame: pd.DataFrame, *, current: pd.Timestamp) -> set[str]:
    """Resolve the exact set of subordinate Reader domains from a registry frame."""
    curated = _curated_events(_normalize_reader_registry_frame(frame), current)
    domain_events: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    for event in curated:
        domain = str(event.get("owner_domain") or event.get("domain") or "").strip().lower()
        surface = str(event.get("surface") or "").strip().lower()
        if domain not in domain_events or surface not in {"domain", "tab", "macro", "both", "all"}:
            continue
        item = dict(event)
        item["domain"] = domain
        item["owner_domain"] = domain
        item["owner_score"] = float(item.get("rank_score", item.get("priority", 0)) or 0) + 1000.0
        domain_events[domain].append(item)
    owned = _assign_event_owners(domain_events)
    return {domain for domain in DOMAIN_KEYS if owned.get(domain)}


def _retained_reader_domains(path: Path, *, current: pd.Timestamp) -> set[str]:
    """Return domains that are actually renderable from the current retained registry."""
    try:
        frame = pd.read_csv(path) if path.exists() and path.stat().st_size > 0 else pd.DataFrame()
    except Exception:
        frame = pd.DataFrame()
    return _reader_visible_domains_from_frame(frame, current=current)


def _continuity_seed_candidate(row: dict, *, current: pd.Timestamp) -> dict | None:
    """Turn a still-current retained/historical event into a discovery seed only.

    The prior prose is never trusted as Reader evidence.  It is used only to
    identify an event that must be fetched and grounded again under the current
    source-body contract.
    """
    domain = str(row.get("domain") or "").strip().lower()
    source_url = str(row.get("source_url") or "").strip()
    if domain not in DOMAIN_KEYS or not _valid_https_url(source_url):
        return None
    try:
        event_date = pd.Timestamp(row.get("event_date")).normalize()
    except Exception:
        return None
    age = int((current - event_date).days)
    if age < 0 or age >= CURRENT_CONTEXT_HARD_WINDOW_DAYS:
        return None
    tier_key = str(row.get("qualification_tier") or "").strip().upper()
    if tier_key not in {tier.key for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS}:
        tier_key = "A" if age < CURRENT_CONTEXT_PREFERRED_WINDOW_DAYS else "C"
    if age >= CURRENT_CONTEXT_PREFERRED_WINDOW_DAYS and current_context_tier_index(tier_key) < current_context_tier_index("C"):
        tier_key = "C"
    policy = current_context_qualification_policy(domain, tier_key)
    title = str(row.get("source_title") or row.get("verified_fact") or "").strip()
    if not title:
        return None
    priority_value = pd.to_numeric(row.get("priority"), errors="coerce")
    priority = 0.0 if pd.isna(priority_value) else float(priority_value)
    return {
        "event_id": str(row.get("event_id") or hashlib.sha256(f"{domain}|{source_url}|{event_date.date()}".encode()).hexdigest()[:16]),
        "event_date": event_date.date().isoformat(),
        "domain": domain,
        "owner_domain": domain,
        "event_type": str(row.get("event_type") or "reported_development"),
        "priority": priority,
        "rank_score": priority,
        "owner_score": priority,
        "verified_fact": title,
        "discovery_title": title,
        "discovery_description": str(row.get("verified_fact") or "").strip(),
        "source_name": str(row.get("source_name") or "").strip(),
        "source_label": str(row.get("source_label") or row.get("source_name") or "").strip(),
        "source_url": source_url,
        "publisher_url": source_url,
        "source_type": str(row.get("source_type") or "news").strip().lower(),
        "verification_status": str(row.get("verification_status") or "reported").strip().lower(),
        "status": str(row.get("status") or "Reported"),
        "qualification_tier": tier_key,
        "qualification_tier_label": current_context_qualification_tier(tier_key).label,
        "lookback_days": int(policy.get("lookback_days", CURRENT_CONTEXT_HARD_WINDOW_DAYS) or CURRENT_CONTEXT_HARD_WINDOW_DAYS),
        "discovery_provider": "retained_continuity",
        "discovery_query": "retained continuity revalidation",
        "discovered_via": "retained_continuity",
        "discovery_source_url": source_url,
        "_continuity_seed": True,
    }


def _retained_continuity_seeds(
    *, current: pd.Timestamp, registry_path: Path, retrospective_path: Path | None = None
) -> dict[str, list[dict]]:
    """Collect still-current event identities that merit source re-grounding.

    Current-version live rows need no extra fetch. Older reconstruction rows and
    quarantined historical rows are eligible only as leads; they must pass live
    source grounding before they can return to the Reader.
    """
    paths = [Path(registry_path)]
    if retrospective_path is not None:
        paths.append(Path(retrospective_path))
    by_domain: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    seen: set[tuple[str, str]] = set()
    live_event_ids: set[str] = set()
    live_source_urls: set[str] = set()
    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        for row in frame.to_dict("records"):
            # Current-version automated rows are already eligible for ordinary
            # retained continuity and do not need another network fetch.
            if path == Path(registry_path):
                if (
                    str(row.get("record_origin") or "").strip().casefold() == "automated_discovery"
                    and str(row.get("grounding_status") or "").strip().casefold() == "grounded"
                    and str(row.get("grounding_version") or "").strip() == GROUNDING_VERSION
                ):
                    event_id = str(row.get("event_id") or "").strip()
                    source_url = str(row.get("source_url") or "").strip().casefold()
                    if event_id:
                        live_event_ids.add(event_id)
                    if source_url:
                        live_source_urls.add(source_url)
                    continue
            candidate = _continuity_seed_candidate(row, current=current)
            if candidate is None:
                continue
            event_id = str(candidate.get("event_id") or "")
            source_url = str(candidate.get("source_url") or "").casefold()
            if event_id in live_event_ids or source_url in live_source_urls:
                continue
            key = (event_id, source_url)
            if key in seen:
                continue
            seen.add(key)
            by_domain[str(candidate["domain"])].append(candidate)
    for domain in DOMAIN_KEYS:
        by_domain[domain].sort(key=lambda item: (float(item.get("rank_score", 0) or 0), str(item.get("event_date", ""))), reverse=True)
        by_domain[domain] = by_domain[domain][:2]
    return by_domain


def _select_progressive_coverage(assigned: dict[str, list[dict]], *, retained_domains: set[str] | None = None) -> tuple[dict[str, list[dict]], dict]:
    """Relax A→E only until the six-domain coverage constraint is satisfied.

    Discovery fetches the maximum fallback window once for efficiency, but
    selection behaves as a true progressive ladder: Tier B cannot enter the
    retained registry if Tier A alone already covers six domains, and so on.
    """
    retained_domains = {str(domain).strip().lower() for domain in (retained_domains or set()) if str(domain).strip().lower() in DOMAIN_KEYS}
    ranked_by_domain = {
        domain: _rank_progressive_events(list(assigned.get(domain, []) or []))
        for domain in DOMAIN_KEYS
    }
    cumulative: dict[str, int] = {}
    reached = CURRENT_CONTEXT_QUALIFICATION_TIERS[-1]
    for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS:
        cutoff = current_context_tier_index(tier.key)
        candidate_domains = {
            domain for domain in DOMAIN_KEYS
            if any(current_context_tier_index(event.get("qualification_tier", "A")) <= cutoff for event in ranked_by_domain[domain])
        }
        available = len(retained_domains | candidate_domains)
        cumulative[tier.key] = available
        reached = tier
        if available >= CURRENT_CONTEXT_COVERAGE_TARGET:
            break

    cutoff = current_context_tier_index(reached.key)
    selected: dict[str, list[dict]] = {}
    for domain in DOMAIN_KEYS:
        eligible = [
            event for event in ranked_by_domain[domain]
            if current_context_tier_index(event.get("qualification_tier", "A")) <= cutoff
        ]
        max_items = max(1, min(int((DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}).get("max_items", 2)), 2))
        selected[domain] = _select_ranked_domain_events(eligible, max_items)

    selected_domains = [domain for domain in DOMAIN_KEYS if selected.get(domain)]
    reader_domains = sorted(retained_domains | set(selected_domains))
    domain_tiers = Counter(
        str((selected[domain][0] or {}).get("qualification_tier") or "A")
        for domain in selected_domains
    )
    event_tiers = Counter(
        str(event.get("qualification_tier") or "A")
        for domain in DOMAIN_KEYS
        for event in selected.get(domain, [])
    )
    return selected, {
        "target_domains": CURRENT_CONTEXT_COVERAGE_TARGET,
        "preferred_window_days": CURRENT_CONTEXT_PREFERRED_WINDOW_DAYS,
        "hard_window_days": CURRENT_CONTEXT_HARD_WINDOW_DAYS,
        "selected_domain_count": len(reader_domains),
        "selected_domains": selected_domains,
        "new_selected_domain_count": len(selected_domains),
        "retained_baseline_domain_count": len(retained_domains),
        "retained_baseline_domains": sorted(retained_domains),
        "reader_domains": reader_domains,
        "target_met": len(reader_domains) >= CURRENT_CONTEXT_COVERAGE_TARGET,
        "tier_reached": reached.key,
        "tier_reached_label": reached.label,
        "expanded_discovery_required": reached.key != "A",
        "available_domains_by_tier": {tier.key: int(cumulative.get(tier.key, cumulative.get(reached.key, 0))) for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS if current_context_tier_index(tier.key) <= cutoff},
        "selected_domains_by_tier": {tier.key: int(domain_tiers.get(tier.key, 0)) for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS},
        "selected_events_by_tier": {tier.key: int(event_tiers.get(tier.key, 0)) for tier in CURRENT_CONTEXT_QUALIFICATION_TIERS},
    }


def discover_domain(domain: str, *, as_of=None) -> tuple[list[dict], list[dict], list[FetchStatus]]:
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    policy = DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}
    days = current_context_max_lookback_days(domain)
    queries = domain_news_queries(domain)
    statuses: list[FetchStatus] = []
    items: list[dict] = []

    # Google News gets the narrow query set.  This is independent of any Tier-2
    # bibliography and therefore helps prevent curator selection bias.
    for query in queries:
        google_items, google_error = fetch_google_news(query, days=days)
        for item in google_items:
            item["provider"] = "google_news_rss"
            item["discovery_query"] = query
        statuses.append(FetchStatus(domain, "google_news_rss", query, days, "ok" if not google_error else "error", len(google_items), google_error))
        items.extend(google_items)

    # Primary feeds are direct evidence discovery.  They are intentionally few
    # and domain-filtered rather than a general government-document fire hose.
    for source_name, feed_url in PRIMARY_DISCOVERY_FEEDS.get(domain, ()):
        primary_items, error = fetch_primary_feed(source_name, feed_url)
        statuses.append(FetchStatus(domain, "primary_feed", feed_url, days, "ok" if not error else "error", len(primary_items), error))
        items.extend(primary_items)

    # Tier-2 sources never enter the evidence set themselves.  Only eligible
    # outbound primary/approved links are harvested from their recent posts.
    for source_name, feed_url in TIER2_DISCOVERY_FEEDS.get(domain, ()):
        outbound, error = fetch_tier2_outbound(source_name, feed_url)
        statuses.append(FetchStatus(domain, "tier2_outbound", feed_url, days, "ok" if not error else "error", len(outbound), error))
        items.extend(outbound)

    items = _dedupe_items(items)
    audit: list[dict] = []
    evaluated: list[tuple[dict, dict]] = []
    for item in items:
        provider = str(item.get("provider") or "unknown")
        candidate, record = evaluate_item(item, domain=domain, current=current, provider=provider)
        audit.append(record)
        evaluated.append((candidate, record))
    metadata_qualified = _enforce_tier2_evidence_boundary(evaluated)
    metadata_qualified.sort(
        key=lambda item: (
            -current_context_tier_index(item.get("qualification_tier", "A")),
            float(item.get("rank_score", 0)),
            str(item.get("event_date", "")),
        ),
        reverse=True,
    )
    # Ground adaptively rather than giving up after an arbitrary first six.
    # High-cadence Market/Finance get a slightly larger request budget because
    # they encounter more paywalls, commentary, and duplicate coverage.
    max_items = max(1, min(int(policy.get("max_items", 2)), 2))
    # Ground enough of the progressively qualified queue to make coverage a
    # real constraint rather than a metadata-only aspiration.  Quality order is
    # preserved because Tier A candidates are attempted before B→E.
    target_grounded = max(2, max_items)
    # Sparse domains receive a deeper grounding search so the six-domain floor
    # is an operating requirement rather than a metadata-only aspiration.
    max_attempts = 24 if domain in {"grid_storage", "water", "connectivity", "workforce", "economic_impact", "adoption"} else 20
    grounded = _ground_domain_candidates(
        metadata_qualified,
        audit,
        domain=domain,
        target_grounded=target_grounded,
        max_attempts=max_attempts,
        current=current,
        discovery_items=items,
        statuses=statuses,
    )
    grounded.sort(
        key=lambda item: (
            -current_context_tier_index(item.get("qualification_tier", "A")),
            float(item.get("rank_score", 0)),
            str(item.get("event_date", "")),
        ),
        reverse=True,
    )
    return grounded, audit, statuses


def _registry_row(event: dict, *, retrieved_at: str) -> dict:
    tier_key = str(event.get("qualification_tier") or "A")
    tier_policy = current_context_qualification_policy(str(event.get("domain") or ""), tier_key)
    return {
        "event_id": event.get("event_id", ""),
        "event_date": event.get("event_date", ""),
        "domain": event.get("domain", ""),
        "event_type": event.get("event_type", "reported_development"),
        "priority": event.get("priority", event.get("rank_score", 0)),
        "verified_fact": event.get("verified_fact", ""),
        "platform_relevance": event.get("platform_relevance", ""),
        "source_name": event.get("source_name", ""),
        "source_label": event.get("source_label", event.get("source_name", "")),
        "source_url": event.get("source_url", ""),
        "source_type": event.get("source_type", "news"),
        "verification_status": event.get("verification_status", "reported"),
        "expires_after_days": int(tier_policy.get("lookback_days", 7) or 7),
        "surface": "domain",
        "sectors": "",
        "tickers": "",
        "status": event.get("status", "Reported"),
        "legal_status": "",
        "resolution_status": "recent",
        "resolved_date": "",
        "source_tier": event.get("source_tier", ""),
        "evidence_role": event.get("evidence_role", "secondary"),
        "persistent": False,
        "secondary_domains": "|".join(event.get("secondary_domains", []) or []),
        "record_origin": "automated_discovery",
        "retrieved_at": retrieved_at,
        "discovery_provider": event.get("discovery_provider", ""),
        "discovery_query": event.get("discovery_query", ""),
        "discovered_via": event.get("discovered_via", ""),
        "discovery_source_url": event.get("discovery_source_url", ""),
        "grounding_version": event.get("grounding_version", GROUNDING_VERSION),
        "grounding_status": event.get("grounding_status", "grounded"),
        "source_resolved_url": event.get("source_url", ""),
        "source_text_method": event.get("source_text_method", ""),
        "source_text_chars": event.get("source_text_chars", 0),
        "source_evidence_hash": event.get("source_evidence_hash", ""),
        "source_title": event.get("source_title", ""),
        "source_published_date": event.get("source_published_date", ""),
        "source_modified_date": event.get("source_modified_date", ""),
        "evidence_resolution_mode": event.get("evidence_resolution_mode", "direct_source"),
        "evidence_seed_source_name": event.get("evidence_seed_source_name", ""),
        "evidence_seed_source_url": event.get("evidence_seed_source_url", ""),
        "evidence_resolution_query": event.get("evidence_resolution_query", ""),
        "evidence_resolution_similarity": event.get("evidence_resolution_similarity", ""),
        "qualification_tier": tier_key,
        "qualification_tier_label": event.get("qualification_tier_label", current_context_qualification_tier(tier_key).label),
        "effective_minimum_materiality": float(tier_policy.get("minimum_materiality", 0.0) or 0.0),
        "topic_anchor_required": bool(tier_policy.get("require_topic_anchor", True)),
        "minimum_source_text_chars": int(tier_policy.get("minimum_source_text_chars", 220) or 220),
        "minimum_anchor_score": float(tier_policy.get("minimum_anchor_score", 8.0) or 8.0),
    }


def _merged_registry_frame(
    selected: dict[str, list[dict]],
    *,
    path=DEFAULT_EVENT_PATH,
    retrieved_at: str,
) -> tuple[pd.DataFrame | None, int]:
    """Build the qualified-registry upsert without publishing it yet."""
    path = Path(path)
    rows = [_registry_row(event, retrieved_at=retrieved_at) for events in selected.values() for event in events]
    if not rows:
        return None, 0

    existing = pd.read_csv(path) if path.exists() and path.stat().st_size > 0 else pd.DataFrame()
    if not existing.empty:
        # The qualified registry is a live evidence surface, not a historical
        # archive.  Legacy rows without modern source-grounding provenance are
        # retained in the audit corpus, but may not survive a successful v3
        # registry publication.
        existing = existing.loc[
            existing.apply(lambda row: _automated_row_still_qualifies(row.to_dict()), axis=1)
        ].copy()
    additions = pd.DataFrame(rows)
    if additions.empty:
        return None, 0

    # weekly_context_events.csv is the current qualified registry; the audit
    # CSV owns history. Rediscovering the same event is therefore an upsert,
    # not a reason to discard newer grounded provenance.
    additions = additions.drop_duplicates(subset=["event_id"], keep="last")
    if not existing.empty and "event_id" in existing.columns:
        replacement_ids = set(additions["event_id"].astype(str))
        existing = existing.loc[~existing["event_id"].astype(str).isin(replacement_ids)].copy()

    columns = list(dict.fromkeys([*existing.columns.tolist(), *additions.columns.tolist()]))
    existing = existing.reindex(columns=columns)
    additions = additions.reindex(columns=columns)
    combined = pd.concat([existing, additions], ignore_index=True)
    return combined, len(additions)


def merge_selected_into_registry(selected: dict[str, list[dict]], *, path=DEFAULT_EVENT_PATH, retrieved_at: str) -> int:
    """Compatibility helper for callers that only need the registry upsert."""
    path = Path(path)
    with synchronized_path(path.parent / ".current_context_refresh"):
        combined, added = _merged_registry_frame(selected, path=path, retrieved_at=retrieved_at)
        if combined is not None:
            atomic_write_csv(combined, path, lock=False)
        return added


def _portable_manifest_path(path: Path) -> str:
    """Persist repository-relative paths and never leak a developer home path."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def refresh_current_context(*, as_of=None, audit_path=DEFAULT_AUDIT_PATH, manifest_path=DEFAULT_MANIFEST_PATH, registry_path=DEFAULT_EVENT_PATH, merge_registry=True) -> dict:
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    audit_path = Path(audit_path)
    manifest_path = Path(manifest_path)
    registry_path = Path(registry_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    accepted_by_domain: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    audit_rows: list[dict] = []
    fetch_statuses: list[FetchStatus] = []
    retained_domains = _retained_reader_domains(registry_path, current=current)

    retrospective_path = (
        DEFAULT_RETROSPECTIVE_REGISTRY_PATH
        if registry_path.resolve() == Path(DEFAULT_EVENT_PATH).resolve()
        else None
    )
    continuity_seeds = _retained_continuity_seeds(
        current=current,
        registry_path=registry_path,
        retrospective_path=retrospective_path,
    )
    continuity_attempted = sum(len(items) for items in continuity_seeds.values())
    continuity_recovered = 0

    with ThreadPoolExecutor(max_workers=min(8, len(DOMAIN_KEYS))) as executor:
        futures = {
            executor.submit(discover_domain, domain, as_of=current): domain
            for domain in DOMAIN_KEYS
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                accepted, audit, statuses = future.result()
            except Exception as exc:
                accepted, audit = [], []
                policy = DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}
                statuses = [FetchStatus(
                    domain,
                    "discovery_pipeline",
                    " || ".join(domain_news_queries(domain)),
                    max(int(policy.get("lookback_days", 7)), 1),
                    "error",
                    0,
                    f"{type(exc).__name__}: {exc}",
                )]
            accepted_by_domain[domain].extend(accepted)
            audit_rows.extend(audit)
            fetch_statuses.extend(statuses)

    # Continuity rows are leads, never evidence.  Still-current events from an
    # older reconstruction contract (or the quarantined retrospective corpus)
    # get one chance to re-establish themselves from the live source.  This
    # preserves strong events such as a still-current earnings release without
    # grandfathering bad prose or stale page identity.
    for domain in DOMAIN_KEYS:
        seeds = list(continuity_seeds.get(domain, []) or [])
        if not seeds:
            continue
        recovered = _ground_domain_candidates(
            seeds,
            [],
            domain=domain,
            target_grounded=len(seeds),
            max_attempts=len(seeds),
            current=current,
            discovery_items=[],
            statuses=fetch_statuses,
        )
        continuity_recovered += len(recovered)
        accepted_by_domain[domain].extend(recovered)

    assigned = _assign_event_owners(accepted_by_domain)
    assigned = _reader_renderable_assigned(
        assigned, current=current, retrieved_at=retrieved_at, audit_rows=audit_rows
    )

    fresh_reader_qualified_count = sum(
        1 for domain in DOMAIN_KEYS for event in assigned.get(domain, []) if not bool(event.get("_continuity_seed"))
    )

    continuity_selected: dict[str, list[dict]] = {
        domain: [event for event in assigned.get(domain, []) if bool(event.get("_continuity_seed"))]
        for domain in DOMAIN_KEYS
    }
    continuity_domains = {domain for domain in DOMAIN_KEYS if continuity_selected.get(domain)}
    fresh_assigned: dict[str, list[dict]] = {
        domain: [event for event in assigned.get(domain, []) if not bool(event.get("_continuity_seed"))]
        for domain in DOMAIN_KEYS
    }
    fresh_selected, coverage = _select_progressive_coverage(
        fresh_assigned, retained_domains=(retained_domains | continuity_domains)
    )

    # Successfully re-grounded continuity events are restored irrespective of
    # the tier needed for *new* discovery.  The quality ladder governs how far
    # we relax to acquire additional news; it should not evict a still-current
    # event that has just passed the current source-body contract.
    selected: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    for domain in DOMAIN_KEYS:
        seen_ids: set[str] = set()
        seen_urls: set[str] = set()
        combined = [*(continuity_selected.get(domain, []) or []), *(fresh_selected.get(domain, []) or [])]
        for event in combined:
            event_id = str(event.get("event_id") or "")
            source_url = str(event.get("source_url") or "").strip().casefold()
            if event_id and event_id in seen_ids:
                continue
            if source_url and source_url in seen_urls:
                continue
            selected[domain].append(event)
            if event_id:
                seen_ids.add(event_id)
            if source_url:
                seen_urls.add(source_url)

    selected_ids: set[str] = {
        str(item.get("event_id") or "")
        for domain in DOMAIN_KEYS
        for item in selected.get(domain, [])
    }

    owner_by_id = {
        str(event.get("event_id") or ""): domain
        for domain, events in assigned.items()
        for event in events
    }
    for row in audit_rows:
        event_id = str(row.get("event_id") or "")
        row["owner_domain"] = owner_by_id.get(event_id, "")
        row["selected"] = event_id in selected_ids
        if row["decision"] == "accepted" and event_id not in owner_by_id:
            row["decision"] = "rejected_after_deduplication"
            row["reason"] = "same development assigned to a stronger domain owner"
        elif row["decision"] == "accepted" and not row["selected"]:
            row["decision"] = "accepted_not_selected"
            row["reason"] = "qualified but ranked below the domain's selected development(s)"

    registry_frame: pd.DataFrame | None = None
    prospective_frame: pd.DataFrame | None = None
    added = 0
    if coverage.get("target_met"):
        with synchronized_path(registry_path.parent / ".current_context_refresh"):
            prospective_frame, added = _merged_registry_frame(
                selected,
                path=registry_path,
                retrieved_at=retrieved_at,
            )

    # The floor is a Reader contract, not a discovery statistic.  Recompute it
    # from the exact prospective registry that would be published.  If the
    # final retained loader cannot render six domains, publication is refused.
    if prospective_frame is None:
        try:
            prospective_frame = pd.read_csv(registry_path) if registry_path.exists() and registry_path.stat().st_size > 0 else pd.DataFrame()
        except Exception:
            prospective_frame = pd.DataFrame()
    reader_domains = sorted(_reader_visible_domains_from_frame(prospective_frame, current=current))
    coverage["reader_domains"] = reader_domains
    coverage["selected_domain_count"] = len(reader_domains)
    coverage["reader_domain_count"] = len(reader_domains)
    coverage["target_met"] = len(reader_domains) >= CURRENT_CONTEXT_COVERAGE_TARGET
    if coverage["target_met"] and merge_registry and prospective_frame is not None:
        registry_frame = prospective_frame
    else:
        registry_frame = None
        if not coverage["target_met"]:
            added = 0


    snapshot_material = {
        "discovery_version": DISCOVERY_VERSION,
        "as_of": current.date().isoformat(),
        "retrieved_at": retrieved_at,
        "selected": {
            domain: [
                {
                    "event_id": event.get("event_id", ""),
                    "source_url": event.get("source_url", ""),
                    "event_date": event.get("event_date", ""),
                }
                for event in events
            ]
            for domain, events in selected.items()
        },
    }
    snapshot_id = hashlib.sha256(
        json.dumps(snapshot_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]

    grounding_reasons = Counter(
        str(row.get("grounding_reason") or row.get("reason") or "source grounding rejected").strip()
        for row in audit_rows
        if str(row.get("grounding_status") or "").strip() == "rejected"
    )
    grounding_by_domain = {}
    for domain in DOMAIN_KEYS:
        rows = [row for row in audit_rows if str(row.get("domain_query") or "") == domain]
        rejected = Counter(
            str(row.get("grounding_reason") or row.get("reason") or "source grounding rejected").strip()
            for row in rows
            if str(row.get("grounding_status") or "").strip() == "rejected"
        )
        metadata_rejected = Counter(
            str(row.get("reason") or "metadata rejected").strip()
            for row in rows
            if str(row.get("decision") or "").strip() == "rejected"
            and str(row.get("grounding_status") or "").strip() not in {"grounded", "rejected"}
        )
        grounding_by_domain[domain] = {
            "discovered": len(rows),
            "metadata_qualified": sum(1 for row in rows if str(row.get("event_id") or "").strip()),
            "direct_source_grounded": sum(1 for row in rows if str(row.get("evidence_resolution_status") or "") == "direct_source_grounded"),
            "alternate_source_grounded": sum(1 for row in rows if str(row.get("evidence_resolution_status") or "") == "alternate_source_grounded"),
            "evidence_resolution_attempts": sum(int(row.get("evidence_resolution_attempts") or 0) for row in rows),
            "metadata_rejection_reasons": [
                {"reason": reason, "count": count}
                for reason, count in metadata_rejected.most_common(6)
                if reason
            ],
            "attempted": sum(1 for row in rows if str(row.get("grounding_status") or "").strip() in {"grounded", "rejected"}),
            "succeeded": sum(1 for row in rows if str(row.get("grounding_status") or "").strip() == "grounded"),
            "failed": sum(1 for row in rows if str(row.get("grounding_status") or "").strip() == "rejected"),
            "selected": len(selected.get(domain, [])),
            "rejection_reasons": [
                {"reason": reason, "count": count}
                for reason, count in rejected.most_common(4)
                if reason
            ],
        }

    manifest = {
        "discovery_version": DISCOVERY_VERSION,
        "snapshot_id": snapshot_id,
        "as_of": current.date().isoformat(),
        "retrieved_at": retrieved_at,
        "providers": ["google_news_rss", "primary_feed", "tier2_outbound"],
        "domains": list(DOMAIN_KEYS),
        "fetch_status": [asdict(status) for status in fetch_statuses],
        "candidate_count": len(audit_rows),
        "qualified_count": int(fresh_reader_qualified_count),
        "continuity": {
            "attempted": int(continuity_attempted),
            "recovered": int(continuity_recovered),
            "selected": int(sum(len(items) for items in continuity_selected.values())),
            "domains": sorted(domain for domain in DOMAIN_KEYS if continuity_selected.get(domain)),
        },
        "fresh_selected_counts": {
            domain: len(fresh_selected.get(domain, [])) for domain in DOMAIN_KEYS
        },
        "grounding": {
            "version": GROUNDING_VERSION,
            "attempted": sum(1 for row in audit_rows if str(row.get("grounding_status", "")) in {"grounded", "rejected"}),
            "succeeded": sum(1 for row in audit_rows if str(row.get("grounding_status", "")) == "grounded"),
            "failed": sum(1 for row in audit_rows if str(row.get("grounding_status", "")) == "rejected"),
            "alternate_source_grounded": sum(1 for row in audit_rows if str(row.get("evidence_resolution_status") or "") == "alternate_source_grounded"),
            "rejection_reasons": [
                {"reason": reason, "count": count}
                for reason, count in grounding_reasons.most_common(8)
                if reason
            ],
            "by_domain": grounding_by_domain,
        },
        "selected": {
            domain: [
                {
                    "event_id": event.get("event_id", ""),
                    "source_name": event.get("source_name", ""),
                    "source_url": event.get("source_url", ""),
                    "event_date": event.get("event_date", ""),
                    "rank_score": event.get("rank_score", 0),
                    "qualification_tier": event.get("qualification_tier", "A"),
                    "qualification_tier_label": event.get("qualification_tier_label", "Preferred"),
                }
                for event in events
            ]
            for domain, events in selected.items()
        },
        "coverage": coverage,
        "publication_status": "selected_and_merged" if coverage.get("target_met") else "retained_fallback_coverage_floor",
        "registry_rows_added": added,
        "audit_path": _portable_manifest_path(audit_path),
        "registry_path": _portable_manifest_path(registry_path),
    }

    payloads: dict[Path, bytes] = {
        audit_path: pd.DataFrame(audit_rows).to_csv(index=False).encode("utf-8"),
        manifest_path: (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8"),
    }
    if registry_frame is not None:
        payloads[registry_path] = registry_frame.to_csv(index=False).encode("utf-8")
    atomic_write_bundle(
        payloads,
        transaction_key=manifest_path.parent / ".current_context_refresh",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh AI Macro Current Context with an auditable approved-source discovery pass.")
    parser.add_argument("--as-of", default=None, help="YYYY-MM-DD effective date; defaults to today")
    parser.add_argument("--no-merge", action="store_true", help="Write audit/manifest without adding selected events to the retained ledger")
    parser.add_argument("--audit-path", default=str(DEFAULT_AUDIT_PATH))
    parser.add_argument("--manifest-path", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--registry-path", default=str(DEFAULT_EVENT_PATH))
    args = parser.parse_args()
    manifest = refresh_current_context(
        as_of=args.as_of,
        audit_path=args.audit_path,
        manifest_path=args.manifest_path,
        registry_path=args.registry_path,
        merge_registry=not args.no_merge,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
