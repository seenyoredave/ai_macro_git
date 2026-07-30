import streamlit as st

from analytics.macro_dataframe import build_macro_dashboard_data
from helpers.macro_dashboard import render_finance_snapshot


def render_finance_dashboard(
    sector_metrics,
    sector_data=None,
    fred_data=None,
    regime_metrics=None,
    nfci_history=None,
    dashboard_data=None,
):
    """Render the financing and financial-condition tab."""
    st.title("Finance")
    st.caption("Buildout funding • borrower condition • intermediation strain • financial conditions")
    st.markdown("---")

    dashboard_data = dashboard_data or build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )

    macro_df = dashboard_data["macro_df"]
    trends = dashboard_data["trends"]
    regime_metrics = dashboard_data["regime_metrics"]

    if macro_df is None or macro_df.empty:
        st.error("Macro dataframe build failed")
        return

    render_finance_snapshot(
        macro_df=macro_df,
        fred_data=fred_data,
        sector_data=sector_data,
        regime_metrics=regime_metrics,
        borrower_financial_condition_trend=trends["borrower_financial_condition_trend"],
        intermediation_strain_trend=trends["intermediation_strain_trend"],
        nfci_history=nfci_history,
    )
