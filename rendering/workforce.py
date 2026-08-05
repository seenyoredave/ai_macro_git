from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_workforce import current_momentum, indexed_history, level_history
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_date, fmt_number, inject_panel_height_rules, render_domain_read, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.dataframe import arrow_safe_dataframe


def _row(frame: pd.DataFrame, series: str) -> dict:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    rows = frame.loc[frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq(series)]
    return rows.iloc[-1].to_dict() if not rows.empty else {}


def _yoy_text(row: dict) -> str:
    value = pd.to_numeric(row.get("YoY Change"), errors="coerce")
    return fmt_number(value * 100.0, 1, signed=True, suffix="%")


def _render_pulse(data: dict) -> None:
    latest = data.get("employment_latest", pd.DataFrame())
    openings = data.get("job_openings_latest", pd.DataFrame())
    systems = _row(latest, "Computer systems design")
    infra = _row(latest, "Computing infrastructure")
    semis = _row(latest, "Semiconductor manufacturing")
    information_openings = _row(openings, "Information")
    render_section("Workforce pulse", "Employment momentum in directly relevant industries and the broader labor-demand environment.", first=True, compact=True)
    render_statline([
        ("Computer systems design", _yoy_text(systems), f"{fmt_number(systems.get('Value'), 1, suffix='K jobs')} · {fmt_date(systems.get('Date'))}"),
        ("Computing infrastructure", _yoy_text(infra), f"{fmt_number(infra.get('Value'), 1, suffix='K jobs')} · {fmt_date(infra.get('Date'))}"),
        ("Semiconductor manufacturing", _yoy_text(semis), f"{fmt_number(semis.get('Value'), 1, suffix='K jobs')} · {fmt_date(semis.get('Date'))}"),
        ("Information openings", fmt_number(information_openings.get("Value"), 0, suffix="K"), f"{_yoy_text(information_openings)} YoY · {fmt_date(information_openings.get('Date'))}"),
    ], key_prefix="workforce-pulse")


def render_workforce_tab(workforce_data: dict, tab_read=None) -> None:
    inject_panel_height_rules({
        "workforce-panel-employment-history": 505,
        "workforce-panel-employment-momentum": 505,
    })
    render_tab_header(
        "Workforce",
        "Employment, compensation, and labor demand across the industries building, operating, and applying AI.",
        "U.S. Bureau of Labor Statistics",
    )
    render_line_break()
    _render_tab_metric_registry("workforce")
    render_domain_read(tab_read, label="Workforce Read", accent="blue")
    _render_pulse(workforce_data)

    render_section("Labor footprint", "How employment has moved since 2020 across four directly relevant production and deployment channels.")
    left, right = st.columns([1.55, 0.85])
    with left:
        with st.container(border=True, key="workforce-panel-employment-history"):
            render_panel_heading("Employment trajectory", "January 2020 = 100")
            st.plotly_chart(indexed_history(workforce_data.get("employment_history")), width="stretch", config={"displayModeBar": False, "responsive": True}, key="workforce-employment-history")
    with right:
        with st.container(border=True, key="workforce-panel-employment-momentum"):
            render_panel_heading("Current employment momentum", "Year over year")
            st.plotly_chart(current_momentum(workforce_data.get("employment_latest")), width="stretch", config={"displayModeBar": False, "responsive": True}, key="workforce-employment-momentum")
    st.caption("These industries are tightly connected to the AI production and deployment stack. Their employment changes are observed labor-market outcomes, not a count of jobs caused by AI.")

    render_section("Labor demand", "Job openings in the broader labor markets that supply technology, manufacturing, construction, and business-service workers.")
    with st.container(border=True, key="workforce-panel-openings"):
        render_panel_heading("Job openings by supporting labor market", "Thousands of openings")
        st.plotly_chart(level_history(workforce_data.get("job_openings_history"), value_suffix="K"), width="stretch", config={"displayModeBar": False, "responsive": True}, key="workforce-job-openings")
    st.caption("JOLTS industry categories are broader than AI. They measure the hiring environment in which AI-related employers compete for labor; they do not isolate AI-specific vacancies.")

    render_section("Compensation", "Hourly-earnings trajectories in the same directly relevant industries.")
    with st.container(border=True, key="workforce-panel-earnings"):
        render_panel_heading("Average hourly earnings", "BLS Current Employment Statistics")
        st.plotly_chart(level_history(workforce_data.get("earnings_history"), value_suffix="", value_prefix="$"), width="stretch", config={"displayModeBar": False, "responsive": True}, key="workforce-earnings-history")
        st.caption("Nominal dollars per hour. Wage growth can reflect labor scarcity, composition changes, inflation, and bargaining conditions; the chart does not assign those movements to AI alone.")

    with st.expander("Workforce evidence ledger", expanded=False):
        view = st.radio("Ledger", ["Employment", "Hourly earnings", "Job openings", "Sources"], horizontal=True, key="workforce-ledger-view")
        frame = {
            "Employment": workforce_data.get("employment_history"),
            "Hourly earnings": workforce_data.get("earnings_history"),
            "Job openings": workforce_data.get("job_openings_history"),
            "Sources": workforce_data.get("source_manifest"),
        }.get(view)
        st.dataframe(arrow_safe_dataframe(frame), width="stretch", height=420, hide_index=True)
