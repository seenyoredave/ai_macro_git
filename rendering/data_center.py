from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from rendering.charts_data_center import (
    ACTIVE_CAMPUS_STATUSES,
    data_center_capacity_distribution,
    data_center_largest_campuses,
    data_center_operator_pipeline,
    data_center_stage_profile,
    data_center_state_pipeline,
)
from rendering.charts_infrastructure import data_center_connectivity_state
from rendering.common import _render_floating_terms
from rendering.components import (
    fmt_number,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_statline,
    render_summary_row,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe
from rendering.spatial import render_spatial_explorer
from rendering.visual_system import render_plotly_chart


def _inject_data_center_page_theme() -> None:
    st.markdown(
        """
        <style>
        div[class*="st-key-data-center-panel-"] {
            border-color: rgba(148, 163, 184, 0.15) !important;
            background: rgba(17, 24, 39, 0.72) !important;
            box-shadow: inset 0 1px 0 rgba(129, 140, 248, 0.04) !important;
        }
        div[class*="st-key-data-center-panel-"] [data-testid="stPlotlyChart"] { margin-top: -0.15rem; }
        div[class*="st-key-statline-data-center-pulse-"] { border-top-color: rgba(129, 140, 248, 0.84) !important; }
        div[class*="st-key-statline-data-center-geography-"] { border-top-color: rgba(96, 165, 250, 0.74) !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _inventory(infrastructure_data) -> dict:
    value = (infrastructure_data or {}).get("data_center_inventory")
    return value if isinstance(value, dict) else {}


def _campuses(infrastructure_data) -> pd.DataFrame:
    frame = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Data Centers requires the Universal Data Center Registry")
    if "Campus ID" not in frame.columns:
        raise ValueError("Universal Data Center Registry is missing Campus ID")
    if frame["Campus ID"].astype(str).duplicated().any():
        raise ValueError("Universal Data Center Registry contains duplicate Campus IDs")
    return frame.copy()


def _campus_capacity(frame: pd.DataFrame) -> pd.Series:
    planned = pd.to_numeric(frame.get("Planned Data Center Capacity MW", pd.Series(np.nan, index=frame.index)), errors="coerce")
    published = pd.to_numeric(frame.get("Published Capacity Estimate MW", pd.Series(np.nan, index=frame.index)), errors="coerce")
    return planned.combine_first(published).where(lambda values: values > 0)


def _active_campuses(campuses: pd.DataFrame) -> pd.DataFrame:
    if campuses.empty:
        return campuses.copy()
    status = campuses.get("Status", pd.Series("", index=campuses.index)).fillna("").astype(str)
    return campuses.loc[status.isin(ACTIVE_CAMPUS_STATUSES)].copy()


def _campus_detail(campuses: pd.DataFrame) -> pd.DataFrame:
    clean = campuses.copy()
    if clean.empty:
        return pd.DataFrame()
    clean["Published capacity estimate (MW)"] = pd.to_numeric(clean.get("Published Capacity Estimate MW"), errors="coerce").where(lambda values: values > 0)
    clean["Planned data-center capacity (MW)"] = pd.to_numeric(clean.get("Planned Data Center Capacity MW"), errors="coerce").where(lambda values: values > 0)
    clean["Expected service"] = pd.to_datetime(clean.get("Expected Service Date"), errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")
    clean["Operator display"] = clean.get("Operator", pd.Series("", index=clean.index)).fillna("").astype(str).replace("", "Unreported")
    stage_order = {
        "Operational": 0, "Expanding": 1, "Under construction": 2,
        "Approved / permitted / under construction": 3, "Proposed": 4,
        "Planned": 5, "Announced": 6,
    }
    clean["_stage_order"] = clean.get("Status", pd.Series("", index=clean.index)).map(stage_order).fillna(99)
    clean = clean.sort_values(
        ["_stage_order", "State", "Published capacity estimate (MW)", "Campus Label"],
        ascending=[True, True, False, True],
        na_position="last",
        kind="stable",
    )
    columns = [
        "Campus Label", "Campus ID", "Operator display", "State", "County", "Status",
        "Identity Basis", "Identity Confidence", "Facility Count", "Building Count",
        "Published capacity estimate (MW)", "Planned data-center capacity (MW)", "Expected service",
    ]
    return clean[[column for column in columns if column in clean.columns]].rename(
        columns={"Campus Label": "Campus", "Operator display": "Operator"}
    ).reset_index(drop=True)


def _operator_detail(campuses: pd.DataFrame) -> pd.DataFrame:
    clean = _active_campuses(campuses)
    if clean.empty:
        return pd.DataFrame()
    clean["Operator"] = clean.get("Operator", pd.Series("", index=clean.index)).fillna("").astype(str).str.strip().replace("", np.nan)
    clean = clean.dropna(subset=["Operator"])
    clean["Capacity MW"] = _campus_capacity(clean)
    return (
        clean.groupby("Operator", as_index=False)
        .agg(**{
            "Active campuses": ("Campus ID", "nunique"),
            "States": ("State", lambda values: values.replace("", np.nan).nunique()),
            "Published capacity estimate (MW)": ("Capacity MW", lambda values: values.sum(min_count=1)),
        })
        .sort_values(["Active campuses", "Published capacity estimate (MW)"], ascending=False, kind="stable")
        .head(40)
        .reset_index(drop=True)
    )


def _render_pulse(campuses: pd.DataFrame, infrastructure_data: dict) -> None:
    summary = dict((infrastructure_data or {}).get("data_center_registry_summary", {}) or {})
    active = _active_campuses(campuses)
    status = campuses.get("Status", pd.Series("", index=campuses.index)).fillna("").astype(str)
    operating = int(status.eq("Operational").sum())
    development = int(status.isin(ACTIVE_CAMPUS_STATUSES - {"Operational"}).sum())
    capacity = _campus_capacity(active)
    render_section(
        "Canonical data-center footprint",
        "One campus universe shared by Data Centers, Water, Power, Grid & Storage, and Connectivity.",
        first=True,
        compact=True,
    )
    render_statline(
        [
            ("Canonical campuses", f"{len(campuses):,}", f"registry v{summary.get('registry_version', '9.6.0')}"),
            ("Operating campuses", f"{operating:,}", "canonical Campus IDs"),
            ("Development campuses", f"{development:,}", "active development stages"),
            ("Published capacity", fmt_number(capacity.sum(min_count=1) / 1000.0, 1, suffix=" GW"), f"{int(capacity.notna().sum()):,} campuses with MW"),
        ],
        key_prefix="data-center-pulse",
    )


def _render_geography(campuses: pd.DataFrame, infrastructure_data: dict) -> None:
    state_counts = campuses.groupby("State", as_index=False)["Campus ID"].nunique().rename(columns={"Campus ID": "Campuses"}) if not campuses.empty else pd.DataFrame()
    leading = state_counts.nlargest(1, "Campuses") if not state_counts.empty else pd.DataFrame()
    summary = dict((infrastructure_data or {}).get("data_center_registry_summary", {}) or {})
    render_section("Campus geography", "Interactive canonical campus map with state drilldown and campus selection.")
    render_summary_row(
        [
            ("Largest campus footprint", str(leading.iloc[0]["State"]) if not leading.empty else "n/a", f"{int(leading.iloc[0]['Campuses']):,} campuses" if not leading.empty else "n/a"),
            ("States represented", f"{int(summary.get('states', 0) or 0):,}", "universal registry"),
            ("Mapped campuses", f"{int(summary.get('mapped_campuses', 0) or 0):,}", "canonical campus points"),
            ("Building entities", f"{int(summary.get('building_entities', 0) or 0):,}", "children of campuses"),
        ],
        key_prefix="data-center-geography",
    )
    with st.container(border=True, key="data-center-panel-geography"):
        render_spatial_explorer(
            infrastructure_data,
            key_prefix="data-center-campus-geography",
            show_heading=False,
            show_table=False,
            default_layer="All campuses",
            height=620,
        )


def _render_scale(campuses: pd.DataFrame) -> None:
    render_section("Campus scale", "Published capacity resolved at the canonical campus grain.")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="data-center-panel-largest-campuses"):
            render_panel_heading("Largest published campuses", "Canonical campus records")
            render_plotly_chart(
                data_center_largest_campuses(campuses, height=460),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="data-center-largest-campuses",
            )
    with right:
        with st.container(border=True, key="data-center-panel-capacity-distribution"):
            render_panel_heading("Published capacity distribution", "Campus-level MW")
            render_plotly_chart(
                data_center_capacity_distribution(campuses, height=460),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="data-center-capacity-distribution",
            )


def _render_development_profile(inventory: dict) -> None:
    stage = inventory.get("national_stage")
    tracker = inventory.get("open_tracker_summary", {}) or {}
    states = inventory.get("state_stage")
    render_section("Source project pipeline", "Development-stage source records supporting the canonical registry.")
    render_summary_row(
        [
            ("Proposed source records", f"{int(tracker.get('proposed', 0) or 0):,}", "FracTracker"),
            ("Approved / construction", f"{int(tracker.get('approved_or_construction', 0) or 0):,}", "FracTracker"),
            ("Expanding", f"{int(tracker.get('expanding', 0) or 0):,}", "FracTracker"),
            ("Published operating capacity", fmt_number(pd.to_numeric(tracker.get("operating_published_mw"), errors="coerce") / 1000.0, 1, suffix=" GW"), "source records"),
        ],
        key_prefix="data-center-development-profile",
    )
    with st.container(border=True, key="data-center-panel-development-profile"):
        view = st.radio(
            "Development view",
            ["Lifecycle stage", "Leading state pipelines"],
            horizontal=True,
            label_visibility="collapsed",
            key="data-center-view-pipeline-explorer",
        )
        if view == "Leading state pipelines":
            render_panel_heading("Leading state development pipelines", "Source project records")
            figure, key = data_center_state_pipeline(states, height=500), "data-center-leading-pipelines"
        else:
            render_panel_heading("Source records by lifecycle stage", "FracTracker")
            figure, key = data_center_stage_profile(stage, height=500), "data-center-stage-profile"
        render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=key)


def _render_connectivity_operator_structure(connectivity: dict | None, campuses: pd.DataFrame) -> None:
    payload = connectivity or {}
    national = payload.get("national_summary", {}) or {}
    coverage = payload.get("coverage", {}) or {}
    active = _active_campuses(campuses)
    operators = active.get("Operator", pd.Series("", index=active.index)).replace("", np.nan).nunique() if not active.empty else 0
    render_section("Connectivity and operators", "Connectivity evidence joined to canonical Campus IDs.")
    render_summary_row(
        [
            ("Active IXPs", f"{int(pd.to_numeric(national.get('Active IXPs'), errors='coerce') or 0):,}", "national public registry"),
            ("Campuses screened", f"{int(coverage.get('campuses_screened', 0) or 0):,}", "coverage subset"),
            ("Active campuses", f"{len(active):,}", "universal registry"),
            ("Active operators", f"{int(operators):,}", "reported operator names"),
        ],
        key_prefix="data-center-structure",
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="data-center-panel-connectivity-context"):
            render_panel_heading("Campus capacity and network depth", "Connectivity domain")
            render_plotly_chart(
                data_center_connectivity_state(payload.get("state_summary"), height=470, lens="Mismatch screen"),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="data-center-connectivity-context-chart",
            )
    with right:
        with st.container(border=True, key="data-center-panel-operator-structure"):
            render_panel_heading("Active campuses by operator", "Universal registry")
            render_plotly_chart(
                data_center_operator_pipeline(campuses, height=470),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="data-center-operator-pipeline",
            )


def _render_data_center_ledger(campuses: pd.DataFrame, infrastructure_data: dict) -> None:
    entities = (infrastructure_data or {}).get("data_center_entities")
    entities = entities.copy() if isinstance(entities, pd.DataFrame) else pd.DataFrame()
    with st.expander("Universal data-center registry", expanded=False):
        options = ["Campuses", "Operators"] + (["Hierarchy"] if not entities.empty else [])
        view = st.radio("Registry view", options, horizontal=True, key="data-center-ledger-view")
        if view == "Operators":
            frame = _operator_detail(campuses)
        elif view == "Hierarchy":
            columns = ["Entity Level", "Entity Name", "Entity ID", "Parent Entity ID", "Campus ID", "Operator", "State", "County", "Square Feet"]
            frame = entities[[column for column in columns if column in entities.columns]].copy()
        else:
            frame = _campus_detail(campuses)
        st.dataframe(arrow_safe_dataframe(frame), width="stretch", hide_index=True, height=480)


def render_data_center_tab(infrastructure_data, tab_read=None):
    _inject_data_center_page_theme()
    render_tab_header(
        "Data Centers",
        "Canonical U.S. data-center campuses with child facilities and buildings, development status, capacity, geography, and connectivity.",
        "Universal Data Center Registry",
    )
    _render_floating_terms("data_center")
    render_domain_read(tab_read, label="Read", domain="data_centers")
    campuses = _campuses(infrastructure_data)
    inventory = _inventory(infrastructure_data)
    connectivity = (infrastructure_data or {}).get("connectivity", {}) or {}
    _render_pulse(campuses, infrastructure_data)
    _render_geography(campuses, infrastructure_data)
    _render_scale(campuses)
    _render_development_profile(inventory)
    _render_connectivity_operator_structure(connectivity, campuses)
    _render_data_center_ledger(campuses, infrastructure_data)


__all__ = [
    "_active_campuses",
    "_campus_capacity",
    "_render_development_profile",
    "_render_geography",
    "_render_pulse",
    "_render_connectivity_operator_structure",
    "render_data_center_tab",
]
