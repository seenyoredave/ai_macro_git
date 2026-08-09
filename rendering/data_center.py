from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from rendering.visual_system import render_plotly_chart
from rendering.charts_data_center import (
    ACTIVE_CAMPUS_STATUSES,
    data_center_capacity_distribution,
    data_center_largest_campuses,
    data_center_operator_label,
    data_center_operator_pipeline,
    data_center_region_landscape,
    data_center_stage_profile,
    data_center_state_footprint,
    data_center_state_pipeline,
    data_center_state_published_capacity,
)
from rendering.common import _render_floating_terms
from rendering.charts_infrastructure import data_center_connectivity_state
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


def _count(value) -> int:
    numeric = pd.to_numeric(value, errors="coerce")
    return 0 if pd.isna(numeric) else int(numeric)


def _inject_data_center_page_theme() -> None:
    st.markdown(
        """
        <style>
        div[class*="st-key-data-center-panel-"] {
            border-color: rgba(148, 163, 184, 0.15) !important;
            background: rgba(17, 24, 39, 0.72) !important;
            box-shadow: inset 0 1px 0 rgba(129, 140, 248, 0.04) !important;
        }
        div[class*="st-key-data-center-panel-"] [data-testid="stPlotlyChart"] {
            margin-top: -0.15rem;
        }
        div[class*="st-key-statline-data-center-pulse-"] {
            border-top-color: rgba(129, 140, 248, 0.84) !important;
        }
        div[class*="st-key-statline-data-center-geography-"] ,
        div[class*="st-key-statline-data-center-project-"] {
            border-top-color: rgba(96, 165, 250, 0.74) !important;
        }
        div[class*="st-key-data-center-view-"] [role="radiogroup"] {
            gap: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _campus_capacity(frame: pd.DataFrame) -> pd.Series:
    published = pd.to_numeric(frame.get("Published Capacity Estimate MW"), errors="coerce")
    planned = pd.to_numeric(frame.get("Planned Data Center Capacity MW"), errors="coerce")
    return planned.combine_first(published).where(lambda values: values > 0)


def _active_footprint(campuses: pd.DataFrame) -> pd.DataFrame:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame(columns=getattr(campuses, "columns", None))
    status = campuses.get("Status", pd.Series("", index=campuses.index)).fillna("").astype(str)
    return campuses.loc[status.eq("Operational") | status.isin(ACTIVE_CAMPUS_STATUSES)].copy()


def _inventory(infrastructure_data) -> dict:
    value = (infrastructure_data or {}).get("data_center_inventory")
    return value if isinstance(value, dict) else {}


def _campuses(infrastructure_data) -> pd.DataFrame:
    frame = (infrastructure_data or {}).get("campus_registry")
    if not isinstance(frame, pd.DataFrame):
        frame = (infrastructure_data or {}).get("facility_registry")
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _campus_detail(campuses: pd.DataFrame) -> pd.DataFrame:
    clean = _active_footprint(campuses)
    if clean.empty:
        return pd.DataFrame()

    published = pd.to_numeric(clean.get("Published Capacity Estimate MW"), errors="coerce")
    planned = pd.to_numeric(clean.get("Planned Data Center Capacity MW"), errors="coerce")
    clean["Published capacity estimate (MW)"] = published.where(published > 0)
    clean["Planned data-center capacity (MW)"] = planned.where(planned > 0)
    clean["Expected service"] = pd.to_datetime(
        clean.get("Expected Service Date"), errors="coerce", format="mixed"
    ).dt.strftime("%Y-%m-%d")
    clean["Campus"] = clean.get("Facility", "").replace("", "Unnamed campus")
    clean["Operator display"] = clean.get("Operator", "").replace("", "Unreported")

    stage_order = {
        "Operational": 0,
        "Expanding": 1,
        "Under construction": 2,
        "Approved / permitted / under construction": 3,
        "Proposed": 4,
        "Planned": 5,
        "Announced": 6,
    }
    clean["_stage_order"] = clean.get("Status", "").map(stage_order).fillna(99)
    clean = clean.sort_values(
        ["_stage_order", "State", "Published capacity estimate (MW)", "Campus"],
        ascending=[True, True, False, True],
        na_position="last",
        kind="stable",
    )
    columns = {
        "Campus": "Campus",
        "Operator display": "Operator",
        "State": "State",
        "County": "County",
        "Status": "Status",
        "Published capacity estimate (MW)": "Published capacity estimate (MW)",
        "Planned data-center capacity (MW)": "Planned data-center capacity (MW)",
        "Expected service": "Expected service",
    }
    available = [column for column in columns if column in clean.columns]
    return clean[available].rename(columns=columns).reset_index(drop=True)


def _operator_detail(campuses: pd.DataFrame) -> pd.DataFrame:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame()
    clean = campuses.loc[campuses.get("Status", "").isin(ACTIVE_CAMPUS_STATUSES)].copy()
    clean["Operator"] = clean.get("Operator", "").map(data_center_operator_label).replace("", np.nan)
    clean = clean.dropna(subset=["Operator"])
    clean["Capacity MW"] = _campus_capacity(clean)
    return (
        clean.groupby("Operator", as_index=False)
        .agg(
            **{
                "Active campuses": ("Facility ID", "size"),
                "States": ("State", lambda values: values.replace("", np.nan).nunique()),
                "Published capacity estimate (MW)": ("Capacity MW", lambda values: values.sum(min_count=1)),
            }
        )
        .sort_values(
            ["Active campuses", "Published capacity estimate (MW)"],
            ascending=False,
            kind="stable",
        )
        .head(40)
        .reset_index(drop=True)
    )


def _render_pulse(inventory: dict) -> None:
    broad = inventory.get("broad_summary", {}) or {}
    tracker = inventory.get("open_tracker_summary", {}) or {}
    render_section(
        "Data-center pulse",
        "Operating facilities, projects in development, active pipeline sites, and published capacity.",
        first=True,
        compact=True,
    )
    render_statline(
        [
            (
                "Operating footprint",
                f"{int(broad.get('operating', 0) or 0):,}",
                str(broad.get('observation_date', 'n/a')),
            ),
            (
                "Development footprint",
                f"{int(broad.get('development', 0) or 0):,}",
                str(broad.get('observation_date', 'n/a')),
            ),
            (
                "Active project pipeline",
                f"{int(tracker.get('active_pipeline', 0) or 0):,}",
                f"proposed through expanding · {tracker.get('observation_date', 'n/a')}",
            ),
            (
                "Published pipeline capacity",
                fmt_number(pd.to_numeric(tracker.get("active_pipeline_published_mw"), errors="coerce") / 1000.0, 1, suffix=" GW"),
                "published estimates only",
            ),
        ],
        key_prefix="data-center-pulse",
    )
def _render_development_profile(inventory: dict) -> None:
    stage = inventory.get("national_stage")
    tracker = inventory.get("open_tracker_summary", {}) or {}
    states = inventory.get("state_stage")
    render_section("Pipeline explorer", "The signature development view: where projects sit in the lifecycle and where the active pipeline is concentrating.")
    render_summary_row([
        ("Proposed", f"{int(tracker.get('proposed', 0) or 0):,}", "projects"),
        ("Approved / construction", f"{int(tracker.get('approved_or_construction', 0) or 0):,}", "projects"),
        ("Expanding", f"{int(tracker.get('expanding', 0) or 0):,}", "operating footprint additions"),
        ("Operating capacity", fmt_number(pd.to_numeric(tracker.get("operating_published_mw"), errors="coerce") / 1000.0, 1, suffix=" GW"), "published estimates only"),
    ], key_prefix="data-center-development-profile")
    with st.container(key="full-width-layout-data-center-pipeline-explorer"):
        with st.container(border=True, key="data-center-panel-development-profile"):
            view = st.radio("Pipeline view", ["Lifecycle stage", "Leading state pipelines"], horizontal=True, label_visibility="collapsed", key="data-center-view-pipeline-explorer")
            if view == "Leading state pipelines":
                render_panel_heading("Leading state development pipelines", "Proposed, approved / construction, and expanding")
                figure, key = data_center_state_pipeline(states, height=520), "data-center-leading-pipelines"
            else:
                render_panel_heading("Sites and published capacity by stage", "FracTracker open tracker")
                figure, key = data_center_stage_profile(stage, height=520), "data-center-stage-profile"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=key)

def _render_geography(inventory: dict, campuses: pd.DataFrame, connectivity: dict | None = None) -> None:
    del connectivity
    regions = inventory.get("regions")
    states = inventory.get("state_stage")
    top_states = inventory.get("top_states")
    leading_total = pd.DataFrame(top_states).sort_values("Total", ascending=False, kind="stable").head(1)
    leading_pipeline = pd.DataFrame(states).sort_values("Active Pipeline", ascending=False, kind="stable").head(1)
    region_frame = pd.DataFrame(regions)
    development_total = pd.to_numeric(region_frame.get("Development"), errors="coerce").sum(min_count=1)
    south_development = pd.to_numeric(region_frame.loc[region_frame.get("Region", "").eq("South"), "Development"], errors="coerce").sum(min_count=1)
    south_share = south_development / development_total * 100.0 if pd.notna(development_total) and development_total > 0 else np.nan
    active_states = int(pd.to_numeric(pd.DataFrame(states).get("Active Pipeline"), errors="coerce").gt(0).sum())
    render_section("Geographic concentration", "Where the footprint is established and where the next wave is concentrating.")
    render_summary_row([
        ("Largest footprint", str(leading_total.iloc[0].get("State", "n/a")) if not leading_total.empty else "n/a", f"{int(leading_total.iloc[0].get('Total', 0) or 0):,} facilities" if not leading_total.empty else "n/a"),
        ("Largest active pipeline", str(leading_pipeline.iloc[0].get("State", "n/a")) if not leading_pipeline.empty else "n/a", f"{int(leading_pipeline.iloc[0].get('Active Pipeline', 0) or 0):,} pipeline sites" if not leading_pipeline.empty else "n/a"),
        ("South development share", fmt_number(south_share, 1, suffix="%"), "regional facility share"),
        ("States with active pipeline", f"{active_states:,}", "projects"),
    ], key_prefix="data-center-geography")
    with st.container(key="full-width-layout-data-center-geography"):
        with st.container(border=True, key="data-center-panel-geography-selected"):
            view = st.radio("Geography view", ["National map", "Published capacity", "Regional balance"], horizontal=True, label_visibility="collapsed", key="data-center-view-geography")
            if view == "Regional balance":
                render_panel_heading("Regional operating and development footprint", "Pew / Data Center Map")
                figure, chart_key = data_center_region_landscape(regions, height=520), "data-center-regional-balance"
            elif view == "Published capacity":
                render_panel_heading("Published development capacity by state", "Published estimates only")
                figure, chart_key = data_center_state_published_capacity(campuses, height=540), "data-center-published-capacity"
            else:
                render_panel_heading("Active development footprint", "Pipeline sites by state")
                figure, chart_key = data_center_state_footprint(states, metric="Active Pipeline", height=540), "data-center-national-map"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=chart_key)

def _render_connectivity_operator_structure(connectivity: dict | None, campuses: pd.DataFrame) -> None:
    payload = connectivity or {}
    national = payload.get("national_summary", {}) or {}
    coverage = payload.get("coverage", {}) or {}
    active = _active_footprint(campuses)
    operators = active.get("Operator", pd.Series("", index=active.index)).replace("", np.nan).nunique() if not active.empty else 0
    render_section("Connectivity & operator structure", "Two structural screens: whether capacity is well connected, and which operators carry the active pipeline.")
    render_summary_row([
        ("Active IXPs", f"{_count(national.get('Active IXPs')):,}", "national public registry"),
        ("Mismatch states", f"{_count(coverage.get('mismatch_states')):,}", "capacity with limited public IXP depth"),
        ("Active campuses", f"{len(active):,}", "operating + active development"),
        ("Active operators", f"{int(operators):,}", "reported operator names"),
    ], key_prefix="data-center-structure")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="data-center-panel-connectivity-context"):
            render_panel_heading("Capacity-to-connectivity screen", "Selected hubs and high-capacity outliers")
            render_plotly_chart(data_center_connectivity_state(payload.get("state_summary"), height=470, lens="Mismatch screen"), width="stretch", config={"displayModeBar": False, "responsive": True}, key="data-center-connectivity-context-chart")
    with right:
        with st.container(border=True, key="data-center-panel-operator-structure"):
            render_panel_heading("Active pipeline by operator", "Campus count")
            render_plotly_chart(data_center_operator_pipeline(campuses, height=470), width="stretch", config={"displayModeBar": False, "responsive": True}, key="data-center-operator-pipeline")


def _render_data_center_ledger(campuses: pd.DataFrame) -> None:
    detail = _campus_detail(campuses)
    with st.expander("Data-center project ledger", expanded=False):
        view = st.radio("Ledger", ["Campuses", "Operators"], horizontal=True, key="data-center-ledger-view")
        frame = _operator_detail(campuses) if view == "Operators" else detail
        st.dataframe(arrow_safe_dataframe(frame), width="stretch", hide_index=True, height=480)

def render_data_center_tab(infrastructure_data, tab_read=None):
    _inject_data_center_page_theme()
    render_tab_header("Data Centers", "National scale, development conversion, geographic concentration, connectivity, and project structure.", "Pew / FracTracker / Connectivity")
    _render_floating_terms("data_center")
    render_domain_read(tab_read, label="Data Centers Read", domain="data_centers")
    inventory = _inventory(infrastructure_data)
    campuses = _campuses(infrastructure_data)
    connectivity = (infrastructure_data or {}).get("connectivity", {}) or {}
    _render_pulse(inventory)
    _render_development_profile(inventory)
    _render_geography(inventory, campuses, connectivity)
    _render_connectivity_operator_structure(connectivity, campuses)
    _render_data_center_ledger(campuses)

