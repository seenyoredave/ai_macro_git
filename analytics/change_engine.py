"""Deterministic point-in-time change classification for canonical metrics.

The engine describes what changed between two canonical publication snapshots.
It does not generate prose and does not make provider calls.  Materiality here
is an analytical presentation rule, not an OpenAI publication decision.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analytics.comparison_state import ComparisonState
from config.deployment import PROJECT_ROOT


CHANGE_ENGINE_VERSION = "1.0.0"
CHANGE_POLICY_VERSION = "1.0.0"
NUMERIC_TOLERANCE = 1e-12
RELATIVE_MATERIALITY_THRESHOLD = 0.10
PERCENTAGE_POINT_MATERIALITY_THRESHOLD = 2.0
POINT_SCALE_METRIC_IDS = frozenset({
    "market.aei",
    "market.pressure",
    "finance.borrower_strain",
    "finance.lender_strain",
    "finance.debt_financing_pulse",
    "finance.bond_distress",
})

# These are established semantic bands already used by the analytical product.
# Keep the registry deliberately small; a threshold is included only when its
# interpretation is explicit in the existing metric contract.
REGIME_THRESHOLDS: dict[str, tuple[float, ...]] = {
    "market.aei": (30.0, 60.0, 80.0),
    "finance.borrower_strain": (0.0,),
    "finance.lender_strain": (0.0,),
    "finance.debt_financing_pulse": (0.0,),
    "finance.nfci": (0.0,),
}

CHANGE_CLASS_ORDER = {
    "regime_threshold_crossed": 0,
    "metric_new": 1,
    "metric_unavailable": 1,
    "metric_restored": 1,
    "material_movement": 2,
    "categorical_change": 3,
    "incremental_change": 4,
    "quality_changed": 5,
    "unchanged": 9,
}

_INVALID_QUALITY = {"", "missing", "unavailable", "failed", "error"}


@dataclass(slots=True)
class ChangeSet:
    version: str
    comparison: ComparisonState
    frame: pd.DataFrame
    summary: dict[str, Any]

    def to_dict(self, *, include_rows: bool = True) -> dict[str, Any]:
        payload = {
            "version": self.version,
            "comparison": self.comparison.to_dict(),
            "summary": dict(self.summary),
        }
        if include_rows:
            clean = self.frame.replace({np.nan: None})
            payload["changes"] = clean.to_dict(orient="records")
        return payload


def _scalar_missing(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if isinstance(missing, (bool, np.bool_)) else False


def _text(value: Any) -> str:
    return "" if _scalar_missing(value) or value is None else str(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or _scalar_missing(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _present(quality: Any, display: Any, numeric: Any) -> bool:
    return not (_scalar_missing(quality) and _scalar_missing(display) and _scalar_missing(numeric))


def _valid_quality(quality: Any) -> bool:
    return _text(quality).strip().casefold() not in _INVALID_QUALITY


def _threshold_crossings(metric_id: str, base: float, head: float) -> list[dict[str, Any]]:
    crossings: list[dict[str, Any]] = []
    if math.isclose(base, head, rel_tol=0.0, abs_tol=NUMERIC_TOLERANCE):
        return crossings
    for threshold in REGIME_THRESHOLDS.get(metric_id, ()):
        if base < threshold <= head:
            crossings.append({"threshold": float(threshold), "direction": "up"})
        elif head < threshold <= base:
            crossings.append({"threshold": float(threshold), "direction": "down"})
    return crossings


def _materiality(
    *,
    metric_id: str,
    unit: str,
    display_scale: float,
    display_digits: int,
    base: float,
    head: float,
) -> tuple[bool, tuple[str, ...], float | None, float | None, float | None]:
    delta = head - base
    display_delta = delta * display_scale
    relative = (
        delta / abs(base)
        if abs(base) > NUMERIC_TOLERANCE
        else None
    )
    reasons: list[str] = []
    ratios: list[float] = []

    if relative is not None:
        relative_ratio = abs(relative) / RELATIVE_MATERIALITY_THRESHOLD
        ratios.append(relative_ratio)
        if relative_ratio >= 1.0:
            reasons.append("relative_change")

    if unit == "%":
        point_ratio = abs(display_delta) / PERCENTAGE_POINT_MATERIALITY_THRESHOLD
        ratios.append(point_ratio)
        if point_ratio >= 1.0:
            reasons.append("percentage_point_change")
    elif metric_id in POINT_SCALE_METRIC_IDS:
        point_ratio = abs(delta) / PERCENTAGE_POINT_MATERIALITY_THRESHOLD
        ratios.append(point_ratio)
        if point_ratio >= 1.0:
            reasons.append("point_scale_change")

    # Relative change is undefined at a zero baseline.  In that case require a
    # move of at least two displayed increments before calling it material.
    if (
        relative is None
        and unit != "%"
        and metric_id not in POINT_SCALE_METRIC_IDS
        and not math.isclose(delta, 0.0, abs_tol=NUMERIC_TOLERANCE)
    ):
        quantum = 10.0 ** (-max(0, int(display_digits)))
        zero_floor = max(2.0 * quantum, NUMERIC_TOLERANCE)
        zero_ratio = abs(display_delta) / zero_floor
        ratios.append(zero_ratio)
        if zero_ratio >= 1.0:
            reasons.append("zero_baseline_display_change")

    ratio = max(ratios) if ratios else None
    return bool(reasons), tuple(dict.fromkeys(reasons)), relative, display_delta, ratio


def _classify_row(row: pd.Series) -> dict[str, Any]:
    metric_id = _text(row.get("metric_id")).strip()
    domain = _text(row.get("domain")).strip()
    unit = _text(row.get("unit")).strip()
    scale = _number(row.get("display_scale")) or 1.0
    digits_num = _number(row.get("display_digits"))
    digits = int(digits_num) if digits_num is not None else 1

    base_quality = row.get("quality_status_base")
    head_quality = row.get("quality_status_head")
    base_display = _text(row.get("display_value_base"))
    head_display = _text(row.get("display_value_head"))
    base_numeric = _number(row.get("value_double_base"))
    head_numeric = _number(row.get("value_double_head"))
    base_present = _present(base_quality, row.get("display_value_base"), row.get("value_double_base"))
    head_present = _present(head_quality, row.get("display_value_head"), row.get("value_double_head"))
    base_valid = base_present and _valid_quality(base_quality)
    head_valid = head_present and _valid_quality(head_quality)

    output: dict[str, Any] = {
        "metric_id": metric_id,
        "domain": domain,
        "entity_id": _text(row.get("entity_id")),
        "geography": _text(row.get("geography")),
        "label": _text(row.get("label")) or metric_id,
        "unit": unit,
        "display_scale": scale,
        "display_digits": digits,
        "base_display": base_display,
        "head_display": head_display,
        "base_value": base_numeric,
        "head_value": head_numeric,
        "delta_numeric": None,
        "delta_display": None,
        "relative_change": None,
        "direction": "flat",
        "classification": "unchanged",
        "material": False,
        "materiality_reasons": (),
        "materiality_ratio": None,
        "threshold_crossings": (),
        "base_quality": _text(base_quality),
        "head_quality": _text(head_quality),
        "base_present": base_present,
        "head_present": head_present,
    }

    if not base_present and head_present:
        output.update(
            classification="metric_new",
            material=True,
            materiality_reasons=("metric_added",),
        )
        return output
    if base_present and not head_present:
        output.update(
            classification="metric_unavailable",
            material=True,
            materiality_reasons=("metric_removed",),
        )
        return output
    if not base_present and not head_present:
        return output

    if not base_valid and head_valid:
        output.update(
            classification="metric_restored",
            material=True,
            materiality_reasons=("quality_restored",),
        )
        return output
    if base_valid and not head_valid:
        output.update(
            classification="metric_unavailable",
            material=True,
            materiality_reasons=("quality_degraded",),
        )
        return output

    if base_numeric is not None and head_numeric is not None:
        delta = head_numeric - base_numeric
        output["delta_numeric"] = delta
        if delta > NUMERIC_TOLERANCE:
            output["direction"] = "up"
        elif delta < -NUMERIC_TOLERANCE:
            output["direction"] = "down"

        numeric_changed = not math.isclose(
            base_numeric,
            head_numeric,
            rel_tol=NUMERIC_TOLERANCE,
            abs_tol=NUMERIC_TOLERANCE,
        )
        quality_changed = _text(base_quality) != _text(head_quality)
        if not numeric_changed and not quality_changed:
            return output

        crossings = _threshold_crossings(metric_id, base_numeric, head_numeric)
        material, reasons, relative, display_delta, ratio = _materiality(
            metric_id=metric_id,
            unit=unit,
            display_scale=scale,
            display_digits=digits,
            base=base_numeric,
            head=head_numeric,
        )
        output.update(
            delta_display=display_delta,
            relative_change=relative,
            materiality_ratio=ratio,
            threshold_crossings=tuple(crossings),
        )
        if crossings:
            output.update(
                classification="regime_threshold_crossed",
                material=True,
                materiality_reasons=("regime_threshold", *reasons),
            )
        elif numeric_changed and material:
            output.update(
                classification="material_movement",
                material=True,
                materiality_reasons=reasons,
            )
        elif numeric_changed:
            output.update(
                classification="incremental_change",
                material=False,
                materiality_reasons=reasons,
            )
        else:
            output.update(
                classification="quality_changed",
                material=False,
                materiality_reasons=("quality_changed",),
            )
        return output

    display_changed = base_display != head_display
    quality_changed = _text(base_quality) != _text(head_quality)
    if display_changed:
        output.update(
            classification="categorical_change",
            material=True,
            materiality_reasons=("categorical_change",),
        )
    elif quality_changed:
        output.update(
            classification="quality_changed",
            material=False,
            materiality_reasons=("quality_changed",),
        )
    return output


def classify_canonical_diff(diff: pd.DataFrame) -> pd.DataFrame:
    """Classify a canonical snapshot diff without reading any external state."""
    if diff is None or diff.empty:
        return pd.DataFrame(columns=[
            "metric_id",
            "domain",
            "classification",
            "material",
        ])
    required = {
        "metric_id",
        "domain",
        "display_value_base",
        "display_value_head",
        "value_double_base",
        "value_double_head",
        "quality_status_base",
        "quality_status_head",
    }
    missing = required - set(diff.columns)
    if missing:
        raise ValueError(f"Canonical diff is missing columns: {sorted(missing)}")

    rows = pd.DataFrame(_classify_row(row) for _, row in diff.iterrows())
    if rows.empty:
        return rows
    rows["_class_order"] = rows["classification"].map(CHANGE_CLASS_ORDER).fillna(8).astype(int)
    rows = rows.sort_values(
        ["_class_order", "domain", "metric_id", "entity_id", "geography"],
        kind="stable",
    ).drop(columns=["_class_order"])
    return rows.reset_index(drop=True)


def _summary(frame: pd.DataFrame, comparison: ComparisonState, *, status: str) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {
            "status": status,
            "policy_version": CHANGE_POLICY_VERSION,
            "relative_materiality_threshold": RELATIVE_MATERIALITY_THRESHOLD,
            "percentage_point_materiality_threshold": PERCENTAGE_POINT_MATERIALITY_THRESHOLD,
            "head_snapshot_id": comparison.head.snapshot_id if comparison.head else "",
            "baseline_snapshot_id": comparison.baseline.snapshot_id if comparison.baseline else "",
            "metric_count": 0,
            "changed_metric_count": 0,
            "material_change_count": 0,
            "incremental_change_count": 0,
            "threshold_crossing_count": 0,
            "new_metric_count": 0,
            "unavailable_metric_count": 0,
            "restored_metric_count": 0,
            "changed_domains": [],
            "material_domains": [],
        }

    changed = frame.loc[frame["classification"].ne("unchanged")]
    material = changed.loc[changed["material"].astype(bool)]
    counts = changed["classification"].value_counts().to_dict()
    return {
        "status": status,
        "policy_version": CHANGE_POLICY_VERSION,
        "relative_materiality_threshold": RELATIVE_MATERIALITY_THRESHOLD,
        "percentage_point_materiality_threshold": PERCENTAGE_POINT_MATERIALITY_THRESHOLD,
        "head_snapshot_id": comparison.head.snapshot_id if comparison.head else "",
        "baseline_snapshot_id": comparison.baseline.snapshot_id if comparison.baseline else "",
        "metric_count": int(len(frame)),
        "changed_metric_count": int(len(changed)),
        "material_change_count": int(len(material)),
        "incremental_change_count": int(counts.get("incremental_change", 0)),
        "threshold_crossing_count": int(counts.get("regime_threshold_crossed", 0)),
        "new_metric_count": int(counts.get("metric_new", 0)),
        "unavailable_metric_count": int(counts.get("metric_unavailable", 0)),
        "restored_metric_count": int(counts.get("metric_restored", 0)),
        "changed_domains": sorted(set(changed["domain"].dropna().astype(str))),
        "material_domains": sorted(set(material["domain"].dropna().astype(str))),
    }


def build_change_set(
    comparison: ComparisonState,
    *,
    root: Path = PROJECT_ROOT,
    diff_frame: pd.DataFrame | None = None,
) -> ChangeSet:
    """Build one deterministic metric change set for resolved comparison state."""
    if comparison.head is None:
        frame = pd.DataFrame()
        return ChangeSet(
            version=CHANGE_ENGINE_VERSION,
            comparison=comparison,
            frame=frame,
            summary=_summary(frame, comparison, status="head_unavailable"),
        )
    if comparison.baseline is None:
        frame = pd.DataFrame()
        return ChangeSet(
            version=CHANGE_ENGINE_VERSION,
            comparison=comparison,
            frame=frame,
            summary=_summary(frame, comparison, status="baseline_unavailable"),
        )

    if diff_frame is None:
        from analytics.canonical_store import canonical_snapshot_diff

        raw = canonical_snapshot_diff(
            comparison.baseline.snapshot_id,
            comparison.head.snapshot_id,
            root=root,
        )
    else:
        raw = diff_frame.copy()

    frame = classify_canonical_diff(raw)
    status = "ready" if not raw.empty else "diff_unavailable"
    return ChangeSet(
        version=CHANGE_ENGINE_VERSION,
        comparison=comparison,
        frame=frame,
        summary=_summary(frame, comparison, status=status),
    )


__all__ = [
    "CHANGE_ENGINE_VERSION",
    "CHANGE_POLICY_VERSION",
    "CHANGE_CLASS_ORDER",
    "NUMERIC_TOLERANCE",
    "PERCENTAGE_POINT_MATERIALITY_THRESHOLD",
    "POINT_SCALE_METRIC_IDS",
    "REGIME_THRESHOLDS",
    "RELATIVE_MATERIALITY_THRESHOLD",
    "ChangeSet",
    "build_change_set",
    "classify_canonical_diff",
]
