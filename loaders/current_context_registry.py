from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import re

import pandas as pd

from config.current_context_policy import (
    DOMAIN_CONTEXT_FALLBACK,
    assess_source,
    recent_development_copy_issues,
)
from config.sector_config import SECTOR_CONFIG
from loaders.current_context_news import (
    _bool,
    _clean_sentence,
    _fetch_live_sector_event,
    _valid_https_url,
)

ROOT = Path(__file__).resolve().parents[1]


DEFAULT_EVENT_PATH = ROOT / "data" / "weekly_context_events.csv"


WEEKLY_CONTEXT_VERSION = "2.1"


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


NO_QUALIFYING_NEWS = "No qualifying sector-specific headline was identified in the last seven days."


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
