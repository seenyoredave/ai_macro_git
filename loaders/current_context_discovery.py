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
    DOMAIN_NEWS_QUERIES,
    DOMAIN_NEWS_TERMS,
    DOMAIN_TOPIC_ANCHORS,
    DISCOVERY_ONLY_DOMAINS,
    assess_source,
    domain_news_queries,
    recent_development_copy_issues,
    materiality_score,
    term_present,
)
from helpers.atomic_io import atomic_write_csv, atomic_write_json, synchronized_path
from loaders.current_context_grounding import GROUNDING_VERSION, ground_candidate, is_preview_or_calendar_item
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
from loaders.current_context_registry import DEFAULT_EVENT_PATH

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = ROOT / "data" / "current_context_candidate_audit.csv"
DEFAULT_MANIFEST_PATH = ROOT / "data" / "current_context_refresh_manifest.json"
DISCOVERY_VERSION = "2.1"

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


def evaluate_item(item: dict, *, domain: str, current: pd.Timestamp, provider: str) -> tuple[dict | None, dict]:
    """Evaluate one discovery item and return both candidate and audit record."""
    policy = DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}
    days = max(int(policy.get("lookback_days", 7)), 1)
    published = item.get("published")
    title = " ".join(str(item.get("title") or "").split()).strip()
    source_name = " ".join(str(item.get("source_name") or "News source").split()).strip()
    article_url = str(item.get("link") or "").strip()
    publisher_url = str(item.get("source_url") or "").strip()
    assessment = assess_source(source_name, publisher_url, article_url)
    text = f"{title} {item.get('description', '')}".strip()
    materiality = float(materiality_score(text, domain))
    relevance_matches = [term for term in DOMAIN_NEWS_TERMS.get(domain, ()) if term_present(text, str(term))]
    topic_anchor_matches = [term for term in DOMAIN_TOPIC_ANCHORS.get(domain, ()) if term_present(text, str(term))]
    fit = float(_domain_fit_score(text, domain))
    freshness = 0.0
    score = assessment.score + (materiality * 2.5) + (fit * 1.5)
    age_days = None
    decision = "rejected"
    reason = ""

    if published is None:
        reason = "missing publication date"
    else:
        published = pd.Timestamp(published).normalize()
        age_days = int((current - published).days)
        freshness = max(0.0, float(days - max(age_days, 0)))
        score += freshness
        if age_days < 0 or age_days >= days:
            reason = "outside domain lookback window"
        elif not assessment.auto_eligible:
            reason = assessment.reason
        elif is_preview_or_calendar_item(title):
            reason = "preview/calendar item is not a completed development"
        elif not relevance_matches:
            reason = "no domain relevance term"
        elif DOMAIN_TOPIC_ANCHORS.get(domain) and not topic_anchor_matches:
            reason = "no AI/technology or system-wide domain anchor"
        elif materiality < float(policy.get("minimum_materiality", 0.0001)):
            reason = "insufficient domain materiality"
        elif not _valid_https_url(article_url):
            reason = "missing traceable HTTPS article URL"
        elif recent_development_copy_issues(title):
            reason = "headline lacks formal first-reference context"
        else:
            decision = "metadata_qualified"
            reason = "cleared discovery-metadata gates; underlying source grounding required before selection"

    audit = {
        "audit_version": DISCOVERY_VERSION,
        "as_of": current.date().isoformat(),
        "domain_query": domain,
        "provider": provider,
        "query": " || ".join(domain_news_queries(domain)),
        "lookback_days": days,
        "title": title,
        "published": published.date().isoformat() if published is not None else "",
        "age_days": age_days if age_days is not None else "",
        "source_name": source_name,
        "publisher_url": publisher_url,
        "article_url": article_url,
        "source_tier": assessment.tier,
        "source_score": assessment.score,
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
        "evidence_path": "primary_or_approved_source" if assessment.auto_eligible else "",
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
    }
    if decision != "metadata_qualified":
        return None, audit

    headline = _strip_source_suffix(title, source_name)
    digest = __import__("hashlib").sha1(f"{headline}|{article_url}".casefold().encode("utf-8")).hexdigest()[:12]
    event_id = f"auto-{published.date().isoformat()}-{digest}"
    fact_text, relevance_text = headline, ""
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
        "verified_fact": fact_text,
        "platform_relevance": relevance_text,
        "display": f"{fact_text} {relevance_text}".strip(),
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
        "owner_score": score,
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
    }
    audit["event_id"] = event_id
    return candidate, audit


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


def _ground_domain_candidates(
    candidates: list[dict],
    audit_rows: list[dict],
    *,
    domain: str,
    target_grounded: int,
    max_attempts: int,
) -> list[dict]:
    """Ground ranked candidates until the domain has usable evidence or hits a cap.

    A fixed top-N crawl can starve a high-volume domain when the first few
    publisher pages are inaccessible or fail the evidence gate.  We therefore
    continue down the ranked queue until enough source-grounded candidates exist
    to survive cross-domain ownership/deduplication, subject to a strict request
    budget.  The evidence threshold itself is unchanged.
    """
    by_event = {str(row.get("event_id") or ""): row for row in audit_rows if row.get("event_id")}
    grounded: list[dict] = []
    attempted: set[str] = set()
    target = max(1, int(target_grounded))
    budget = max(target, int(max_attempts))

    for candidate in candidates:
        if len(attempted) >= budget or len(grounded) >= target:
            break
        event_id = str(candidate.get("event_id") or "")
        attempted.add(event_id)
        row = by_event.get(event_id)
        result_candidate, result = ground_candidate(candidate, domain=domain)
        if row is not None:
            row.update({
                "grounding_status": "grounded" if result.accepted else "rejected",
                "source_resolved_url": result.resolved_url,
                "source_text_method": result.extraction_method,
                "source_text_chars": result.text_chars,
                "source_evidence_hash": result.evidence_hash,
                "headline_similarity": result.headline_similarity,
                "source_published_date": result.source_published_date,
                "source_modified_date": result.source_modified_date,
                "grounding_reason": result.reason,
                "grounding_error": result.error,
            })
        if result_candidate is None:
            if row is not None:
                row["decision"] = "rejected_source_grounding"
                row["reason"] = result.reason or result.error or "underlying source did not establish the development"
            continue
        if row is not None:
            row["decision"] = "accepted"
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


def discover_domain(domain: str, *, as_of=None) -> tuple[list[dict], list[dict], list[FetchStatus]]:
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    policy = DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}
    days = max(int(policy.get("lookback_days", 7)), 1)
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
            float(item.get("rank_score", 0)),
            str(item.get("event_date", "")),
        ),
        reverse=True,
    )
    # Ground adaptively rather than giving up after an arbitrary first six.
    # High-cadence Market/Finance get a slightly larger request budget because
    # they encounter more paywalls, commentary, and duplicate coverage.
    max_items = max(1, min(int(policy.get("max_items", 2)), 2))
    target_grounded = min(4, max_items * 2)
    max_attempts = 12 if domain in {"market", "finance"} else 8
    grounded = _ground_domain_candidates(
        metadata_qualified,
        audit,
        domain=domain,
        target_grounded=target_grounded,
        max_attempts=max_attempts,
    )
    grounded.sort(
        key=lambda item: (
            float(item.get("rank_score", 0)),
            str(item.get("event_date", "")),
        ),
        reverse=True,
    )
    return grounded, audit, statuses


def _registry_row(event: dict, *, retrieved_at: str) -> dict:
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
        "expires_after_days": (DOMAIN_CONTEXT_POLICY.get(event.get("domain", ""), {}) or {}).get("lookback_days", 7),
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
    }


def merge_selected_into_registry(selected: dict[str, list[dict]], *, path=DEFAULT_EVENT_PATH, retrieved_at: str) -> int:
    path = Path(path)
    rows = [_registry_row(event, retrieved_at=retrieved_at) for events in selected.values() for event in events]
    if not rows:
        return 0

    with synchronized_path(path):
        existing = pd.read_csv(path) if path.exists() and path.stat().st_size > 0 else pd.DataFrame()
        additions = pd.DataFrame(rows)
        if not existing.empty and "event_id" in existing.columns:
            additions = additions.loc[~additions["event_id"].isin(existing["event_id"].astype(str))]
        if additions.empty:
            return 0
        columns = list(dict.fromkeys([*existing.columns.tolist(), *additions.columns.tolist()]))
        existing = existing.reindex(columns=columns)
        additions = additions.reindex(columns=columns)
        combined = pd.concat([existing, additions], ignore_index=True)
        atomic_write_csv(combined, path, lock=False)
        return len(additions)


def refresh_current_context(*, as_of=None, audit_path=DEFAULT_AUDIT_PATH, manifest_path=DEFAULT_MANIFEST_PATH, registry_path=DEFAULT_EVENT_PATH, merge_registry=True) -> dict:
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    accepted_by_domain: dict[str, list[dict]] = {domain: [] for domain in DOMAIN_KEYS}
    audit_rows: list[dict] = []
    fetch_statuses: list[FetchStatus] = []

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

    assigned = _assign_event_owners(accepted_by_domain)
    selected: dict[str, list[dict]] = {}
    selected_ids: set[str] = set()
    for domain in DOMAIN_KEYS:
        ranked = sorted(
            assigned.get(domain, []),
            key=lambda item: (float(item.get("rank_score", 0)), str(item.get("event_date", ""))),
            reverse=True,
        )
        max_items = max(1, min(int((DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}).get("max_items", 2)), 2))
        selected[domain] = _select_ranked_domain_events(ranked, max_items)
        selected_ids.update(str(item.get("event_id") or "") for item in selected[domain])

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

    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(pd.DataFrame(audit_rows), audit_path)

    added = 0
    if merge_registry:
        added = merge_selected_into_registry(selected, path=registry_path, retrieved_at=retrieved_at)

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
        grounding_by_domain[domain] = {
            "metadata_qualified": sum(1 for row in rows if str(row.get("event_id") or "").strip()),
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
        "qualified_count": sum(1 for row in audit_rows if str(row.get("decision", "")).startswith("accepted")),
        "grounding": {
            "version": GROUNDING_VERSION,
            "attempted": sum(1 for row in audit_rows if str(row.get("grounding_status", "")) in {"grounded", "rejected"}),
            "succeeded": sum(1 for row in audit_rows if str(row.get("grounding_status", "")) == "grounded"),
            "failed": sum(1 for row in audit_rows if str(row.get("grounding_status", "")) == "rejected"),
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
                }
                for event in events
            ]
            for domain, events in selected.items()
        },
        "registry_rows_added": added,
        "audit_path": str(audit_path),
        "registry_path": str(registry_path),
    }
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest, manifest_path)
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
