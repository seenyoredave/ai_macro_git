import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

from archive.archive_reader import load_macro_history

from analytics.trend_engine import calc_metric_trend
from analytics.macro_dataframe import build_macro_dataframe 

from helpers.macro_dashboard import (
    render_regime_snapshot,
    render_sector_assessment,
    render_positioning_charts,
    render_sector_cards,
    render_macro_data,
    render_edgar_data
)


def render_ai_macro_dashboard(
    sector_metrics,
    sector_data=None,
    fred_data=None,
    sentiment_data=None
):

    st.title("AI Regime Dashboard")
    st.caption("AI market structure • positioning • regime analysis")
    st.markdown("---")

    if not sector_metrics:
        st.error("Empty sector_metrics")
        return

    macro_df = build_macro_dataframe(sector_metrics)

    if macro_df is None or macro_df.empty:
        st.error("macro_df build failed")
        return

    macro_history = load_macro_history()

    cycle_trend = calc_metric_trend(
        macro_history,
        "Avg Cycle Score"
    )

    divergence_trend = calc_metric_trend(
        macro_history,
        "AI Divergence"
    )
    
    render_regime_snapshot(macro_df,fred_data,sentiment_data,cycle_trend,divergence_trend)

    render_sector_assessment(macro_df)

    render_positioning_charts(macro_df)

    render_sector_cards(macro_df)

    render_macro_data(fred_data)   
    
    render_edgar_data(sector_data)
                 
