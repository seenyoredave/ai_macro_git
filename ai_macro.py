"""Primary Streamlit entry point for the AI Economic Research Platform."""

from __future__ import annotations

from datetime import date

import streamlit as st

from analytics.factor_engine import calc_sector_factors
from analytics.regime_engine import build_regime_metrics
from analytics.sector_engine import build_sector_metrics
from archive.archive import (
    append_benchmark_history,
    append_edgar_history,
    append_fred_history,
    append_macro_history,
    append_sector_history,
    append_yf_history,
)
from archive.archive_reader import load_fred_history, load_macro_history
from benchmarks.benchmark_service import get_benchmark_metrics
from config.sector_config import SECTOR_CONFIG
from helpers.render_sector import render_basket_tier_developer_tool
from loaders.construction_loader import load_data_center_construction
from loaders.edgar_loader import build_edgar_archive_snapshot
from loaders.fred_loader import load_fred
from loaders.market_loader import load_market_universe
from loaders.nfci_loader import load_nfci_history
from research_overlay.components import render_masthead
from research_overlay.renderers import render_research_dashboard
from research_overlay.theme import inject_research_theme
from sectors.sector_builder import get_sector_data


APP_VERSION = "v3.15"
APP_STATE_SCHEMA_VERSION = "16.4-market-freshness-capital-dynamics"


st.set_page_config(
    page_title="AI Economic Research Platform",
    layout="wide",
)
inject_research_theme()


if "archive_suspended" not in st.session_state:
    st.session_state.archive_suspended = False

if "sectors" not in st.session_state:
    st.session_state.sectors = {
        sector: SECTOR_CONFIG[sector].copy()
        for sector in SECTOR_CONFIG
    }

if st.session_state.get("app_state_schema_version") != APP_STATE_SCHEMA_VERSION:
    st.session_state.force_rebuild = True
    st.session_state.app_state_schema_version = APP_STATE_SCHEMA_VERSION

if "force_rebuild" not in st.session_state:
    st.session_state.force_rebuild = True

if "tier_test_module_open" not in st.session_state:
    st.session_state.tier_test_module_open = False

if "developer_load_report_open" not in st.session_state:
    st.session_state.developer_load_report_open = False


def build_tabs():
    return st.tabs(["AI MACRO", "FINANCE", "SECTORS", "EVIDENCE"])


def build_sector_dashboard_data():
    sector_data = {}
    sector_metrics = {}

    all_tickers = sorted({
        ticker
        for cfg in st.session_state.sectors.values()
        for ticker in cfg["basket"]
    })
    ticker_map = {ticker: ticker for ticker in all_tickers}

    raw_universe_data = load_market_universe(ticker_map)
    st.session_state.market_universe_load_report = raw_universe_data.get("_load_report", {})
    benchmark_metrics = get_benchmark_metrics("QQQ")

    for sector, cfg in st.session_state.sectors.items():
        df = get_sector_data(
            sector,
            cfg["basket"],
            raw_universe_data=raw_universe_data,
        )
        factor_df = calc_sector_factors(
            sector=sector,
            yf_df=df,
            benchmark_metrics=benchmark_metrics,
        )
        sector_data[sector] = df
        sector_metrics[sector] = build_sector_metrics(factor_df, df)

    return sector_data, sector_metrics, raw_universe_data


def render_developer_load_report(report):
    if not report:
        st.caption("No load report is available yet.")
        return

    def fmt_seconds(value):
        try:
            return f"{float(value):.2f}s"
        except Exception:
            return "n/a"

    def render_source(label, block):
        block = block or {}
        missing = (
            block.get("missing_tickers")
            or block.get("today_missing_tickers")
            or block.get("recent_missing_tickers")
            or []
        )
        fallback_symbols = block.get("archive_fallback_symbols") or []
        st.markdown(f"**{label}**")
        st.write(f"Mode: `{block.get('source_mode', 'unknown')}`")
        st.write(f"Elapsed: `{fmt_seconds(block.get('elapsed_sec'))}`")
        st.write(f"Returned: `{block.get('returned_tickers', 0)}` tickers")
        if "live_tickers" in block:
            st.write(f"Live rows: `{block.get('live_tickers', 0)}` tickers")
            st.write(
                "Archive fallback: "
                f"`{block.get('archive_fallback_tickers', 0)}` ticker rows / "
                f"`{block.get('archive_field_backfills', 0)}` fields"
            )
        if block.get("requested_at_utc"):
            st.write(f"Requested: `{block.get('requested_at_utc')}`")
        if block.get("latest_complete_date"):
            st.write(f"Latest complete archive: `{block.get('latest_complete_date')}`")
        if fallback_symbols:
            shown = ", ".join(fallback_symbols[:30])
            suffix = "" if len(fallback_symbols) <= 30 else f" … +{len(fallback_symbols) - 30}"
            st.caption(f"Archive row fallback ({len(fallback_symbols)}): {shown}{suffix}")
        if missing:
            shown = ", ".join(missing[:30])
            suffix = "" if len(missing) <= 30 else f" … +{len(missing) - 30}"
            st.caption(f"Missing ({len(missing)}): {shown}{suffix}")

    st.caption(f"Total load: {fmt_seconds(report.get('total_elapsed_sec'))}")
    render_source("YFinance", report.get("yfinance"))
    st.markdown("---")
    render_source("EDGAR", report.get("edgar"))


with st.sidebar:
    st.markdown(
        f"""
        <div class="rm-developer-tools-header">
            <span class="rm-developer-tools-title">Developer Tools</span>
            <span class="rm-developer-tools-version">{APP_VERSION}</span>
        </div>
        <div class="rm-developer-tools-divider"></div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("Rebuild dashboard", use_container_width=True):
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Clear cache", use_container_width=True):
        st.cache_data.clear()
        st.session_state.force_rebuild = True
        st.rerun()

    archive_label = "Resume archive" if st.session_state.archive_suspended else "Suspend archive"
    if st.button(archive_label, use_container_width=True):
        st.session_state.archive_suspended = not st.session_state.archive_suspended
        st.rerun()

    st.markdown("---")
    if st.button(
        "Close tier diagnostics" if st.session_state.tier_test_module_open else "Open tier diagnostics",
        use_container_width=True,
    ):
        st.session_state.tier_test_module_open = not st.session_state.tier_test_module_open
        st.rerun()

    if st.button(
        "Close load report" if st.session_state.developer_load_report_open else "Open load report",
        use_container_width=True,
    ):
        st.session_state.developer_load_report_open = not st.session_state.developer_load_report_open
        st.rerun()

    if st.session_state.developer_load_report_open:
        st.markdown("---")
        render_developer_load_report(st.session_state.get("market_universe_load_report"))


if st.session_state.force_rebuild:
    sector_data, sector_metrics, raw_universe_data = build_sector_dashboard_data()

    fred_data = load_fred()
    nfci_history = load_nfci_history()
    construction_data = load_data_center_construction()
    fred_history = load_fred_history()
    macro_history = load_macro_history()

    regime_metrics = build_regime_metrics(
        sector_metrics=sector_metrics,
        sector_data=sector_data,
        fred_history=fred_history,
        fred_data=fred_data,
        construction_data=construction_data,
        macro_history=macro_history,
    )

    if not st.session_state.archive_suspended:
        append_macro_history(regime_metrics, fred_data)
        append_sector_history(sector_metrics)
        append_benchmark_history()
        append_yf_history(sector_data)
        edgar_snapshot = build_edgar_archive_snapshot(
            sector_data,
            raw_universe_data.get("edgar", {}),
        )
        append_edgar_history(edgar_snapshot)
        append_fred_history(fred_data)

    st.session_state.sector_data = sector_data
    st.session_state.sector_metrics = sector_metrics
    st.session_state.fred_data = fred_data
    st.session_state.nfci_history = nfci_history
    st.session_state.construction_data = construction_data
    st.session_state.regime_metrics = regime_metrics
    st.session_state.force_rebuild = False


sector_data = st.session_state.sector_data
sector_metrics = st.session_state.sector_metrics
fred_data = st.session_state.fred_data
nfci_history = st.session_state.get("nfci_history")
regime_metrics = st.session_state.regime_metrics


ticker_count = len({
    ticker
    for df in sector_data.values()
    if df is not None and not df.empty and "Ticker" in df.columns
    for ticker in df["Ticker"].dropna().astype(str)
})

render_masthead(
    "AI Economic Research Platform",
    "A structural assessment of the AI economy linking market expectations, capital deployment, financing conditions, infrastructure constraints, and observable economic validation.",
    [
        ("Run", date.today().isoformat()),
        ("Archive", "suspended" if st.session_state.archive_suspended else "active"),
        ("Universe", f"{len(sector_data)} sectors / {ticker_count} tickers"),
        ("Build", "primary app"),
    ],
)

if st.session_state.tier_test_module_open:
    render_basket_tier_developer_tool(sector_data)
else:
    render_research_dashboard(
        build_tabs(),
        sector_data,
        sector_metrics,
        fred_data,
        regime_metrics,
        nfci_history=nfci_history,
    )
