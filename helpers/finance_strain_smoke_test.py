"""Regression checks for Finance strain history, dynamics, and summary layout."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.borrower_strain_engine import normalize_borrower_strain_history
from analytics.borrower_strain_history import combine_borrower_strain_history
from analytics.lender_strain_engine import calculate_lender_strain
from analytics.trend_engine import calc_metric_trend
from archive.archive_reader import load_macro_history


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def _strain_trend(history, metric, **kwargs):
    return calc_metric_trend(
        history,
        metric,
        distinct_observations=True,
        repeat_tolerance=1e-8,
        dynamics_window_days=365,
        dynamics_min_observations=3,
        dynamics_min_span_days=120,
        **kwargs,
    )


def check_lender_history() -> None:
    result = calculate_lender_strain({})
    history = result.get("history")
    _check(history is not None and not history.empty, "Lender Strain history is empty.")
    start = history["Date"].min()
    end = history["Date"].max()
    _check((end - start).days >= 3650, "Lender Strain no longer spans a ten-year window.")
    _check(len(history) >= 40, "Lender Strain history is too sparse for a ten-year chart.")
    _check(
        set(history["Valid Components"].astype(int)) == {4},
        "Historical bridge weakened the four-pillar Lender Strain contract.",
    )
    modes = set(history["Private Credit Evidence"].astype(str))
    _check(
        "Federal Reserve business-loan delinquency bridge" in modes,
        "The historical private-credit bridge is absent.",
    )
    _check(
        "Direct listed-BDC nonaccrual panel" in modes,
        "The direct BDC panel is absent from recent Lender Strain history.",
    )

    trend = _strain_trend(history, "Lender Strain")
    _check(np.isfinite(trend["velocity"]), "Lender Strain velocity is unavailable.")
    _check(np.isfinite(trend["acceleration"]), "Lender Strain acceleration is unavailable.")


def check_borrower_dynamics() -> None:
    history = normalize_borrower_strain_history(
        combine_borrower_strain_history(load_macro_history())
    )
    trend = _strain_trend(
        history,
        "Borrower Strain",
        version_column="Borrower Strain Version",
        required_version="3.0",
    )
    _check(np.isfinite(trend["velocity"]), "Borrower Strain velocity is unavailable.")
    _check(np.isfinite(trend["acceleration"]), "Borrower Strain acceleration is unavailable.")


def check_summary_layout_contract() -> None:
    source = (PROJECT_ROOT / "rendering" / "finance.py").read_text(encoding="utf-8")
    stats_block = source.split("def _financial_condition_stats", 1)[1].split(
        "def _financial_condition_source_meta", 1
    )[0]
    _check(stats_block.count('"Current"') == 1, "Finance strain summary lost Current.")
    _check(stats_block.count('"Velocity"') == 1, "Finance strain summary lost Velocity.")
    _check(stats_block.count('"Acceleration"') == 1, "Finance strain summary lost Acceleration.")
    _check('"Source"' not in stats_block, "Source remains as a fourth strain stat bubble.")
    _check(
        "_financial_condition_source_meta(trend, live_sources)" in source,
        "Finance strain source is not rendered in the panel heading.",
    )
    _check("12-month OLS slope" in source, "Finance strain dynamics reverted to a 90-day window.")


def main() -> None:
    checks = (
        ("Lender ten-year history", check_lender_history),
        ("Borrower dynamics", check_borrower_dynamics),
        ("Finance summary layout", check_summary_layout_contract),
    )
    for label, function in checks:
        function()
        print(f"PASS  {label}")
    print(f"PASS  {len(checks)} Finance strain contracts")


if __name__ == "__main__":
    main()
