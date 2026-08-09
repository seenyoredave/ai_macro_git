from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.energy_pulse import development_snapshot, supply_snapshot
from analytics.grid_deliverability import (
    queue_outcome_snapshot,
    queue_region_profile,
    reserve_margin_profile,
    storage_duration_profile,
)
from rendering.visual_system import render_plotly_chart
from rendering.charts_energy import queue_by_region, queue_by_technology
from rendering.charts_grid_storage import (
    grid_construction_history,
    queue_age_by_region,
    queue_conversion_funnel,
    reserve_margin_stress,
    storage_duration_distribution,
    storage_pipeline_by_region,
)
from rendering.common import _render_floating_terms
from rendering.components import (
    fmt_number,
    render_deliverability_screen,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)
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
    operating = _frame(energy_data, "operating_generators")
    outcomes = _frame(energy_data, "queue_outcomes_summary")
    reserves = _frame(energy_data, "reliability_reserve_margins")
    development = development_snapshot(pipeline, queue, summary)
    supply = supply_snapshot(generation, capacity, changes)
    active = development.get("active_queue", pd.DataFrame())
    storage_mw = pd.to_numeric(active.get("Storage MW", pd.Series(dtype=float)), errors="coerce") if isinstance(active, pd.DataFrame) else pd.Series(dtype=float)
    submitted_mw = pd.to_numeric(active.get("Queue MW", pd.Series(dtype=float)), errors="coerce") if isinstance(active, pd.DataFrame) else pd.Series(dtype=float)
    storage_queue_gw = storage_mw.sum(min_count=1) / 1000.0
    storage_share = storage_mw.sum(min_count=1) / submitted_mw.sum(min_count=1) * 100.0 if submitted_mw.sum(min_count=1) > 0 else np.nan
    duration_frame, duration_summary = storage_duration_profile(operating)
    return {
        "queue": queue,
        "summary": summary,
        "development": development,
        "supply": supply,
        "storage_queue_gw": storage_queue_gw,
        "storage_share": storage_share,
        "construction": (infrastructure_data or {}).get("construction_history"),
        "construction_item": _construction_item(infrastructure_data),
        "queue_outcomes": outcomes,
        "queue_outcome": queue_outcome_snapshot(outcomes),
        "queue_regions": queue_region_profile(queue),
        "reserve_margins": reserve_margin_profile(reserves),
        "storage_duration": duration_frame,
        "storage_duration_summary": duration_summary,
        "source_manifest": _frame(energy_data, "grid_storage_source_manifest"),
    }


def _fallback_read(context: dict) -> dict:
    development = context.get("development", {})
    active = pd.to_numeric(development.get("headline_queue_gw"), errors="coerce")
    advanced = pd.to_numeric(development.get("advanced_share"), errors="coerce")
    median_years = pd.to_numeric(context.get("queue_outcome", {}).get("Median Request to COD Years"), errors="coerce")
    if pd.notna(active) and pd.notna(advanced) and advanced < 30:
        headline = "The interconnection queue is huge, but most projects are still early-stage."
    elif pd.notna(active):
        headline = "Proposed grid projects are taking too long to become operating capacity."
    else:
        headline = "No current grid-delivery reading is available."
    body = (
        f"Only {fmt_number(advanced, 1, suffix='%')} of the {fmt_number(active, 0, suffix=' GW')} active queue "
        "has reached executed-agreement or construction stages, so queue size should not be read as near-term supply. "
        f"Projects completed in 2025 took more than {fmt_number(median_years, 0, suffix=' years')} from request to commercial operation, "
        "making conversion time the central constraint."
    )
    return {"headline": headline, "body": body, "confidence": "high" if pd.notna(active) and pd.notna(advanced) else "moderate"}


def _queue_conversion_stats(context: dict):
    development = context["development"]
    outcome = context.get("queue_outcome", {})
    median_years = pd.to_numeric(outcome.get("Median Request to COD Years"), errors="coerce")
    return [
        ("Active queue", fmt_number(development.get("headline_queue_gw"), 0, suffix=" GW"), f"{int(development.get('queue_projects', 0) or 0):,} requests"),
        ("Draft or executed IA", fmt_number(outcome.get("Draft or Executed IA GW"), 0, suffix=" GW"), "pre-operation capacity"),
        ("Advanced-stage share", fmt_number(development.get("advanced_share"), 1, suffix="%"), "executed IA or construction"),
        ("Median request to COD", ">5 years" if pd.notna(median_years) and median_years > 5 else fmt_number(median_years, 1, suffix=" years"), "projects completed in 2025"),
    ]


def _regional_stats(context: dict):
    regions = context.get("queue_regions")
    top = regions.iloc[0] if isinstance(regions, pd.DataFrame) and not regions.empty else pd.Series(dtype=object)
    oldest = regions.sort_values("Median Queue Age Years", ascending=False).iloc[0] if isinstance(regions, pd.DataFrame) and not regions.empty else pd.Series(dtype=object)
    past_target = pd.to_numeric(regions.get("Past Target GW"), errors="coerce").sum(min_count=1) if isinstance(regions, pd.DataFrame) else np.nan
    return [
        ("Largest regional queue", str(top.get("Region") or "n/a"), fmt_number(top.get("Queue GW"), 0, suffix=" GW")),
        ("Oldest regional median", str(oldest.get("Region") or "n/a"), fmt_number(oldest.get("Median Queue Age Years"), 1, suffix=" years")),
        ("Past target year", fmt_number(past_target, 0, suffix=" GW"), "active requests"),
        ("Storage components", fmt_number(context.get("storage_queue_gw"), 0, suffix=" GW"), fmt_number(context.get("storage_share"), 1, suffix="% of queue")),
    ]


def _reliability_snapshot(context: dict) -> dict:
    reserves = context.get("reserve_margins")
    extreme = pd.to_numeric(reserves.get("Extreme Conditions Margin Percent"), errors="coerce") if isinstance(reserves, pd.DataFrame) else pd.Series(dtype=float)
    lowest = reserves.loc[extreme.idxmin()] if isinstance(reserves, pd.DataFrame) and not extreme.dropna().empty else pd.Series(dtype=object)
    compression = pd.to_numeric(reserves.get("Stress Compression Points"), errors="coerce") if isinstance(reserves, pd.DataFrame) else pd.Series(dtype=float)
    return {
        "lowest_area": str(lowest.get("Assessment Area") or "n/a"),
        "lowest_margin": pd.to_numeric(lowest.get("Extreme Conditions Margin Percent"), errors="coerce"),
        "below_zero": int(extreme.lt(0).sum()) if not extreme.empty else 0,
        "under_five": int(extreme.lt(5).sum()) if not extreme.empty else 0,
        "compression": compression.median() if not compression.dropna().empty else np.nan,
    }


def _investment_snapshot(context: dict) -> dict:
    construction = context["construction_item"]
    return {
        "value": pd.to_numeric(construction.get("value"), errors="coerce"),
        "yoy": pd.to_numeric(construction.get("yoy_growth"), errors="coerce"),
        "date": pd.to_datetime(construction.get("date"), errors="coerce", format="mixed"),
    }


def _render_deliverability_screen(context: dict) -> None:
    development = context["development"]
    reliability = _reliability_snapshot(context)
    duration_summary = context.get("storage_duration_summary", {}) or {}
    investment = _investment_snapshot(context)
    render_section(
        "Grid connection conditions",
        "Queue size, project progress, reserve margins, battery duration, and grid construction spending.",
        first=True,
    )
    render_deliverability_screen(
        [
            ("Queue scale", fmt_number(development.get("headline_queue_gw"), 0, suffix=" GW"), "active generation and storage requests"),
            ("Project maturity", fmt_number(development.get("advanced_share"), 1, suffix="%"), "executed IA or construction"),
            ("Reliability", f"{reliability['under_five']:,} areas", "below 5% in the extreme summer case"),
            ("Storage duration", fmt_number(duration_summary.get("weighted_duration_hours"), 1, suffix=" hours"), "weighted operating battery duration"),
            ("Grid construction spending", "n/a" if pd.isna(investment["value"]) else f"${investment['value'] / 1000.0:.1f}B", "electric-power construction annual rate"),
        ],
        key_prefix="grid-storage-deliverability",
    )


def _render_queue_conversion(context: dict) -> None:
    outcome = context.get("queue_outcome", {})
    render_section(
        "Queue outcomes",
        "Historical completion, withdrawal, and cancellation rates, plus time to connection.",
    )
    render_statline(_queue_conversion_stats(context), key_prefix="grid-storage-queue-conversion")
    with st.container(border=True, key="full-width-layout-grid-storage-queue-conversion"):
        render_panel_heading("Historical interconnection outcomes", str(outcome.get("Historical Submission Cohort") or "2000–2020 submissions"))
        render_plotly_chart(
            queue_conversion_funnel(context.get("queue_outcomes")),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="grid-storage-conversion-funnel",
        )


def _render_reliability_storage(context: dict) -> None:
    reserves = context.get("reserve_margins")
    development = context["development"]
    duration = context.get("storage_duration")
    duration_summary = context.get("storage_duration_summary", {}) or {}
    reliability = _reliability_snapshot(context)
    render_section(
        "Reliability and storage",
        "Summer reserve margins and operating battery duration.",
    )
    render_statline(
        [
            ("Lowest extreme margin", reliability["lowest_area"], fmt_number(reliability["lowest_margin"], 1, signed=True, suffix="%")),
            ("Below zero", f"{reliability['below_zero']:,}", "assessment areas"),
            ("Operating battery power", fmt_number(duration_summary.get("power_gw"), 1, suffix=" GW"), f"{int(duration_summary.get('generators', 0) or 0):,} generators"),
            ("4+ hour power share", fmt_number(duration_summary.get("four_hour_plus_share"), 1, suffix="%"), "reported operating batteries"),
        ],
        key_prefix="grid-storage-resilience-state",
    )
    with st.container(key="grid-storage-resilience-pair"):
        left, right = st.columns(2, gap="large")
        with left:
            with st.container(border=True, key="grid-storage-panel-reliability"):
                render_panel_heading("Summer 2026 reserve margins", "U.S. NERC assessment areas")
                render_plotly_chart(
                    reserve_margin_stress(reserves, height=500),
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key="grid-storage-reserve-margins",
                )
        with right:
            with st.container(border=True, key="grid-storage-panel-storage"):
                view = st.radio(
                    "Storage view",
                    ["Operating duration", "Queue pipeline"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="grid-storage-storage-view",
                )
                if view == "Queue pipeline":
                    render_panel_heading("Storage pipeline by region", "Active submitted storage components")
                    figure = storage_pipeline_by_region(development.get("active_queue"), height=500)
                    chart_key = "grid-storage-storage-region"
                else:
                    render_panel_heading("Operating battery capacity by duration", "Nameplate power and energy")
                    figure = storage_duration_distribution(duration, height=500)
                    chart_key = "grid-storage-storage-duration"
                render_plotly_chart(
                    figure,
                    width="stretch",
                    config={"displayModeBar": False, "responsive": True},
                    key=chart_key,
                )


def _render_queue_regions(context: dict) -> None:
    development = context["development"]
    regions = context.get("queue_regions")
    render_section(
        "Regional queue conditions",
        "Queue size, median age, and target-year status by region.",
    )
    render_statline(_regional_stats(context), key_prefix="grid-storage-regional-state")
    with st.container(border=True, key="full-width-layout-grid-storage-regional-maturity"):
        view = st.radio(
            "Queue view",
            ["Age", "Technology", "Region"],
            horizontal=True,
            label_visibility="collapsed",
            key="grid-storage-queue-view",
        )
        if view == "Age":
            render_panel_heading("Median queue age by region", "Active requests through year-end 2025")
            figure = queue_age_by_region(regions, height=450)
            chart_key = "grid-storage-queue-age"
        elif view == "Region":
            render_panel_heading("Active queue by region", "Submitted generation and storage components")
            figure = queue_by_region(development.get("active_queue"), height=450)
            chart_key = "grid-storage-queue-region"
        else:
            render_panel_heading("Active queue by technology", development.get("technology_note"))
            figure = queue_by_technology(development.get("technology_frame"), height=450)
            chart_key = "grid-storage-queue-technology"
        render_plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=chart_key,
        )


def _render_investment(context: dict) -> None:
    investment = _investment_snapshot(context)
    render_section(
        "Grid construction spending",
        "U.S. electric-power construction spending.",
    )
    render_statline(
        [
            ("Current pace", "n/a" if pd.isna(investment["value"]) else f"${investment['value'] / 1000.0:.1f}B", "annual rate"),
            ("Year-over-year", fmt_number(investment["yoy"] * 100.0, 1, signed=True, suffix="%"), "construction spending"),
            ("Latest observation", "n/a" if pd.isna(investment["date"]) else investment["date"].strftime("%Y-%m"), "U.S. Census Bureau"),
        ],
        key_prefix="grid-storage-investment",
    )
    with st.container(border=True, key="full-width-layout-grid-storage-investment"):
        render_panel_heading("Electric-power construction", "Seasonally adjusted annual rate")
        render_plotly_chart(
            grid_construction_history(context.get("construction"), height=400),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="grid-storage-construction-history",
        )


def render_grid_storage_tab(energy_data: dict, infrastructure_data: dict, tab_read=None) -> None:
    context = _context(energy_data, infrastructure_data)
    render_tab_header(
        "Grid & Storage",
        "Interconnection queues, project progress, reliability, storage duration, and grid construction spending.",
        "Berkeley Lab / NERC / EIA / U.S. Census Bureau",
    )
    _render_floating_terms("grid_storage")
    render_domain_read(tab_read or _fallback_read(context), label="Read", domain="grid_storage")
    _render_deliverability_screen(context)
    _render_queue_conversion(context)
    _render_reliability_storage(context)
    _render_queue_regions(context)
    _render_investment(context)

    with st.expander("Grid and storage data", expanded=False):
        ledger_view = st.radio(
            "Ledger",
            ["Interconnection requests", "Queue outcomes", "Queue conditions by region", "Reserve margins", "Operating storage"],
            horizontal=True,
            key="grid-storage-ledger-view",
        )
        frames = {
            "Interconnection requests": context.get("development", {}).get("active_queue"),
            "Queue outcomes": context.get("queue_outcomes"),
            "Queue conditions by region": context.get("queue_regions"),
            "Reserve margins": context.get("reserve_margins"),
            "Operating storage": context.get("storage_duration"),
        }
        st.dataframe(arrow_safe_dataframe(frames.get(ledger_view)), width="stretch", height=430, hide_index=True)
