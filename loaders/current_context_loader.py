"""Stable read interface for the canonical Current Context registry.

All network discovery is owned by ``current_context_discovery``.  This loader
only resolves already-qualified registry records into domain and macro
surfaces, which keeps retained startup provider-free by construction.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from loaders.current_context_news import DOMAIN_KEYS, _assign_event_owners
from config.current_context_policy import current_context_tier_index
from loaders.current_context_registry import (
    DEFAULT_EVENT_PATH,
    _curated_events,
    _dedupe_events,
    _fallback_domain_event,
    _read_registry,
    _renumber_context,
    CURRENT_CONTEXT_READ_VERSION,
)


def _context_window_start(events: list[dict], current: pd.Timestamp) -> str:
    dates = pd.to_datetime(
        [event.get("event_date") for event in events if isinstance(event, dict) and event.get("event_date")],
        errors="coerce",
    )
    dates = dates[~pd.isna(dates)]
    if len(dates):
        return pd.Timestamp(dates.min()).date().isoformat()
    return (current - pd.Timedelta(days=6)).date().isoformat()


def _macro_ranked_events(events: list[dict], *, limit: int = 3) -> list[dict]:
    """Select the strongest macro headlines with simple diversity constraints."""
    ranked = [
        dict(event) for event in _dedupe_events(events)
        if str(event.get("verification_status") or event.get("status") or "").strip().lower() != "no_match"
    ]
    ranked.sort(
        key=lambda item: (
            -current_context_tier_index(item.get("qualification_tier", "A")),
            float(item.get("rank_score", item.get("priority", 0)) or 0),
            str(item.get("event_date", "")),
        ),
        reverse=True,
    )
    chosen: list[dict] = []
    domain_counts: dict[str, int] = {}
    market_finance = 0
    for event in ranked:
        domain = str(event.get("owner_domain") or event.get("domain") or "").strip().lower()
        if domain_counts.get(domain, 0) >= 2:
            continue
        if domain in {"market", "finance"} and market_finance >= 2:
            continue
        chosen.append(event)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        if domain in {"market", "finance"}:
            market_finance += 1
        if len(chosen) >= max(1, int(limit)):
            break
    return chosen


def load_current_context(*, as_of=None, path=None, limit_per_domain=2) -> dict:
    """Return up to two qualified developments per domain plus a diverse macro top three.

    Each event has exactly one visible tab owner.  The discovery engine writes
    qualified evidence into the supplied registry; this function never performs
    network retrieval and never creates a second qualification path.
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
            # Explicit registry ownership outranks accidental cross-domain term overlap.
            item["owner_score"] = float(item.get("rank_score", item.get("priority", 0)) or 0) + 1000.0
            domain_events[domain].append(item)

    # One source URL or canonical event may appear in only one subordinate Read.
    owned_events = _assign_event_owners(domain_events)

    by_domain: dict[str, dict] = {}
    all_events: list[dict] = []
    all_references: list[dict] = []
    limit = max(1, min(int(limit_per_domain), 2))
    for domain in DOMAIN_KEYS:
        selected = _dedupe_events(owned_events.get(domain, []))[:limit]
        if not selected:
            selected = [_fallback_domain_event(domain, current)]
        context = _renumber_context(selected, current, source="current-context registry")
        by_domain[domain] = context
        all_events.extend(context["events"])
        for reference in context["references"]:
            all_references.append({**reference, "domain": domain})

    macro_only = [
        event for event in curated
        if str(event.get("surface") or "").strip().lower() in {"macro", "both", "all"}
        and str(event.get("domain") or "").strip().lower() not in DOMAIN_KEYS
    ]
    macro_events = _macro_ranked_events(all_events + macro_only, limit=3)
    macro_context = _renumber_context(macro_events, current, source="current-context registry")
    return {
        "by_domain": by_domain,
        "events": macro_context["events"],
        "references": macro_context["references"],
        "as_of": current.date().isoformat(),
        "window_start": _context_window_start(macro_events, current),
        "source": "current-context registry",
        "version": CURRENT_CONTEXT_READ_VERSION,
        "macro_display_limit": 3,
    }



__all__ = ["DOMAIN_KEYS", "load_current_context"]
