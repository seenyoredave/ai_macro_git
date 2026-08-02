from __future__ import annotations

import streamlit as st

from analytics.factor_engine import calc_sector_factors
from analytics.macro_interpretation import build_macro_interpretation
from analytics.regime_engine import build_regime_metrics
from analytics.sector_engine import build_sector_metrics
from archive.archive import (
    append_benchmark_history,
    append_edgar_history,
    append_energy_history,
    append_fred_history,
    append_macro_history,
    append_sector_history,
    append_yf_history,
)
from archive.archive_reader import load_fred_history, load_macro_history
from benchmarks.benchmark_service import get_benchmark_metrics
from config.market_clock import market_date
from config.sector_config import SECTOR_CONFIG
from rendering.sector import render_basket_tier_developer_tool
from loaders.construction_loader import load_data_center_construction
from loaders.debt_markets_loader import load_debt_markets_data
from loaders.edgar_loader import build_edgar_archive_snapshot
from loaders.energy_loader import load_energy_data
from loaders.infrastructure_loader import load_infrastructure_data
from loaders.water_loader import load_water_utilization_data
from loaders.adaptation_loader import load_adaptation_data
from loaders.fred_loader import load_fred
from loaders.market_loader import load_market_universe
from loaders.nfci_loader import load_nfci_history
from loaders.weekly_context_loader import load_weekly_context
from rendering.components import render_masthead
from rendering.dashboard import render_research_dashboard
from rendering.theme import inject_research_theme
from analytics.sector_builder import get_sector_data
from analytics.spatial_context import attach_water_context

APP_VERSION = "v5.14"
APP_STATE_SCHEMA_VERSION = "37.0-v5.14-spatial-platform"

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

if "force_yfinance_refresh" not in st.session_state:
    st.session_state.force_yfinance_refresh = False

if "force_edgar_refresh" not in st.session_state:
    st.session_state.force_edgar_refresh = False

if "yfinance_refresh_token" not in st.session_state:
    st.session_state.yfinance_refresh_token = 0

if "edgar_refresh_token" not in st.session_state:
    st.session_state.edgar_refresh_token = 0

if "force_energy_refresh" not in st.session_state:
    st.session_state.force_energy_refresh = False

if "energy_refresh_token" not in st.session_state:
    st.session_state.energy_refresh_token = 0

if "force_debt_markets_refresh" not in st.session_state:
    st.session_state.force_debt_markets_refresh = False

if "debt_markets_refresh_token" not in st.session_state:
    st.session_state.debt_markets_refresh_token = 0

if "force_infrastructure_refresh" not in st.session_state:
    st.session_state.force_infrastructure_refresh = False

if "infrastructure_refresh_token" not in st.session_state:
    st.session_state.infrastructure_refresh_token = 0

if "force_adaptation_refresh" not in st.session_state:
    st.session_state.force_adaptation_refresh = False

if "adaptation_refresh_token" not in st.session_state:
    st.session_state.adaptation_refresh_token = 0

def build_tabs():
    return st.tabs(["AI MACRO", "MARKET", "FINANCE", "DATA CENTER", "COMPUTE", "INFRASTRUCTURE", "ENERGY", "WATER", "ADAPTATION", "EVIDENCE"])

def build_sector_dashboard_data():
    sector_data = {}
    sector_metrics = {}

    all_tickers = sorted({
        ticker
        for cfg in st.session_state.sectors.values()
        for ticker in cfg["basket"]
    })
    ticker_map = {ticker: ticker for ticker in all_tickers}

    raw_universe_data = load_market_universe(
        ticker_map,
        force_yfinance_refresh=st.session_state.force_yfinance_refresh,
        yfinance_refresh_token=st.session_state.yfinance_refresh_token,
        force_edgar_refresh=st.session_state.force_edgar_refresh,
        edgar_refresh_token=st.session_state.edgar_refresh_token,
    )
    st.session_state.market_universe_load_report = raw_universe_data.get("_load_report", {})
    benchmark_metrics = get_benchmark_metrics(
        "QQQ",
        force_refresh=st.session_state.force_yfinance_refresh,
        refresh_token=st.session_state.yfinance_refresh_token,
    )

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

    return sector_data, sector_metrics, raw_universe_data, benchmark_metrics

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
        returned = block.get("returned_series", block.get("returned_tickers", 0))
        unit = "series" if "returned_series" in block else "tickers"
        st.write(f"Returned: `{returned}` {unit}")
        if block.get("decision"):
            st.write(f"Decision: `{block.get('decision')}`")
        if block.get("refresh_trigger"):
            st.write(f"Trigger: `{block.get('refresh_trigger')}`")
        if "archive_tickers" in block:
            st.write(f"Archive rows: `{block.get('archive_tickers', 0)}` tickers")
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
        if block.get("error"):
            st.error(str(block.get("error")))
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
    st.markdown("---")
    render_source("Energy", report.get("energy"))
    st.markdown("---")
    render_source("Debt Markets", report.get("debt_markets"))

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

    if st.button("Refresh Dashboard", use_container_width=True):
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Refresh YFinance", use_container_width=True):
        st.session_state.yfinance_refresh_token += 1
        st.session_state.force_yfinance_refresh = True
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Refresh EDGAR", use_container_width=True):
        st.session_state.edgar_refresh_token += 1
        st.session_state.force_edgar_refresh = True
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Refresh Energy", use_container_width=True):
        st.session_state.energy_refresh_token += 1
        st.session_state.force_energy_refresh = True
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Refresh Debt Markets", use_container_width=True):
        st.session_state.debt_markets_refresh_token += 1
        st.session_state.force_debt_markets_refresh = True
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Refresh Infrastructure", use_container_width=True):
        st.session_state.infrastructure_refresh_token += 1
        st.session_state.force_infrastructure_refresh = True
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("Refresh Adaptation", use_container_width=True):
        st.session_state.adaptation_refresh_token += 1
        st.session_state.force_adaptation_refresh = True
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
    sector_data, sector_metrics, raw_universe_data, benchmark_metrics = (
        build_sector_dashboard_data()
    )

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

    energy_data = load_energy_data(
        fred_data=fred_data,
        force_refresh=st.session_state.force_energy_refresh,
        refresh_token=st.session_state.energy_refresh_token,
    )
    debt_markets_data = load_debt_markets_data(
        force_refresh=st.session_state.force_debt_markets_refresh,
        refresh_token=st.session_state.debt_markets_refresh_token,
    )
    infrastructure_data = load_infrastructure_data(
        force_refresh=st.session_state.force_infrastructure_refresh,
        refresh_token=st.session_state.infrastructure_refresh_token,
    )
    water_data = load_water_utilization_data()
    infrastructure_data, water_data = attach_water_context(infrastructure_data, water_data)
    adaptation_data = load_adaptation_data(
        force_refresh=st.session_state.force_adaptation_refresh,
        refresh_token=st.session_state.adaptation_refresh_token,
    )
    weekly_context = load_weekly_context(as_of=market_date())
    regime_metrics["Macro Interpretation"] = build_macro_interpretation(
        regime_metrics=regime_metrics,
        macro_history=macro_history,
        debt_markets_data=debt_markets_data,
        energy_data=energy_data,
        fred_data=fred_data,
        nfci_history=nfci_history,
        infrastructure_data=infrastructure_data,
        adaptation_data=adaptation_data,
        weekly_context=weekly_context,
    )
    market_report = dict(st.session_state.get("market_universe_load_report", {}) or {})
    market_report["energy"] = energy_data.get("load_report", {})
    market_report["debt_markets"] = debt_markets_data.get("load_report", {})
    market_report["total_elapsed_sec"] = float(
        market_report.get("total_elapsed_sec", 0.0) or 0.0
    ) + float((energy_data.get("load_report", {}) or {}).get("elapsed_sec", 0.0) or 0.0)
    market_report["total_elapsed_sec"] += float(
        (debt_markets_data.get("load_report", {}) or {}).get("elapsed_sec", 0.0) or 0.0
    )
    st.session_state.market_universe_load_report = market_report

    if not st.session_state.archive_suspended:
        append_macro_history(regime_metrics, fred_data)
        append_sector_history(sector_metrics)
        benchmark_source_mode = str(benchmark_metrics.get("source_mode", ""))
        if benchmark_source_mode == "live":
            append_benchmark_history({"QQQ": benchmark_metrics})

        yfinance_source_mode = str(
            ((raw_universe_data.get("_load_report", {}) or {}).get("yfinance", {}) or {}).get(
                "source_mode",
                "",
            )
        )
        if yfinance_source_mode in {"live_complete", "live_with_archive_fallback"}:
            append_yf_history(sector_data)
        edgar_snapshot = build_edgar_archive_snapshot(
            sector_data,
            raw_universe_data.get("edgar", {}),
        )
        append_edgar_history(edgar_snapshot)
        append_fred_history(fred_data)
        append_energy_history(energy_data)

    st.session_state.sector_data = sector_data
    st.session_state.sector_metrics = sector_metrics
    st.session_state.fred_data = fred_data
    st.session_state.nfci_history = nfci_history
    st.session_state.construction_data = construction_data
    st.session_state.regime_metrics = regime_metrics
    st.session_state.energy_data = energy_data
    st.session_state.debt_markets_data = debt_markets_data
    st.session_state.infrastructure_data = infrastructure_data
    st.session_state.water_data = water_data
    st.session_state.adaptation_data = adaptation_data
    st.session_state.force_yfinance_refresh = False
    st.session_state.force_edgar_refresh = False
    st.session_state.force_energy_refresh = False
    st.session_state.force_debt_markets_refresh = False
    st.session_state.force_infrastructure_refresh = False
    st.session_state.force_adaptation_refresh = False
    st.session_state.force_rebuild = False

sector_data = st.session_state.sector_data
sector_metrics = st.session_state.sector_metrics
fred_data = st.session_state.fred_data
nfci_history = st.session_state.get("nfci_history")
regime_metrics = st.session_state.regime_metrics
energy_data = st.session_state.get("energy_data", {})
debt_markets_data = st.session_state.get("debt_markets_data", {})
infrastructure_data = st.session_state.get("infrastructure_data", {})
water_data = st.session_state.get("water_data", {})
adaptation_data = st.session_state.get("adaptation_data", {})

loaded_ticker_count = sum(
    len({str(ticker).strip() for ticker in frame["Ticker"].dropna() if str(ticker).strip()})
    for frame in sector_data.values()
    if frame is not None and not frame.empty and "Ticker" in frame.columns
)
configured_ticker_count = sum(
    len({str(ticker).strip() for ticker in config.get("basket", []) if str(ticker).strip()})
    for config in st.session_state.sectors.values()
)
market_universe_summary = {
    "loaded_sectors": sum(
        1 for frame in sector_data.values()
        if frame is not None and not frame.empty and "Ticker" in frame.columns
    ),
    "configured_sectors": len(st.session_state.sectors),
    "loaded_tickers": int(loaded_ticker_count),
    "configured_tickers": int(configured_ticker_count),
}

render_masthead(
    "AI Economic Research Platform",
    "market conditions • capital deployment • financing • infrastructure development • resource utilization • observable economic validation",
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
        energy_data=energy_data,
        debt_markets_data=debt_markets_data,
        infrastructure_data=infrastructure_data,
        water_data=water_data,
        adaptation_data=adaptation_data,
        market_universe_summary=market_universe_summary,
    )
