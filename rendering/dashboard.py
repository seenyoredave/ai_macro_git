from __future__ import annotations

from analytics.macro_dataframe import build_macro_dashboard_data
from rendering.adaptation import render_adaptation_tab
from rendering.compute import render_compute_tab
from rendering.data_center import render_data_center_tab
from rendering.energy import render_energy_tab
from rendering.evidence import render_evidence_tab
from rendering.finance import render_finance_tab
from rendering.infrastructure import render_infrastructure_tab
from rendering.macro import render_macro_tab
from rendering.market import render_market_tab
from rendering.water import render_water_tab

def render_research_dashboard(
    tabs,
    sector_data,
    sector_metrics,
    fred_data,
    regime_metrics,
    nfci_history=None,
    energy_data=None,
    debt_markets_data=None,
    infrastructure_data=None,
    water_data=None,
    adaptation_data=None,
    market_universe_summary=None,
):
    dashboard_data = build_macro_dashboard_data(
        sector_metrics=sector_metrics,
        regime_metrics=regime_metrics,
    )

    with tabs[0]:
        render_macro_tab(
            sector_metrics,
            sector_data,
            fred_data,
            regime_metrics,
            dashboard_data,
            adaptation_data or {},
            infrastructure_data or {},
        )
    with tabs[1]:
        render_market_tab(
            sector_metrics,
            sector_data,
            regime_metrics,
            dashboard_data,
            market_universe_summary,
        )
    with tabs[2]:
        render_finance_tab(
            sector_metrics,
            sector_data,
            fred_data,
            regime_metrics,
            nfci_history,
            debt_markets_data or {},
            dashboard_data,
        )
    with tabs[3]:
        render_data_center_tab(infrastructure_data or {})
    with tabs[4]:
        render_compute_tab(infrastructure_data or {})
    with tabs[5]:
        render_infrastructure_tab(infrastructure_data or {})
    with tabs[6]:
        render_energy_tab(
            fred_data,
            regime_metrics,
            energy_data or {},
            dashboard_data,
            infrastructure_data or {},
        )
    with tabs[7]:
        render_water_tab(water_data or {}, infrastructure_data or {})
    with tabs[8]:
        render_adaptation_tab(adaptation_data or {})
    with tabs[9]:
        render_evidence_tab(
            fred_data,
            sector_data,
            regime_metrics,
            energy_data or {},
            debt_markets_data or {},
            infrastructure_data or {},
            water_data or {},
            adaptation_data or {},
        )
