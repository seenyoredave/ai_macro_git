from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.energy_pulse import development_snapshot, supply_snapshot
from rendering.charts_energy import queue_by_region, queue_by_technology
from rendering.charts_grid_storage import grid_construction_history, storage_pipeline_by_region
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_number, render_domain_read, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.dataframe import arrow_safe_dataframe


def _frame(data: dict, key: str) -> pd.DataFrame:
    value = (data or {}).get(key)
    return value.copy() if isinstance(value, pd.DataFrame) else pd.DataFrame()


def _construction_item(infrastructure_data: dict) -> dict:
    return (((infrastructure_data or {}).get("series", {}) or {}).get("Electric Power Construction", {}) or {})


def _context(energy_data: dict, infrastructure_data: dict) -> dict:
    queue = _frame(energy_data, "interconnection_queue")
    summary = _frame(energy_data, "interconnection_queue_summary")
    pipeline = _frame(energy_data, "generator_pipeline")
    capacity = _frame(energy_data, "capacity_snapshot")
    changes = _frame(energy_data, "capacity_changes")
    generation = _frame(energy_data, "generation_history")
    development = development_snapshot(pipeline, queue, summary)
    supply = supply_snapshot(generation, capacity, changes)
    active = development.get("active_queue", pd.DataFrame())
    storage_mw = pd.to_numeric(active.get("Storage MW", pd.Series(dtype=float)), errors="coerce") if isinstance(active, pd.DataFrame) else pd.Series(dtype=float)
    submitted_mw = pd.to_numeric(active.get("Queue MW", pd.Series(dtype=float)), errors="coerce") if isinstance(active, pd.DataFrame) else pd.Series(dtype=float)
    storage_queue_gw = storage_mw.sum(min_count=1) / 1000.0
    storage_share = storage_mw.sum(min_count=1) / submitted_mw.sum(min_count=1) * 100.0 if submitted_mw.sum(min_count=1) > 0 else np.nan
    return {
        "queue": queue,
        "summary": summary,
        "development": development,
        "supply": supply,
        "storage_queue_gw": storage_queue_gw,
        "storage_share": storage_share,
        "construction": (infrastructure_data or {}).get("construction_history"),
        "construction_item": _construction_item(infrastructure_data),
    }


def _fallback_read(context: dict) -> dict:
    development = context.get("development", {})
    active = pd.to_numeric(development.get("headline_queue_gw"), errors="coerce")
    advanced = pd.to_numeric(development.get("advanced_share"), errors="coerce")
    storage = pd.to_numeric(context.get("storage_queue_gw"), errors="coerce")
    if pd.notna(active) and pd.notna(advanced) and advanced < 30:
        headline = "The connection pipeline is large, but most capacity remains early-stage."
    elif pd.notna(active):
        headline = "Grid access—not project interest—is the key conversion question."
    else:
        headline = "Grid and storage evidence is incomplete."
    body = (
        f"The active interconnection pipeline totals {fmt_number(active, 0, suffix=' GW')}; "
        f"{fmt_number(advanced, 1, suffix='%')} has reached executed-agreement or construction stages. "
        f"Submitted storage components total {fmt_number(storage, 0, suffix=' GW')}. "
        "Queue capacity is not the same as deliverable capacity, and projects can withdraw or change before operation."
    )
    return {"headline": headline, "body": body, "confidence": "high" if pd.notna(active) and pd.notna(advanced) else "moderate"}


def render_grid_storage_tab(energy_data: dict, infrastructure_data: dict, tab_read=None) -> None:
    context = _context(energy_data, infrastructure_data)
    development = context["development"]
    supply = context["supply"]
    construction = context["construction_item"]
    construction_value = pd.to_numeric(construction.get("value"), errors="coerce")
    construction_yoy = pd.to_numeric(construction.get("yoy_growth"), errors="coerce")

    render_tab_header(
        "Grid & Storage",
        "Whether new power can connect, move through the system, and remain available when large loads need it.",
        "Berkeley Lab / EIA / U.S. Census Bureau",
    )
    render_line_break()
    _render_tab_metric_registry("grid_storage")
    render_domain_read(tab_read or _fallback_read(context), label="Grid & Storage Read", accent="blue")

    render_section("Delivery pulse", "The scale, maturity, storage content, and investment context of the connection pipeline.", first=True, compact=True)
    render_statline([
        ("Active queue", fmt_number(development.get("headline_queue_gw"), 0, suffix=" GW"), development.get("queue_context", "")),
        ("Advanced-stage share", fmt_number(development.get("advanced_share"), 1, suffix="%"), "executed IA or construction"),
        ("Storage in queue", fmt_number(context.get("storage_queue_gw"), 0, suffix=" GW"), fmt_number(context.get("storage_share"), 1, suffix="% of submitted capacity")),
        ("Electric-power construction", "n/a" if pd.isna(construction_value) else f"${construction_value / 1000.0:.1f}B", f"{fmt_number(construction_yoy * 100.0, 1, signed=True, suffix='%')} YoY · broad Census category"),
    ], key_prefix="grid-storage-pulse")

    render_section("Connection pipeline", "Projects waiting to connect, viewed by technology or region and separated from planned generation already captured on Power.")
    view = st.radio("Queue view", ["Technology", "Region"], horizontal=True, label_visibility="collapsed", key="grid-storage-queue-view")
    with st.container(border=True, key="grid-storage-panel-queue"):
        if view == "Region":
            render_panel_heading("Active interconnection queue by region", "Submitted components; storage imputation excluded")
            figure = queue_by_region(development.get("active_queue"), height=430)
            chart_key = "grid-storage-queue-region"
        else:
            render_panel_heading("Active interconnection queue by technology", development.get("technology_note"))
            figure = queue_by_technology(development.get("technology_frame"), height=430)
            chart_key = "grid-storage-queue-technology"
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=chart_key)
    st.caption("Queue capacity measures requested interconnection, not completed or deliverable capacity. Projects can withdraw, resize, or change technology before operation.")

    render_section("Storage deployment", "Operating battery capacity and the storage components seeking interconnection.")
    render_statline([
        ("Operating battery power", fmt_number(supply.get("battery_gw"), 1, suffix=" GW"), "latest EIA fleet snapshot"),
        ("Operating storage energy", fmt_number(supply.get("storage_gwh"), 1, suffix=" GWh"), "latest EIA fleet snapshot"),
        ("Submitted storage", fmt_number(context.get("storage_queue_gw"), 0, suffix=" GW"), "active queue components"),
        ("Queue projects", f"{int(development.get('queue_projects', 0) or 0):,}", "active requests"),
    ], key_prefix="grid-storage-storage")
    with st.container(border=True, key="grid-storage-panel-storage-region"):
        render_panel_heading("Storage pipeline by region", "Active submitted storage components")
        st.plotly_chart(storage_pipeline_by_region(development.get("active_queue")), width="stretch", config={"displayModeBar": False, "responsive": True}, key="grid-storage-storage-region")

    render_section("Delivery investment", "A broad construction proxy for electric-power systems; the Census category does not isolate transmission, distribution, substations, or generation.")
    with st.container(border=True, key="grid-storage-panel-construction"):
        render_panel_heading("Electric-power construction", "Seasonally adjusted annual rate · 2020-present")
        st.plotly_chart(grid_construction_history(context.get("construction")), width="stretch", config={"displayModeBar": False, "responsive": True}, key="grid-storage-construction-history")
        st.caption("This is a broad electric-power construction series. It is used as investment context, not as a direct measure of grid adequacy or AI-attributable spending.")

    with st.expander("Grid and storage evidence ledger", expanded=False):
        ledger_view = st.radio("Ledger", ["Interconnection requests", "Queue summary", "Operating capacity", "Construction history"], horizontal=True, key="grid-storage-ledger-view")
        frames = {
            "Interconnection requests": development.get("active_queue"),
            "Queue summary": context.get("summary"),
            "Operating capacity": _frame(energy_data, "capacity_snapshot"),
            "Construction history": context.get("construction"),
        }
        st.dataframe(arrow_safe_dataframe(frames.get(ledger_view)), width="stretch", height=430, hide_index=True)
