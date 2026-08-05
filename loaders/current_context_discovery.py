"""Auditable discovery pipeline for AI Macro Current Context.

This module is deliberately separate from rendering.  It discovers candidate
articles, records every acceptance/rejection decision, assigns each development
to one visible tab owner, and can merge selected records into the retained event
ledger.  The application therefore has a reproducible evidence trail rather
than an opaque "latest headline" call at render time.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import re
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    DOMAIN_LIVE_RELEVANCE,
    DOMAIN_NEWS_QUERIES,
    DOMAIN_NEWS_TERMS,
    assess_source,
    materiality_score,
)
from helpers.atomic_io import atomic_write_csv, atomic_write_json, synchronized_path
from loaders.weekly_context_loader import (
    DEFAULT_EVENT_PATH,
    DOMAIN_KEYS,
    NEWS_MAX_BYTES,
    NEWS_TIMEOUT_SECONDS,
    NEWS_USER_AGENT,
    _assign_live_event_owners,
    _clean_sentence,
    _domain_fit_score,
    _fetch_feed,
    _strip_source_suffix,
    _valid_https_url,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_PATH = ROOT / "data" / "current_context_candidate_audit.csv"
DEFAULT_MANIFEST_PATH = ROOT / "data" / "current_context_refresh_manifest.json"
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"
DISCOVERY_VERSION = "1.0"

_CANONICAL_SOURCE_NAMES = {
    "wsj.com": "The Wall Street Journal",
    "reuters.com": "Reuters",
    "apnews.com": "Associated Press",
    "bloomberg.com": "Bloomberg",
    "ft.com": "Financial Times",
    "barrons.com": "Barron's",
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


def _parse_gdelt_date(value) -> pd.Timestamp | None:
    text = re.sub(r"[^0-9]", "", str(value or ""))
    if len(text) < 8:
        return None
    for fmt, length in (("%Y%m%d%H%M%S", 14), ("%Y%m%d", 8)):
        try:
            stamp = pd.Timestamp(datetime.strptime(text[:length], fmt))
            return stamp.normalize()
        except (TypeError, ValueError):
            continue
    return None


def _gdelt_url(query: str, *, days: int) -> str:
    expression = f"({query}) sourcelang:english"
    params = {
        "query": expression,
        "mode": "ArtList",
        "maxrecords": "100",
        "format": "json",
        "sort": "HybridRel",
        "timespan": f"{max(int(days), 1)}d",
    }
    return GDELT_ENDPOINT + "?" + "&".join(f"{key}={quote_plus(value)}" for key, value in params.items())


def fetch_gdelt(query: str, *, days: int) -> tuple[list[dict], str]:
    """Fetch direct article URLs from GDELT's public document API."""
    request = Request(_gdelt_url(query, days=days), headers={"User-Agent": NEWS_USER_AGENT})
    try:
        with urlopen(request, timeout=max(NEWS_TIMEOUT_SECONDS, 6)) as response:
            payload = response.read(NEWS_MAX_BYTES + 1)
    except Exception as exc:  # network errors are audit data, not fatal app errors
        return [], f"{type(exc).__name__}: {exc}"
    if len(payload) > NEWS_MAX_BYTES:
        return [], "response exceeded byte limit"
    try:
        parsed = json.loads(payload.decode("utf-8", errors="replace"))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return [], f"invalid JSON: {exc}"

    items: list[dict] = []
    for article in parsed.get("articles", []) or []:
        url = str(article.get("url") or "").strip()
        title = " ".join(str(article.get("title") or "").split()).strip()
        published = _parse_gdelt_date(article.get("seendate"))
        if not title or not _valid_https_url(url) or published is None:
            continue
        source_name = _canonical_source_name(url)
        items.append({
            "title": title,
            "link": url,
            "published": published,
            "source_name": source_name,
            "source_url": f"https://{_host(url)}" if _host(url) else "",
            "description": "",
            "provider": "gdelt",
        })
    return items, ""


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
    materiality = float(materiality_score(text))
    relevance_matches = [term for term in DOMAIN_NEWS_TERMS.get(domain, ()) if str(term).casefold() in text.casefold()]
    fit = float(_domain_fit_score(text, domain))
    score = assessment.score + materiality + fit
    age_days = None
    decision = "rejected"
    reason = ""

    if published is None:
        reason = "missing publication date"
    else:
        published = pd.Timestamp(published).normalize()
        age_days = int((current - published).days)
        if age_days < 0 or age_days >= days:
            reason = "outside domain lookback window"
        elif not assessment.auto_eligible:
            reason = assessment.reason
        elif not relevance_matches:
            reason = "no domain relevance term"
        elif materiality <= 0:
            reason = "no material action, result, release, or status change"
        elif score < float(policy.get("minimum_score", 106.0)):
            reason = "below domain score threshold"
        elif not _valid_https_url(article_url):
            reason = "missing traceable HTTPS article URL"
        else:
            decision = "accepted"
            reason = "cleared source, relevance, materiality, freshness, and score gates"

    audit = {
        "audit_version": DISCOVERY_VERSION,
        "as_of": current.date().isoformat(),
        "domain_query": domain,
        "provider": provider,
        "query": DOMAIN_NEWS_QUERIES.get(domain, ""),
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
        "decision": decision,
        "reason": reason,
        "event_id": "",
        "owner_domain": "",
        "selected": False,
    }
    if decision != "accepted":
        return None, audit

    headline = _strip_source_suffix(title, source_name)
    digest = __import__("hashlib").sha1(f"{headline}|{article_url}".casefold().encode("utf-8")).hexdigest()[:12]
    event_id = f"auto-{published.date().isoformat()}-{digest}"
    candidate = {
        "event_id": event_id,
        "event_date": published.date().isoformat(),
        "domain": domain,
        "owner_domain": domain,
        "event_type": "reported_development",
        "priority": score,
        "verified_fact": _clean_sentence(f"{source_name} reports: {headline}"),
        "platform_relevance": _clean_sentence(DOMAIN_LIVE_RELEVANCE.get(domain, "")),
        "display": _clean_sentence(f"{source_name} reports: {headline}") + " " + _clean_sentence(DOMAIN_LIVE_RELEVANCE.get(domain, "")),
        "reference_number": 0,
        "source_name": source_name,
        "source_label": source_name,
        "source_url": article_url,
        "publisher_url": publisher_url,
        "source_type": "news",
        "source_tier": assessment.tier,
        "evidence_role": assessment.evidence_role,
        "verification_status": "reported",
        "status": "Reported",
        "legal_status": "",
        "resolution_status": "recent",
        "surface": "domain",
        "sectors": [],
        "tickers": [],
        "owner_score": score,
        "rank_score": score,
        "discovery_provider": provider,
        "discovery_query": DOMAIN_NEWS_QUERIES.get(domain, ""),
    }
    audit["event_id"] = event_id
    return candidate, audit


def discover_domain(domain: str, *, as_of=None) -> tuple[list[dict], list[dict], list[FetchStatus]]:
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    policy = DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}
    days = max(int(policy.get("lookback_days", 7)), 1)
    query = DOMAIN_NEWS_QUERIES.get(domain, domain.replace("_", " "))
    statuses: list[FetchStatus] = []

    gdelt_items, gdelt_error = fetch_gdelt(query, days=days)
    statuses.append(FetchStatus(domain, "gdelt", query, days, "ok" if not gdelt_error else "error", len(gdelt_items), gdelt_error))

    google_items: list[dict] = []
    google_error = ""
    # Google News is a fallback and supplemental discovery source.  The
    # publisher—not Google—is still assessed by the allowlist.
    try:
        google_items = _fetch_feed(query, days=days)
        for item in google_items:
            item["provider"] = "google_news_rss"
    except Exception as exc:
        google_error = f"{type(exc).__name__}: {exc}"
    statuses.append(FetchStatus(domain, "google_news_rss", query, days, "ok" if not google_error else "error", len(google_items), google_error))

    items = _dedupe_items(gdelt_items + google_items)
    accepted: list[dict] = []
    audit: list[dict] = []
    for item in items:
        provider = str(item.get("provider") or "unknown")
        candidate, record = evaluate_item(item, domain=domain, current=current, provider=provider)
        audit.append(record)
        if candidate is not None:
            accepted.append(candidate)
    accepted.sort(key=lambda item: (float(item.get("rank_score", 0)), str(item.get("event_date", ""))), reverse=True)
    return accepted, audit, statuses


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
        "source_type": "news",
        "verification_status": "reported",
        "expires_after_days": (DOMAIN_CONTEXT_POLICY.get(event.get("domain", ""), {}) or {}).get("lookback_days", 7),
        "surface": "domain",
        "sectors": "",
        "tickers": "",
        "status": "Reported",
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
                    DOMAIN_NEWS_QUERIES.get(domain, ""),
                    max(int(policy.get("lookback_days", 7)), 1),
                    "error",
                    0,
                    f"{type(exc).__name__}: {exc}",
                )]
            accepted_by_domain[domain].extend(accepted)
            audit_rows.extend(audit)
            fetch_statuses.extend(statuses)

    assigned = _assign_live_event_owners(accepted_by_domain)
    selected: dict[str, list[dict]] = {}
    selected_ids: set[str] = set()
    for domain in DOMAIN_KEYS:
        ranked = sorted(
            assigned.get(domain, []),
            key=lambda item: (float(item.get("rank_score", 0)), str(item.get("event_date", ""))),
            reverse=True,
        )
        selected[domain] = ranked[:1]
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
            row["reason"] = "qualified but ranked below the domain's selected development"

    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(pd.DataFrame(audit_rows), audit_path)

    added = 0
    if merge_registry:
        added = merge_selected_into_registry(selected, path=registry_path, retrieved_at=retrieved_at)

    manifest = {
        "discovery_version": DISCOVERY_VERSION,
        "as_of": current.date().isoformat(),
        "retrieved_at": retrieved_at,
        "providers": ["gdelt", "google_news_rss"],
        "domains": list(DOMAIN_KEYS),
        "fetch_status": [asdict(status) for status in fetch_statuses],
        "candidate_count": len(audit_rows),
        "qualified_count": sum(1 for row in audit_rows if str(row.get("decision", "")).startswith("accepted")),
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
