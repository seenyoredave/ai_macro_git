from __future__ import annotations

from pathlib import Path
import re

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_POLICY,
    DOMAIN_CONTEXT_FALLBACK,
    CURRENT_CONTEXT_HARD_WINDOW_DAYS,
    current_context_qualification_policy,
    current_context_qualification_tier,
    domain_relevance_terms,
    domain_topic_anchors,
    assess_source_for_qualification,
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
    GROUNDING_VERSION,
    MIN_SOURCE_TEXT_CHARS,
    is_preview_or_calendar_item,
    retained_reader_quality_gate,
    strip_legacy_source_leadin,
)

ROOT = Path(__file__).resolve().parents[1]


DEFAULT_EVENT_PATH = ROOT / "data" / "weekly_context_events.csv"


CURRENT_CONTEXT_READ_VERSION = "3.3"


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
        "qualification_tier": "A",
        "qualification_tier_label": "Preferred",
        "effective_minimum_materiality": "",
        "topic_anchor_required": "",
        "minimum_source_text_chars": "",
        "minimum_anchor_score": "",
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
    """Revalidate a retained automated source under its recorded ladder tier."""
    if str(row.get("record_origin") or "").strip().casefold() != "automated_discovery":
        return False, "legacy_unproven", "none"
    source_name = str(row.get("source_name") or "").strip()
    source_url = str(row.get("source_url") or "").strip()
    provider = str(row.get("discovery_provider") or "").strip()
    tier_key = str(row.get("qualification_tier") or "A").strip().upper()
    assessment = assess_source_for_qualification(
        source_name, source_url, source_url, provider=provider, tier_key=tier_key
    )
    source_type = str(row.get("source_type") or "").strip().lower()
    verification = str(row.get("verification_status") or "").strip().lower()
    stored_tier = str(row.get("source_tier") or assessment.tier or "").strip()
    stored_role = str(row.get("evidence_role") or assessment.evidence_role or "").strip()

    if not assessment.auto_eligible:
        return False, assessment.tier, assessment.evidence_role
    if source_type in {"primary", "official_statement"} and verification in {"primary", "confirmed", "corroborated"}:
        return True, stored_tier or assessment.tier, stored_role or "official_statement"
    if source_type == "company_statement" and verification in {"company_statement", "confirmed", "corroborated"}:
        return True, stored_tier or assessment.tier, "company_statement"
    if source_type == "news" and verification in {"reported", "independently_retrieved", "confirmed", "corroborated"}:
        return True, stored_tier or assessment.tier, stored_role or "secondary"
    return False, assessment.tier, assessment.evidence_role


def _row_is_temporally_valid(row: dict, current: pd.Timestamp) -> bool:
    date = row.get("event_date")
    if pd.isna(date) or date > current:
        return False
    expiration = pd.to_numeric(row.get("expires_after_days"), errors="coerce")
    if pd.isna(expiration):
        expiration = 7
    # Current Context is a news window, not an unresolved-event archive. Even a
    # still-open action must age out of the Reader surface at the ten-day hard
    # ceiling and can re-enter only through a newly grounded current development.
    expiration = max(1, min(int(expiration), CURRENT_CONTEXT_HARD_WINDOW_DAYS))
    age = int((current - pd.Timestamp(date)).days)
    return 0 <= age < expiration


def _automated_row_still_qualifies(row: dict) -> bool:
    """Require modern source-grounding provenance and reapply its recorded tier.

    Current Context is intentionally independent of manually retained analytical
    data.  Legacy curated/snapshot rows are therefore not Reader-eligible.
    """
    if str(row.get("record_origin") or "").strip().casefold() != "automated_discovery":
        return False
    if str(row.get("grounding_status") or "").strip().casefold() != "grounded":
        return False
    # Event reconstruction is a durable Reader-quality contract.  Rows grounded
    # by an older reconstruction engine are retained in the audit history but
    # are re-grounded before they may re-enter the live Reader surface.
    if str(row.get("grounding_version") or "").strip() != GROUNDING_VERSION:
        return False
    if not str(row.get("source_evidence_hash") or "").strip():
        return False
    if not str(row.get("retrieved_at") or "").strip():
        return False
    if not str(row.get("source_text_method") or "").strip():
        return False

    domain = str(row.get("domain") or "").strip().casefold()
    tier_key = str(row.get("qualification_tier") or "A").strip().upper()
    policy = current_context_qualification_policy(domain, tier_key)
    source_chars = pd.to_numeric(row.get("source_text_chars"), errors="coerce")
    minimum_chars = int(policy.get("minimum_source_text_chars", 220) or 220)
    if pd.isna(source_chars) or int(source_chars) < minimum_chars:
        return False

    fact = strip_legacy_source_leadin(row.get("verified_fact"), row.get("source_name"))
    if is_preview_or_calendar_item(fact):
        return False
    terms = domain_relevance_terms(domain)
    if terms and not any(term_present(fact, term) for term in terms):
        return False
    anchors = domain_topic_anchors(domain)
    if bool(policy.get("require_topic_anchor", True)) and anchors and not any(term_present(fact, term) for term in anchors):
        if domain not in {"grid_storage", "water"}:
            return False
    if materiality_score(fact, domain) < float(policy.get("minimum_materiality", 0.0001)):
        return False
    lookback_days = int(policy.get("lookback_days", 7) or 7)
    quality_ok, _ = retained_reader_quality_gate(
        domain, fact, "", event_date=row.get("event_date"), lookback_days=lookback_days
    )
    return bool(quality_ok)


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
        relevance = ""
        if recent_development_copy_issues(fact):
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
            "display": fact,
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
            "qualification_tier": str(row.get("qualification_tier") or "A").strip().upper(),
            "qualification_tier_label": str(row.get("qualification_tier_label") or current_context_qualification_tier(row.get("qualification_tier") or "A").label).strip(),
            "effective_minimum_materiality": float(pd.to_numeric(row.get("effective_minimum_materiality"), errors="coerce")) if not pd.isna(pd.to_numeric(row.get("effective_minimum_materiality"), errors="coerce")) else float(current_context_qualification_policy(str(row.get("domain") or ""), row.get("qualification_tier") or "A").get("minimum_materiality", 0.0)),
        })
    return events


_EVENT_DEDUPE_STOPWORDS = {
    "about", "after", "against", "also", "among", "announced", "company", "data",
    "development", "from", "into", "million", "billion", "new", "reported",
    "said", "that", "the", "their", "this", "through", "with", "year", "years",
    "artificial", "intelligence", "center", "centers", "market", "markets",
    "nan", "shares", "rose", "fell", "revenue", "guidance", "earnings",
}


def _event_identity_tokens(event: dict) -> set[str]:
    text = " ".join(str(event.get(key) or "") for key in ("source_title", "verified_fact"))
    tokens = {
        token.casefold()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9'’-]{2,}|\d+(?:\.\d+)?", text)
        if token.casefold() not in _EVENT_DEDUPE_STOPWORDS
    }
    return tokens


def _same_reported_event(left: dict, right: dict) -> bool:
    if str(left.get("domain") or "") != str(right.get("domain") or ""):
        return False
    left_url = str(left.get("source_url") or "").strip().casefold()
    right_url = str(right.get("source_url") or "").strip().casefold()
    if left_url and left_url == right_url:
        return True
    try:
        left_date = pd.Timestamp(left.get("event_date")).normalize()
        right_date = pd.Timestamp(right.get("event_date")).normalize()
        if abs(int((left_date - right_date).days)) > 2:
            return False
    except Exception:
        pass
    left_tokens = _event_identity_tokens(left)
    right_tokens = _event_identity_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    shared = left_tokens & right_tokens
    union = left_tokens | right_tokens
    jaccard = len(shared) / max(len(union), 1)
    # Cross-publisher rewrites of the same event often share a company/project
    # name and transaction magnitude while otherwise using different prose.
    return (len(shared) >= 4 and jaccard >= 0.24) or (len(shared) >= 6 and jaccard >= 0.18)


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
        if any(_same_reported_event(event, prior) for prior in chosen):
            continue
        chosen.append(dict(event))
        if event_id:
            seen_ids.add(event_id)
        if title_key:
            seen_titles.add(title_key)
    return chosen


def _context_window_start(events: list[dict], current: pd.Timestamp) -> str:
    dates = pd.to_datetime(
        [event.get("event_date") for event in events if isinstance(event, dict) and event.get("event_date")],
        errors="coerce",
    )
    dates = dates[~pd.isna(dates)]
    if len(dates):
        return pd.Timestamp(dates.min()).date().isoformat()
    return (current - pd.Timedelta(days=6)).date().isoformat()


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
        "window_start": _context_window_start(numbered_events, current),
        "source": source,
        "version": CURRENT_CONTEXT_READ_VERSION,
    }


