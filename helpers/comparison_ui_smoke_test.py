"""Regression smoke test for reader-facing point-in-time comparison contracts."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.streamlit_runtime_stub import install_streamlit_stub  # noqa: E402

install_streamlit_stub()

from analytics.change_engine import build_change_set  # noqa: E402
from analytics.comparison_state import ComparisonMode, resolve_comparison_state  # noqa: E402
from rendering.comparison import (  # noqa: E402
    comparison_ready,
    comparison_request_for_option,
    comparison_subtitle,
)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _history() -> pd.DataFrame:
    rows = []
    for index, day in enumerate(("2026-09-01", "2026-09-08", "2026-09-15"), start=1):
        rows.append({
            "schema_version": "1.0.0",
            "snapshot_id": f"snapshot-{index}",
            "evidence_snapshot_id": f"evidence-{index}",
            "observation_date": day,
            "created_at_utc": f"{day}T12:00:00+00:00",
            "run_id": f"run-{index}",
            "publication_source": "smoke",
            "context_snapshot_id": f"context-{index}",
            "metric_count": 2,
            "domain_count": 1,
            "state_hash": f"hash-{index}",
            "domains_json": "{}",
            "source_status_json": "{}",
        })
    return pd.DataFrame(rows)


def _diff() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "metric_id": "market.aei",
            "domain": "market",
            "entity_id": "market:aggregate",
            "geography": "US",
            "label": "AI Equity Index",
            "unit": "",
            "display_scale": 1.0,
            "display_digits": 1,
            "display_value_base": "55.0",
            "display_value_head": "65.0",
            "value_double_base": 55.0,
            "value_double_head": 65.0,
            "delta_numeric": 10.0,
            "quality_status_base": "valid",
            "quality_status_head": "valid",
            "changed": True,
        },
        {
            "metric_id": "market.pressure",
            "domain": "market",
            "entity_id": "market:aggregate",
            "geography": "US",
            "label": "Market Pressure",
            "unit": "",
            "display_scale": 1.0,
            "display_digits": 1,
            "display_value_base": "10.0",
            "display_value_head": "10.5",
            "value_double_base": 10.0,
            "value_double_head": 10.5,
            "delta_numeric": 0.5,
            "quality_status_base": "valid",
            "quality_status_head": "valid",
            "changed": True,
        },
    ])


def main() -> None:
    request = comparison_request_for_option(
        "Previous publication",
        head_snapshot_id="snapshot-3",
    )
    _check(request.mode == ComparisonMode.PREVIOUS_PUBLICATION, "Previous-publication UI mapping changed")
    state = resolve_comparison_state(request, snapshot_history=_history())
    _check(state.head and state.head.snapshot_id == "snapshot-3", "Comparison head mapping changed")
    _check(state.baseline and state.baseline.snapshot_id == "snapshot-2", "Comparison baseline mapping changed")

    change_set = build_change_set(state, diff_frame=_diff())
    _check(comparison_ready(change_set), "Reader comparison should be ready")
    _check(change_set.summary["changed_metric_count"] == 2, "Changed-metric summary changed")
    _check(change_set.summary["threshold_crossing_count"] == 1, "Threshold-crossing summary changed")
    _check("Sep 8, 2026" in comparison_subtitle(change_set), "Reader comparison period label changed")

    seven_day = comparison_request_for_option("7 days earlier", head_snapshot_id="snapshot-3")
    _check(seven_day.mode == ComparisonMode.LOOKBACK_DAYS and seven_day.lookback_days == 7, "7-day UI mapping changed")
    thirty_day = comparison_request_for_option("30 days earlier", head_snapshot_id="snapshot-3")
    _check(thirty_day.mode == ComparisonMode.LOOKBACK_DAYS and thirty_day.lookback_days == 30, "30-day UI mapping changed")
    current = comparison_request_for_option("Current publication only", head_snapshot_id="snapshot-3")
    _check(current.mode == ComparisonMode.CURRENT_ONLY, "Current-only UI mapping changed")

    print({"status": "PASS", "changed_metrics": 2, "threshold_crossings": 1})


if __name__ == "__main__":
    main()
