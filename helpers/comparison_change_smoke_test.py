"""Smoke test for global comparison state and deterministic canonical changes."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.change_engine import (  # noqa: E402
    CHANGE_ENGINE_VERSION,
    build_change_set,
    classify_canonical_diff,
)
from analytics.comparison_state import (  # noqa: E402
    COMPARISON_STATE_VERSION,
    ComparisonMode,
    ComparisonRequest,
    resolve_comparison_state,
)
from analytics.dashboard_context import DashboardContext  # noqa: E402


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _history() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "schema_version": "1.0.0",
            "snapshot_id": "s1",
            "evidence_snapshot_id": "e1",
            "observation_date": "2026-09-01",
            "created_at_utc": "2026-09-01T12:00:00+00:00",
            "run_id": "r1",
            "publication_source": "test",
            "context_snapshot_id": "c1",
            "metric_count": 10,
            "domain_count": 2,
            "state_hash": "h1",
        },
        {
            "schema_version": "1.0.0",
            "snapshot_id": "s2",
            "evidence_snapshot_id": "e2",
            "observation_date": "2026-09-08",
            "created_at_utc": "2026-09-08T12:00:00+00:00",
            "run_id": "r2",
            "publication_source": "test",
            "context_snapshot_id": "c2",
            "metric_count": 10,
            "domain_count": 2,
            "state_hash": "h2",
        },
        {
            "schema_version": "1.0.0",
            "snapshot_id": "s3",
            "evidence_snapshot_id": "e3",
            "observation_date": "2026-09-15",
            "created_at_utc": "2026-09-15T10:00:00+00:00",
            "run_id": "r3",
            "publication_source": "test",
            "context_snapshot_id": "c3",
            "metric_count": 10,
            "domain_count": 2,
            "state_hash": "h3",
        },
        {
            "schema_version": "1.0.0",
            "snapshot_id": "s4",
            "evidence_snapshot_id": "e4",
            "observation_date": "2026-09-15",
            "created_at_utc": "2026-09-15T12:00:00+00:00",
            "run_id": "r4",
            "publication_source": "test",
            "context_snapshot_id": "c4",
            "metric_count": 10,
            "domain_count": 2,
            "state_hash": "h4",
        },
    ])


def _diff_row(
    metric_id: str,
    domain: str,
    *,
    base_display,
    head_display,
    base_value=np.nan,
    head_value=np.nan,
    base_quality="valid",
    head_quality="valid",
    unit="",
    scale=1.0,
    digits=1,
) -> dict:
    return {
        "metric_id": metric_id,
        "domain": domain,
        "entity_id": f"{domain}:aggregate",
        "geography": "US",
        "label": metric_id,
        "unit": unit,
        "display_scale": scale,
        "display_digits": digits,
        "display_value_base": base_display,
        "display_value_head": head_display,
        "value_double_base": base_value,
        "value_double_head": head_value,
        "delta_numeric": (
            head_value - base_value
            if pd.notna(base_value) and pd.notna(head_value)
            else np.nan
        ),
        "quality_status_base": base_quality,
        "quality_status_head": head_quality,
        "changed": base_display != head_display or base_quality != head_quality,
    }


def _diff() -> pd.DataFrame:
    rows = [
        _diff_row(
            "market.aei",
            "market",
            base_display="55.0",
            head_display="62.0",
            base_value=55.0,
            head_value=62.0,
        ),
        _diff_row(
            "market.positive_breadth",
            "market",
            base_display="50.0%",
            head_display="51.0%",
            base_value=0.50,
            head_value=0.51,
            unit="%",
            scale=100.0,
        ),
        _diff_row(
            "market.median_return",
            "market",
            base_display="10.0%",
            head_display="13.0%",
            base_value=0.10,
            head_value=0.13,
            unit="%",
            scale=100.0,
        ),
        _diff_row(
            "finance.nfci",
            "finance",
            base_display="-0.10",
            head_display="0.10",
            base_value=-0.10,
            head_value=0.10,
            digits=2,
        ),
        _diff_row(
            "water.highest_county_d2_location",
            "water",
            base_display="County A",
            head_display="County B",
        ),
        _diff_row(
            "adoption.new_metric",
            "adoption",
            base_display=np.nan,
            head_display="1",
            base_value=np.nan,
            head_value=1.0,
            base_quality=np.nan,
        ),
        _diff_row(
            "compute.unavailable_metric",
            "compute",
            base_display="10",
            head_display="",
            base_value=10.0,
            head_value=np.nan,
            head_quality="missing",
        ),
        _diff_row(
            "power.restored_metric",
            "power",
            base_display="",
            head_display="5",
            base_value=np.nan,
            head_value=5.0,
            base_quality="missing",
        ),
        _diff_row(
            "finance.quality_metric",
            "finance",
            base_display="2.0",
            head_display="2.0",
            base_value=2.0,
            head_value=2.0,
            base_quality="estimated",
            head_quality="valid",
        ),
        _diff_row(
            "workforce.unchanged",
            "workforce",
            base_display="3.0",
            head_display="3.0",
            base_value=3.0,
            head_value=3.0,
        ),
    ]
    return pd.DataFrame(rows)


def main() -> None:
    history = _history()

    state = resolve_comparison_state(snapshot_history=history)
    _check(state.version == COMPARISON_STATE_VERSION, "Comparison state version changed")
    _check(state.head and state.head.snapshot_id == "s4", "Latest head snapshot resolution failed")
    _check(state.baseline and state.baseline.snapshot_id == "s3", "Previous-publication baseline failed")
    _check(state.comparison_available, "Resolved comparison unexpectedly unavailable")

    weekly = resolve_comparison_state(
        ComparisonRequest(mode=ComparisonMode.LOOKBACK_DAYS, lookback_days=7),
        snapshot_history=history,
    )
    _check(weekly.baseline and weekly.baseline.snapshot_id == "s2", "Seven-day lookback selected the wrong baseline")

    historical = resolve_comparison_state(
        ComparisonRequest(head_as_of="2026-09-08"),
        snapshot_history=history,
    )
    _check(historical.head and historical.head.snapshot_id == "s2", "Historical head resolution failed")
    _check(historical.baseline and historical.baseline.snapshot_id == "s1", "Historical previous baseline failed")

    invalid_head = resolve_comparison_state(
        ComparisonRequest(head_snapshot_id="missing"),
        snapshot_history=history,
    )
    _check(invalid_head.head and invalid_head.head.snapshot_id == "s4", "Missing head did not fall back to latest")
    _check("head_snapshot_not_found_latest_used" in invalid_head.fallback_codes, "Head fallback was not recorded")

    bad_baseline = resolve_comparison_state(
        ComparisonRequest(
            head_snapshot_id="s2",
            mode=ComparisonMode.SNAPSHOT,
            baseline_snapshot_id="s4",
        ),
        snapshot_history=history,
    )
    _check(not bad_baseline.comparison_available, "Newer baseline should not be accepted")
    _check("baseline_snapshot_newer_than_head" in bad_baseline.fallback_codes, "Newer-baseline rejection was not recorded")

    current_only = resolve_comparison_state(
        ComparisonRequest(mode=ComparisonMode.CURRENT_ONLY),
        snapshot_history=history,
    )
    _check(current_only.status == "current_only" and current_only.baseline is None, "Current-only state failed")

    too_early = resolve_comparison_state(
        ComparisonRequest(head_as_of="2020-01-01"),
        snapshot_history=history,
    )
    _check(too_early.status == "unavailable" and too_early.head is None, "Pre-history head fallback should stay unavailable")

    classified = classify_canonical_diff(_diff())
    classes = dict(zip(classified["metric_id"], classified["classification"]))
    _check(classes["market.aei"] == "regime_threshold_crossed", "AEI threshold crossing was missed")
    _check(classes["finance.nfci"] == "regime_threshold_crossed", "NFCI zero crossing was missed")
    _check(classes["market.positive_breadth"] == "incremental_change", "Small breadth move was over-classified")
    _check(classes["market.median_return"] == "material_movement", "Material return move was missed")
    _check(classes["water.highest_county_d2_location"] == "categorical_change", "Categorical change was missed")
    _check(classes["adoption.new_metric"] == "metric_new", "New metric was missed")
    _check(classes["compute.unavailable_metric"] == "metric_unavailable", "Unavailable metric was missed")
    _check(classes["power.restored_metric"] == "metric_restored", "Restored metric was missed")
    _check(classes["finance.quality_metric"] == "quality_changed", "Quality-only transition was missed")
    _check(classes["workforce.unchanged"] == "unchanged", "Unchanged metric was misclassified")

    changes = build_change_set(state, diff_frame=_diff())
    _check(changes.version == CHANGE_ENGINE_VERSION, "Change engine version changed")
    context = DashboardContext(comparison_state=state, comparison_change_set=changes)
    _check(context.comparison_state is state, "Dashboard context lost global comparison state")
    _check(context.comparison_change_set is changes, "Dashboard context lost deterministic change set")
    _check(changes.summary["status"] == "ready", "Change set did not resolve")
    _check(changes.summary["threshold_crossing_count"] == 2, "Threshold crossing count changed")
    _check(changes.summary["changed_metric_count"] == 9, "Changed metric count changed")
    _check(changes.summary["material_change_count"] == 7, "Material change count changed")
    _check(changes.summary["comparable_change_count"] == 6, "Comparable change count changed")
    _check(changes.summary["material_comparable_change_count"] == 4, "Comparable material count changed")
    _check(changes.summary["coverage_change_count"] == 3, "Coverage change count changed")
    _check(set(changes.summary["coverage_domains"]) == {"adoption", "compute", "power"}, "Coverage domains changed")
    _check("market" in changes.summary["material_domains"], "Material domain summary lost Market")

    no_baseline = build_change_set(current_only, diff_frame=_diff())
    _check(no_baseline.summary["status"] == "baseline_unavailable", "Missing baseline did not degrade cleanly")
    _check(no_baseline.frame.empty, "Missing baseline should not manufacture change rows")

    print({
        "status": "PASS",
        "comparison_state_version": COMPARISON_STATE_VERSION,
        "change_engine_version": CHANGE_ENGINE_VERSION,
        "rows": len(classified),
    })


if __name__ == "__main__":
    main()
