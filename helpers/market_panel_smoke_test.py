"""Targeted smoke test for the Market visual system and sector dossier."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.factor_engine import calc_sector_factors
from analytics.market_ledger import _company_ownership, _one_year_contributions
from analytics.sector_engine import build_sector_metrics
from archive.archive_reader import load_yf_history
from config.factor_config import FACTOR_DISPLAY_NAMES
from rendering.charts_market import (
    MARKET_COLORS,
    MARKET_SEQUENTIAL_SCALE,
    concentration_history_chart,
    earnings_support_map,
    market_ownership_treemap,
    participation_history_chart,
    return_contribution_chart,
    sector_signal_anatomy_chart,
    speculative_load_matrix,
)
from rendering.sector_dossier import build_structure_interpretation, build_structure_snapshot


def main() -> None:
    history = load_yf_history()
    if history is None or history.empty or "Date" not in history.columns:
        raise AssertionError("Retained YFinance history is unavailable.")

    dates = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    latest_date = dates.max()
    current = history.loc[dates.eq(latest_date)].copy()
    companies = _company_ownership(current)
    contributions, metadata = _one_year_contributions(current)

    if companies.empty:
        raise AssertionError("Ownership table is empty.")
    if contributions.empty:
        raise AssertionError(f"1-year contribution table is empty: {metadata}")
    if not np.isclose(contributions["Start Weight"].sum(), 1.0, atol=1e-12):
        raise AssertionError("1-year start weights do not sum to one.")
    if not np.allclose(
        contributions["Contribution"],
        contributions["Start Weight"] * contributions["Price Return"],
        equal_nan=True,
    ):
        raise AssertionError("Contribution identity failed.")

    treemap = market_ownership_treemap(companies)
    trace = treemap.data[0]
    sector_nodes = [index for index, parent in enumerate(trace.parents) if parent == "universe"]
    sector_colors = [trace.marker.colors[index] for index in sector_nodes]
    if len(set(sector_colors)) != len(sector_nodes):
        raise AssertionError("Sector overview colors are not unique and stable.")
    if not all(str(trace.labels[index]).strip() for index in sector_nodes):
        raise AssertionError("A sector overview label is blank.")
    if trace.pathbar.visible is not True:
        raise AssertionError("Treemap navigation path is disabled.")

    return_chart = return_contribution_chart(contributions)
    categories = list(return_chart.data[0].y)
    if "Other" in categories and categories[0] != "Other":
        raise AssertionError("Other is not pinned to the bottom of the return chart.")
    return_colors = set(return_chart.data[0].marker.color)
    allowed_return_colors = {
        MARKET_COLORS["positive"],
        MARKET_COLORS["negative"],
        MARKET_COLORS["neutral_deep"],
    }
    if not return_colors.issubset(allowed_return_colors):
        raise AssertionError(f"Unexpected return colors: {sorted(return_colors)}")

    sector_history = pd.read_csv(PROJECT_ROOT / "archive" / "sector_history.csv")
    sector_history["Date"] = pd.to_datetime(
        sector_history["Date"], errors="coerce", format="mixed"
    )
    latest_sector_date = sector_history["Date"].max()
    current_sectors = sector_history.loc[
        sector_history["Date"].eq(latest_sector_date)
    ].copy()
    concentration = concentration_history_chart(
        pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=2),
            "Top 6 Share": [0.50, 0.51],
            "Top 10 Share": [0.62, 0.63],
            "Effective Firms": [18.0, 18.5],
        })
    )
    participation = participation_history_chart(
        pd.DataFrame({
            "Date": pd.date_range("2026-01-01", periods=2),
            "Cap-Weighted Return": [0.00, 0.02],
            "Equal-Weighted Return": [0.00, 0.01],
            "Median Return": [0.00, 0.005],
        })
    )
    expected_series_colors = [
        MARKET_COLORS["primary"],
        MARKET_COLORS["secondary"],
        MARKET_COLORS["neutral"],
    ]
    if [trace.line.color for trace in concentration.data] != expected_series_colors:
        raise AssertionError("Concentration series do not use the Market palette hierarchy.")
    if [trace.line.color for trace in participation.data] != expected_series_colors:
        raise AssertionError("Participation series do not use the Market palette hierarchy.")

    expected_scale = tuple((float(position), color) for position, color in MARKET_SEQUENTIAL_SCALE)
    earnings = earnings_support_map(current_sectors)
    speculative = speculative_load_matrix(current_sectors)
    if tuple(earnings.data[0].marker.colorscale) != expected_scale:
        raise AssertionError("Earnings Support is not using the unified Market scale.")
    if tuple(speculative.data[0].marker.colorscale) != expected_scale:
        raise AssertionError("Speculative Load is not using the unified Market scale.")
    if earnings.layout.plot_bgcolor != MARKET_COLORS["plot"]:
        raise AssertionError("Market chart surface is inconsistent.")

    benchmark_history = pd.read_csv(PROJECT_ROOT / "archive" / "benchmark_history.csv")
    benchmark_history["Date"] = pd.to_datetime(
        benchmark_history["Date"], errors="coerce", format="mixed"
    )
    benchmark_row = benchmark_history.sort_values("Date", kind="stable").iloc[-1]
    compute = current.loc[current["Sector"].eq("COMPUTE")].copy()
    factor_input = calc_sector_factors(
        "COMPUTE",
        compute,
        benchmark_metrics={
            "avg_return": benchmark_row.get("Avg Return"),
            "forward_ebit_yield": benchmark_row.get("Forward EBIT Yield"),
        },
    )
    compute_metrics = build_sector_metrics(factor_input, compute)
    factor_frame = compute_metrics["Scored Factors"].copy()
    factor_frame["Factor"] = factor_frame["Factor"].map(
        lambda name: FACTOR_DISPLAY_NAMES.get(name, str(name))
    )
    anatomy = sector_signal_anatomy_chart(
        factor_frame,
        compute_metrics["Pressure Components"],
    )
    if len(anatomy.data) != 2:
        raise AssertionError("Signal anatomy must contain one AEI trace and one pressure trace.")
    if [trace.marker.color for trace in anatomy.data] != [
        MARKET_COLORS["primary"],
        MARKET_COLORS["secondary"],
    ]:
        raise AssertionError("Signal anatomy does not use the Market palette hierarchy.")
    if list(anatomy.layout.xaxis2.range) != [0, 108]:
        raise AssertionError("Signal anatomy is not using the shared normalized scale.")

    structure_copy = build_structure_interpretation(compute_metrics)
    if not structure_copy or "market-cap" not in structure_copy.casefold():
        raise AssertionError("Sector structure interpretation lost its measured market-structure context.")

    snapshot = dict(build_structure_snapshot(compute_metrics, len(compute)))
    required_snapshot = {
        "Constituents",
        "Effective firms",
        "Adjusted HHI",
        "Loss-making EV",
        "Profitable cohort",
        "Market-cap data",
    }
    if set(snapshot) != required_snapshot:
        raise AssertionError("Structure snapshot is missing required facts.")

    market_source = (PROJECT_ROOT / "rendering" / "market.py").read_text()
    sector_source = (PROJECT_ROOT / "rendering" / "sector_dossier.py").read_text()
    if "Sector read" in market_source or "build_sector_narrative" in market_source or "build_sector_narrative" in sector_source:
        raise AssertionError("Retired deterministic Sector read commentary remains reachable.")
    if 'with st.expander("Company records", expanded=False):' not in market_source:
        raise AssertionError("Constituent ledger is not collapsed by default.")
    if '_render_market_constituent_ledger(selection, market_ledger)' not in market_source:
        raise AssertionError("Constituent ledger no longer finishes the Market workflow.")

    print(
        "PASS  Market visual-system and sector-dossier smoke test · "
        f"{len(companies)} ownership companies · "
        f"{len(contributions)} return companies · "
        f"{len(sector_nodes)} sectors"
    )


if __name__ == "__main__":
    main()
