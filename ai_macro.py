import streamlit as st

from config.sector_config import SECTOR_CONFIG

from sectors.sector_builder import get_sector_data

from analytics.factor_engine import calc_sector_factors
from analytics.sector_engine import build_sector_metrics
from analytics.regime_engine import build_regime_metrics

from benchmarks.benchmark_service import get_benchmark_metrics

from loaders.fred_loader import load_fred
from loaders.construction_loader import load_data_center_construction
from loaders.market_loader import load_market_universe
from loaders.edgar_loader import build_edgar_archive_snapshot

from helpers.render_all import render_all_dashboards
from helpers.labels import sector_display_name

from archive.archive import (
    append_macro_history,
    append_sector_history,
    append_benchmark_history,
    append_yf_history,
    append_edgar_history,
    append_fred_history
)
from archive.archive_reader import load_fred_history, load_macro_history
from helpers.render_sector import render_basket_tier_developer_tool



#################################################
# PAGE CONFIG
#################################################

st.set_page_config(
    page_title="AI Regime Dashboard",
    layout="wide"
)

st.markdown(
    """
    <style>
    div[data-testid="stTabs"] [role="tablist"] {
        justify-content: center;
    }

    div[data-testid="stTabs"] button[role="tab"] {
        text-transform: uppercase;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True
)


#################################################
# ARCHIVE SUSPEND
#################################################

if "archive_suspended" not in st.session_state:
    st.session_state.archive_suspended = False

#################################################
# DEBUG SWITCH + CACHE CLEARING 
#################################################

with st.sidebar:

    st.markdown("### Developer Tools")

    if st.button("🔄 Rebuild Dashboard"):
        st.session_state.force_rebuild = True
        st.rerun()

    if st.button("🧹 Clear Cache"):
        st.cache_data.clear()
        st.session_state.force_rebuild = True
        st.rerun()

    archive_button_label = (
        "▶️ Resume Archive"
        if st.session_state.archive_suspended
        else "⏸️ Suspend Archive"
    )

    if st.button(archive_button_label):

        st.session_state.archive_suspended = (
            not st.session_state.archive_suspended
        )

        st.rerun()

    st.markdown("---")

    if "tier_test_module_open" not in st.session_state:
        st.session_state.tier_test_module_open = False

    tier_test_button_label = (
        "Close Tier Test Module"
        if st.session_state.tier_test_module_open
        else "Open Tier Test Module"
    )

    if st.button(tier_test_button_label):
        st.session_state.tier_test_module_open = (
            not st.session_state.tier_test_module_open
        )
        st.rerun()

    if "developer_load_report_open" not in st.session_state:
        st.session_state.developer_load_report_open = False

    load_report_button_label = (
        "Close Developer Load Report"
        if st.session_state.developer_load_report_open
        else "Open Developer Load Report"
    )

    if st.button(load_report_button_label):
        st.session_state.developer_load_report_open = (
            not st.session_state.developer_load_report_open
        )
        st.rerun()



def render_developer_load_report(report):
    if not report:
        st.markdown("### Developer Load Report")
        st.caption("No load report is available yet. Rebuild the dashboard to generate one.")
        return

    def fmt_seconds(value):
        try:
            return f"{float(value):.2f}s"
        except Exception:
            return "n/a"

    def render_source_block(label, block):
        block = block or {}
        missing = block.get("today_missing_tickers") or block.get("recent_missing_tickers") or []

        st.markdown(f"**{label}**")
        st.write(f"Source mode: `{block.get('source_mode', 'unknown')}`")
        st.write(f"Elapsed: `{fmt_seconds(block.get('elapsed_sec'))}`")

        if "recent_archive_tickers" in block:
            st.write(
                "Recent archive: "
                f"`{block.get('recent_archive_tickers', 0)}` / "
                f"`{block.get('expected_tickers', 0)}` tickers "
                f"over `{block.get('freshness_days', 0)}` days"
            )

            live_needed = block.get("live_needed_tickers") or []
            live_attempted = block.get("live_attempted_tickers") or []
            live_succeeded = block.get("live_succeeded_tickers") or []
            live_failed = block.get("live_failed_tickers") or []

            st.write(f"Live needed: `{len(live_needed)}` tickers")
            st.write(f"Live attempted: `{len(live_attempted)}` tickers")
            st.write(f"Live succeeded: `{len(live_succeeded)}` tickers")
            st.write(f"Live failed: `{len(live_failed)}` tickers")
        else:
            st.write(
                "Archive today: "
                f"`{block.get('today_archive_tickers', 0)}` / "
                f"`{block.get('expected_tickers', 0)}` tickers"
            )

        st.write(f"Returned: `{block.get('returned_tickers', 0)}` tickers")

        if block.get("latest_complete_date"):
            st.write(f"Latest complete archive: `{block.get('latest_complete_date')}`")

        if missing:
            shown = ", ".join(missing[:40])
            suffix = "" if len(missing) <= 40 else f" ... +{len(missing) - 40} more"
            st.caption(f"Missing/fetched ({len(missing)}): {shown}{suffix}")

    with st.expander("Developer Load Report", expanded=False):
        st.caption("Last universe load")
        st.write(f"Total: `{fmt_seconds(report.get('total_elapsed_sec'))}`")
        st.write(f"Expected tickers: `{report.get('expected_tickers', 0)}`")
        st.markdown("---")
        render_source_block("YFinance", report.get("yfinance"))
        st.markdown("---")
        render_source_block("EDGAR", report.get("edgar"))


#################################################
# DASHBOARD DATA PIPELINE
#################################################
def build_tabs():

    sectors = list(st.session_state.sectors.keys())

    tab_labels = ["AI MACRO"] + [
        sector_display_name(sector, style="upper")
        for sector in sectors
    ]

    tabs = st.tabs(tab_labels)

    return tabs, sectors

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

        tickers = cfg["basket"]

        df = get_sector_data(
            sector,
            tickers,
            raw_universe_data=raw_universe_data
        )

        factor_df = calc_sector_factors(
            sector=sector,
            yf_df=df,
            benchmark_metrics=benchmark_metrics 
        )

        metrics = build_sector_metrics(factor_df, df)

        sector_data[sector] = df
        sector_metrics[sector] = metrics

    return sector_data, sector_metrics, raw_universe_data

#################################################
# SESSION STATE INIT
#################################################

if "sectors" not in st.session_state:

    st.session_state.sectors = {
        sector: SECTOR_CONFIG[sector].copy()
        for sector in SECTOR_CONFIG
    }

if "force_rebuild" not in st.session_state:
    st.session_state.force_rebuild = True


#################################################
# DATA LOAD
#################################################

if st.session_state.force_rebuild:

    sector_data, sector_metrics, raw_universe_data = build_sector_dashboard_data()

    fred_data = load_fred()
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
    
    ###################################
    # ARCHIVE RETRIEVAL + TOGGLE BUTTON
    ###################################
    
    if not st.session_state.archive_suspended:
        append_macro_history(regime_metrics, fred_data)

        append_sector_history(sector_metrics)
        append_benchmark_history()
        append_yf_history(sector_data)
        edgar_archive_snapshot = build_edgar_archive_snapshot(
            sector_data,
            raw_universe_data.get("edgar", {}),
        )
        append_edgar_history(edgar_archive_snapshot)
        append_fred_history(fred_data)

    st.session_state.sector_data = sector_data
    st.session_state.sector_metrics = sector_metrics
    st.session_state.fred_data = fred_data
    st.session_state.construction_data = construction_data
    st.session_state.regime_metrics = regime_metrics

    st.session_state.force_rebuild = False


sector_data = st.session_state.sector_data
sector_metrics = st.session_state.sector_metrics
fred_data = st.session_state.fred_data
regime_metrics = st.session_state.regime_metrics


with st.sidebar:
    if st.session_state.get("developer_load_report_open", False):
        render_developer_load_report(
            st.session_state.get("market_universe_load_report")
        )


#################################################
# RENDER
#################################################

if st.session_state.get("tier_test_module_open", False):
    st.header("Developer Tools")
    render_basket_tier_developer_tool(sector_data)
else:
    tabs, sectors = build_tabs()

    render_all_dashboards(
        tabs,
        sector_data,
        sector_metrics,
        fred_data,
        regime_metrics
    )
