from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_data_center import (
    data_center_national_stage,
    data_center_region_landscape,
    data_center_service_trajectory,
    data_center_state_pipeline,
)
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_date, fmt_number, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header


def _render_data_center_summary(infrastructure_data):
    inventory = (infrastructure_data or {}).get("data_center_inventory", {}) or {}
    national = inventory.get("broad_summary", {}) or {}
    pipeline = inventory.get("open_tracker_summary", {}) or {}

    operating = int(national.get("operating", 0) or 0)
    development = int(national.get("development", 0) or 0)
    total = int(national.get("total", 0) or 0)
    expanding = int(pipeline.get("expanding", 0) or 0)

    operating_mw = pd.to_numeric(pipeline.get("operating_published_mw"), errors="coerce")
    planned_mw = pd.to_numeric(pipeline.get("active_pipeline_published_mw"), errors="coerce")

    render_panel_heading("U.S. data center footprint", "Pew national census · FracTracker project tracker")
    render_statline(
        [
            ("Broad census", f"{total:,}", f"operating + development · {fmt_date(national.get('observation_date'))}"),
            ("Operating", f"{operating:,}", "broad census"),
            ("In development", f"{development:,}", "planned, building, or land banked"),
            ("Expanding", f"{expanding:,}", "open tracker sites"),
        ],
        key_prefix="data-center-national-footprint",
    )
    render_panel_heading("Published tracker capacity", "FracTracker disclosed capacity")
    render_statline(
        [
            ("Operating published MW", "n/a" if pd.isna(operating_mw) else f"{operating_mw / 1000.0:,.1f} GW", f"{int(pipeline.get('operating', 0) or 0):,} operating tracker sites"),
            ("Pipeline published MW", "n/a" if pd.isna(planned_mw) else f"{planned_mw / 1000.0:,.1f} GW", f"{int(pipeline.get('active_pipeline', 0) or 0):,} active tracker projects"),
            ("Approved / permitted / construction", f"{int(pipeline.get('approved_or_construction', 0) or 0):,}", "projects"),
            ("Proposed", f"{int(pipeline.get('proposed', 0) or 0):,}", "projects"),
        ],
        key_prefix="data-center-published-capacity",
    )


def _render_facility_coverage(infrastructure_data):
    coverage = (infrastructure_data or {}).get("facility_coverage", {}) or {}
    fields = coverage.get("fields", {}) or {}

    published_records = int(((fields.get("Published Capacity Estimate MW", {}) or {}).get("records", 0) or 0))
    contracted_records = int(((fields.get("Contracted Utility Capacity MW", {}) or {}).get("records", 0) or 0))
    energized_records = int(((fields.get("Energized Capacity MW", {}) or {}).get("records", 0) or 0))

    render_section(
        "Facility coverage",
        "Location, project-stage, and capacity coverage across the canonical facility registry.",
        compact=True,
    )
    render_statline(
        [
            ("Footprint records", f"{int(coverage.get('mapped_footprints', 0) or 0):,}", "mapped locations"),
            ("Project records", f"{int(coverage.get('project_records', 0) or 0):,}", "development-stage records"),
            ("Published MW", f"{published_records:,}", "records with disclosed capacity"),
            ("Contracted / energized", f"{contracted_records:,} / {energized_records:,}", "utility and operating stages"),
        ],
        key_prefix="data-center-evidence-coverage",
    )

def _render_data_center_pipeline(infrastructure_data):
    inventory = (infrastructure_data or {}).get("data_center_inventory", {}) or {}
    national_stage = inventory.get("national_stage")
    regions = inventory.get("regions")
    states = inventory.get("state_stage")
    registry = (infrastructure_data or {}).get("facility_registry")

    render_section("Development pipeline", "Published project stages, regional concentration, and disclosed service timing.")
    columns = st.columns(2)
    with columns[0]:
        with st.container(border=True):
            render_panel_heading("Buildout stage", "FracTracker project status")
            st.plotly_chart(data_center_national_stage(national_stage), width="stretch", config={"displayModeBar": True, "responsive": True}, key="data-center-national-stage")
    with columns[1]:
        with st.container(border=True):
            render_panel_heading("Regional footprint", "Pew operating and development counts")
            st.plotly_chart(data_center_region_landscape(regions), width="stretch", config={"displayModeBar": True, "responsive": True}, key="data-center-regions")

    columns = st.columns(2)
    with columns[0]:
        with st.container(border=True):
            render_panel_heading("State pipeline leaders", "FracTracker active projects")
            st.plotly_chart(data_center_state_pipeline(states), width="stretch", config={"displayModeBar": True, "responsive": True}, key="data-center-state-pipeline")
    with columns[1]:
        with st.container(border=True):
            render_panel_heading("Capacity coming online", "Projects with disclosed service dates")
            st.plotly_chart(data_center_service_trajectory(registry), width="stretch", config={"displayModeBar": True, "responsive": True}, key="data-center-service-trajectory")


def render_data_center_tab(infrastructure_data):
    render_tab_header(
        "Data Center",
        "The U.S. facility universe, active development pipeline, capacity evidence, and geographic concentration.",
        "Pew / FracTracker / PNNL / primary project sources",
    )
    render_line_break()
    _render_tab_metric_registry("data_center")
    render_section("Data Center Buildout", "National facility populations and development pipeline.")
    _render_data_center_summary(infrastructure_data)
    _render_facility_coverage(infrastructure_data)
    _render_data_center_pipeline(infrastructure_data)
