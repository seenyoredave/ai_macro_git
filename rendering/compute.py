from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_infrastructure import (
    compute_capacity_utilization_history,
    compute_info_processing_investment_history,
    compute_m3_backlog_inventory,
    compute_m3_orders_shipments,
    compute_manufacturing_capacity_history,
    compute_manufacturing_output_history,
    compute_project_layer_sites,
    compute_project_state_sites,
)
from rendering.common import _render_tab_metric_registry
from rendering.components import (
    inject_panel_height_rules,
    fmt_date,
    fmt_number,
    render_domain_read,
    render_line_break,
    render_panel_heading,
    render_section,
    render_statline,
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

    render_section(
        "Manufacturing output",
        "Domestic production across computers, communications equipment, and semiconductor components.",
        first=True,
    )
    render_statline(
        [
            ("Computers / peripherals", _index_value(computers), _growth_detail(computers)),
            ("Communications equipment", _index_value(communications), _growth_detail(communications)),
            ("Semiconductors / components", _index_value(semiconductors), _growth_detail(semiconductors)),
        ],
        key_prefix="compute-output",
    )
    with st.container(border=True):
        render_panel_heading("Compute-manufacturing output", "Federal Reserve G.17 · 2017=100")
        st.plotly_chart(
            compute_manufacturing_output_history(history, height=350, years=10),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="compute-output-history",
        )


def _render_capacity_and_demand(infrastructure_data):
    compute = _compute_data(infrastructure_data)
    history = compute.get("history")
    info_history = compute.get("info_investment_history")
    m3_history = compute.get("m3_history")
    computer_utilization = _series_item(
        infrastructure_data, "Computer and Peripheral Equipment Capacity Utilization"
    )
    semiconductor_utilization = _series_item(
        infrastructure_data, "Semiconductor and Electronic Component Capacity Utilization"
    )
    investment = _series_item(infrastructure_data, "Info Processing Investment Level")

    render_section("Capacity and demand", "Manufacturing capacity, operating rates, and information-processing investment.")
    render_statline(
        [
            (
                "Computer utilization",
                _index_value(computer_utilization, suffix="%"),
                fmt_date(computer_utilization.get("date")),
            ),
            (
                "Semiconductor utilization",
                _index_value(semiconductor_utilization, suffix="%"),
                fmt_date(semiconductor_utilization.get("date")),
            ),
            (
                "Information-processing investment",
                "$" + fmt_number(pd.to_numeric(investment.get("value"), errors="coerce") / 1000.0, 2, suffix="T"),
                _growth_detail(investment),
            ),
        ],
        key_prefix="compute-capacity-demand",
    )

    columns = st.columns(2)
    with columns[0]:
        with st.container(border=True, key="compute-panel-manufacturing-capacity"):
            render_panel_heading("Manufacturing capacity", "Federal Reserve G.17 · 2017=100")
            st.plotly_chart(
                compute_manufacturing_capacity_history(history, height=325, years=10),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="compute-capacity-history",
            )
    with columns[1]:
        with st.container(border=True, key="compute-panel-capacity-utilization"):
            render_panel_heading("Capacity utilization", "Federal Reserve G.17 · percent")
            st.plotly_chart(
                compute_capacity_utilization_history(history, height=325, years=10),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="compute-utilization-history",
            )

    if isinstance(m3_history, pd.DataFrame) and not m3_history.empty:
        columns = st.columns(2)
        with columns[0]:
            with st.container(border=True, key="compute-panel-orders-shipments"):
                render_panel_heading("Orders and shipments", "Census M3 · monthly value")
                st.plotly_chart(
                    compute_m3_orders_shipments(m3_history, height=325, years=10),
                    width="stretch",
                    config={"displayModeBar": True, "responsive": True},
                    key="compute-orders-shipments",
                )
        with columns[1]:
            with st.container(border=True, key="compute-panel-backlog-inventory"):
                render_panel_heading("Backlog and inventory", "Census M3 · monthly ratios")
                st.plotly_chart(
                    compute_m3_backlog_inventory(m3_history, height=325, years=10),
                    width="stretch",
                    config={"displayModeBar": True, "responsive": True},
                    key="compute-backlog-inventory",
                )

    with st.container(border=True):
        render_panel_heading("Information-processing investment", "BEA · real private fixed investment")
        st.plotly_chart(
            compute_info_processing_investment_history(info_history, height=330, years=10),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="compute-info-investment",
        )


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
        "Source URL",
    ]
    fields = [field for field in fields if field in projects.columns]
    return projects[fields].reset_index(drop=True)


def _render_domestic_buildout(infrastructure_data):
    compute = _compute_data(infrastructure_data)
    projects = compute.get("projects")
    summary = compute.get("project_summary", {}) or {}
    if not isinstance(projects, pd.DataFrame):
        projects = pd.DataFrame()

    render_section("Domestic buildout", "Manufacturing sites, supply-chain coverage, and public-private investment.")
    render_statline(
        [
            ("Manufacturing sites", f"{int(summary.get('projects', 0) or 0):,}", "tracked facilities"),
            ("States", f"{int(summary.get('states', 0) or 0):,}", f"{int(summary.get('portfolios', 0) or 0):,} portfolios"),
            (
                "Expected investment",
                "$" + fmt_number(summary.get("expected_capex_usd_b"), 1, suffix="B"),
                "announced capital spending",
            ),
            (
                "Direct awards",
                "$" + fmt_number(summary.get("direct_funding_usd_b"), 1, suffix="B"),
                "federal incentives",
            ),
        ],
        key_prefix="compute-buildout",
    )

    columns = st.columns(2)
    with columns[0]:
        with st.container(border=True, key="compute-panel-supply-chain"):
            render_panel_heading("Supply-chain coverage", "Tracked manufacturing sites")
            st.plotly_chart(
                compute_project_layer_sites(projects, height=360),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="compute-layer-sites",
            )
    with columns[1]:
        with st.container(border=True, key="compute-panel-buildout-geography"):
            render_panel_heading("Buildout geography", "Tracked manufacturing sites")
            st.plotly_chart(
                compute_project_state_sites(projects, height=360),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="compute-state-sites",
            )

    with st.expander("Compute project ledger", expanded=False):
        st.dataframe(
            arrow_safe_dataframe(_project_detail(projects)),
            width="stretch",
            hide_index=True,
        )


def render_compute_tab(infrastructure_data, tab_read=None):
    inject_panel_height_rules({
        "compute-panel-manufacturing-capacity": 405,
        "compute-panel-capacity-utilization": 405,
        "compute-panel-orders-shipments": 405,
        "compute-panel-backlog-inventory": 405,
        "compute-panel-supply-chain": 440,
        "compute-panel-buildout-geography": 440,
    })
    compute = _compute_data(infrastructure_data)
    sources = ["Federal Reserve", "BEA", "NIST CHIPS"]
    m3_history = compute.get("m3_history")
    if isinstance(m3_history, pd.DataFrame) and not m3_history.empty:
        sources.insert(1, "Census")
    render_tab_header(
        "Compute",
        "Domestic compute manufacturing, capacity, demand, and production buildout.",
        " / ".join(sources),
    )
    render_line_break()
    _render_tab_metric_registry("compute")
    render_domain_read(tab_read, label="Compute Read", accent="blue")
    _render_manufacturing_output(infrastructure_data)
    _render_capacity_and_demand(infrastructure_data)
    _render_domestic_buildout(infrastructure_data)
