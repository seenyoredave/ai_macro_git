from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.infrastructure_cycle import current_buildout_momentum, supporting_balance
from rendering.charts_infrastructure import (
    infrastructure_leadership_rotation,
    infrastructure_support_alignment,
    wider_system_profile,
)
from rendering.common import _render_tab_metric_registry
from rendering.components import (
    fmt_number,
    render_domain_read,
    render_line_break,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe
from rendering.infrastructure_common import _construction_change_text, _construction_value_text, _infrastructure_item


def _format_balance(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "n/a" if pd.isna(numeric) else f"${numeric / 1000.0:+.1f}B"


def _render_buildout_pulse(infrastructure_data):
    data_centers = _infrastructure_item(infrastructure_data, "Data Center Construction")
    compute = _infrastructure_item(infrastructure_data, "Computer, Electronic & Electrical Manufacturing Construction")
    electric = _infrastructure_item(infrastructure_data, "Electric Power Construction")
    attribution = (infrastructure_data or {}).get("infrastructure_attribution", {}) or {}
    latest = attribution.get("latest", {}) or {}
    render_statline(
        [
            ("Data centers", _construction_value_text(data_centers), _construction_change_text(data_centers)),
            ("Compute manufacturing", _construction_value_text(compute), _construction_change_text(compute)),
            ("Electric power", _construction_value_text(electric), _construction_change_text(electric)),
            ("Net support balance", _format_balance(latest.get("net_support_balance")), "observed minus lagged baseline"),
        ],
        key_prefix="infrastructure-buildout-pulse",
    )


def _render_capital_rotation(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    current = current_buildout_momentum(history)
    leader = current.iloc[0] if not current.empty else None
    meta = "Quarterly year-over-year construction growth"
    if leader is not None:
        meta = f"Current leader: {leader['Series']} · {float(leader['YoY Growth']) * 100:+.1f}% YoY"
    with st.container(border=True, key="infrastructure-panel-capital-rotation"):
        render_panel_heading("Buildout leadership rotation", meta)
        st.plotly_chart(
            infrastructure_leadership_rotation(history),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="infrastructure-capital-rotation",
        )
        st.caption(
            "A falling growth rate can reflect normalization from an unusually high base. "
            "Read momentum alongside the current spending level rather than as a standalone verdict on the category."
        )


def _render_support_alignment(infrastructure_data):
    attribution = (infrastructure_data or {}).get("infrastructure_attribution", {}) or {}
    components = attribution.get("components")
    balance = supporting_balance(components)
    render_statline(
        [
            ("Gross positive excess", _format_balance(balance.get("gross_positive_excess")), "components above baseline"),
            ("Gross shortfall", _format_balance(balance.get("gross_shortfall")), "components below baseline"),
            ("Net support balance", _format_balance(balance.get("net_support_balance")), "all component deviations combined"),
            ("Components above / below", f"{int(balance.get('components_above', 0))} / {int(balance.get('components_below', 0))}", "relative to lagged baseline"),
        ],
        key_prefix="infrastructure-support-alignment",
    )
    with st.container(border=True, key="infrastructure-panel-support-alignment"):
        render_panel_heading(
            "Support alignment",
            "Six enabling systems relative to lagged channel-specific baselines",
        )
        st.plotly_chart(
            infrastructure_support_alignment(components),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="infrastructure-support-alignment-chart",
        )
        st.caption(
            "The net balance includes both above- and below-baseline channels. Private compute, power, and communications are benchmarked to broad private construction; "
            "public water, roads, and transit are benchmarked to their selected public-system mix. These are statistical composition relationships—not AI attribution or capacity adequacy. "
            "Gross positive excess is retained as a secondary diagnostic, not the headline result."
        )
    if isinstance(components, pd.DataFrame) and not components.empty:
        with st.expander("Supporting-build baseline methodology and components", expanded=False):
            st.dataframe(
                arrow_safe_dataframe(components),
                width="stretch",
                height=390,
                hide_index=True,
            )


def _render_wider_systems(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    mode = st.radio(
        "Wider-system view",
        ["Indexed history", "Year-over-year momentum", "Spending levels"],
        horizontal=True,
        key="infrastructure-view-wider-systems",
    )
    with st.container(border=True, key="infrastructure-panel-wider-systems"):
        render_panel_heading(
            "Wider enabling systems",
            "Communications · electric power · public water · roads · transit",
        )
        st.plotly_chart(
            wider_system_profile(history, mode=mode),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="infrastructure-wider-systems",
        )


def render_infrastructure_tab(infrastructure_data, tab_read=None):
    render_tab_header(
        "Infrastructure",
        "Capital rotation through the physical AI stack and whether enabling systems are arriving in the right sequence.",
        "U.S. Census Bureau / primary project sources",
    )
    render_line_break()
    _render_tab_metric_registry("infrastructure")
    render_domain_read(tab_read, label="Infrastructure Read", accent="slate")

    render_section(
        "Buildout pulse",
        "Current construction levels, momentum, and the net balance of supporting systems versus baseline.",
    )
    _render_buildout_pulse(infrastructure_data)

    render_section(
        "Capital rotation",
        "How investment leadership has moved through compute manufacturing, data centers, power, communications, and public systems.",
    )
    _render_capital_rotation(infrastructure_data)

    render_section(
        "Support alignment",
        "Which private and public enabling systems are running ahead of or behind channel-specific historical baselines.",
    )
    _render_support_alignment(infrastructure_data)

    render_section(
        "Wider system context",
        "A selected view of the broader systems that enable, absorb, or constrain physical AI development.",
    )
    _render_wider_systems(infrastructure_data)
