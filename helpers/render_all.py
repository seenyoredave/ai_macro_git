from analytics.macro_dataframe import build_macro_dashboard_data
from helpers.render_ai_macro import render_ai_macro_dashboard
from helpers.render_evidence import render_evidence_dashboard
from helpers.render_finance import render_finance_dashboard
from helpers.render_sectors import render_sectors_dashboard


def render_all_dashboards(
    tabs,
    sector_data,
    sector_metrics,
    fred_data,
    regime_metrics,
    nfci_history=None,
):
    """Render the four phase-one research tabs from one shared data context."""
    dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )

    with tabs[0]:
        render_ai_macro_dashboard(
            sector_metrics=sector_metrics,
            sector_data=sector_data,
            fred_data=fred_data,
            regime_metrics=regime_metrics,
            dashboard_data=dashboard_data,
        )

    with tabs[1]:
        render_finance_dashboard(
            sector_metrics=sector_metrics,
            sector_data=sector_data,
            fred_data=fred_data,
            regime_metrics=regime_metrics,
            nfci_history=nfci_history,
            dashboard_data=dashboard_data,
        )

    with tabs[2]:
        render_sectors_dashboard(
            sector_data=sector_data,
            sector_metrics=sector_metrics,
            regime_metrics=regime_metrics,
            dashboard_data=dashboard_data,
        )

    with tabs[3]:
        render_evidence_dashboard(
            fred_data=fred_data,
            sector_data=sector_data,
        )
