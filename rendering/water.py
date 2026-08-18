from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.water_competition import (
    campus_water_dossier,
    county_water_exposure_profile,
    current_top_withdrawal_profile,
    local_context_coverage_profile,
    state_facility_evidence_profile,
    state_water_exposure_profile,
)
from analytics.water_local import local_water_constraint_summary
from rendering.visual_system import render_plotly_chart
from rendering.charts_water import (
    thermoelectric_water_groups,
    water_county_drought_exposure,
    water_local_context_coverage,
    water_state_evidence_profile,
    water_top_withdrawals_2020,
    wastewater_construction_history,
)
from rendering.common import _render_floating_terms
from rendering.components import (
    fmt_number,
    render_detail_dossier,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe


def _payload(water_data) -> dict:
    return water_data if isinstance(water_data, dict) else {}


def _context(water_data: dict, infrastructure_data: dict) -> dict:
    water = _payload(water_data)
    facilities = water.get("facility_context")
    if not isinstance(facilities, pd.DataFrame):
        facilities = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(facilities, pd.DataFrame):
        facilities = pd.DataFrame()
    summary = water.get("facility_context_summary", {}) or {}
    local_summary = local_water_constraint_summary(facilities)
    county_profile = county_water_exposure_profile(facilities)
    state_profile = state_water_exposure_profile(facilities, water.get("usgs_state_categories"))
    dossier = campus_water_dossier(facilities)
    national_profile = current_top_withdrawal_profile(water.get("usgs_2020_top_withdrawals"))
    return {
        "water": water,
        "facilities": facilities,
        "summary": summary,
        "local_summary": local_summary,
        "county_profile": county_profile,
        "state_profile": state_profile,
        "dossier": dossier,
        "national_profile": national_profile,
    }


def _pct(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "n/a" if pd.isna(numeric) else f"{float(numeric) * 100.0:.1f}%"


def _latest_county_snapshot(context: dict) -> str:
    facilities = context["facilities"]
    if facilities.empty or "County Drought Snapshot Date" not in facilities.columns:
        return "current county snapshot"
    dates = pd.to_datetime(facilities["County Drought Snapshot Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return "current county snapshot"
    return dates.max().strftime("%Y-%m-%d")


def _local_exposure_stats(context: dict):
    local = context["local_summary"]
    mapped = int(local.get("mapped_facilities", 0) or 0)
    resolved = int(local.get("county_drought_resolved", 0) or 0)
    d2 = int(local.get("facilities_in_counties_with_d2", 0) or 0)
    material = int(local.get("facilities_in_counties_with_25pct_d2", 0) or 0)
    highest_location = str(local.get("highest_county_d2_location") or "n/a")
    highest_d2 = pd.to_numeric(local.get("highest_county_d2_area_pct"), errors="coerce")
    return [
        ("County drought resolved", f"{resolved:,} / {mapped:,}", _pct(local.get("county_drought_resolution_share"))),
        ("Facilities in D2+ counties", f"{d2:,}", f"{_pct(local.get('facilities_in_counties_with_d2_share'))} of county-resolved"),
        ("Facilities in ≥25% D2+ counties", f"{material:,}", f"{_pct(local.get('facilities_in_counties_with_25pct_d2_share'))} of county-resolved"),
        ("Highest current D2+ county", highest_location, "n/a" if pd.isna(highest_d2) else f"{float(highest_d2):.1f}% county area"),
    ]


def _render_local_exposure(context: dict) -> None:
    render_section(
        "Local water constraint",
        "Current county drought conditions around mapped campuses. Drought overlap is physical context, not a claim of campus shortage or curtailment.",
        first=True,
    )
    render_statline(_local_exposure_stats(context), key_prefix="water-local-exposure")
    with st.container(border=True, key="full-width-layout-water-county-exposure"):
        render_panel_heading("Mapped campuses in current drought", _latest_county_snapshot(context))
        figure = water_county_drought_exposure(context["facilities"], height=490)
        render_plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="water-county-drought-exposure",
        )


def _service_area_status(row: pd.Series) -> tuple[str, str]:
    resolved = bool(row.get("PWS Service Area Query Resolved", False))
    overlap = bool(row.get("PWS Service Area Overlap", False))
    ambiguous = bool(row.get("PWS Ambiguous Overlap", False))
    basis = str(row.get("PWS Boundary Basis") or "").strip().casefold()
    if not resolved:
        return "Not resolved", "EPA point query"
    if not overlap:
        return "No boundary overlap", "resolved EPA point query"
    if ambiguous:
        return "Multiple overlaps", "geographic overlap only"
    if basis == "authoritative":
        return "Authoritative overlap", "state/system-sourced boundary"
    if basis == "modeled":
        return "Modeled overlap", "modeled service-area boundary"
    if basis == "mixed":
        return "Mixed overlap", "authoritative + modeled boundaries"
    if basis == "unclassified":
        return "Unclassified overlap", "EPA boundary provenance not populated"
    return "Boundary overlap", "geographic overlap only"


def _render_campus_dossier(context: dict) -> None:
    dossier = context["dossier"]
    render_section(
        "Campus water profile",
        "Facility-level local drought, public-water service-area context, cooling and water-source records, and direct disclosure.",
    )
    if dossier.empty:
        st.info("No facility records are available for the campus profile.")
        return

    state_series = dossier.get("State", pd.Series("", index=dossier.index, dtype=str)).fillna("").astype(str).str.strip()
    states = sorted(state_series.loc[state_series.ne("")].unique().tolist())
    if not states:
        st.info("Campus records are available, but none include a usable state identifier.")
        return

    state = st.selectbox("State", states, key="water-dossier-state")
    subset = dossier.loc[state_series.eq(state)].copy()
    if subset.empty:
        st.info("No campus records are available for the selected state.")
        return

    labels = subset.apply(
        lambda row: f"{row.get('Facility', 'Unnamed facility')} · {row.get('Operator', 'Unknown operator')}",
        axis=1,
    ).tolist()
    selected_label = st.selectbox("Campus", labels, key="water-dossier-campus")
    row = subset.iloc[labels.index(selected_label)] if selected_label in labels else subset.iloc[0]

    def text(value, fallback="Not disclosed"):
        if value is None or pd.isna(value) or not str(value).strip() or str(value).strip().casefold() == "nan":
            return fallback
        return str(value).strip()

    capacity = fmt_number(row.get("Published Capacity MW"), 0, suffix=" MW")
    if capacity == "n/a":
        capacity = "Not published"
    d1 = fmt_number(row.get("Local D1+ Area Percent"), 1, suffix="%")
    d2 = fmt_number(row.get("Local D2+ Area Percent"), 1, suffix="%")
    quantified = (
        pd.notna(pd.to_numeric(row.get("Water Withdrawal Gallons/Year"), errors="coerce"))
        or pd.notna(pd.to_numeric(row.get("Water Consumption Gallons/Year"), errors="coerce"))
    )
    location = ", ".join(part for part in [text(row.get("County"), ""), text(row.get("State"), "")] if part)
    operator = text(row.get("Operator"), "Operator not reported")
    snapshot = text(row.get("Local Drought Snapshot Date"), "Snapshot date unavailable")
    geography = text(row.get("Local Drought Geography"), "local context")
    service_value, service_note = _service_area_status(row)
    pws_names = text(row.get("PWS Names"), "No intersecting community-water boundary")
    pws_count_value = pd.to_numeric(row.get("PWS Match Count"), errors="coerce")
    pws_count = int(pws_count_value) if pd.notna(pws_count_value) else 0

    with st.container(key="water-campus-dossier-record"):
        render_detail_dossier(
            title=text(row.get("Facility"), "Unnamed campus"),
            subtitle=f"{operator} · {location}" if location else operator,
            badge=text(row.get("Status"), "Status not reported"),
            headline_facts=[
                ("Current D2+ overlap", d2, f"{geography} drought context"),
                ("EPA service-area context", service_value, service_note),
                ("Direct water evidence", "Yes" if bool(row.get("Direct Water Evidence", False)) else "No", "facility-level public record"),
            ],
            groups=[
                (
                    "Local physical context",
                    [
                        ("D1+ area", d1, snapshot),
                        ("D2+ area", d2, snapshot),
                        ("Drought geography", geography.title(), "county preferred; state fallback only"),
                        ("Published capacity", capacity, "public campus estimate"),
                    ],
                ),
                (
                    "Public-water service-area context",
                    [
                        ("EPA query", "Resolved" if bool(row.get("PWS Service Area Query Resolved", False)) else "Not resolved", "point-in-polygon query"),
                        ("Boundary overlap", service_value, "does not establish service or purchases"),
                        ("Intersecting systems", pws_names, f"{pws_count} boundary record(s)"),
                        ("Boundary basis", text(row.get("PWS Boundary Basis"), "No overlap"), "authoritative / modeled / mixed / unclassified"),
                    ],
                ),
                (
                    "Direct facility disclosure",
                    [
                        ("Cooling system", text(row.get("Cooling System")), "facility evidence"),
                        ("Water source", text(row.get("Water Source")), "facility evidence"),
                        ("Quantified use", "Yes" if quantified else "No", "annual withdrawal or consumption"),
                        ("Withdrawal", fmt_number(row.get("Water Withdrawal Gallons/Year"), 0, suffix=" gal/year"), "published facility record"),
                        ("Consumption", fmt_number(row.get("Water Consumption Gallons/Year"), 0, suffix=" gal/year"), "published facility record"),
                        ("Evidence grade", text(row.get("Water Evidence Grade"), "Unrated"), "facility-level disclosure"),
                    ],
                ),
            ],
            key_prefix="water-campus-dossier",
        )


def _coverage_stats(context: dict):
    summary = context["summary"]
    facilities = max(int(summary.get("facilities", 0) or 0), 1)
    pws_resolved = int(summary.get("pws_service_area_query_resolved_records", 0) or 0)
    pws_overlap = int(summary.get("pws_service_area_overlap_records", 0) or 0)
    direct = int(summary.get("direct_water_evidence_records", 0) or 0)
    quantified = int(summary.get("quantified_withdrawal_records", 0) or 0) + int(summary.get("quantified_consumption_records", 0) or 0)
    return [
        ("Mapped facilities", f"{int(summary.get('facilities', 0) or 0):,}", "facility registry"),
        ("EPA point queries resolved", f"{pws_resolved:,}", f"{pws_resolved / facilities * 100.0:.1f}% of mapped facilities"),
        ("EPA boundary overlaps", f"{pws_overlap:,}", "geographic context only"),
        ("Direct / quantified", f"{direct:,} / {quantified:,}", "facility evidence / quantified records"),
    ]


def _render_coverage(context: dict) -> None:
    facilities = context["facilities"]
    summary = context["summary"]
    render_section(
        "Water observability",
        "Coverage of current physical context, EPA service-area geography, and direct facility water disclosure. These layers are independent rather than a single evidence funnel.",
    )
    render_statline(_coverage_stats(context), key_prefix="water-observability")
    with st.container(border=True, key="full-width-layout-water-observability"):
        view = st.radio(
            "Water observability view",
            ["Coverage layers", "Direct evidence by state"],
            horizontal=True,
            label_visibility="collapsed",
            key="water-observability-view",
        )
        if view == "Direct evidence by state":
            render_panel_heading("Direct facility water evidence by state", "Mapped campus records")
            figure = water_state_evidence_profile(facilities, height=450)
            chart_key = "water-state-evidence-profile"
        else:
            render_panel_heading("What the Water layer can observe", "Independent context and disclosure surfaces")
            figure = water_local_context_coverage(summary, height=450)
            chart_key = "water-local-context-coverage"
        render_plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=chart_key,
        )


def _national_claim_stats(context: dict):
    profile = context["national_profile"]
    values = profile.set_index("Use Category")["Withdrawal Bgal/day"].to_dict() if not profile.empty else {}
    summary = context["summary"]
    quantified = int(summary.get("quantified_withdrawal_records", 0) or 0) + int(summary.get("quantified_consumption_records", 0) or 0)
    return [
        ("Crop irrigation", fmt_number(values.get("Crop irrigation"), 1, suffix=" Bgal/day"), "USGS modeled withdrawal"),
        ("Thermoelectric power", fmt_number(values.get("Thermoelectric power"), 1, suffix=" Bgal/day"), "USGS modeled withdrawal"),
        ("Public supply", fmt_number(values.get("Public supply"), 1, suffix=" Bgal/day"), "USGS modeled withdrawal"),
        ("Quantified facility records", f"{quantified:,}", "not extrapolated nationally"),
    ]


def _thermoelectric_stats(context: dict):
    eia = ((context["water"].get("summary", {}) or {}).get("eia_2024_thermoelectric", {}) or {})
    if not eia:
        return []
    return [
        ("Reported withdrawal", fmt_number(eia.get("withdrawal_bgal_day"), 2, suffix=" Bgal/day"), "annual total ÷ 366"),
        ("Reported consumption", fmt_number(eia.get("consumption_bgal_day"), 2, suffix=" Bgal/day"), "annual total ÷ 366"),
        ("Withdrawal coverage", f"{int(eia.get('plants_with_withdrawal', 0) or 0):,} / {int(eia.get('plants', 0) or 0):,}", "plants"),
        ("Consumption coverage", f"{int(eia.get('plants_with_consumption', 0) or 0):,} / {int(eia.get('plants', 0) or 0):,}", "plants"),
    ]


def _wastewater_stats(context: dict, infrastructure_data: dict):
    series = (((infrastructure_data or {}).get("series", {}) or {}).get("Public Sewage and Waste Disposal Construction", {}) or {})
    value = pd.to_numeric(series.get("value"), errors="coerce")
    growth = pd.to_numeric(series.get("yoy_growth"), errors="coerce")
    date = pd.to_datetime(series.get("date"), errors="coerce", format="mixed")
    return [
        ("Current pace", "n/a" if pd.isna(value) else f"${value / 1000.0:.1f}B", "annual rate"),
        ("Year-over-year", fmt_number(growth * 100.0, 1, signed=True, suffix="%"), "construction spending"),
        ("Latest observation", "n/a" if pd.isna(date) else date.strftime("%Y-%m"), "U.S. Census Bureau"),
    ]


def _render_system_context_workbench(context: dict, infrastructure_data: dict) -> None:
    water = context["water"]
    thermo_stats = _thermoelectric_stats(context)
    views = ["National water allocation"]
    if thermo_stats:
        views.append("Thermoelectric system")
    views.append("Wastewater investment")
    render_section(
        "System context, not data-center use",
        "National water allocation, thermoelectric demand, and wastewater investment provide scale and infrastructure context without estimating data-center water consumption.",
    )
    with st.container(border=True, key="water-system-workbench"):
        view = st.radio(
            "Comparison view",
            views,
            horizontal=True,
            label_visibility="collapsed",
            key="water-system-context-view",
        )
        if view == "Thermoelectric system":
            metric = st.radio(
                "Thermoelectric metric",
                ["Withdrawal", "Consumption"],
                horizontal=True,
                label_visibility="collapsed",
                key="water-thermoelectric-metric",
            )
            render_panel_heading(f"Thermoelectric {metric.lower()} by cooling group", "EIA 2024")
            render_statline(thermo_stats, key_prefix="water-context-thermoelectric")
            figure = thermoelectric_water_groups(water.get("eia_groups"), metric=metric, height=430)
            chart_key = "water-thermoelectric-groups"
        elif view == "Wastewater investment":
            render_panel_heading("Wastewater-system construction", "Seasonally adjusted annual rate")
            render_statline(_wastewater_stats(context, infrastructure_data), key_prefix="water-context-wastewater")
            figure = wastewater_construction_history((infrastructure_data or {}).get("construction_history"), height=430)
            chart_key = "water-wastewater-construction-history"
        else:
            render_panel_heading("Largest national withdrawal categories", "Conterminous U.S. · 2020")
            render_statline(_national_claim_stats(context), key_prefix="water-context-national")
            figure = water_top_withdrawals_2020(water.get("usgs_2020_top_withdrawals"), height=430)
            chart_key = "water-competing-uses-2020"
        render_plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=chart_key,
        )


def render_water_tab(water_data: dict, infrastructure_data: dict, tab_read=None) -> None:
    context = _context(water_data, infrastructure_data)
    render_tab_header(
        "Water",
        "Local drought exposure, public-water service-area context, facility disclosure, competing water demand, and water-system investment.",
        "USGS / U.S. Drought Monitor / EPA / EIA / U.S. Census Bureau",
    )
    _render_floating_terms("water")
    render_domain_read(tab_read, label="Read", domain="water")
    _render_local_exposure(context)
    _render_campus_dossier(context)
    _render_coverage(context)
    _render_system_context_workbench(context, infrastructure_data)

    with st.expander("Water data", expanded=False):
        view = st.radio(
            "Ledger",
            ["Campus profile", "County exposure", "County drought snapshot", "EPA service-area matches", "Facility records", "Thermoelectric plants"],
            horizontal=True,
            key="water-ledger-view",
        )
        frames = {
            "Campus profile": context.get("dossier"),
            "County exposure": context.get("county_profile"),
            "County drought snapshot": context.get("water", {}).get("usdm_county_drought"),
            "EPA service-area matches": context.get("water", {}).get("epa_pws_matches"),
            "Facility records": context.get("facilities"),
            "Thermoelectric plants": context.get("water", {}).get("eia_plants"),
        }
        st.dataframe(arrow_safe_dataframe(frames.get(view)), width="stretch", height=460, hide_index=True)
