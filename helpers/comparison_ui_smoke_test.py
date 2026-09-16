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
    _ledger_frame,
    _presentation_counts,
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
        {
            "metric_id": "adoption.new_metric",
            "domain": "adoption",
            "entity_id": "adoption:aggregate",
            "geography": "US",
            "label": "New adoption metric",
            "unit": "%",
            "display_scale": 100.0,
            "display_digits": 1,
            "display_value_base": None,
            "display_value_head": "25.0%",
            "value_double_base": None,
            "value_double_head": 0.25,
            "delta_numeric": None,
            "quality_status_base": None,
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
    _check(change_set.summary["changed_metric_count"] == 3, "Changed-metric summary changed")
    _check(change_set.summary["comparable_change_count"] == 2, "Comparable-metric summary changed")
    _check(change_set.summary["coverage_change_count"] == 1, "Coverage-metric summary changed")
    _check(change_set.summary["threshold_crossing_count"] == 1, "Threshold-crossing summary changed")
    counts = _presentation_counts(change_set)
    _check(counts == {"changed": 3, "comparable": 2, "material": 1, "coverage": 1, "crossings": 1}, "Frame-derived presentation counts changed")
    stale_summary = dict(change_set.summary)
    for key in ("comparable_change_count", "material_comparable_change_count", "coverage_change_count"):
        stale_summary.pop(key, None)
    change_set.summary = stale_summary
    _check(_presentation_counts(change_set)["comparable"] == 2, "Presentation counts must not depend on newer summary keys")
    _check("Sep 8, 2026" in comparison_subtitle(change_set), "Reader comparison period label changed")
    all_changes = _ledger_frame(change_set, "All changes")
    comparable = _ledger_frame(change_set, "Comparable changes")
    coverage = _ledger_frame(change_set, "Coverage changes")
    _check(len(all_changes) == 3, "All-changes ledger lost rows")
    _check(len(comparable) == 2 and set(comparable["Group"]) == {"Comparable"}, "Comparable ledger changed")
    _check(len(coverage) == 1 and coverage.iloc[0]["Group"] == "Coverage", "Coverage ledger changed")
    _check(all_changes.iloc[0]["Group"] == "Comparable", "Coverage changes should not lead the all-changes ledger")

    seven_day = comparison_request_for_option("7 days earlier", head_snapshot_id="snapshot-3")
    _check(seven_day.mode == ComparisonMode.LOOKBACK_DAYS and seven_day.lookback_days == 7, "7-day UI mapping changed")
    thirty_day = comparison_request_for_option("30 days earlier", head_snapshot_id="snapshot-3")
    _check(thirty_day.mode == ComparisonMode.LOOKBACK_DAYS and thirty_day.lookback_days == 30, "30-day UI mapping changed")
    current = comparison_request_for_option("Current publication only", head_snapshot_id="snapshot-3")
    _check(current.mode == ComparisonMode.CURRENT_ONLY, "Current-only UI mapping changed")

    macro_source = (ROOT / "rendering" / "macro.py").read_text(encoding="utf-8")
    evidence_source = (ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    comparison_source = (ROOT / "rendering" / "comparison.py").read_text(encoding="utf-8")
    app_source = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    components_source = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    theme_source = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    _check("render_change_evidence(" not in macro_source, "Change inspector should not crowd the Macro tab")
    _check("render_change_evidence(" in evidence_source, "Change inspector must live on the Evidence tab")
    _check("All changed metrics" in comparison_source, "Full changed-metric ledger surface is missing")
    _check("render_macro_comparison_toolbar(" in macro_source, "Comparison controls must live with the Macro change engine")
    _check("render_global_comparison_controls" not in app_source, "Comparison controls should not render above the tabs")
    _check('terms_key="macro"' in macro_source, "Macro terms control must be integrated into the tab header")
    _check("_render_floating_terms(terms_key)" in components_source, "Tab header must own the terms control")
    labels = [
        comparison_source.index('_comparison_value_html("What changed"'),
        comparison_source.index('_comparison_value_html("Current publication"'),
        comparison_source.index('"Compare with"'),
        comparison_source.index('_comparison_value_html("Point-in-time view"'),
    ]
    _check(labels == sorted(labels), "Comparison toolbar sequence changed")
    _check('v3.0.4.4 page rhythm' in theme_source, "Macro/Evidence spacing contract is missing")
    _check('st-key-domain-header-macro' in theme_source, "Macro header-to-Read spacing contract is missing")
    _check('st-key-change-evidence-inspector' in theme_source, "Evidence change-inspector spacing contract is missing")
    page_tail = evidence_source[evidence_source.index("def render_evidence_tab("):]
    _check("compact=True" not in page_tail, "Evidence page top-level sections must use the standard section rhythm")

    print({"status": "PASS", "changed_metrics": 3, "threshold_crossings": 1})


if __name__ == "__main__":
    main()
