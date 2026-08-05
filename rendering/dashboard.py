from __future__ import annotations

from analytics.dashboard_context import DashboardContext
from analytics.macro_dataframe import build_macro_dashboard_data
from rendering.adaptation import render_adaptation_tab
from rendering.compute import render_compute_tab
from rendering.data_center import render_data_center_tab
from rendering.economic_impact import render_economic_impact_tab
from rendering.evidence import render_evidence_tab
from rendering.finance import render_finance_tab
from rendering.grid_storage import render_grid_storage_tab
from rendering.macro import render_macro_tab
from rendering.market import render_market_tab
from rendering.power import render_power_tab
from rendering.water import render_water_tab
from rendering.workforce import render_workforce_tab



def render_research_dashboard(tabs, context: DashboardContext):
    """Render all dashboard surfaces from one explicit application payload."""
    if not isinstance(context, DashboardContext):
        raise TypeError("context must be a DashboardContext")
    dashboard_data = context.dashboard_data or build_macro_dashboard_data(
        sector_metrics=context.sector_metrics,
        regime_metrics=context.regime_metrics,
    )
    platform_reads = context.platform_reads

    with tabs[0]:
        render_macro_tab(
            context.sector_metrics,
            context.sector_data,
            context.fred_data,
            context.regime_metrics,
            dashboard_data,
            context.adaptation_data,
            context.infrastructure_data,
            tab_read=platform_reads.get("macro"),
        )
    with tabs[1]:
        render_market_tab(
            context.sector_metrics,
            context.sector_data,
            context.regime_metrics,
            dashboard_data,
            context.market_universe_summary,
            weekly_context=context.sector_weekly_context,
            tab_read=platform_reads.get("market"),
        )
    with tabs[2]:
        render_finance_tab(
            context.sector_metrics,
            context.sector_data,
            context.fred_data,
            context.regime_metrics,
            context.nfci_history,
            context.debt_markets_data,
            dashboard_data,
            tab_read=platform_reads.get("finance"),
        )
    with tabs[3]:
        render_compute_tab(context.infrastructure_data, tab_read=platform_reads.get("compute"))
    with tabs[4]:
        render_data_center_tab(
            context.infrastructure_data,
            tab_read=platform_reads.get("data_center"),
        )
    with tabs[5]:
        render_power_tab(
            context.fred_data,
            context.regime_metrics,
            context.energy_data,
            dashboard_data,
            context.infrastructure_data,
            tab_read=platform_reads.get("power"),
        )
    with tabs[6]:
        render_grid_storage_tab(
            context.energy_data,
            context.infrastructure_data,
            tab_read=platform_reads.get("grid_storage"),
        )
    with tabs[7]:
        render_water_tab(
            context.water_data,
            context.infrastructure_data,
            tab_read=platform_reads.get("water"),
        )
    with tabs[8]:
        render_adaptation_tab(
            context.adaptation_data,
            tab_read=platform_reads.get("adaptation"),
        )
    with tabs[9]:
        render_workforce_tab(
            context.workforce_data,
            tab_read=platform_reads.get("workforce"),
        )
    with tabs[10]:
        render_economic_impact_tab(
            context.economic_impact_data,
            tab_read=platform_reads.get("economic_impact"),
        )
    with tabs[11]:
        render_evidence_tab(
            context.fred_data,
            context.sector_data,
            context.sector_metrics,
            context.regime_metrics,
            context.energy_data,
            context.debt_markets_data,
            dashboard_data,
            context.infrastructure_data,
            context.water_data,
            context.adaptation_data,
            context.workforce_data,
            context.economic_impact_data,
        )
