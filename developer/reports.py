"""Compact developer-facing views over verbose runtime reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContextDomainStatus:
    domain: str
    discovered: int = 0
    metadata_qualified: int = 0
    attempted: int = 0
    grounded: int = 0
    alternate_grounded: int = 0
    selected: int = 0
    rendered: int = 0


@dataclass(frozen=True, slots=True)
class CurrentContextStatus:
    source_mode: str
    engine_version: str
    retained_version: str
    snapshot_id: str
    as_of: str
    discovered: int
    metadata_qualified: int
    attempted: int
    grounded: int
    qualified: int
    selected: int
    rendered: int
    engine_mismatch: bool
    refresh_required: bool
    domains: tuple[ContextDomainStatus, ...]
    grounding_rejections: tuple[dict[str, Any], ...]
    provider_errors: tuple[dict[str, Any], ...]


def current_context_status(report: dict | None) -> CurrentContextStatus:
    payload = dict(report or {})
    grounding = dict(payload.get("grounding") or {})
    by_domain = grounding.get("by_domain") or {}
    selected_counts = payload.get("selected_counts") or {
        domain: len(items) if isinstance(items, list) else 0
        for domain, items in (payload.get("selected") or {}).items()
    }
    rendered_counts = payload.get("rendered_context_counts") or {}
    domain_rows: list[ContextDomainStatus] = []
    metadata_total = 0
    for domain, row in by_domain.items():
        if not isinstance(row, dict):
            continue
        metadata = int(row.get("metadata_qualified", 0) or 0)
        metadata_total += metadata
        status = ContextDomainStatus(
            domain=str(domain),
            discovered=int(row.get("discovered", 0) or 0),
            metadata_qualified=metadata,
            attempted=int(row.get("attempted", 0) or 0),
            grounded=int(row.get("succeeded", 0) or 0),
            alternate_grounded=int(row.get("alternate_source_grounded", 0) or 0),
            selected=int(selected_counts.get(domain, row.get("selected", 0)) or 0),
            rendered=int(rendered_counts.get(domain, 0) or 0),
        )
        if any((status.discovered, status.metadata_qualified, status.attempted, status.grounded, status.selected, status.rendered)):
            domain_rows.append(status)
    if not metadata_total:
        metadata_total = int(payload.get("metadata_qualified_count", 0) or 0)
    selected_total = sum(int(value or 0) for value in selected_counts.values())
    rendered_total = sum(int(value or 0) for value in rendered_counts.values())
    fetch_errors = payload.get("fetch_errors") or [
        row for row in (payload.get("fetch_status") or [])
        if isinstance(row, dict) and str(row.get("error") or "").strip()
    ]
    return CurrentContextStatus(
        source_mode=str(payload.get("source_mode") or payload.get("refresh_status") or "unknown"),
        engine_version=str(payload.get("engine_version") or "unknown"),
        retained_version=str(payload.get("retained_discovery_version") or payload.get("discovery_version") or "unknown"),
        snapshot_id=str(payload.get("snapshot_id") or payload.get("context_packet_id") or ""),
        as_of=str(payload.get("as_of") or ""),
        discovered=int(payload.get("candidate_count", 0) or 0),
        metadata_qualified=metadata_total,
        attempted=int(grounding.get("attempted", 0) or 0),
        grounded=int(grounding.get("succeeded", 0) or 0),
        qualified=int(payload.get("qualified_count", 0) or 0),
        selected=selected_total,
        rendered=rendered_total,
        engine_mismatch=bool(payload.get("engine_mismatch")),
        refresh_required=bool(payload.get("refresh_required")),
        domains=tuple(domain_rows),
        grounding_rejections=tuple(item for item in (grounding.get("rejection_reasons") or []) if isinstance(item, dict)),
        provider_errors=tuple(item for item in fetch_errors if isinstance(item, dict)),
    )


def format_seconds(value: Any) -> str:
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return "n/a"
