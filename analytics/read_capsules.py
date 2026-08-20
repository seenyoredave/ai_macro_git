"""Compact, trajectory-aware evidence capsules for one-call editorial synthesis.

The deterministic application remains responsible for measurement, arithmetic,
provenance, and change detection.  This module only reduces that finished state
into a bounded model-facing representation; it never writes analytical prose.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import math
from typing import Any

from analytics.read_evidence import DOMAIN_LABELS, DOMAIN_ORDER

CAPSULE_ARCHITECTURE_VERSION = "1.0.0"
EVALUATED_STATE_VERSION = "1.0.0"
MAX_FACTS_PER_DOMAIN_CAPSULE = 4
MAX_SUPPLEMENTAL_CAPSULES = 4
MAX_HISTORY_OBSERVATIONS = 4

LIFECYCLE_STAGE = {
    "market": "capital_and_markets",
    "finance": "capital_and_markets",
    "compute": "physical_buildout",
    "data_center": "physical_buildout",
    "connectivity": "physical_buildout",
    "power": "physical_buildout",
    "grid_storage": "physical_buildout",
    "water": "physical_buildout",
    "adoption": "use_and_diffusion",
    "workforce": "realized_outcomes",
    "economic_impact": "realized_outcomes",
}

# These are stable orientation signals, not deterministic conclusions. Material
# changes always take priority over anchors when a capsule is assembled.
DOMAIN_ANCHORS: dict[str, tuple[str, ...]] = {
    "market": ("market.aei", "market.positive_breadth", "market.top_10_share"),
    "finance": (
        "finance.internal_funding_coverage",
        "finance.forward_commitment_load",
        "finance.borrower_strain",
    ),
    "compute": (
        "compute.semiconductor_output_growth",
        "compute.project_capex_b",
        "compute.core_ai_capex_b",
    ),
    "data_center": (
        "data_center.development_to_operating",
        "data_center.pipeline_capacity_gw",
        "data_center.published_capacity_coverage",
    ),
    "connectivity": (
        "connectivity.active_ixps",
        "connectivity.middle_mile_new_fiber_miles",
        "connectivity.high_capacity_low_public_connectivity_states",
    ),
    "power": ("power.demand_growth", "power.planned_net_gw", "power.large_load_capacity_mw"),
    "grid_storage": (
        "grid_storage.queue_gw",
        "grid_storage.advanced_share",
        "grid_storage.historical_operational_pct",
    ),
    "water": (
        "water.campuses_in_counties_with_25pct_d2_share_pct",
        "water.direct_evidence_share_pct",
        "water.published_capacity_in_counties_with_25pct_d2_gw",
    ),
    "adoption": (
        "adoption.current_business_use_pct",
        "adoption.expected_adoption_gap_ppts",
        "adoption.function_le3_share_pct",
    ),
    "workforce": (
        "workforce.employment_breadth",
        "workforce.weakest_channel_growth",
        "workforce.median_llm_software_exposure_pct",
    ),
    "economic_impact": (
        "economic_impact.productivity_growth",
        "economic_impact.real_compensation_growth",
        "economic_impact.productivity_real_comp_gap",
    ),
}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _facts(packets: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for packet in packets.values():
        if not isinstance(packet, dict):
            continue
        for fact in packet.get("facts", []) or []:
            if isinstance(fact, dict) and fact.get("id"):
                output[str(fact["id"])] = dict(fact)
    return output


def _change_index(materiality: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(change.get("fact_id")): dict(change)
        for change in (materiality.get("changes") or [])
        if isinstance(change, dict) and change.get("fact_id")
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _change_score(change: dict[str, Any]) -> tuple[int, float]:
    material = int(bool(change.get("material")))
    relative = abs(_number(change.get("relative_change")) or 0.0)
    points = abs(_number(change.get("percentage_point_change")) or 0.0) / 10.0
    categorical = 2.0 if str(change.get("kind") or "") != "numeric_change" else 0.0
    return material, relative + points + categorical


def materially_changed_domains(materiality: dict[str, Any]) -> list[str]:
    domains: list[str] = []
    for change in materiality.get("changes", []) or []:
        if not isinstance(change, dict) or not change.get("material"):
            continue
        domain = str(change.get("domain") or str(change.get("fact_id") or "").split(".", 1)[0])
        if domain in DOMAIN_ORDER and domain not in domains:
            domains.append(domain)
    return [domain for domain in DOMAIN_ORDER if domain in domains]


def changed_fact_ids(materiality: dict[str, Any], *, material_only: bool = False) -> set[str]:
    output: set[str] = set()
    for change in materiality.get("changes", []) or []:
        if not isinstance(change, dict) or not change.get("fact_id"):
            continue
        if material_only and not change.get("material"):
            continue
        output.add(str(change["fact_id"]))
    return output


def required_update_domains(
    prior_artifact: dict[str, Any],
    materiality: dict[str, Any],
) -> list[str]:
    """Return domains whose published prose cites a changed fact or semantic scope."""
    reads = dict(prior_artifact.get("reads") or {})
    if not reads:
        return list(DOMAIN_ORDER)
    changed_ids = changed_fact_ids(materiality)
    semantic_domains = {
        str(change.get("domain") or "")
        for change in (materiality.get("changes") or [])
        if isinstance(change, dict)
        and str(change.get("kind") or "") in {
            "domain_added", "domain_removed", "evidence_semantics_changed"
        }
    }
    required: list[str] = []
    for domain in DOMAIN_ORDER:
        read = dict(reads.get(domain) or {})
        citations = {
            str(fact_id)
            for claim in (read.get("claim_support") or [])
            if isinstance(claim, dict)
            for fact_id in (claim.get("fact_ids") or [])
        }
        if domain in semantic_domains or citations.intersection(changed_ids):
            required.append(domain)
    return required


def _seed_history(
    prior_state: dict[str, Any],
    prior_artifact: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    retained = prior_state.get("fact_history")
    if isinstance(retained, dict):
        return {
            str(fact_id): [dict(item) for item in rows if isinstance(item, dict)][-MAX_HISTORY_OBSERVATIONS:]
            for fact_id, rows in retained.items()
            if isinstance(rows, list)
        }
    packets = dict(prior_artifact.get("evidence_packets") or {})
    snapshot = str(prior_artifact.get("evidence_snapshot_id") or "")
    observed_at = str(prior_artifact.get("generated_at") or "")
    return {
        fact_id: [{
            "snapshot_id": snapshot,
            "observed_at": observed_at,
            "value": fact.get("value"),
            "display": str(fact.get("display") or ""),
        }]
        for fact_id, fact in _facts(packets).items()
    }


def extend_fact_history(
    packets: dict[str, Any],
    *,
    snapshot_id: str,
    observed_at: str,
    prior_state: dict[str, Any] | None = None,
    prior_artifact: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    history = _seed_history(dict(prior_state or {}), dict(prior_artifact or {}))
    for fact_id, fact in _facts(packets).items():
        rows = list(history.get(fact_id) or [])
        observation = {
            "snapshot_id": str(snapshot_id or ""),
            "observed_at": str(observed_at or ""),
            "value": fact.get("value"),
            "display": str(fact.get("display") or ""),
        }
        if rows and str(rows[-1].get("snapshot_id") or "") == str(snapshot_id or ""):
            rows[-1] = observation
        else:
            rows.append(observation)
        history[fact_id] = rows[-MAX_HISTORY_OBSERVATIONS:]
    return history


def _elapsed_days(prior_observed_at: str, current_observed_at: str) -> float | None:
    try:
        prior = datetime.fromisoformat(str(prior_observed_at).replace("Z", "+00:00"))
        current = datetime.fromisoformat(str(current_observed_at).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if prior.tzinfo is None:
        prior = prior.replace(tzinfo=timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return round(max(0.0, (current - prior).total_seconds()) / 86400.0, 2)


def _fact_payload(
    fact: dict[str, Any],
    *,
    history: list[dict[str, Any]],
    change: dict[str, Any] | None,
    observed_at: str,
) -> dict[str, Any]:
    prior = history[-2] if len(history) >= 2 else None
    output: dict[str, Any] = {
        "fact_id": str(fact.get("id") or ""),
        "label": str(fact.get("label") or ""),
        "current": str(fact.get("display") or ""),
        "previous_evaluation": str((prior or {}).get("display") or "") or None,
        "elapsed_days": _elapsed_days(str((prior or {}).get("observed_at") or ""), observed_at) if prior else None,
        "trajectory": [
            {
                "observed_at": str(item.get("observed_at") or ""),
                "display": str(item.get("display") or ""),
            }
            for item in history[-MAX_HISTORY_OBSERVATIONS:]
        ],
    }
    context = str(fact.get("context") or "").strip()
    if context:
        output["context"] = context
    if change:
        output["change"] = {
            "kind": str(change.get("kind") or ""),
            "material": bool(change.get("material")),
            "relative_change_pct": (
                round(float(change["relative_change"]) * 100.0, 2)
                if _number(change.get("relative_change")) is not None
                else None
            ),
            "percentage_point_change": change.get("percentage_point_change"),
            "comparison_basis": str(change.get("comparison_basis") or ""),
            "baseline_value": change.get("old_value"),
            "current_value": change.get("new_value"),
            "also_changed_since_publication": bool(change.get("also_changed_since_publication")),
            "publication_baseline_value": change.get("publication_old_value"),
        }
    return output


def _selected_fact_ids(
    domain: str,
    packet: dict[str, Any],
    changes: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    available = {
        str(fact.get("id"))
        for fact in (packet.get("facts") or [])
        if isinstance(fact, dict) and fact.get("id")
    }
    changed = sorted(
        (fact_id for fact_id in available if fact_id in changes),
        key=lambda fact_id: _change_score(changes[fact_id]),
        reverse=True,
    )
    selected: list[str] = []
    for fact_id in [*changed, *DOMAIN_ANCHORS.get(domain, ()), *sorted(available)]:
        if fact_id in available and fact_id not in selected:
            selected.append(fact_id)
        if len(selected) >= MAX_FACTS_PER_DOMAIN_CAPSULE:
            break
    leftovers = [fact_id for fact_id in changed if fact_id not in selected]
    return selected, leftovers


def build_signal_capsules(
    packets: dict[str, Any],
    *,
    snapshot_id: str,
    materiality: dict[str, Any],
    prior_state: dict[str, Any] | None = None,
    prior_artifact: dict[str, Any] | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Build eleven core domain capsules plus at most four change supplements."""
    current_at = str(observed_at or _utc_now_text())
    prior_state = dict(prior_state or {})
    prior_artifact = dict(prior_artifact or {})
    history = extend_fact_history(
        packets,
        snapshot_id=snapshot_id,
        observed_at=current_at,
        prior_state=prior_state,
        prior_artifact=prior_artifact,
    )
    changes = _change_index(materiality)
    fact_index = _facts(packets)
    capsules: list[dict[str, Any]] = []
    supplemental: list[tuple[float, str, list[str]]] = []
    for domain in DOMAIN_ORDER:
        packet = dict(packets.get(domain) or {})
        selected, leftovers = _selected_fact_ids(domain, packet, changes)
        importance = float(packet.get("importance") or 0.0)
        changed = [fact_id for fact_id in selected if fact_id in changes]
        capsules.append({
            "capsule_id": f"{domain}.core",
            "domain": domain,
            "label": str(packet.get("label") or DOMAIN_LABELS.get(domain, domain)),
            "lifecycle_stage": LIFECYCLE_STAGE[domain],
            "role": "material_change" if any(changes[item].get("material") for item in changed) else "system_context",
            "importance": round(importance, 1),
            "facts": [
                _fact_payload(
                    fact_index[fact_id],
                    history=history.get(fact_id, []),
                    change=changes.get(fact_id),
                    observed_at=current_at,
                )
                for fact_id in selected
            ],
            "boundaries": [str(item) for item in (packet.get("boundaries") or [])],
            "sources": [
                str(reference.get("source_label") or "")
                for reference in (packet.get("references") or [])
                if isinstance(reference, dict) and reference.get("source_label")
            ],
        })
        if leftovers:
            score = max((_change_score(changes[item])[1] for item in leftovers), default=0.0) + importance / 100.0
            supplemental.append((score, domain, leftovers))

    for _, domain, leftovers in sorted(supplemental, reverse=True)[:MAX_SUPPLEMENTAL_CAPSULES]:
        capsules.append({
            "capsule_id": f"{domain}.changes",
            "domain": domain,
            "label": f"{DOMAIN_LABELS.get(domain, domain)} additional changes",
            "lifecycle_stage": LIFECYCLE_STAGE[domain],
            "role": "supplemental_material_change",
            "facts": [
                _fact_payload(
                    fact_index[fact_id],
                    history=history.get(fact_id, []),
                    change=changes.get(fact_id),
                    observed_at=current_at,
                )
                for fact_id in leftovers[:MAX_FACTS_PER_DOMAIN_CAPSULE]
            ],
        })

    return {
        "capsule_architecture_version": CAPSULE_ARCHITECTURE_VERSION,
        "evidence_snapshot_id": str(snapshot_id or ""),
        "observed_at": current_at,
        "materiality": {
            "decision": str(materiality.get("decision") or ""),
            "material": bool(materiality.get("material")),
            "changed_domains": materially_changed_domains(materiality),
            "change_count": int(materiality.get("change_count", 0) or 0),
            "material_change_count": int(materiality.get("material_change_count", 0) or 0),
        },
        "capsules": capsules,
        "fact_history": history,
    }


def prior_publication_payload(
    prior_artifact: dict[str, Any],
    *,
    relevant_domains: list[str],
) -> dict[str, Any]:
    reads = dict(prior_artifact.get("reads") or {})

    def compact(read: Any) -> dict[str, Any]:
        item = dict(read or {})
        return {
            "headline": str(item.get("headline") or ""),
            "analysis": str(item.get("analysis") or ""),
            "selected_domains": list(item.get("selected_domains") or []),
            "generated_at": str(item.get("generated_at") or prior_artifact.get("generated_at") or ""),
        }

    return {
        "available": bool(reads),
        "published_at": str(prior_artifact.get("generated_at") or ""),
        "macro": compact(reads.get("macro")) if reads else {},
        "relevant_domain_reads": {
            domain: compact(reads.get(domain))
            for domain in relevant_domains
            if reads.get(domain)
        },
    }


def build_evaluated_state(
    *,
    snapshot_id: str,
    packets: dict[str, Any],
    capsules: dict[str, Any],
    attempt_id: str,
    decision: str,
    decision_reason: str,
    analytical_state: dict[str, Any] | None,
    validation: dict[str, Any],
    status: str,
) -> dict[str, Any]:
    return {
        "evaluated_state_version": EVALUATED_STATE_VERSION,
        "status": str(status or ""),
        "evidence_snapshot_id": str(snapshot_id or ""),
        "evaluated_at": str(capsules.get("observed_at") or _utc_now_text()),
        "attempt_id": str(attempt_id or ""),
        "decision": str(decision or ""),
        "decision_reason": str(decision_reason or ""),
        "analytical_state": deepcopy(dict(analytical_state or {})),
        "validation": deepcopy(dict(validation or {})),
        "evidence_packets": deepcopy(packets),
        "fact_history": deepcopy(dict(capsules.get("fact_history") or {})),
        "capsule_architecture_version": CAPSULE_ARCHITECTURE_VERSION,
    }


__all__ = [
    "CAPSULE_ARCHITECTURE_VERSION",
    "EVALUATED_STATE_VERSION",
    "build_evaluated_state",
    "build_signal_capsules",
    "changed_fact_ids",
    "materially_changed_domains",
    "prior_publication_payload",
    "required_update_domains",
]
