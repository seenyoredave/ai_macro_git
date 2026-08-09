from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.visual_system import render_plotly_chart
from rendering.charts_infrastructure import (
    compute_capacity_utilization_history,
    compute_info_processing_investment_history,
    compute_m3_backlog_inventory,
    compute_m3_orders_shipments,
    compute_manufacturing_capacity_history,
    compute_manufacturing_output_history,
    compute_project_layer_sites,
    compute_project_state_sites,
    compute_critical_supply_chain,
)
from rendering.common import _render_floating_terms
from rendering.commercialization import filtered_ledger, metric_value
from rendering.components import (
    inject_panel_height_rules,
    fmt_date,
    fmt_number,
    render_compact_chart_rail,
    render_domain_read,
    render_metric_stack,
    render_panel_heading,
    render_section,
    render_statline,
    render_summary_row,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe


def _compute_data(infrastructure_data):
    return (infrastructure_data or {}).get("compute_manufacturing", {}) or {}


def _series_item(infrastructure_data, name):
    return ((_compute_data(infrastructure_data).get("series", {}) or {}).get(name, {}) or {})


def _index_value(item, *, suffix=""):
    value = pd.to_numeric((item or {}).get("value"), errors="coerce")
    return "n/a" if pd.isna(value) else f"{value:,.1f}{suffix}"


def _compute_index_value(item, *, suffix=""):
    return _index_value(item, suffix=suffix)


def _compute_index_change(item):
    growth = pd.to_numeric((item or {}).get("yoy_growth"), errors="coerce")
    return "year over year n/a" if pd.isna(growth) else f"{growth * 100:+.1f}% year over year"


def _growth_detail(item):
    growth = pd.to_numeric((item or {}).get("yoy_growth"), errors="coerce")
    change = "year over year n/a" if pd.isna(growth) else f"{growth * 100:+.1f}% year over year"
    return f"{change} · {fmt_date((item or {}).get('date'))}"


def _render_manufacturing_output(infrastructure_data):
    compute = _compute_data(infrastructure_data)
    history = compute.get("history")
    computers = _series_item(infrastructure_data, "Computer and Peripheral Equipment Output")
    communications = _series_item(infrastructure_data, "Communications Equipment Output")
    semiconductors = _series_item(infrastructure_data, "Semiconductor and Electronic Component Output")

    render_section("Manufacturing output", "U.S. output of computers, communications equipment, and semiconductor components.", first=True)
    render_summary_row([
        ("Computers / peripherals", _index_value(computers), _growth_detail(computers)),
        ("Communications equipment", _index_value(communications), _growth_detail(communications)),
        ("Semiconductors / components", _index_value(semiconductors), _growth_detail(semiconductors)),
    ], key_prefix="compute-output")
    with st.container(key="full-width-layout-compute-manufacturing-hero"):
        with st.container(border=True, key="compute-panel-output-history"):
            render_panel_heading("Compute-manufacturing output", "Federal Reserve G.17 · 2017=100 · ten-year history")
            render_plotly_chart(compute_manufacturing_output_history(history, height=500, years=10), width="stretch", config={"displayModeBar": True, "responsive": True}, key="compute-output-history")

def _render_capacity_and_demand(infrastructure_data):
    compute = _compute_data(infrastructure_data)
    history = compute.get("history")
    info_history = compute.get("info_investment_history")
    m3_history = compute.get("m3_history")
    computer_utilization = _series_item(infrastructure_data, "Computer and Peripheral Equipment Capacity Utilization")
    semiconductor_utilization = _series_item(infrastructure_data, "Semiconductor and Electronic Component Capacity Utilization")
    investment = _series_item(infrastructure_data, "Info Processing Investment Level")

    render_section("Factory capacity and demand", "Factory capacity, utilization, orders, backlogs, and information-processing investment.")
    render_summary_row([
        ("Computer utilization", _index_value(computer_utilization, suffix="%"), fmt_date(computer_utilization.get("date"))),
        ("Semiconductor utilization", _index_value(semiconductor_utilization, suffix="%"), fmt_date(semiconductor_utilization.get("date"))),
        ("Information-processing investment", "$" + fmt_number(pd.to_numeric(investment.get("value"), errors="coerce") / 1000.0, 2, suffix="T"), _growth_detail(investment)),
    ], key_prefix="compute-capacity-demand")
    views = ["Capacity utilization", "Manufacturing capacity"]
    if isinstance(m3_history, pd.DataFrame) and not m3_history.empty:
        views.extend(["Orders and shipments", "Backlog and inventory"])
    views.append("Information-processing investment")
    with st.container(key="full-width-layout-compute-capacity-demand"):
        with st.container(border=True, key="compute-panel-capacity-demand-selected"):
            view = st.radio("Factory view", views, horizontal=True, label_visibility="collapsed", key="compute-view-capacity-demand")
            if view == "Manufacturing capacity":
                render_panel_heading("Manufacturing capacity", "Federal Reserve G.17 · 2017=100")
                figure, chart_key = compute_manufacturing_capacity_history(history, height=430, years=10), "compute-capacity-history"
            elif view == "Orders and shipments":
                render_panel_heading("Orders and shipments", "Census M3 · monthly value")
                figure, chart_key = compute_m3_orders_shipments(m3_history, height=430, years=10), "compute-orders-shipments"
            elif view == "Backlog and inventory":
                render_panel_heading("Backlog and inventory", "Census M3 · monthly ratios")
                figure, chart_key = compute_m3_backlog_inventory(m3_history, height=430, years=10), "compute-backlog-inventory"
            elif view == "Information-processing investment":
                render_panel_heading("Information-processing investment", "BEA · real private fixed investment")
                figure, chart_key = compute_info_processing_investment_history(info_history, height=430, years=10), "compute-info-investment"
            else:
                render_panel_heading("Capacity utilization", "Federal Reserve G.17 · percent")
                figure, chart_key = compute_capacity_utilization_history(history, height=430, years=10), "compute-utilization-history"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": True, "responsive": True}, key=chart_key)

def _project_detail(projects: pd.DataFrame) -> pd.DataFrame:
    if projects is None or not isinstance(projects, pd.DataFrame) or projects.empty:
        return pd.DataFrame()
    fields = [
        "Recipient",
        "Facility",
        "City",
        "State",
        "Supply Chain Layer",
        "Technology",
        "Planned Output",
        "Production Timeline",
        "Expected CapEx USD B",
        "Direct Funding USD B",
        "Available Loan USD B",
    ]
    fields = [field for field in fields if field in projects.columns]
    return projects[fields].reset_index(drop=True)


def _render_critical_supply_chain(infrastructure_data):
    compute = _compute_data(infrastructure_data)
    critical = compute.get("critical_supply_chain", {}) or {}
    render_section("Critical supply chain", "U.S. production and project evidence for logic chips, HBM, advanced packaging, and optical interconnect.")
    with st.container(key="full-width-layout-compute-critical-supply-chain"):
        with st.container(border=True, key="compute-panel-critical-supply-chain"):
            render_panel_heading("Critical AI supply-chain layers", "Logic, HBM, packaging, and optical interconnect")
            render_plotly_chart(compute_critical_supply_chain(critical.get("layers"), height=470), width="stretch", config={"displayModeBar": True, "responsive": True}, key="compute-critical-supply-chain")

def _render_domestic_buildout(infrastructure_data):
    compute = _compute_data(infrastructure_data)
    projects = compute.get("projects")
    summary = compute.get("project_summary", {}) or {}
    if not isinstance(projects, pd.DataFrame):
        projects = pd.DataFrame()
    render_section("U.S. manufacturing projects", "Announced U.S. manufacturing projects by product, location, and expected investment.")
    render_summary_row([
        ("Manufacturing sites", f"{int(summary.get('projects', 0) or 0):,}", "announced projects"),
        ("States", f"{int(summary.get('states', 0) or 0):,}", f"{int(summary.get('portfolios', 0) or 0):,} portfolios"),
        ("Expected investment", "$" + fmt_number(summary.get("expected_capex_usd_b"), 1, suffix="B"), "announced capital spending"),
        ("Direct awards", "$" + fmt_number(summary.get("direct_funding_usd_b"), 1, suffix="B"), "federal incentives"),
    ], key_prefix="compute-buildout")
    with st.container(key="full-width-layout-compute-domestic-buildout"):
        with st.container(border=True, key="compute-panel-buildout-selected"):
            view = st.radio("Project view", ["Project footprint", "Project geography"], horizontal=True, label_visibility="collapsed", key="compute-view-domestic-buildout")
            if view == "Project geography":
                render_panel_heading("Project geography", "Announced manufacturing sites")
                figure, chart_key = compute_project_state_sites(projects, height=470), "compute-state-sites"
            else:
                render_panel_heading("Projects by production layer", "Announced manufacturing sites")
                figure, chart_key = compute_project_layer_sites(projects, height=470), "compute-layer-sites"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": True, "responsive": True}, key=chart_key)

def _render_serving_economics(commercialization_data):
    openai_compute = metric_value(commercialization_data, "OpenAI", "Available compute")
    openai_arr = metric_value(commercialization_data, "OpenAI", "Annualized revenue run rate")
    microsoft_arr = metric_value(commercialization_data, "Microsoft", "Annual revenue run rate")
    alphabet_efficiency = metric_value(commercialization_data, "Alphabet", "Serving unit-cost reduction")
    if all(pd.isna(value) for value in [openai_compute, openai_arr, microsoft_arr, alphabet_efficiency]):
        return
    render_section("Cost of serving AI demand", "Provider revenue and the reported cost of serving AI demand.")
    render_summary_row([
        ("Available compute", fmt_number(openai_compute, 1, suffix=" GW"), "OpenAI · company reported"),
        ("OpenAI ARR", "$" + fmt_number(openai_arr, 1, suffix="B+"), "2025 disclosed floor"),
        ("Microsoft AI ARR", "$" + fmt_number(microsoft_arr, 1, suffix="B"), "provider-defined AI business"),
        ("Serving unit cost", fmt_number(alphabet_efficiency, 0, suffix="% lower"), "Alphabet · during 2025"),
    ], key_prefix="compute-serving-economics")

def _render_compute_ledger(infrastructure_data, commercialization_data):
    projects = _compute_data(infrastructure_data).get("projects")
    with st.expander("Compute data", expanded=False):
        view = st.radio("Ledger", ["Manufacturing projects", "AI service-cost disclosures"], horizontal=True, key="compute-ledger-view")
        if view == "AI service-cost disclosures":
            frame = filtered_ledger(commercialization_data, pillars=["Compute economics", "Revenue realization", "Cost pressure"])
        else:
            frame = _project_detail(projects if isinstance(projects, pd.DataFrame) else pd.DataFrame())
        st.dataframe(arrow_safe_dataframe(frame), width="stretch", hide_index=True, height=440)

def render_compute_tab(infrastructure_data, commercialization_data=None, tab_read=None):
    inject_panel_height_rules({"compute-panel-capacity-demand-selected": 470, "compute-panel-buildout-selected": 500})
    compute = _compute_data(infrastructure_data)
    sources = ["Federal Reserve", "BEA", "NIST CHIPS", "company disclosures"]
    m3_history = compute.get("m3_history")
    if isinstance(m3_history, pd.DataFrame) and not m3_history.empty:
        sources.insert(1, "Census")
    render_tab_header("Compute", "U.S. compute manufacturing, factory capacity, demand, supply-chain projects, and AI service costs.", " / ".join(sources))
    _render_floating_terms("compute")
    render_domain_read(tab_read, label="Read", domain="compute")
    _render_manufacturing_output(infrastructure_data)
    _render_capacity_and_demand(infrastructure_data)
    _render_serving_economics(commercialization_data)
    _render_critical_supply_chain(infrastructure_data)
    _render_domestic_buildout(infrastructure_data)
    _render_compute_ledger(infrastructure_data, commercialization_data)

