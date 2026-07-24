import streamlit as st

from analytics.macro_dataframe import build_macro_dashboard_data
from config.metric_definitions import METRIC_DEFINITIONS
from helpers.macro_dashboard import (
    render_edgar_data,
    render_macro_data,
    render_positioning_charts,
    render_regime_snapshot,
    render_sector_assessment,
    render_sector_table,
)


def render_ai_macro_dashboard(
    sector_metrics,
    sector_data=None,
    fred_data=None,
    regime_metrics=None,
    nfci_history=None,
):
    st.title("AI Regime Dashboard")
    st.caption("AI equity conditions • physical buildout • capital stress • sector rotation")

    st.markdown("---")

    st.subheader("Purpose Statement")
    # Zero-width label leaves only the native disclosure chevron below the title.
    with st.expander("\u200b", expanded=False):
        st.write(METRIC_DEFINITIONS["Purpose Statement"])

    st.markdown("---")

    macro_dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )

    regime_metrics = macro_dashboard_data["regime_metrics"]
    macro_df = macro_dashboard_data["macro_df"]
    trends = macro_dashboard_data["trends"]

    if macro_df is None or macro_df.empty:
        st.error("Macro dataframe build failed")
        return

    render_regime_snapshot(
        macro_df=macro_df,
        fred_data=fred_data,
        aei_trend=trends["aei_trend"],
        adi_trend=trends["adi_trend"],
        power_stress_trend=trends["power_stress_trend"],
        concentration_trend=trends["concentration_trend"],
        capital_stress_trend=trends["capital_stress_trend"],
        intermediation_stress_trend=trends["intermediation_stress_trend"],
        sector_data=sector_data,
        regime_metrics=regime_metrics,
        nfci_history=nfci_history,
    )

    render_sector_assessment(macro_df, sector_data=sector_data)
    render_positioning_charts(macro_df)

    # The former bubble-card section is now a compact, collapsible table.
    render_sector_table(macro_df)
    render_macro_data(fred_data)
    render_edgar_data(sector_data)
