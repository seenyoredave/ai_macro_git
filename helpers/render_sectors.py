import streamlit as st

from analytics.macro_dataframe import build_macro_dashboard_data
from helpers.labels import sector_display_name
from helpers.macro_dashboard import (
    render_positioning_charts,
    render_sector_assessment,
    render_sector_table,
)
from helpers.render_sector import render_sector_dashboard


def render_sectors_dashboard(
    sector_data,
    sector_metrics,
    regime_metrics=None,
    dashboard_data=None,
):
    """Render the consolidated sector overview and selected-sector detail."""
    st.title("Market")
    st.caption("AI-specific sector analysis with cross-sectional positioning, movement, fundamental evolution, and market performance.")
    st.markdown("---")

    dashboard_data = dashboard_data or build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )
    macro_df = dashboard_data["macro_df"]

    if macro_df is None or macro_df.empty:
        st.error("Sector dataframe build failed")
        return

    render_sector_assessment(macro_df, sector_data=sector_data)
    render_positioning_charts(macro_df)

    st.subheader("Sector Data")
    render_sector_table(macro_df, use_expander=False)
    st.markdown("---")

    available_sectors = [
        sector
        for sector in sector_data
        if sector in sector_metrics
        and sector_data.get(sector) is not None
        and not sector_data[sector].empty
    ]

    if not available_sectors:
        st.warning("No sector detail is available.")
        return

    selected_sector = st.selectbox(
        "Select sector to evaluate",
        available_sectors,
        format_func=sector_display_name,
        key="sector_dashboard_selector",
    )

    st.markdown("---")
    render_sector_dashboard(
        selected_sector,
        sector_data[selected_sector],
        sector_metrics[selected_sector],
    )
