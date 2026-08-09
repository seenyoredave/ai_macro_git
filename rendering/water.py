from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.water_competition import (
    campus_water_dossier,
    current_top_withdrawal_profile,
    evidence_ladder,
    state_facility_evidence_profile,
    state_water_exposure_profile,
)
from rendering.visual_system import render_plotly_chart
from rendering.charts_water import (
    thermoelectric_water_groups,
    water_capacity_disclosure_scatter,
    water_drought_exposure,
    water_evidence_ladder,
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
    state_profile = state_water_exposure_profile(facilities, water.get("usgs_state_categories"))
    dossier = campus_water_dossier(facilities)
    national_profile = current_top_withdrawal_profile(water.get("usgs_2020_top_withdrawals"))
    return {
        "water": water,
        "facilities": facilities,
        "summary": summary,
        "state_profile": state_profile,
        "dossier": dossier,
        "national_profile": national_profile,
    }


def _fallback_read(context: dict) -> dict:
    summary = context.get("summary", {})
    facilities = int(summary.get("facilities", 0) or 0)
    direct = int(summary.get("direct_water_evidence_records", 0) or 0)
    severe = int(summary.get("severe_drought_facilities", 0) or 0)
    if facilities and direct / max(facilities, 1) < 0.1:
        headline = "Local water exposure is visible; facility disclosure remains sparse."
    elif severe:
        headline = "Data-center development overlaps active drought in several states."
    else:
        headline = "Water exposure varies sharply by place and cooling design."
    body = (
        f"The dataset includes {facilities:,} facilities, including {direct:,} with direct water evidence. "
        f"{severe:,} facilities sit in states reporting severe-drought area in July 2026."
    )
    return {"headline": headline, "body": body, "confidence": "moderate" if facilities else "limited"}


def _state_exposure_stats(context: dict):
    state_profile = context["state_profile"]
    severe_mask = state_profile.get("D2+ Area Percent", pd.Series(dtype=float)).fillna(0).gt(0) if not state_profile.empty else pd.Series(dtype=bool)
    severe_states = int(severe_mask.sum()) if not state_profile.empty else 0
    severe_capacity = pd.to_numeric(
        state_profile.loc[severe_mask, "Published Capacity MW"], errors="coerce"
    ).sum(min_count=1) if not state_profile.empty else np.nan
    highest = state_profile.iloc[0] if not state_profile.empty else pd.Series(dtype=object)
    summary = context["summary"]
    coverage = summary.get("direct_water_evidence_records", 0) / max(summary.get("facilities", 0), 1) * 100.0
    return [
        ("States with D2+ area", f"{severe_states:,}", "among mapped facility states"),
        ("Capacity in D2+ states", fmt_number(severe_capacity, 0, suffix=" MW"), "published campus capacity"),
        ("Highest current overlap", str(highest.get("State") or "n/a"), fmt_number(highest.get("D2+ Area Percent"), 1, suffix="% D2+ area")),
        ("Direct evidence coverage", fmt_number(coverage, 1, suffix="%"), "mapped facilities"),
    ]


def _render_state_exposure(context: dict) -> None:
    facilities = context["facilities"]
    water = context["water"]
    render_section(
        "Exposure state",
        "Where data-center capacity overlaps current drought and how much facility-level water evidence is visible.",
        first=True,
    )
    render_statline(_state_exposure_stats(context), key_prefix="water-exposure-state")
    with st.container(border=True, key="full-width-layout-water-state-exposure"):
        view = st.radio(
            "Water exposure view",
            ["Drought overlap", "Capacity and disclosure"],
            horizontal=True,
            label_visibility="collapsed",
            key="water-exposure-view",
        )
        if view == "Capacity and disclosure":
            render_panel_heading("Capacity and water disclosure", "State footprint")
            figure = water_capacity_disclosure_scatter(facilities, water.get("usgs_state_categories"), height=480)
            chart_key = "water-capacity-disclosure"
        else:
            render_panel_heading("Data-center footprint and drought area", "July 2026")
            figure = water_drought_exposure(facilities, water.get("usgs_state_categories"), height=480)
            chart_key = "water-drought-exposure"
        render_plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=chart_key,
        )


def _render_campus_dossier(context: dict) -> None:
    dossier = context["dossier"]
    render_section("Campus water exposure dossier", "A campus-level record of development status, local exposure, and the strength of public water evidence.")
    if dossier.empty:
        st.info("No facility records are available for the campus dossier.")
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

    labels = subset.apply(lambda row: f"{row.get('Facility', 'Unnamed facility')} · {row.get('Operator', 'Unknown operator')}", axis=1).tolist()
    if not labels:
        st.info("No campus records are available for the selected state.")
        return
    selected_label = st.selectbox("Campus", labels, key="water-dossier-campus")
    row = subset.iloc[labels.index(selected_label)] if selected_label in labels else subset.iloc[0]

    def text(value, fallback="Not disclosed"):
        if value is None or pd.isna(value) or not str(value).strip() or str(value).strip().casefold() == "nan":
            return fallback
        return str(value).strip()

    capacity = fmt_number(row.get("Published Capacity MW"), 0, suffix=" MW")
    if capacity == "n/a":
        capacity = "Not published"
    d1 = fmt_number(row.get("D1+ Area Percent"), 1, suffix="%")
    d2 = fmt_number(row.get("D2+ Area Percent"), 1, suffix="%")
    quantified = (
        pd.notna(pd.to_numeric(row.get("Water Withdrawal Gallons/Year"), errors="coerce"))
        or pd.notna(pd.to_numeric(row.get("Water Consumption Gallons/Year"), errors="coerce"))
    )
    location = ", ".join(part for part in [text(row.get("County"), ""), text(row.get("State"), "")] if part)
    operator = text(row.get("Operator"), "Operator not reported")
    snapshot = text(row.get("Snapshot Date"), "Snapshot date unavailable")

    with st.container(key="water-campus-dossier-record"):
        render_detail_dossier(
            title=text(row.get("Facility"), "Unnamed campus"),
            subtitle=f"{operator} · {location}" if location else operator,
            badge=text(row.get("Status"), "Status not reported"),
            headline_facts=[
                ("Published capacity", capacity, "public campus estimate"),
                ("Current D2+ overlap", d2, text(row.get("Exposure Tier"), "current drought context")),
                ("Evidence grade", text(row.get("Water Evidence Grade"), "Unrated"), "facility-level water disclosure"),
            ],
            groups=[
                (
                    "Physical exposure",
                    [
                        ("D1+ area", d1, snapshot),
                        ("D2+ area", d2, snapshot),
                        ("Cooling system", text(row.get("Cooling System")), "facility evidence"),
                        ("Water source", text(row.get("Water Source")), "facility evidence"),
                    ],
                ),
                (
                    "Evidence and disclosure",
                    [
                        ("Quantified use", "Yes" if quantified else "No", "annual withdrawal or consumption"),
                        ("Withdrawal", fmt_number(row.get("Water Withdrawal Gallons/Year"), 0, suffix=" gal/year"), "published facility record"),
                        ("Consumption", fmt_number(row.get("Water Consumption Gallons/Year"), 0, suffix=" gal/year"), "published facility record"),
                        ("Evidence status", text(row.get("Water Evidence Status"), "No direct record"), "public record"),
                    ],
                ),
            ],
            key_prefix="water-campus-dossier",
        )

def _disclosure_stats(context: dict):
    facilities = context["facilities"]
    summary = context["summary"]
    state_profile = state_facility_evidence_profile(facilities)
    mapped_states = int(state_profile["State"].nunique()) if not state_profile.empty else 0
    direct_states = int(state_profile.loc[state_profile["Direct Water Evidence"].gt(0), "State"].nunique()) if not state_profile.empty else 0
    ladder = evidence_ladder(summary)
    quantified = int(ladder.loc[ladder["Evidence Stage"].isin(["Quantified withdrawal", "Quantified consumption"]), "Facilities"].sum()) if not ladder.empty else 0
    return [
        ("Mapped facilities", f"{int(summary.get('facilities', 0) or 0):,}", f"{mapped_states} states"),
        ("Direct evidence", f"{int(summary.get('direct_water_evidence_records', 0) or 0):,}", f"{direct_states} states"),
        ("Quantified records", f"{quantified:,}", "withdrawal + consumption stages"),
        ("County water context", f"{int(summary.get('county_context_records', 0) or 0):,}", "historical county context"),
    ]


def _render_disclosure(context: dict) -> None:
    facilities = context["facilities"]
    summary = context["summary"]
    render_section(
        "Evidence ladder",
        "How quickly the evidence thins from mapped location to direct, quantified facility-level water use.",
    )
    render_statline(_disclosure_stats(context), key_prefix="water-evidence-state")
    with st.container(border=True, key="full-width-layout-water-evidence"):
        view = st.radio(
            "Disclosure view",
            ["Evidence ladder", "State coverage"],
            horizontal=True,
            label_visibility="collapsed",
            key="water-disclosure-view",
        )
        if view == "State coverage":
            render_panel_heading("Facility and disclosure coverage by state", "Operating and in-development campuses")
            figure = water_state_evidence_profile(facilities, height=450)
            chart_key = "water-state-evidence-profile"
        else:
            render_panel_heading("AI water evidence ladder", "Facility records")
            figure = water_evidence_ladder(summary, height=450)
            chart_key = "water-evidence-ladder"
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
        ("Quantified facility records", f"{quantified:,}", "withdrawal or consumption"),
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
    views = ["National water claims"]
    if thermo_stats:
        views.append("Thermoelectric system")
    views.append("Wastewater investment")
    render_section(
        "Broader water-system context",
        "Reference context sits behind the facility evidence rather than competing with it for top-of-page attention.",
    )
    with st.container(border=True, key="water-system-workbench"):
        view = st.radio(
            "Context view",
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
        "Local water exposure, cooling evidence, drought conditions, competing demand, and public-system investment.",
        "USGS / NOAA-NCEI / EIA / U.S. Census Bureau",
    )
    _render_floating_terms("water")
    render_domain_read(tab_read or _fallback_read(context), label="Water Read", domain="water")
    _render_state_exposure(context)
    _render_campus_dossier(context)
    _render_disclosure(context)
    _render_system_context_workbench(context, infrastructure_data)

    with st.expander("Water data", expanded=False):
        view = st.radio(
            "Ledger",
            ["Campus dossier", "State exposure", "Drought snapshot", "Facility records", "Thermoelectric plants"],
            horizontal=True,
            key="water-ledger-view",
        )
        frames = {
            "Campus dossier": context.get("dossier"),
            "State exposure": context.get("state_profile"),
            "Drought snapshot": context.get("water", {}).get("usdm_state_drought"),
            "Facility records": context.get("facilities"),
            "Thermoelectric plants": context.get("water", {}).get("eia_plants"),
        }
        st.dataframe(arrow_safe_dataframe(frames.get(view)), width="stretch", height=460, hide_index=True)
