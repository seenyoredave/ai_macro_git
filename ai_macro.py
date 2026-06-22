import streamlit as st
import pandas as pd
import numpy as np

from config.sector_config import SECTOR_CONFIG
from config.debug_config import DEBUG 
from config.debug_config import debug_print 

from sectors.sector_builder import get_sector_data

from analytics.factor_engine import calc_sector_factors
from analytics.sector_engine import build_sector_metrics

from benchmarks.benchmark_service import get_benchmark_metrics

from loaders.fred_loader import load_fred
from loaders.sentiment_loader import load_put_call

from helpers.render_all import render_all_dashboards
from helpers.labels import sector_display_name

from archive.archive import (
    append_macro_history,
    append_sector_history,
    append_benchmark_history,
    append_yf_history,
    append_edgar_history,
    append_put_call_history,
    append_fred_history
    
)



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


def build_dashboard_data():

    sector_data = {}
    sector_metrics = {}

    for sector, cfg in st.session_state.sectors.items():

        tickers = cfg["basket"]

        # 1. raw sector universe
        df = get_sector_data(sector, tickers)
    
        # 2. benchmark-aware factor generation
        factor_df = calc_sector_factors(
            sector=sector,
            yf_df=df,
            benchmark="QQQ"
        )
        
        #3 sector aggregation 
        metrics = build_sector_metrics(factor_df, df)

        sector_data[sector] = df
        sector_metrics[sector] = metrics

    return sector_data, sector_metrics  

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

    sector_data, sector_metrics = build_dashboard_data()

    fred_data = load_fred()
    market_sentiment = load_put_call()
    
    ###################################
    # ARCHIVE RETRIEVAL + TOGGLE BUTTON
    ###################################
    
    if not st.session_state.archive_suspended:

        append_macro_history(
            sector_metrics,
            fred_data,
            market_sentiment,
            sector_data=sector_data
        )

        append_sector_history(sector_metrics)
        append_benchmark_history()
        append_yf_history(sector_data)
        append_edgar_history(sector_data)
        append_put_call_history(market_sentiment)
        append_fred_history(fred_data)
   

    st.session_state.sector_data = sector_data
    st.session_state.sector_metrics = sector_metrics
    st.session_state.fred_data = fred_data
    st.session_state.market_sentiment = market_sentiment

    st.session_state.force_rebuild = False


sector_data = st.session_state.sector_data
sector_metrics = st.session_state.sector_metrics
fred_data = st.session_state.fred_data
market_sentiment = st.session_state.market_sentiment


#################################################
# RENDER
#################################################

tabs, sectors = build_tabs()

render_all_dashboards(
    tabs,
    sectors,
    sector_data,
    sector_metrics,
    fred_data,
    market_sentiment
)
        