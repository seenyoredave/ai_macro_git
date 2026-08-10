"""Stable read interface for the canonical Current Context registry.

All network discovery is owned by ``current_context_discovery``.  This loader
only resolves already-qualified registry records into domain, sector, and macro
surfaces, which keeps retained startup provider-free by construction.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from loaders.current_context_news import DOMAIN_KEYS, _assign_event_owners
from loaders.current_context_registry import (
    DEFAULT_EVENT_PATH,
    NO_QUALIFYING_NEWS,
    _complete_sector_context,
    _curated_events,
    _dedupe_events,
    _fallback_domain_event,
    _read_registry,
    _renumber_context,
)


def load_current_context(*, as_of=None, path=None, limit_per_domain=2) -> dict:
    """Return zero, one, or two qualified developments for every domain.

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
    return {
        "by_domain": by_domain,
        "events": _dedupe_events(all_events + macro_only),
        "references": all_references,
        "as_of": current.date().isoformat(),
        "window_start": (current - pd.Timedelta(days=6)).date().isoformat(),
        "source": "current-context registry",
        "version": "2.3",
    }


def load_weekly_context(*, as_of=None, path=None, limit=3, surface="macro"):
    """Resolve macro or Sector Dossier context from the same qualified registry."""
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    frame = _read_registry(Path(path or DEFAULT_EVENT_PATH))
    curated = _curated_events(frame, current)
    surface_value = str(surface or "macro").strip().lower()

    if surface_value == "sector":
        base = [
            event for event in curated
            if str(event.get("surface") or "").strip().lower() in {"sector", "both", "all"}
        ]
        return _complete_sector_context(base, current)

    if surface_value == "domain":
        return load_current_context(
            as_of=current,
            path=path,
            limit_per_domain=min(max(int(limit), 1), 2),
        )

    candidates = [
        event for event in curated
        if str(event.get("surface") or "").strip().lower() in {surface_value, "both", "all"}
    ]
    selected = _dedupe_events(candidates)[: max(0, int(limit))]
    return _renumber_context(selected, current, source="current-context registry")


__all__ = ["DOMAIN_KEYS", "NO_QUALIFYING_NEWS", "load_current_context", "load_weekly_context"]
