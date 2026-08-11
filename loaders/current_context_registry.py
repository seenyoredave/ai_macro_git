from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    DOMAIN_CONTEXT_FALLBACK,
    domain_relevance_terms,
    domain_topic_anchors,
    assess_source,
    materiality_score,
    recent_development_copy_issues,
    term_present,
)
from helpers.atomic_io import synchronized_path
from loaders.current_context_news import (
    _bool,
    _clean_sentence,
    _valid_https_url,
)
from loaders.current_context_grounding import (
    MIN_SOURCE_TEXT_CHARS,
    is_preview_or_calendar_item,
    retained_reader_quality_gate,
    strip_legacy_source_leadin,
)

ROOT = Path(__file__).resolve().parents[1]


DEFAULT_EVENT_PATH = ROOT / "data" / "weekly_context_events.csv"


CURRENT_CONTEXT_READ_VERSION = "2.8"


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
    transaction_key = path.parent / ".current_context_refresh"
    with synchronized_path(transaction_key):
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
        "discovered_via": "",
        "discovery_source_url": "",
        "evidence_resolution_mode": "",
        "evidence_seed_source_name": "",
        "evidence_seed_source_url": "",
        "evidence_resolution_query": "",
        "evidence_resolution_similarity": "",
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

    # The event registry is a current-state store, not the audit ledger. If an
    # older release left multiple rows for one event_id, use the most recently
    # retrieved row. Engine/grounding version is provenance; it is not freshness.
    # Full discovery history lives in current_context_candidate_audit.csv.
    if "event_id" in frame.columns and not frame.empty:
        retrieved = pd.to_datetime(frame.get("retrieved_at", ""), errors="coerce", utc=True)
        frame["_retrieved_order"] = retrieved
        frame["_row_order"] = range(len(frame))
        frame = (
            frame.sort_values(
                ["event_id", "_retrieved_order", "_row_order"],
                na_position="first",
            )
            .drop_duplicates(subset=["event_id"], keep="last")
            .drop(columns=["_retrieved_order", "_row_order"])
            .reset_index(drop=True)
        )
    return frame


def _curated_source_allowed(row: dict) -> tuple[bool, str, str]:
    """Apply the same evidence-status contract on retained reload as discovery.

    Automated discovery records provenance states such as ``reported``,
    ``primary``, ``company_statement`` and ``independently_retrieved``.  The
    registry loader preserves those qualified states and applies the same
    evidence boundary on every reload.
    """
    source_name = str(row.get("source_name") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    assessment = assess_source(source_name, source_url, source_url)
    source_type = str(row.get("source_type") or "").strip().lower()
    verification = str(row.get("verification_status") or "").strip().lower()
    stored_tier = str(row.get("source_tier") or assessment.tier or "").strip()
    stored_role = str(row.get("evidence_role") or assessment.evidence_role or "").strip()

    if assessment.tier in {"blocked", "blocked_social", "discovery_only"}:
        return False, assessment.tier, assessment.evidence_role
    if assessment.tier == "manual_review" and verification != "corroborated":
        return False, assessment.tier, assessment.evidence_role

    # Curated primary records may include official corporate investor releases
    # not present on the unattended-news allowlist.  Automated institutional
    # records use source_type=official_statement and verification=primary.
    if source_type in {"primary", "official_statement"} and verification in {
        "confirmed", "corroborated", "primary"
    }:
        return True, stored_tier or "primary", stored_role or "official_statement"

    # Issuer-distributed releases are evidence of what the issuer said, not
    # independent journalism.  Preserve that bounded role across persistence.
    if source_type == "company_statement" and verification in {
        "confirmed", "corroborated", "company_statement"
    } and (assessment.auto_eligible or stored_role == "company_statement"):
        return True, stored_tier or assessment.tier, "company_statement"

    # Approved journalism may be a legacy curated confirmation, an unattended
    # reported item, or a Tier-2 lead that was independently rediscovered.
    if source_type == "news" and verification in {
        "confirmed", "corroborated", "reported", "independently_retrieved"
    } and assessment.auto_eligible:
        return True, stored_tier or assessment.tier, stored_role or assessment.evidence_role

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


def _automated_row_still_qualifies(row: dict) -> bool:
    """Revalidate automated rows against the durable evidence contract.

    Grounding/discovery versions are provenance, not expiration controls. Once
    an automated row has actually been source-grounded, carries an evidence
    hash, and remains temporally/materially eligible, a later engine version
    must not make that vetted fact disappear. Pre-grounding headline-derived
    rows fail this contract because they lack the grounded evidence fields.
    """
    if str(row.get("record_origin") or "").strip().casefold() != "automated_discovery":
        return True
    if str(row.get("grounding_status") or "").strip().casefold() != "grounded":
        return False
    if not str(row.get("source_evidence_hash") or "").strip():
        return False
    source_chars = pd.to_numeric(row.get("source_text_chars"), errors="coerce")
    if pd.isna(source_chars) or int(source_chars) < MIN_SOURCE_TEXT_CHARS:
        return False

    domain = str(row.get("domain") or "").strip().casefold()
    fact = strip_legacy_source_leadin(row.get("verified_fact"), row.get("source_name"))
    relevance = str(row.get("platform_relevance") or "")
    text = f"{fact} {relevance}".strip()
    if is_preview_or_calendar_item(fact):
        return False
    terms = domain_relevance_terms(domain)
    if terms and not any(term_present(text, term) for term in terms):
        return False
    anchors = domain_topic_anchors(domain)
    if anchors and not any(term_present(text, term) for term in anchors):
        # Source-grounded Grid/Water system constraints may legitimately omit an
        # AI token in the final compact prose while still affecting the platform.
        if domain not in {"grid_storage", "water"}:
            return False
    minimum = float((DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}).get("minimum_materiality", 0.0001))
    if materiality_score(text, domain) < minimum:
        return False
    lookback_days = int((DOMAIN_CONTEXT_POLICY.get(domain, {}) or {}).get("lookback_days", 7) or 7)
    quality_ok, _ = retained_reader_quality_gate(
        domain, fact, relevance, event_date=row.get("event_date"), lookback_days=lookback_days
    )
    if not quality_ok:
        return False
    return True


def _curated_events(frame: pd.DataFrame, current: pd.Timestamp) -> list[dict]:
    events: list[dict] = []
    if frame.empty:
        return events
    for row in frame.to_dict("records"):
        if pd.isna(row.get("priority")) or not _row_is_temporally_valid(row, current):
            continue
        if not _automated_row_still_qualifies(row):
            continue
        if not _valid_https_url(row.get("source_url")):
            continue
        allowed, tier, evidence_role = _curated_source_allowed(row)
        if not allowed:
            continue
        fact = _clean_sentence(row.get("verified_fact"))
        relevance = _clean_sentence(row.get("platform_relevance"))
        if recent_development_copy_issues(f"{fact} {relevance}"):
            continue
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
            "discovered_via": str(row.get("discovered_via") or "").strip(),
            "discovery_source_url": str(row.get("discovery_source_url") or "").strip(),
            "grounding_version": str(row.get("grounding_version") or "").strip(),
            "grounding_status": str(row.get("grounding_status") or "").strip(),
            "source_resolved_url": str(row.get("source_resolved_url") or row.get("source_url") or "").strip(),
            "source_text_method": str(row.get("source_text_method") or "").strip(),
            "source_text_chars": int(float(row.get("source_text_chars") or 0)) if str(row.get("source_text_chars") or "").strip() not in {"", "nan"} else 0,
            "source_evidence_hash": str(row.get("source_evidence_hash") or "").strip(),
            "source_title": str(row.get("source_title") or "").strip(),
            "source_published_date": str(row.get("source_published_date") or "").strip(),
            "source_modified_date": str(row.get("source_modified_date") or "").strip(),
            "evidence_resolution_mode": str(row.get("evidence_resolution_mode") or "").strip(),
            "evidence_seed_source_name": str(row.get("evidence_seed_source_name") or "").strip(),
            "evidence_seed_source_url": str(row.get("evidence_seed_source_url") or "").strip(),
            "evidence_resolution_query": str(row.get("evidence_resolution_query") or "").strip(),
            "evidence_resolution_similarity": str(row.get("evidence_resolution_similarity") or "").strip(),
        })
    return events


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
                    "grounding_version": item.get("grounding_version", ""),
                    "grounding_status": item.get("grounding_status", ""),
                    "source_evidence_hash": item.get("source_evidence_hash", ""),
                })
        item["reference_number"] = number
        numbered_events.append(item)
    return {
        "events": numbered_events,
        "references": references,
        "as_of": current.date().isoformat(),
        "window_start": (current - pd.Timedelta(days=6)).date().isoformat(),
        "source": source,
        "version": CURRENT_CONTEXT_READ_VERSION,
    }


