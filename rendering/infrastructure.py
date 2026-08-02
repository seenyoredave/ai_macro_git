from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from rendering.charts_infrastructure import (
    infrastructure_attribution_history,
    infrastructure_construction_history,
    supporting_construction_history,
)
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_number, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.dataframe import arrow_safe_dataframe
from rendering.infrastructure_common import _construction_change_text, _construction_value_text, _infrastructure_item


def _render_direct_buildout(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    data_centers = _infrastructure_item(infrastructure_data, "Data Center Construction")
    compute = _infrastructure_item(infrastructure_data, "Computer, Electronic & Electrical Manufacturing Construction")
    electric = _infrastructure_item(infrastructure_data, "Electric Power Construction")
    render_statline(
        [
            ("Data centers", _construction_value_text(data_centers), _construction_change_text(data_centers)),
            ("Compute manufacturing", _construction_value_text(compute), _construction_change_text(compute)),
            ("Electric power", _construction_value_text(electric), _construction_change_text(electric)),
        ],
        key_prefix="infrastructure-direct-buildout",
    )
    with st.container(border=True):
        render_panel_heading("Core physical buildout", "Census construction spending · seasonally adjusted annual rate")
        st.plotly_chart(
            infrastructure_construction_history(history),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="infrastructure-core-buildout",
        )


def _render_inferred_buildout(infrastructure_data):
    attribution = (infrastructure_data or {}).get("infrastructure_attribution", {}) or {}
    latest = attribution.get("latest", {}) or {}
    direct = pd.to_numeric(latest.get("direct_ai_construction"), errors="coerce")
    observed = pd.to_numeric(latest.get("supporting_construction"), errors="coerce")
    baseline = pd.to_numeric(latest.get("expected_baseline"), errors="coerce")
    excess = pd.to_numeric(latest.get("excess_above_baseline"), errors="coerce")
    excess_share = excess / observed if pd.notna(excess) and pd.notna(observed) and observed > 0 else np.nan
    render_statline(
        [
            ("Direct data-center build", f"${fmt_number(direct / 1000.0 if pd.notna(direct) else np.nan, 1, suffix='B')}", "Census SAAR"),
            ("Supporting construction", f"${fmt_number(observed / 1000.0 if pd.notna(observed) else np.nan, 1, suffix='B')}", "compute, power, communications"),
            ("Historical baseline", f"${fmt_number(baseline / 1000.0 if pd.notna(baseline) else np.nan, 1, suffix='B')}", "lagged 60-month normal share"),
            ("Excess above baseline", f"${fmt_number(excess / 1000.0 if pd.notna(excess) else np.nan, 1, suffix='B')}", fmt_number(excess_share * 100.0 if pd.notna(excess_share) else np.nan, 1, suffix="% of observed")),
        ],
        key_prefix="infrastructure-attribution",
    )
    with st.container(border=True):
        render_panel_heading("Observed supporting build versus baseline", "Compute manufacturing · electric power · communications")
        st.plotly_chart(
            infrastructure_attribution_history(attribution.get("history")),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="infrastructure-attribution-history",
        )
    components = attribution.get("components")
    if isinstance(components, pd.DataFrame) and not components.empty:
        with st.expander("Supporting-build baseline components", expanded=False):
            st.dataframe(arrow_safe_dataframe(components), width="stretch", hide_index=True)


def _render_supporting_systems(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    names = [
        "Communication Construction",
        "Public Highway and Street Construction",
        "Public Transportation Construction",
        "Public Water Supply Construction",
    ]
    labels = {
        "Communication Construction": "Communications",
        "Public Highway and Street Construction": "Roads",
        "Public Transportation Construction": "Transit",
        "Public Water Supply Construction": "Water supply",
    }
    stats = []
    for name in names:
        item = _infrastructure_item(infrastructure_data, name)
        stats.append((labels[name], _construction_value_text(item), _construction_change_text(item)))
    render_statline(stats, key_prefix="infrastructure-supporting-systems")
    with st.container(border=True):
        render_panel_heading("Wider infrastructure", "Communications · roads · transit · public water")
        st.plotly_chart(
            supporting_construction_history(history),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="infrastructure-supporting-history",
        )


def render_infrastructure_tab(infrastructure_data):
    render_tab_header(
        "Infrastructure",
        "Direct AI construction and broader infrastructure development relative to its historical baseline.",
        "U.S. Census Bureau / primary project sources",
    )
    render_line_break()
    _render_tab_metric_registry("infrastructure")
    render_section("Direct buildout", "Data-center, compute-manufacturing, and electric-power construction.")
    _render_direct_buildout(infrastructure_data)
    render_section("Inferred supporting build", "Supporting construction compared with its lagged 60-month baseline.")
    _render_inferred_buildout(infrastructure_data)
    render_section("Wider system context", "National communications, road, transit, and public water construction.")
    _render_supporting_systems(infrastructure_data)
