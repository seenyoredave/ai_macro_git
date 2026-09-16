from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.evidence_gateway import render_evidence_gateway
from rendering.visual_system import render_plotly_chart
from rendering.charts_connectivity import (
    cable_pipeline_status,
    campus_distance_distribution,
    interconnection_market_depth,
    landing_gateway_map,
    landing_markets_by_region,
    middle_mile_awards_by_state,
)
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


def _count(value) -> int:
    numeric = pd.to_numeric(value, errors="coerce")
    return 0 if pd.isna(numeric) else int(numeric)


def _money_billions(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "n/a" if pd.isna(numeric) else f"${numeric / 1_000_000_000:.2f}B"


def _inject_connectivity_theme() -> None:
    st.html(
        """
        <style>
        div[class*="st-key-connectivity-panel-"] {
            border-color: rgba(96, 165, 250, 0.16) !important;
            background: rgba(17, 24, 39, 0.72) !important;
            box-shadow: inset 0 1px 0 rgba(96, 165, 250, 0.04) !important;
        }
        div[class*="st-key-statline-connectivity-"] {
            border-top-color: rgba(96, 165, 250, 0.78) !important;
        }
        </style>
        """,
    )


def _render_current_state(connectivity: dict) -> None:
    national = connectivity.get("national_summary", {}) or {}
    coverage = connectivity.get("coverage", {}) or {}
    facility_count = _count(national.get("PeeringDB Facilities"))
    facility_floor = _count(national.get("PeeringDB Facility Coverage Floor") or coverage.get("facility_search_floor"))
    facility_value = f"{facility_count:,}" if facility_count else f"{facility_floor:,}+"
    render_section(
        "Network overview",
        "U.S.-connected submarine cables, internet exchanges, and federally funded middle-mile fiber.",
        first=True,
        compact=True,
    )
    render_statline([
        ("States with network gap", f"{_count(coverage.get('mismatch_states')):,}", "data-center capacity with limited public interconnection depth"),
        ("Campuses screened", f"{_count(coverage.get('campuses_screened')):,}", "data-center connectivity context"),
        ("Active IXPs", f"{_count(national.get('Active IXPs')):,}", f"{_count(national.get('Combined Reported Members')):,} memberships"),
        ("Interconnection facilities", facility_value, "PeeringDB records"),
        ("Middle-mile fiber", f"{_count(national.get('Middle-Mile New Fiber Miles')):,}+ mi", f"{_count(national.get('Middle-Mile Award Records')):,} awards"),
    ], key_prefix="connectivity-pulse")


def _render_submarine(connectivity: dict) -> None:
    cables = connectivity.get("submarine_cable_systems")
    landings = connectivity.get("cable_landing_markets")
    coverage = connectivity.get("coverage", {}) or {}
    national = connectivity.get("national_summary", {}) or {}
    render_section("Submarine cable gateways", "U.S.-connected submarine cable systems and the markets where they land.")
    metrics = [
        ("Catalog entries", f"{_count(coverage.get('cable_catalog_entries')):,}", "U.S.-connected systems"),
        ("Planned entries", f"{_count(coverage.get('planned_cable_entries')):,}", "RFS after 2026"),
        ("Landing markets", f"{_count(coverage.get('selected_landing_markets')):,}", "selected U.S. gateways"),
        ("Current-year / future", f"{_count(national.get('Future / Current-Year Cable Entries')):,}", "catalog entries"),
    ]
    render_summary_row(metrics, key_prefix="connectivity-submarine-map")
    with st.container(key="full-width-layout-connectivity-gateway-map"):
        with st.container(border=True, key="connectivity-panel-submarine-map"):
            view = st.radio("Cable view", ["Submarine cable gateways", "Cable pipeline", "Landing regions"], horizontal=True, label_visibility="collapsed", key="connectivity-view-submarine")
            if view == "Cable pipeline":
                render_panel_heading("Cable catalog by service status", "U.S.-connected entries")
                figure, key = cable_pipeline_status(cables, height=520), "connectivity-cable-pipeline"
            elif view == "Landing regions":
                render_panel_heading("Landing markets by ocean region", "Market-level register")
                figure, key = landing_markets_by_region(landings, height=520), "connectivity-landing-regions"
            else:
                render_panel_heading("Selected U.S. cable-landing gateway markets", "Mainland, Alaska, Hawaii, and territories")
                figure, key = landing_gateway_map(landings, height=560), "connectivity-gateway-map"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=key, role="map" if view == "Submarine cable gateways" else "pipeline")

def _render_interconnection(connectivity: dict) -> None:
    markets = connectivity.get("interconnection_market_summary")
    national = connectivity.get("national_summary", {}) or {}
    render_section("Internet exchanges", "Exchange participation, physical locations, and concentration by market.")
    centers = _count(national.get("Population Centers With IXP")); center_total = _count(national.get("Population Centers Over 300k"))
    render_summary_row([
        ("Reported memberships", f"{_count(national.get('Combined Reported Members')):,}", "exchange memberships"),
        ("Markets in register", f"{len(markets) if isinstance(markets, pd.DataFrame) else 0:,}", "published IXP locations"),
        ("Large population centers", f"{centers:,} / {center_total:,}", "with an IXP"),
        ("Domestic network coverage", fmt_number(national.get("Domestic Network Coverage Percent"), 0, suffix="%"), "Pulse country measure"),
    ], key_prefix="connectivity-interconnection-metrics")
    with st.container(key="full-width-layout-connectivity-interconnection"):
        with st.container(border=True, key="connectivity-panel-interconnection"):
            metric_label = st.radio("Interconnection metric", ["Reported memberships", "IXP physical-location references", "IXPs"], horizontal=True, label_visibility="collapsed", key="connectivity-view-interconnection")
            metric = {"Reported memberships": "Reported Memberships", "IXP physical-location references": "IXP Physical Location References", "IXPs": "IXPs"}[metric_label]
            render_panel_heading("Leading interconnection markets", f"Ranked by {metric_label.lower()}")
            render_plotly_chart(interconnection_market_depth(markets, metric=metric, height=520), width="stretch", config={"displayModeBar": False, "responsive": True}, key="connectivity-interconnection-markets")

def _render_middle_mile(connectivity: dict) -> None:
    awards = connectivity.get("middle_mile_awards")
    summary = connectivity.get("middle_mile_summary", {}) or {}
    render_section("Middle-mile fiber", "Federal middle-mile awards, planned fiber miles, and the states and territories they cover.")
    render_summary_row([
        ("Federal awards", _money_billions(summary.get("Federal Awards USD")), "NTIA program"),
        ("Award records", f"{_count(summary.get('Award Records')):,}", f"{_count(summary.get('Award Recipients')):,} recipients"),
        ("New fiber miles", f"{_count(summary.get('New Fiber Miles')):,}+", "planned construction"),
        ("States & territories", f"{_count(summary.get('States and Territories Reached')):,}", "program reach"),
    ], key_prefix="connectivity-middle-mile-metrics")
    with st.container(key="full-width-layout-connectivity-middle-mile"):
        with st.container(border=True, key="connectivity-panel-middle-mile"):
            render_panel_heading("Middle-mile awards by state or territory", "Awarded funding")
            render_plotly_chart(middle_mile_awards_by_state(awards, height=520), width="stretch", config={"displayModeBar": False, "responsive": True}, key="connectivity-middle-mile-awards")

def _render_ai_network_interaction(connectivity: dict) -> None:
    state = connectivity.get("state_summary")
    campuses = connectivity.get("campus_connectivity_snapshot")
    coverage = connectivity.get("coverage", {}) or {}
    render_section("Data centers and network access", "Published data-center capacity alongside local internet-exchange activity and cable-landing proximity.")
    render_summary_row([
        ("States with network gap", f"{_count(coverage.get('mismatch_states')):,}", "capacity with limited IXP depth"),
        ("Campuses compared", f"{_count(coverage.get('campuses_screened')):,}", "published capacity"),
        ("Landing proximity", f"{_count(coverage.get('campuses_with_landing_proximity')):,}", "campus records"),
        ("Facility proximity", f"{_count(coverage.get('campuses_with_live_facility_proximity')):,}", "PeeringDB matches"),
    ], key_prefix="connectivity-mismatch-metrics")
    with st.container(key="full-width-layout-connectivity-compute-transport"):
        with st.container(border=True, key="connectivity-panel-compute-transport"):
            view = st.radio("Comparison view", ["State comparison", "Campus proximity"], horizontal=True, label_visibility="collapsed", key="connectivity-compute-transport-view")
            if view == "Campus proximity":
                render_panel_heading("Campus distance to landing markets", "Great-circle proximity")
                figure, key = campus_distance_distribution(campuses, height=520), "connectivity-campus-distance"
            else:
                lens = st.radio("Map view", ["Data-center/network gap", "Connectivity depth", "Published capacity"], horizontal=True, label_visibility="collapsed", key="connectivity-view-mismatch")
                render_panel_heading("Data-center capacity and network access", lens)
                figure, key = data_center_connectivity_state(state, height=520, lens=lens), "connectivity-state-mismatch"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=key)

def _coverage_ratio(numerator, denominator) -> str:
    numerator_value = _count(numerator)
    denominator_value = _count(denominator)
    if denominator_value <= 0:
        return "n/a"
    return fmt_number(numerator_value / denominator_value * 100.0, 0, suffix="%")


def _render_evidence_coverage(connectivity: dict) -> None:
    coverage = connectivity.get("coverage", {}) or {}
    screened = _count(coverage.get("campuses_screened"))
    landing = _count(coverage.get("campuses_with_landing_proximity"))
    facilities = _count(coverage.get("campuses_with_live_facility_proximity"))
    render_section(
        "Evidence coverage",
        "Public-network observations available for the current data-center connectivity screen.",
    )
    render_statline([
        ("Campuses screened", f"{screened:,}", "connectivity comparison set"),
        ("Landing proximity", f"{landing:,}", f"{_coverage_ratio(landing, screened)} of screened campuses"),
        ("Facility proximity", f"{facilities:,}", f"{_coverage_ratio(facilities, screened)} of screened campuses"),
        ("States with IXP evidence", f"{_count(coverage.get('states_with_ixp_evidence')):,}", "reported public interconnection activity"),
    ], key_prefix="connectivity-evidence-coverage")


def render_connectivity_tab(connectivity_data: dict | None, infrastructure_data: dict | None = None, tab_read=None) -> None:
    connectivity = connectivity_data if isinstance(connectivity_data, dict) else {}
    if not connectivity and isinstance(infrastructure_data, dict):
        connectivity = infrastructure_data.get("connectivity", {}) or {}
    _inject_connectivity_theme()
    render_tab_header(
        "Connectivity",
        "Submarine cables, internet exchanges, middle-mile fiber, and links to major data-center markets.",
        "FCC / Internet Society Pulse / PeeringDB / TeleGeography / NTIA",
        terms_key="connectivity",
    )
    render_domain_read(tab_read, label="Read", domain="connectivity")
    _render_current_state(connectivity)
    _render_ai_network_interaction(connectivity)
    _render_interconnection(connectivity)
    _render_submarine(connectivity)
    _render_middle_mile(connectivity)
    _render_evidence_coverage(connectivity)
    render_evidence_gateway("connectivity")

