"""Deterministic materiality gate for scheduled OpenAI commentary.

The exact evidence fingerprint remains the audit identity.  This module answers
a different question: whether changes since the last completed API evaluation
are large enough to justify another paid one-call synthesis. Comparisons use the
separate evaluated baseline when it exists, so an explicit model abstention is
not purchased again while sub-threshold changes still accumulate.
"""

from __future__ import annotations

import math
import re
from typing import Any


MATERIALITY_VERSION = "1.1.0"
RELATIVE_CHANGE_THRESHOLD = 0.10
PERCENTAGE_POINT_THRESHOLD = 2.0
POINT_SCALE_FACT_IDS = {
    "market.aei",
    "market.pressure",
    "finance.borrower_strain",
    "finance.lender_strain",
    "finance.debt_financing_pulse",
    "finance.bond_distress",
}

_DISPLAY_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _packets(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    return {
        str(domain): dict(packet)
        for domain, packet in payload.items()
        if isinstance(packet, dict)
    }


def _facts(packets: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for packet in packets.values():
        for fact in packet.get("facts", []) or []:
            if not isinstance(fact, dict):
                continue
            fact_id = str(fact.get("id") or "").strip()
            if fact_id:
                output[fact_id] = dict(fact)
    return output


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _display_number(fact: dict[str, Any]) -> float | None:
    match = _DISPLAY_NUMBER_RE.search(str(fact.get("display") or ""))
    if not match:
        return None
    return _number(match.group(0).replace(",", ""))


def _percentage_fact(fact: dict[str, Any]) -> bool:
    display = str(fact.get("display") or "").casefold()
    return "%" in display or "percentage point" in display


def _point_scale_fact(fact_id: str, old: dict[str, Any], new: dict[str, Any]) -> bool:
    return fact_id in POINT_SCALE_FACT_IDS or _percentage_fact(old) or _percentage_fact(new)


def _semantic_packet_changes(
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for domain in sorted(set(previous) | set(current)):
        old = previous.get(domain)
        new = current.get(domain)
        if old is None or new is None:
            changes.append({
                "kind": "domain_added" if old is None else "domain_removed",
                "domain": domain,
                "material": True,
            })
            continue
        for field in ("label", "boundaries", "references"):
            if old.get(field) != new.get(field):
                changes.append({
                    "kind": "evidence_semantics_changed",
                    "domain": domain,
                    "field": field,
                    "material": True,
                })
    return changes


def compare_evidence_materiality(
    previous_packets: Any,
    current_packets: Any,
    *,
    previous_snapshot_id: str = "",
    current_snapshot_id: str = "",
) -> dict[str, Any]:
    """Compare current evidence with the last completed evaluation baseline."""

    previous = _packets(previous_packets)
    current = _packets(current_packets)
    report: dict[str, Any] = {
        "version": MATERIALITY_VERSION,
        "previous_snapshot_id": str(previous_snapshot_id or ""),
        "current_snapshot_id": str(current_snapshot_id or ""),
        "relative_change_threshold": RELATIVE_CHANGE_THRESHOLD,
        "percentage_point_threshold": PERCENTAGE_POINT_THRESHOLD,
        "baseline_available": bool(previous),
        "exact_match": bool(
            previous_snapshot_id
            and current_snapshot_id
            and str(previous_snapshot_id) == str(current_snapshot_id)
        ),
        "material": False,
        "changes": [],
    }
    if report["exact_match"]:
        report["decision"] = "reuse_exact_evidence"
        return report
    if not previous:
        report.update({
            "material": True,
            "decision": "generate_missing_baseline",
            "changes": [{"kind": "missing_generated_evidence_baseline", "material": True}],
        })
        return report

    changes = _semantic_packet_changes(previous, current)
    old_facts = _facts(previous)
    new_facts = _facts(current)
    for fact_id in sorted(set(old_facts) | set(new_facts)):
        old = old_facts.get(fact_id)
        new = new_facts.get(fact_id)
        if old is None or new is None:
            changes.append({
                "kind": "fact_added" if old is None else "fact_removed",
                "fact_id": fact_id,
                "domain": fact_id.split(".", 1)[0],
                "material": True,
            })
            continue

        old_value = old.get("value")
        new_value = new.get("value")
        old_numeric = _number(old_value)
        new_numeric = _number(new_value)
        if old_numeric is not None and new_numeric is not None:
            if old_numeric == new_numeric and old.get("display") == new.get("display"):
                continue
            percentage_points = None
            percentage_material = False
            if _point_scale_fact(fact_id, old, new):
                old_display = _display_number(old)
                new_display = _display_number(new)
                if old_display is not None and new_display is not None:
                    percentage_points = abs(new_display - old_display)
                    percentage_material = percentage_points >= PERCENTAGE_POINT_THRESHOLD
                    relative = percentage_points / max(abs(old_display), 1.0)
                else:
                    relative = abs(new_numeric - old_numeric) / max(abs(old_numeric), 1e-12)
            else:
                relative = abs(new_numeric - old_numeric) / max(abs(old_numeric), 1e-12)
            material = relative >= RELATIVE_CHANGE_THRESHOLD or percentage_material
            changes.append({
                "kind": "numeric_change",
                "fact_id": fact_id,
                "domain": fact_id.split(".", 1)[0],
                "old_value": old_numeric,
                "new_value": new_numeric,
                "relative_change": relative,
                "percentage_point_change": percentage_points,
                "material": material,
            })
            continue

        if old_value != new_value or old.get("display") != new.get("display"):
            changes.append({
                "kind": "categorical_change",
                "fact_id": fact_id,
                "domain": fact_id.split(".", 1)[0],
                "old_value": old_value,
                "new_value": new_value,
                "material": True,
            })

    material = any(bool(change.get("material")) for change in changes)
    report["changes"] = changes
    report["change_count"] = len(changes)
    report["material_change_count"] = sum(bool(change.get("material")) for change in changes)
    report["immaterial_change_count"] = sum(not bool(change.get("material")) for change in changes)
    report["material"] = material
    report["decision"] = "generate_material_change" if material else "reuse_immaterial_change"
    return report


__all__ = [
    "MATERIALITY_VERSION",
    "PERCENTAGE_POINT_THRESHOLD",
    "POINT_SCALE_FACT_IDS",
    "RELATIVE_CHANGE_THRESHOLD",
    "compare_evidence_materiality",
]
