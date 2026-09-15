"""Compact developer-facing views over verbose runtime reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ContextDomainStatus:
    domain: str
    discovered: int = 0
    metadata_qualified: int = 0
    approved_evidence_candidates: int = 0
    approved_source_sweep_candidates: int = 0
    preground_unique_candidates: int = 0
    preground_duplicates_clustered: int = 0
    preground_retained_duplicates_skipped: int = 0
    discovery_leads: int = 0
    discovery_leads_resolved: int = 0
    attempted: int = 0
    grounded: int = 0
    alternate_grounded: int = 0
    trusted_headline_grounded: int = 0
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
    approved_evidence_candidates: int
    approved_source_sweep_candidates: int
    approved_source_sweep_grounded: int
    preground_unique_candidates: int
    preground_duplicates_clustered: int
    preground_retained_duplicates_skipped: int
    attempted: int
    grounded: int
    trusted_headline_grounded: int
    discovery_leads: int
    discovery_leads_resolved: int
    unique_grounded_after_dedup: int
    qualified: int
    selected: int
    rendered: int
    continuity_attempted: int
    continuity_recovered: int
    continuity_selected: int
    engine_mismatch: bool
    refresh_required: bool
    domains: tuple[ContextDomainStatus, ...]
    grounding_rejections: tuple[dict[str, Any], ...]
    provider_errors: tuple[dict[str, Any], ...]
    coverage_selected_domains: int
    coverage_tier_reached: str
    coverage_tier_label: str
    expanded_qualification: bool
    selected_domains_by_tier: tuple[tuple[str, int], ...]
    selected_events_by_tier: tuple[tuple[str, int], ...]
    preferred_window_days: int
    hard_window_days: int
    selection_target_min: int
    selection_target_max: int


def current_context_status(report: dict | None) -> CurrentContextStatus:
    payload = dict(report or {})
    grounding = dict(payload.get("grounding") or {})
    by_domain = grounding.get("by_domain") or {}
    selected_counts = payload.get("fresh_selected_counts") or payload.get("selected_counts") or {
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
            approved_evidence_candidates=int(row.get("approved_evidence_candidates", 0) or 0),
            approved_source_sweep_candidates=int(row.get("approved_source_sweep_candidates", 0) or 0),
            preground_unique_candidates=int(row.get("preground_unique_candidates", 0) or 0),
            preground_duplicates_clustered=int(row.get("preground_duplicates_clustered", 0) or 0),
            preground_retained_duplicates_skipped=int(row.get("preground_retained_duplicates_skipped", 0) or 0),
            discovery_leads=int(row.get("discovery_leads", 0) or 0),
            discovery_leads_resolved=int(row.get("discovery_leads_resolved", 0) or 0),
            attempted=int(row.get("attempted", 0) or 0),
            grounded=int(row.get("succeeded", 0) or 0),
            alternate_grounded=int(row.get("alternate_source_grounded", 0) or 0),
            trusted_headline_grounded=int(row.get("trusted_headline_grounded", 0) or 0),
            selected=int(selected_counts.get(domain, row.get("selected", 0)) or 0),
            rendered=int(rendered_counts.get(domain, 0) or 0),
        )
        if any((status.discovered, status.metadata_qualified, status.attempted, status.grounded, status.selected, status.rendered)):
            domain_rows.append(status)
    if not metadata_total:
        metadata_total = int(payload.get("metadata_qualified_count", 0) or 0)
    selected_total = sum(int(value or 0) for value in selected_counts.values())
    rendered_total = sum(int(value or 0) for value in rendered_counts.values())
    coverage = dict(payload.get("coverage") or {})
    continuity = dict(payload.get("continuity") or {})
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
        approved_evidence_candidates=int(grounding.get("approved_evidence_candidates", 0) or 0),
        approved_source_sweep_candidates=int(grounding.get("approved_source_sweep_candidates", 0) or 0),
        approved_source_sweep_grounded=int(grounding.get("approved_source_sweep_grounded", 0) or 0),
        preground_unique_candidates=int(grounding.get("preground_unique_candidates", 0) or 0),
        preground_duplicates_clustered=int(grounding.get("preground_duplicates_clustered", 0) or 0),
        preground_retained_duplicates_skipped=int(grounding.get("preground_retained_duplicates_skipped", 0) or 0),
        attempted=int(grounding.get("attempted", 0) or 0),
        grounded=int(grounding.get("succeeded", 0) or 0),
        trusted_headline_grounded=int(grounding.get("trusted_headline_grounded", 0) or 0),
        discovery_leads=int(grounding.get("discovery_leads", 0) or 0),
        discovery_leads_resolved=int(grounding.get("discovery_leads_resolved", 0) or 0),
        unique_grounded_after_dedup=int(grounding.get("unique_grounded_after_dedup", 0) or 0),
        qualified=int(payload.get("qualified_count", 0) or 0),
        selected=selected_total,
        rendered=rendered_total,
        continuity_attempted=int(continuity.get("attempted", 0) or 0),
        continuity_recovered=int(continuity.get("recovered", 0) or 0),
        continuity_selected=int(continuity.get("selected", 0) or 0),
        engine_mismatch=bool(payload.get("engine_mismatch")),
        refresh_required=bool(payload.get("refresh_required")),
        domains=tuple(domain_rows),
        grounding_rejections=tuple(item for item in (grounding.get("rejection_reasons") or []) if isinstance(item, dict)),
        provider_errors=tuple(item for item in fetch_errors if isinstance(item, dict)),
        coverage_selected_domains=int(coverage.get("selected_domain_count", 0) or 0),
        coverage_tier_reached=str(coverage.get("tier_reached") or "A"),
        coverage_tier_label=str(coverage.get("tier_reached_label") or "Preferred"),
        expanded_qualification=bool(coverage.get("expanded_discovery_required", False)),
        selected_domains_by_tier=tuple(
            (str(key), int(value or 0)) for key, value in (coverage.get("selected_domains_by_tier") or {}).items()
        ),
        selected_events_by_tier=tuple(
            (str(key), int(value or 0)) for key, value in (coverage.get("selected_events_by_tier") or {}).items()
        ),
        preferred_window_days=int(coverage.get("preferred_window_days", 7) or 7),
        hard_window_days=int(coverage.get("hard_window_days", 10) or 10),
        selection_target_min=int(coverage.get("selection_target_min", 10) or 10),
        selection_target_max=int(coverage.get("selection_target_max", 15) or 15),
    )


def format_seconds(value: Any) -> str:
    try:
        return f"{float(value):.2f}s"
    except (TypeError, ValueError):
        return "n/a"
