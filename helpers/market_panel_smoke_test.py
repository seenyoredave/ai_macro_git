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
from config.sector_config import SECTOR_CONFIG
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
from loaders.weekly_context_loader import (
    NO_QUALIFYING_NEWS,
    _news_item_matches,
    _parse_google_news_rss,
    load_weekly_context,
)
from rendering.sector_dossier import (
    build_sector_narrative,
    build_structure_snapshot,
    company_contribution_shoutout,
)


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

    narrative = build_sector_narrative(
        compute_metrics,
        "COMPUTE",
        "Compute",
        compute,
        {"COMPUTE": compute_metrics},
    )
    if not narrative.get("headline") or "Compute" not in narrative.get("body", ""):
        raise AssertionError("Sector narrative is missing its headline or sector context.")
    if narrative.get("weekly_note") is not None:
        raise AssertionError("Unmapped weekly context was forced into the Compute read.")

    diffuse = pd.DataFrame({
        "Ticker": [f"T{index}" for index in range(6)],
        "Market Cap": [100.0] * 6,
        "1Y Return": [0.20, 0.19, 0.18, 0.17, 0.16, 0.15],
    })
    if company_contribution_shoutout(diffuse) is not None:
        raise AssertionError("Diffuse company contributions should not force a shout-out.")
    concentrated = pd.DataFrame({
        "Ticker": ["AAPL", "B", "C", "D", "E", "F"],
        "Market Cap": [900.0, 20.0, 20.0, 20.0, 20.0, 20.0],
        "1Y Return": [0.60, 0.02, 0.01, 0.00, -0.01, -0.02],
    })
    if company_contribution_shoutout(concentrated) is None:
        raise AssertionError("A materially dominant company contribution was not recognized.")

    sector_context = load_weekly_context(
        as_of="2026-08-03", surface="sector", limit=15, include_live=False
    )
    if len(sector_context.get("events", [])) != 15:
        raise AssertionError("Every configured sector must receive a This Week event or explicit no-match status.")
    events_by_sector = {
        event.get("sectors", [""])[0]: event
        for event in sector_context.get("events", [])
    }
    if set(events_by_sector) != set(SECTOR_CONFIG):
        raise AssertionError("Sector weekly context does not cover the configured universe exactly once.")
    data_ai_event = events_by_sector["DATA_AI_INFRASTRUCTURE"]
    if "MSFT" in set(data_ai_event.get("tickers", [])):
        raise AssertionError("Microsoft leaked into Data & AI Infrastructure weekly context.")
    if data_ai_event.get("display") != NO_QUALIFYING_NEWS:
        raise AssertionError("Unmapped offline sector context should use the explicit no-match status.")
    for sector in SECTOR_CONFIG:
        event = events_by_sector[sector]
        sector_narrative = build_sector_narrative(
            compute_metrics,
            sector,
            sector,
            compute,
            {sector: compute_metrics},
            sector_context,
        )
        is_no_match = str(event.get("verification_status") or event.get("status") or "").strip().lower() == "no_match"
        if is_no_match and sector_narrative.get("weekly_note"):
            raise AssertionError(f"{sector} exposed an internal no-match status as news.")
        if not is_no_match and not sector_narrative.get("weekly_note"):
            raise AssertionError(f"{sector} lost its qualifying This Week narrative row.")

    cloud_narrative = build_sector_narrative(
        compute_metrics,
        "CLOUD_HYPERSCALERS",
        "Cloud Hyperscalers",
        compute,
        {"CLOUD_HYPERSCALERS": compute_metrics},
        sector_context,
    )
    if not cloud_narrative.get("weekly_note") or not cloud_narrative.get("reference"):
        raise AssertionError("Mapped seven-day sector context or its reference is missing.")

    rss_fixture = b"""<?xml version='1.0' encoding='UTF-8'?>
    <rss><channel><item>
      <title>Fortinet reports strong security demand - Example News</title>
      <link>https://news.google.com/rss/articles/example</link>
      <pubDate>Mon, 03 Aug 2026 12:00:00 GMT</pubDate>
      <description>Cybersecurity and AI security demand increased.</description>
      <source url='https://example.com'>Example News</source>
    </item></channel></rss>"""
    parsed_items = _parse_google_news_rss(rss_fixture)
    if len(parsed_items) != 1 or not _news_item_matches(parsed_items[0], "CYBERSECURITY_AI_TRUST"):
        raise AssertionError("Live sector-news RSS parsing or relevance filtering failed.")
    if _news_item_matches(parsed_items[0], "ROBOTICS"):
        raise AssertionError("Sector-news relevance filtering leaked a cyber headline into Robotics.")
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
    if 'with st.expander("Market constituents", expanded=False):' not in market_source:
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
