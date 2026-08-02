from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_infrastructure import compute_capacity_utilization_history, compute_manufacturing_output_history, compute_project_investment_bars
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_date, fmt_number, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.dataframe import arrow_safe_dataframe


def _compute_series_item(infrastructure_data, name):
    compute = (infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    return ((compute.get("series", {}) or {}).get(name, {}) or {})


def _compute_index_value(item, *, suffix=""):
    value = pd.to_numeric((item or {}).get("value"), errors="coerce")
    return "n/a" if pd.isna(value) else f"{value:,.1f}{suffix}"


def _compute_index_change(item):
    growth = pd.to_numeric((item or {}).get("yoy_growth"), errors="coerce")
    return "year over year n/a" if pd.isna(growth) else f"{growth * 100:+.1f}% year over year"


def _compute_summary_detail(item):
    return f"{_compute_index_change(item)} · as of {fmt_date((item or {}).get('date'))}"


def _render_industrial_output(infrastructure_data):
    compute = (infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    history = compute.get("history")
    computers = _compute_series_item(infrastructure_data, "Computer and Peripheral Equipment Output")
    communications = _compute_series_item(infrastructure_data, "Communications Equipment Output")
    semiconductor = _compute_series_item(infrastructure_data, "Semiconductor and Electronic Component Output")
    render_statline(
        [
            ("Computers / peripherals", _compute_index_value(computers), _compute_summary_detail(computers)),
            ("Communications equipment", _compute_index_value(communications), _compute_summary_detail(communications)),
            ("Semiconductors / components", _compute_index_value(semiconductor), _compute_summary_detail(semiconductor)),
        ],
        key_prefix="compute-industrial-output",
    )
    with st.container(border=True):
        render_panel_heading("Domestic compute-related output", "Federal Reserve G.17 · 2017=100")
        st.plotly_chart(
            compute_manufacturing_output_history(history),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="compute-output-history",
        )


def _render_factory_constraint(infrastructure_data):
    compute = (infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    history = compute.get("history")
    computer_utilization = _compute_series_item(infrastructure_data, "Computer and Peripheral Equipment Capacity Utilization")
    semiconductor_utilization = _compute_series_item(infrastructure_data, "Semiconductor and Electronic Component Capacity Utilization")
    render_statline(
        [
            ("Computer utilization", _compute_index_value(computer_utilization, suffix="%"), fmt_date(computer_utilization.get("date"))),
            ("Semiconductor utilization", _compute_index_value(semiconductor_utilization, suffix="%"), fmt_date(semiconductor_utilization.get("date"))),
        ],
        key_prefix="compute-factory-constraint",
    )
    with st.container(border=True):
        render_panel_heading("Factory utilization", "Federal Reserve G.17 · percent of capacity")
        st.plotly_chart(
            compute_capacity_utilization_history(history),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="compute-utilization-history",
        )


def _render_capacity_buildout(infrastructure_data):
    compute = (infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    projects = compute.get("projects")
    project_summary = compute.get("project_summary", {}) or {}
    if not isinstance(projects, pd.DataFrame):
        projects = pd.DataFrame()
    render_statline(
        [
            ("Projects", f"{int(project_summary.get('projects', 0) or 0):,}", "award-backed facilities"),
            ("States", f"{int(project_summary.get('states', 0) or 0):,}", f"{int(project_summary.get('portfolios', 0) or 0):,} portfolios"),
            ("Expected investment", "$" + fmt_number(project_summary.get("expected_capex_usd_b"), 1, suffix="B"), "announced portfolio capex"),
            ("Direct awards", "$" + fmt_number(project_summary.get("direct_funding_usd_b"), 1, suffix="B"), "federal award amounts"),
        ],
        key_prefix="compute-buildout-summary",
    )
    with st.container(border=True):
        render_panel_heading("Manufacturing investment", "NIST CHIPS awards · announced capital spending")
        st.plotly_chart(
            compute_project_investment_bars(projects),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="compute-project-investment",
        )

    if not projects.empty:
        fields = [
            "Recipient", "Facility", "State", "Status", "Component Layer", "AI Relevance",
            "Technology", "Planned Output", "Cleanroom Square Feet", "Production Timeline",
            "Expected CapEx USD B", "Direct Funding USD B", "Evidence Grade", "Source URL",
        ]
        fields = [field for field in fields if field in projects.columns]
        with st.expander(f"Compute project ledger · {len(projects):,} records", expanded=False):
            st.dataframe(arrow_safe_dataframe(projects[fields]), width="stretch", hide_index=True)


def render_compute_tab(infrastructure_data):
    render_tab_header(
        "Compute",
        "The domestic compute supply system: industrial output, factory constraint, capacity buildout, and realized production evidence.",
        "Federal Reserve G.17 / NIST CHIPS",
    )
    render_line_break()
    _render_tab_metric_registry("compute")
    render_section("Industrial output", "Broad domestic production of computers, communications equipment, and semiconductor components.")
    _render_industrial_output(infrastructure_data)
    render_section("Factory constraint", "Operating pressure across the manufacturing base.")
    _render_factory_constraint(infrastructure_data)
    render_section("Domestic capacity buildout", "Award-backed projects tracked from investment commitment toward production.")
    _render_capacity_buildout(infrastructure_data)
