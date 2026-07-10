import streamlit as st

from analytics.macro_dataframe import build_macro_dashboard_data

from config.metric_definitions import METRIC_DEFINITIONS

from helpers.macro_dashboard import (
    render_regime_snapshot,
    render_sector_assessment,
    render_positioning_charts,
    render_sector_cards,
    render_macro_data,
    render_edgar_data
)


def render_ai_macro_dashboard (
    sector_metrics,
    sector_data=None,
    fred_data=None,
    sentiment_data=None,
    regime_metrics=None,
):

    st.title("AI Regime Dashboard")
    st.caption("AI market structure • positioning • regime analysis")
    
    st.markdown("---")
    
    st.subheader("Purpose Statement")
    st.write(METRIC_DEFINITIONS['Purpose Statement'])
    
    st.markdown("---")
        
    macro_dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )

    regime_metrics = macro_dashboard_data["regime_metrics"]
    
    macro_df = macro_dashboard_data["macro_df"]
    trends = macro_dashboard_data["trends"]

    if macro_df is None or macro_df.empty:
        st.error("macro_df build failed")
        return
    
    render_regime_snapshot(
        macro_df=macro_df,
        fred_data=fred_data,
        sentiment_data=sentiment_data,
        cycle_trend=trends["cycle_trend"],
        divergence_trend=trends["divergence_trend"],
        power_stress_trend=trends["power_stress_trend"],
        concentration_trend=trends["concentration_trend"],
        sector_data=sector_data,
        regime_metrics=regime_metrics,
    )

    render_sector_assessment(macro_df, sector_data=sector_data)

    render_positioning_charts(macro_df)

    render_sector_cards(macro_df)

    render_macro_data(fred_data)   
    
    render_edgar_data(sector_data)
                 
