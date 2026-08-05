"""Stable public interface for retained and daily Current Context data."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from loaders.current_context_news import (
    DOMAIN_KEYS,
    NEWS_MAX_BYTES,
    NEWS_RSS_ENDPOINT,
    NEWS_TIMEOUT_SECONDS,
    NEWS_USER_AGENT,
    SECTOR_NEWS_QUERIES,
    SECTOR_NEWS_TERMS,
    _EVENT_STOPWORDS,
    _assign_live_event_owners,
    _bool,
    _canonical_event_key,
    _clean_sentence,
    _domain_fit_score,
    _event_tokens,
    _feed_url,
    _fetch_feed,
    _fetch_live_domain_candidates,
    _fetch_live_sector_event,
    _live_candidate,
    _news_item_matches,
    _parse_google_news_rss,
    _parse_news_date,
    _same_development,
    _strip_source_suffix,
    _text_matches,
    _valid_https_url,
)
from loaders.current_context_registry import (
    DEFAULT_EVENT_PATH,
    NO_QUALIFYING_NEWS,
    REQUIRED_COLUMNS,
    ROOT,
    WEEKLY_CONTEXT_VERSION,
    _complete_sector_context,
    _curated_events,
    _curated_source_allowed,
    _dedupe_events,
    _event_valid_for_sector,
    _fallback_domain_event,
    _fallback_sector_event,
    _read_registry,
    _renumber_context,
    _row_is_temporally_valid,
)

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


__all__ = [name for name in globals() if not name.startswith("__")]
