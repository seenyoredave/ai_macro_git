from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from loaders.data_center_registry import campus_display_labels, campus_display_names

from analytics.water_campus import campus_water_dossier, county_water_exposure_profile
from analytics.water_competition import current_top_withdrawal_profile
from analytics.water_local import local_water_constraint_summary
from rendering.visual_system import render_plotly_chart, selection_points
from rendering.charts_water import (
    county_state_for_fips,
    thermoelectric_water_groups,
    water_county_drought_map,
    water_local_context_coverage,
    water_state_evidence_profile,
    water_top_withdrawals_2020,
    wastewater_construction_history,
)
from rendering.common import _render_floating_terms
from rendering.components import (
    fmt_number,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico",
}


def _payload(water_data) -> dict:
    return water_data if isinstance(water_data, dict) else {}


def _context(water_data: dict, infrastructure_data: dict) -> dict:
    water = _payload(water_data)
    campuses = water.get("campus_context")
    if not isinstance(campuses, pd.DataFrame):
        campuses = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        raise ValueError("Water requires the Universal Data Center Registry")
    summary = water.get("campus_context_summary", {}) or {}
    local_summary = local_water_constraint_summary(campuses)
    county_profile = county_water_exposure_profile(campuses)
    dossier = campus_water_dossier(campuses)
    national_profile = current_top_withdrawal_profile(water.get("usgs_2020_top_withdrawals"))
    return {
        "water": water,
        "campuses": campuses,
        "summary": summary,
        "local_summary": local_summary,
        "county_profile": county_profile,
        "dossier": dossier,
        "national_profile": national_profile,
    }


def _pct(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "n/a" if pd.isna(numeric) else f"{float(numeric) * 100.0:.1f}%"


def _latest_county_snapshot(context: dict) -> str:
    campuses = context["campuses"]
    if campuses.empty or "County Drought Snapshot Date" not in campuses.columns:
        return "current county snapshot"
    dates = pd.to_datetime(campuses["County Drought Snapshot Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return "current county snapshot"
    return dates.max().strftime("%Y-%m-%d")


def _local_exposure_stats(context: dict):
    local = context["local_summary"]
    mapped = int(local.get("campuses", 0) or 0)
    covered = int(local.get("campuses_with_county_drought_data", 0) or 0)
    d2 = int(local.get("campuses_in_counties_with_d2", 0) or 0)
    material = int(local.get("campuses_in_counties_with_25pct_d2", 0) or 0)
    highest_location = str(local.get("highest_county_d2_location") or "n/a")
    highest_d2 = pd.to_numeric(local.get("highest_county_d2_area_pct"), errors="coerce")
    return [
        ("Campuses with county drought data", f"{covered:,} / {mapped:,}", f"{_pct(local.get('county_drought_coverage_share'))} coverage"),
        ("Campuses in D2+ counties", f"{d2:,}", f"{_pct(local.get('campuses_in_counties_with_d2_share'))} of campuses with county data"),
        ("Campuses in ≥25% D2+ counties", f"{material:,}", f"{_pct(local.get('campuses_in_counties_with_25pct_d2_share'))} of campuses with county data"),
        ("Highest current D2+ county", highest_location, "n/a" if pd.isna(highest_d2) else f"{float(highest_d2):.1f}% county area"),
    ]


def _render_local_exposure(context: dict) -> None:
    render_section(
        "Current county drought conditions",
        "Current drought conditions across U.S. counties.",
        first=True,
    )
    render_statline(_local_exposure_stats(context), key_prefix="water-local-exposure")
    county_drought = context["water"].get("usdm_county_drought")
    selected_state = str(st.session_state.get("water-drought-state") or "").strip().upper()

    with st.container(border=True, key="full-width-layout-water-county-map"):
        if selected_state:
            title_col, action_col = st.columns([5.5, 1.0], vertical_alignment="center")
            with title_col:
                state_facilities = context["campuses"]
                state_series = state_facilities.get("State", pd.Series("", index=state_facilities.index, dtype=str)).fillna("").astype(str).str.upper().str.strip()
                state_count = int(state_series.eq(selected_state).sum())
                render_panel_heading(
                    f"{STATE_NAMES.get(selected_state, selected_state)} county drought",
                    f"{state_count:,} mapped campuses · {_latest_county_snapshot(context)}",
                )
            with action_col:
                if st.button("United States", key="water-drought-back", width="stretch"):
                    st.session_state.pop("water-drought-state", None)
                    st.rerun()
            figure = water_county_drought_map(
                county_drought,
                context["campuses"],
                state=selected_state,
                height=610,
            )
            event = render_plotly_chart(
                figure,
                width="stretch",
                role="map",
                key=f"water-county-drought-state-{selected_state}",
                on_select="rerun",
                selection_mode="points",
            )
            for point in selection_points(event):
                custom = point.get("customdata")
                if isinstance(custom, (list, tuple)) and custom and str(custom[0] or "").startswith("campus"):
                    st.session_state["water-dossier-campus-id"] = str(custom[0])
                    st.rerun()
        else:
            render_panel_heading("National county drought map", _latest_county_snapshot(context))
            st.caption("Select a county to open its state.")
            figure = water_county_drought_map(
                county_drought,
                context["campuses"],
                height=570,
            )
            event = render_plotly_chart(
                figure,
                width="stretch",
                key="water-county-drought-national",
                role="map",
                on_select="rerun",
                selection_mode="points",
            )
            points = selection_points(event)
            if points:
                fips = str(points[0].get("location") or "").strip()
                state = county_state_for_fips(fips)
                if state:
                    st.session_state["water-drought-state"] = state
                    st.session_state["water-dossier-state"] = state
                    st.rerun()

def _service_area_status(row: pd.Series) -> tuple[str, str]:
    resolved = bool(row.get("PWS Service Area Query Resolved", False))
    overlap = bool(row.get("PWS Service Area Overlap", False))
    ambiguous = bool(row.get("PWS Ambiguous Overlap", False))
    basis = str(row.get("PWS Boundary Basis") or "").strip().casefold()
    if not resolved:
        return "Not resolved", "EPA query"
    if not overlap:
        return "No overlap", "Resolved"
    if ambiguous:
        return "Multiple overlaps", "EPA boundaries"
    if basis == "authoritative":
        return "Authoritative overlap", "EPA boundary"
    if basis == "modeled":
        return "Modeled overlap", "EPA boundary"
    if basis == "mixed":
        return "Mixed overlap", "EPA boundaries"
    return "Boundary overlap", "EPA boundary"


def _text(value, fallback="") -> str:
    if value is None or pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return fallback
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1].strip()
    return text or fallback


def _safe(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _published_capacity_text(row: pd.Series) -> str:
    for column in (
        "Published Capacity MW",
        "Published Capacity Estimate MW",
        "Planned Data Center Capacity MW",
    ):
        value = fmt_number(row.get(column), 0, suffix=" MW")
        if value != "n/a":
            return value
    return "Not published"


def _row_html(label: str, value: str) -> str:
    return (
        '<div class="rm-water-row">'
        f'<span class="rm-water-row-label">{_safe(label)}</span>'
        f'<span class="rm-water-row-value">{_safe(value)}</span>'
        '</div>'
    )


def _detail_section_html(title: str, rows: list[tuple[str, str]], empty_message: str = "") -> str:
    body = "".join(_row_html(label, value) for label, value in rows if str(value or "").strip())
    if not body and empty_message:
        body = f'<div class="rm-water-empty">{_safe(empty_message)}</div>'
    return (
        '<section class="rm-water-detail">'
        f'<div class="rm-water-detail-title">{_safe(title)}</div>'
        f'{body}'
        '</section>'
    )


def _campus_profile_html(row: pd.Series) -> str:
    facility = _text(row.get("Campus Name"), "Unnamed campus")
    operator = _text(row.get("Operator"), "Operator not reported")
    county = _text(row.get("County"))
    state = _text(row.get("State"))
    location = ", ".join(part for part in [county, state] if part)
    subtitle = operator if not location else f"{operator} · {location}"
    status = _text(row.get("Status"), "Status not reported")

    d1 = fmt_number(row.get("Local D1+ Area Percent"), 1, suffix="%")
    d2 = fmt_number(row.get("Local D2+ Area Percent"), 1, suffix="%")
    capacity = _published_capacity_text(row)
    service_value, _ = _service_area_status(row)
    direct = bool(row.get("Direct Water Evidence", False))
    evidence_value = "Direct record" if direct else "No direct record"

    snapshot = _text(row.get("Local Drought Snapshot Date"))
    local_rows = []
    if location:
        local_rows.append(("County", location))
    if d1 != "n/a":
        local_rows.append(("D1+ area", d1))
    if snapshot:
        local_rows.append(("Snapshot", snapshot))

    service_rows = [
        ("EPA query", "Resolved" if bool(row.get("PWS Service Area Query Resolved", False)) else "Not resolved"),
    ]
    if bool(row.get("PWS Service Area Overlap", False)):
        systems = _text(row.get("PWS Names"))
        basis = _text(row.get("PWS Boundary Basis"))
        if systems:
            service_rows.append(("Intersecting systems", systems))
        if basis:
            service_rows.append(("Boundary basis", basis.title()))

    cooling = _text(row.get("Cooling System"))
    source = _text(row.get("Water Source"))
    reclaimed = _text(row.get("Reclaimed Water Use"))
    grade = _text(row.get("Water Evidence Grade"))
    withdrawal = fmt_number(row.get("Water Withdrawal Gallons/Year"), 0, suffix=" gal/year")
    consumption = fmt_number(row.get("Water Consumption Gallons/Year"), 0, suffix=" gal/year")
    disclosure_rows = []
    if cooling:
        disclosure_rows.append(("Cooling system", cooling))
    if source:
        disclosure_rows.append(("Water source", source))
    if reclaimed:
        disclosure_rows.append(("Reclaimed water", reclaimed))
    if withdrawal != "n/a":
        disclosure_rows.append(("Withdrawal", withdrawal))
    if consumption != "n/a":
        disclosure_rows.append(("Consumption", consumption))
    if grade:
        disclosure_rows.append(("Evidence grade", grade))

    metrics = [
        ("County D2+", d2),
        ("Published capacity", capacity),
        ("EPA service area", service_value),
        ("Water evidence", evidence_value),
    ]
    metric_html = "".join(
        '<div class="rm-water-metric">'
        f'<div class="rm-water-metric-label">{_safe(label)}</div>'
        f'<div class="rm-water-metric-value">{_safe(value)}</div>'
        '</div>'
        for label, value in metrics
    )

    detail_html = "".join([
        _detail_section_html("Local conditions", local_rows),
        _detail_section_html("Service area", service_rows),
        _detail_section_html("Campus water", disclosure_rows, "No cooling, water-source, or quantified-use disclosure"),
    ])

    return f'''
<style>
.rm-water-profile-v3 {{
    border: 1px solid rgba(148,163,184,0.24);
    border-radius: 13px;
    background: rgba(10,15,27,0.34);
    overflow: hidden;
    margin-top: 0.75rem;
}}
.rm-water-profile-head {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1.5rem;
    padding: 1.15rem 1.2rem 1rem;
}}
.rm-water-profile-title {{ color: #f8fafc; font-size: 1.42rem; font-weight: 760; letter-spacing: -0.025em; line-height: 1.15; }}
.rm-water-profile-meta {{ color: #9aa7b9; font-size: 0.78rem; line-height: 1.45; margin-top: 0.32rem; }}
.rm-water-status {{
    color: #d8e1ee; border: 1px solid rgba(148,163,184,0.28); border-radius: 999px;
    padding: 0.34rem 0.58rem; font-size: 0.66rem; font-weight: 760; letter-spacing: 0.08em;
    text-transform: uppercase; white-space: nowrap;
}}
.rm-water-metrics {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
    border-top: 1px solid rgba(148,163,184,0.18); border-bottom: 1px solid rgba(148,163,184,0.18);
    background: rgba(15,23,42,0.28);
}}
.rm-water-metric {{ padding: 0.9rem 1.05rem 0.95rem; min-width: 0; }}
.rm-water-metric + .rm-water-metric {{ border-left: 1px solid rgba(148,163,184,0.16); }}
.rm-water-metric-label {{ color: #7f8ba1; font-size: 0.62rem; font-weight: 760; letter-spacing: 0.08em; text-transform: uppercase; }}
.rm-water-metric-value {{ color: #eef2f7; font-size: 1.02rem; font-weight: 710; line-height: 1.28; margin-top: 0.34rem; overflow-wrap: anywhere; }}
.rm-water-details {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); }}
.rm-water-detail {{ padding: 1rem 1.05rem 1.1rem; min-width: 0; }}
.rm-water-detail + .rm-water-detail {{ border-left: 1px solid rgba(148,163,184,0.16); }}
.rm-water-detail-title {{ color: #cfd8e5; font-size: 0.67rem; font-weight: 780; letter-spacing: 0.09em; text-transform: uppercase; margin-bottom: 0.42rem; }}
.rm-water-row {{ display: grid; grid-template-columns: minmax(7.2rem, 0.85fr) minmax(0, 1.15fr); gap: 0.7rem; align-items: baseline; padding: 0.58rem 0; border-bottom: 1px solid rgba(148,163,184,0.11); }}
.rm-water-row:last-of-type {{ border-bottom: 0; }}
.rm-water-row-label {{ color: #7f8ba1; font-size: 0.7rem; }}
.rm-water-row-value {{ color: #dce4ef; font-size: 0.76rem; font-weight: 620; text-align: right; overflow-wrap: anywhere; }}
.rm-water-empty {{ color: #8d9aae; font-size: 0.76rem; line-height: 1.5; padding-top: 0.5rem; max-width: 22rem; }}
@media (max-width: 900px) {{
    .rm-water-metrics {{ grid-template-columns: repeat(2,minmax(0,1fr)); }}
    .rm-water-metric:nth-of-type(3) {{ border-left: 0; border-top: 1px solid rgba(148,163,184,0.16); }}
    .rm-water-metric:nth-of-type(4) {{ border-top: 1px solid rgba(148,163,184,0.16); }}
    .rm-water-details {{ grid-template-columns: 1fr; }}
    .rm-water-detail + .rm-water-detail {{ border-left: 0; border-top: 1px solid rgba(148,163,184,0.16); }}
}}
</style>
<div class="rm-water-profile-v3">
  <div class="rm-water-profile-head">
    <div>
      <div class="rm-water-profile-title">{_safe(facility)}</div>
      <div class="rm-water-profile-meta">{_safe(subtitle)}</div>
    </div>
    <div class="rm-water-status">{_safe(status)}</div>
  </div>
  <div class="rm-water-metrics">{metric_html}</div>
  <div class="rm-water-details">{detail_html}</div>
</div>
'''


def _state_exposure_order(dossier: pd.DataFrame) -> list[str]:
    if dossier.empty:
        return []
    frame = dossier.copy()
    frame["_state"] = frame.get("State", pd.Series("", index=frame.index, dtype=str)).fillna("").astype(str).str.upper().str.strip()
    frame["_d2"] = pd.to_numeric(frame.get("Local D2+ Area Percent", pd.Series(float("nan"), index=frame.index)), errors="coerce").fillna(-1.0)
    frame["_d2_any"] = frame["_d2"].gt(0).astype(int)
    frame["_d2_25"] = frame["_d2"].ge(25).astype(int)
    ranked = (
        frame.loc[frame["_state"].ne("")]
        .groupby("_state", dropna=False)
        .agg(
            material_d2=("_d2_25", "sum"),
            d2_exposed=("_d2_any", "sum"),
            peak_d2=("_d2", "max"),
            campuses=("_state", "size"),
        )
        .reset_index()
        .sort_values(
            ["material_d2", "d2_exposed", "peak_d2", "campuses", "_state"],
            ascending=[False, False, False, False, True],
            kind="stable",
        )
    )
    return ranked["_state"].astype(str).tolist()


def _campus_priority_frame(subset: pd.DataFrame) -> pd.DataFrame:
    frame = subset.copy()
    frame["_d2"] = pd.to_numeric(frame.get("Local D2+ Area Percent", pd.Series(float("nan"), index=frame.index)), errors="coerce").fillna(-1.0)
    frame["_direct"] = frame.get("Direct Water Evidence", pd.Series(False, index=frame.index)).fillna(False).astype(bool).astype(int)
    capacity = pd.Series(float("nan"), index=frame.index, dtype=float)
    for column in ("Published Capacity MW", "Published Capacity Estimate MW", "Planned Data Center Capacity MW"):
        if column in frame.columns:
            capacity = capacity.fillna(pd.to_numeric(frame[column], errors="coerce"))
    frame["_capacity"] = capacity.fillna(-1.0)
    frame["_campus_sort"] = frame.get("Campus Name", pd.Series("", index=frame.index, dtype=str)).fillna("").astype(str).str.casefold()
    return frame.sort_values(
        ["_d2", "_direct", "_capacity", "_campus_sort"],
        ascending=[False, False, False, True],
        kind="stable",
    )


def _render_campus_dossier(context: dict) -> None:
    dossier = context["dossier"]
    map_state = str(st.session_state.get("water-drought-state") or "").strip().upper()
    render_section(
        "Campus water profile",
        "Campuses ordered by current county D2+ exposure.",
    )
    if dossier.empty:
        st.info("No campus records are available for the campus profile.")
        return

    state_series = dossier.get("State", pd.Series("", index=dossier.index, dtype=str)).fillna("").astype(str).str.upper().str.strip()
    states = sorted(state_series.loc[state_series.ne("")].unique().tolist())
    if not states:
        st.info("Campus records are available, but none include a usable state identifier.")
        return

    ranked_states = _state_exposure_order(dossier)
    preferred_state = map_state if map_state in states else (ranked_states[0] if ranked_states else states[0])
    if "water-dossier-state" not in st.session_state or st.session_state.get("water-dossier-state") not in states:
        st.session_state["water-dossier-state"] = preferred_state

    selector_state, selector_campus = st.columns([0.8, 2.2], gap="medium")
    with selector_state:
        state = st.selectbox(
            "State",
            states,
            key="water-dossier-state",
        )

    subset = dossier.loc[state_series.eq(state)].copy()
    if subset.empty:
        st.info("No campus records are available for the selected state.")
        return
    subset = _campus_priority_frame(subset).reset_index(drop=True)

    display_names = campus_display_names(subset).reset_index(drop=True)
    labels = campus_display_labels(subset).reset_index(drop=True).tolist()
    campus_key = f"water-dossier-campus-{state}"
    selected_campus_id = str(st.session_state.get("water-dossier-campus-id") or "").strip()
    if selected_campus_id and "Campus ID" in subset.columns:
        matches = subset.index[subset["Campus ID"].astype(str).eq(selected_campus_id)].tolist()
        if matches:
            desired = labels[matches[0]]
            if st.session_state.get(campus_key) != desired:
                st.session_state[campus_key] = desired
    with selector_campus:
        selected_label = st.selectbox(
            "Campus",
            labels,
            key=campus_key,
        )
    selected_position = labels.index(selected_label) if selected_label in labels else 0
    row = subset.iloc[selected_position].copy()
    row["Campus Name"] = display_names.iloc[selected_position]
    st.markdown(_campus_profile_html(row), unsafe_allow_html=True)

def _coverage_stats(context: dict):
    summary = context["summary"]
    campuses = int(summary.get("campuses", len(context["campuses"])) or 0)
    denominator = max(campuses, 1)
    pws_resolved = int(summary.get("pws_service_area_query_resolved_records", 0) or 0)
    pws_overlap = int(summary.get("pws_service_area_overlap_records", 0) or 0)
    direct = int(summary.get("direct_water_evidence_records", 0) or 0)
    quantified = int(summary.get("quantified_withdrawal_records", 0) or 0) + int(summary.get("quantified_consumption_records", 0) or 0)
    return [
        ("Campuses", f"{campuses:,}", "Universal Data Center Registry"),
        ("EPA point queries resolved", f"{pws_resolved:,}", f"{pws_resolved / denominator * 100.0:.1f}% of campuses"),
        ("EPA boundary overlaps", f"{pws_overlap:,}", "community-water service areas"),
        ("Direct / quantified", f"{direct:,} / {quantified:,}", "campus evidence / quantified records"),
    ]


def _render_coverage(context: dict) -> None:
    campuses = context["campuses"]
    summary = context["summary"]
    render_section(
        "Water data coverage",
        "Coverage across county drought, EPA service-area geography, and campus water disclosure.",
    )
    render_statline(_coverage_stats(context), key_prefix="water-observability")
    with st.container(border=True, key="full-width-layout-water-observability"):
        view = st.radio(
            "Water evidence view",
            ["Coverage layers", "Direct evidence by state"],
            horizontal=True,
            label_visibility="collapsed",
            key="water-observability-view",
        )
        if view == "Direct evidence by state":
            render_panel_heading("Direct campus water evidence by state", "Campus records")
            figure = water_state_evidence_profile(campuses, height=450)
            chart_key = "water-state-evidence-profile"
        else:
            render_panel_heading("Coverage by evidence layer", "Mapped campus coverage")
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
        ("Quantified campus records", f"{quantified:,}", "campus records"),
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
        "National water system",
        "National water allocation, thermoelectric demand, and wastewater investment.",
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
        "County drought conditions, public-water service areas, campus water disclosure, national water demand, and infrastructure investment.",
        "USGS / U.S. Drought Monitor / EPA / EIA / U.S. Census Bureau",
    )
    _render_floating_terms("water")
    render_domain_read(tab_read, label="Read", domain="water")
    _render_local_exposure(context)
    _render_campus_dossier(context)
    _render_system_context_workbench(context, infrastructure_data)
    _render_coverage(context)

    with st.expander("Water data", expanded=False):
        view = st.radio(
            "Ledger",
            ["Campus profile", "County exposure", "County drought snapshot", "EPA service-area matches", "Campus records", "Thermoelectric plants"],
            horizontal=True,
            key="water-ledger-view",
        )
        frames = {
            "Campus profile": context.get("dossier"),
            "County exposure": context.get("county_profile"),
            "County drought snapshot": context.get("water", {}).get("usdm_county_drought"),
            "EPA service-area matches": context.get("water", {}).get("epa_pws_matches"),
            "Campus records": context.get("campuses"),
            "Thermoelectric plants": context.get("water", {}).get("eia_plants"),
        }
        st.dataframe(arrow_safe_dataframe(frames.get(view)), width="stretch", height=460, hide_index=True)
