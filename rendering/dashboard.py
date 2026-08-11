from __future__ import annotations

from analytics.dashboard_context import DashboardContext
from analytics.macro_dataframe import build_macro_dashboard_data
from analytics.read_evidence import build_evidence_packets
from rendering.adoption import render_adoption_tab
from rendering.compute import render_compute_tab
from rendering.connectivity import render_connectivity_tab
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

    if tabs[0].open:
        with tabs[0]:
            render_macro_tab(
                context.sector_metrics,
                context.sector_data,
                context.fred_data,
                context.regime_metrics,
                dashboard_data,
                context.adoption_data,
                context.infrastructure_data,
                tab_read=platform_reads.get("macro"),
            )
    if tabs[1].open:
        with tabs[1]:
            render_market_tab(
                context.sector_metrics,
                context.sector_data,
                context.regime_metrics,
                dashboard_data,
                context.market_universe_summary,
                tab_read=platform_reads.get("market"),
            )
    if tabs[2].open:
        with tabs[2]:
            render_finance_tab(
                context.sector_metrics,
                context.sector_data,
                context.fred_data,
                context.regime_metrics,
                context.nfci_history,
                context.debt_markets_data,
                dashboard_data,
                commercialization_data=context.commercialization_data,
                tab_read=platform_reads.get("finance"),
            )
    if tabs[3].open:
        with tabs[3]:
            render_compute_tab(
                context.infrastructure_data,
                commercialization_data=context.commercialization_data,
                tab_read=platform_reads.get("compute"),
            )
    if tabs[4].open:
        with tabs[4]:
            render_data_center_tab(
                context.infrastructure_data,
                tab_read=platform_reads.get("data_center"),
            )
    if tabs[5].open:
        with tabs[5]:
            render_connectivity_tab(
                context.connectivity_data,
                context.infrastructure_data,
                tab_read=platform_reads.get("connectivity"),
            )
    if tabs[6].open:
        with tabs[6]:
            render_power_tab(
                context.fred_data,
                context.regime_metrics,
                context.energy_data,
                dashboard_data,
                context.infrastructure_data,
                tab_read=platform_reads.get("power"),
            )
    if tabs[7].open:
        with tabs[7]:
            render_grid_storage_tab(
                context.energy_data,
                context.infrastructure_data,
                tab_read=platform_reads.get("grid_storage"),
            )
    if tabs[8].open:
        with tabs[8]:
            render_water_tab(
                context.water_data,
                context.infrastructure_data,
                tab_read=platform_reads.get("water"),
            )
    if tabs[9].open:
        with tabs[9]:
            render_adoption_tab(
                context.adoption_data,
                commercialization_data=context.commercialization_data,
                tab_read=platform_reads.get("adoption"),
            )
    if tabs[10].open:
        with tabs[10]:
            render_workforce_tab(
                context.workforce_data,
                tab_read=platform_reads.get("workforce"),
            )
    if tabs[11].open:
        with tabs[11]:
            render_economic_impact_tab(
                context.economic_impact_data,
                commercialization_data=context.commercialization_data,
                tab_read=platform_reads.get("economic_impact"),
            )
    if tabs[12].open:
        with tabs[12]:
            evidence_packets = {
                domain: packet.to_dict()
                for domain, packet in build_evidence_packets(context).items()
            }
            render_evidence_tab(
                context.fred_data,
                context.sector_data,
                context.sector_metrics,
                context.regime_metrics,
                context.energy_data,
                context.debt_markets_data,
                dashboard_data,
                context.infrastructure_data,
                context.connectivity_data,
                context.water_data,
                context.adoption_data,
                context.workforce_data,
                context.economic_impact_data,
                platform_reads=platform_reads,
                evidence_packets=evidence_packets,
            )
