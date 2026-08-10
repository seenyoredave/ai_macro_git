"""Regression checks for Finance strain history, dynamics, and summary layout."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.borrower_strain_engine import normalize_borrower_strain_history
from analytics.capital_commitments import (
    FORWARD_CATEGORIES,
    build_current_commitment_ledger,
    load_commitment_components,
)
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



def check_commitment_component_contract() -> None:
    components = load_commitment_components()
    _check(not components.empty, "Capital commitment component ledger is empty.")
    _check(
        not components.duplicated(["Ticker", "Component ID"]).any(),
        "Capital commitment component IDs are not unique within ticker.",
    )
    included = components.loc[components["Included in Forward Commitments"]]
    _check(
        set(included["Category"]).issubset(FORWARD_CATEGORIES),
        "Forward Commitment numerator includes an unsupported component category.",
    )
    _check(
        included["Source URL"].astype(str).str.startswith("https://").all(),
        "Forward Commitment component is missing a source URL.",
    )
    _check(
        included["Scope"].astype(str).str.strip().ne("").all(),
        "Forward Commitment component is missing scope context.",
    )

    ledger = build_current_commitment_ledger()
    exported = pd.read_csv(PROJECT_ROOT / "data" / "capital_commitments.csv")
    numeric = [
        "Uncommenced Leases",
        "Purchase or Contractual Commitments",
        "Contingent Exposure",
    ]
    merged = ledger.merge(exported, on="Ticker", suffixes=("_built", "_exported"), how="outer", indicator=True)
    _check(set(merged["_merge"]) == {"both"}, "Generated capital commitments export does not match component-ledger membership.")
    for column in numeric:
        built = pd.to_numeric(merged[f"{column}_built"], errors="coerce")
        exported_values = pd.to_numeric(merged[f"{column}_exported"], errors="coerce")
        _check(
            np.allclose(built.fillna(0), exported_values.fillna(0), rtol=0, atol=1),
            f"Generated capital commitments export diverges for {column}.",
        )

    expected_latest_filing = {
        "MSFT": "2026-07-29",
        "GOOG": "2026-07-23",
        "META": "2026-07-30",
        "AMZN": "2026-07-31",
        "NVDA": "2026-05-20",
        "ANET": "2026-08-05",
    }
    for ticker, minimum in expected_latest_filing.items():
        latest = components.loc[components["Ticker"].eq(ticker), "Filing Date"].max()
        _check(
            pd.notna(latest) and latest >= pd.Timestamp(minimum),
            f"{ticker} capital commitments regressed behind the reviewed filing dated {minimum}.",
        )

    iren = components.loc[components["Ticker"].eq("IREN")]
    _check(
        not iren.empty and iren["Carried Forward"].all(),
        "IREN's older reviewed commitment balance is no longer marked as carried forward.",
    )


def check_commitment_ledger_surface() -> None:
    source = (PROJECT_ROOT / "rendering" / "finance.py").read_text(encoding="utf-8")
    _check(
        '"Forward commitment records"' in source and "load_commitment_components()" in source,
        "Finance data ledger no longer exposes component-level forward commitment records.",
    )

def main() -> None:
    checks = (
        ("Lender ten-year history", check_lender_history),
        ("Borrower dynamics", check_borrower_dynamics),
        ("Finance summary layout", check_summary_layout_contract),
        ("Capital commitment components", check_commitment_component_contract),
        ("Capital commitment ledger surface", check_commitment_ledger_surface),
    )
    for label, function in checks:
        function()
        print(f"PASS  {label}")
    print(f"PASS  {len(checks)} Finance strain contracts")


if __name__ == "__main__":
    main()
