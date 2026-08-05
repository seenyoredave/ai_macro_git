from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_economic_impact import current_outcomes, investment_vs_output, productivity_index
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_date, fmt_number, inject_panel_height_rules, render_domain_read, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.dataframe import arrow_safe_dataframe


def _metric_text(payload: dict) -> str:
    return fmt_number((payload or {}).get("value"), 1, signed=True, suffix="%")


def _render_pulse(data: dict) -> None:
    prod = data.get("nonfarm_productivity", {})
    output = data.get("nonfarm_output", {})
    comp = data.get("nonfarm_compensation", {})
    investment = data.get("information_investment", {})
    render_section("Impact pulse", "Realized output, productivity, compensation, and investment—not market expectations.", first=True, compact=True)
    render_statline([
        ("Labor productivity", _metric_text(prod), f"nonfarm business · {fmt_date(prod.get('date'))}"),
        ("Real output", _metric_text(output), f"nonfarm business · {fmt_date(output.get('date'))}"),
        ("Hourly compensation", _metric_text(comp), f"nonfarm business · {fmt_date(comp.get('date'))}"),
        ("Information investment", fmt_number(investment.get("yoy"), 1, signed=True, suffix="%"), f"quarterly level · {fmt_date(investment.get('date'))}"),
    ], key_prefix="economic-impact-pulse")


def render_economic_impact_tab(economic_impact_data: dict, tab_read=None) -> None:
    inject_panel_height_rules({
        "economic-impact-panel-index": 505,
        "economic-impact-panel-current": 505,
    })
    render_tab_header(
        "Economic Impact",
        "Whether rising AI-related investment and adoption are coinciding with durable gains in output, productivity, and compensation.",
        "BLS / BEA / FRED",
    )
    render_line_break()
    _render_tab_metric_registry("economic_impact")
    render_domain_read(tab_read, label="Economic Impact Read", accent="violet")
    _render_pulse(economic_impact_data)

    render_section("Realized outcomes", "The national nonfarm-business account: what the economy produced, what workers received, and what it cost to produce.")
    left, right = st.columns([1.45, 0.95])
    with left:
        with st.container(border=True, key="economic-impact-panel-index"):
            render_panel_heading("Productivity, output, and compensation", "BLS indexes · 2017 = 100")
            st.plotly_chart(productivity_index(economic_impact_data.get("productivity_history")), width="stretch", config={"displayModeBar": False, "responsive": True}, key="economic-impact-index-history")
    with right:
        with st.container(border=True, key="economic-impact-panel-current"):
            inflation = economic_impact_data.get("inflation", {}) or {}
            inflation_yoy = pd.to_numeric(inflation.get("yoy"), errors="coerce")
            view = st.radio(
                "Growth basis",
                ["Reported", "Inflation-adjusted"],
                horizontal=True,
                index=1,
                label_visibility="collapsed",
                key="economic-impact-growth-basis",
            )
            subtitle = "Latest year-over-year change"
            if view == "Inflation-adjusted" and pd.notna(inflation_yoy):
                subtitle = f"CPI-normalized · inflation {inflation_yoy:.1f}% YoY"
            render_panel_heading("Current realized growth", subtitle)
            st.plotly_chart(
                current_outcomes(
                    economic_impact_data.get("productivity_history"),
                    inflation_yoy=inflation_yoy,
                    inflation_adjusted=view == "Inflation-adjusted",
                ),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key=f"economic-impact-current-outcomes-{view.casefold().replace('-', '_')}",
            )
    st.caption("Productivity and real output are already inflation-adjusted. The alternate frame converts hourly compensation and unit labor costs into CPI-adjusted growth. These economy-wide outcomes do not prove that AI caused a particular quarterly movement.")

    render_section("Investment validation", "Whether the surge in information-processing investment is being accompanied by broader output and productivity gains.")
    with st.container(border=True, key="economic-impact-panel-validation"):
        render_panel_heading("Investment versus realized performance", "Each series rebased to its first 2020 observation")
        st.plotly_chart(investment_vs_output(economic_impact_data.get("investment_history"), economic_impact_data.get("productivity_history")), width="stretch", config={"displayModeBar": False, "responsive": True}, key="economic-impact-investment-validation")
        st.caption("The investment series covers information-processing equipment and software broadly. Co-movement is descriptive; the platform does not infer AI causality from timing alone.")

    render_section("Production economy", "A manufacturing-specific check on whether physical production is sharing in the gains.")
    mprod = economic_impact_data.get("manufacturing_productivity", {})
    mout = economic_impact_data.get("manufacturing_output", {})
    ulc = economic_impact_data.get("nonfarm_unit_labor_cost", {})
    render_statline([
        ("Manufacturing productivity", _metric_text(mprod), fmt_date(mprod.get("date"))),
        ("Manufacturing real output", _metric_text(mout), fmt_date(mout.get("date"))),
        ("Nonfarm unit labor costs", _metric_text(ulc), fmt_date(ulc.get("date"))),
    ], key_prefix="economic-impact-production")

    with st.expander("Economic-impact evidence ledger", expanded=False):
        view = st.radio("Ledger", ["Productivity and costs", "Information investment", "Inflation", "Sources"], horizontal=True, key="economic-impact-ledger-view")
        frame = {
            "Productivity and costs": economic_impact_data.get("productivity_history"),
            "Information investment": economic_impact_data.get("investment_history"),
            "Inflation": economic_impact_data.get("cpi_history"),
            "Sources": economic_impact_data.get("source_manifest"),
        }.get(view)
        st.dataframe(arrow_safe_dataframe(frame), width="stretch", height=420, hide_index=True)
