from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from rendering.charts_water import thermoelectric_water_groups, water_withdrawal_components
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_number, render_line_break, render_panel_heading, render_section, render_static_table, render_statline, render_tab_header

def _water_utilization_payload(water_data):
    return water_data or {}

def _render_water_utilization(water_data):
    water = _water_utilization_payload(water_data)
    summary = water.get("summary", {}) or {}
    usgs = summary.get("usgs_2015", {}) or {}
    eia = summary.get("eia_2024_thermoelectric", {}) or {}
    national_categories = water.get("usgs_national_categories")
    state_categories = water.get("usgs_state_categories")
    eia_groups = water.get("eia_groups")
    eia_plants = water.get("eia_plants")
    counties = water.get("usgs_counties")

    if not usgs:
        st.error("U.S. water utilization data are unavailable.")
        return

    total = pd.to_numeric(usgs.get("total_withdrawal_mgd"), errors="coerce")
    freshwater_share = pd.to_numeric(usgs.get("freshwater_share"), errors="coerce")
    groundwater_share = pd.to_numeric(usgs.get("groundwater_share"), errors="coerce")
    render_statline(
        [
            ("Total withdrawal", fmt_number(total / 1000.0 if pd.notna(total) else np.nan, 1, suffix=" Bgal/day"), "USGS 2015 national account"),
            ("Freshwater share", fmt_number(freshwater_share * 100 if pd.notna(freshwater_share) else np.nan, 1, suffix="%"), "share of total withdrawal"),
            ("Groundwater share", fmt_number(groundwater_share * 100 if pd.notna(groundwater_share) else np.nan, 1, suffix="%"), "share of total withdrawal"),
            ("County records", f"{int(usgs.get('county_records', 0) or 0):,}", f"{int(usgs.get('jurisdictions', 0) or 0)} jurisdictions"),
        ],
        key_prefix="water-utilization-national-summary",
    )

    geography_options = ["United States"]
    if isinstance(state_categories, pd.DataFrame) and not state_categories.empty and "Geography" in state_categories.columns:
        geography_options.extend(sorted(value for value in state_categories["Geography"].dropna().astype(str).unique() if value != "United States"))
    selected_geography = st.selectbox(
        "Withdrawal geography",
        geography_options,
        key="water-utilization-geography",
    )
    if selected_geography == "United States":
        selected_categories = national_categories
    else:
        selected_categories = state_categories.loc[state_categories["Geography"].eq(selected_geography)].copy() if isinstance(state_categories, pd.DataFrame) else pd.DataFrame()

    with st.container(border=True):
        render_panel_heading("Withdrawal by use and source", f"{selected_geography} · 2015 average daily rate")
        st.plotly_chart(
            water_withdrawal_components(selected_categories),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="water-utilization-withdrawal-components",
        )
    with st.expander("County withdrawal records", expanded=False):
        if isinstance(counties, pd.DataFrame) and not counties.empty:
            table = counties if selected_geography == "United States" else counties.loc[counties["State"].eq(selected_geography)]
            table = table.sort_values("Total Withdrawal Mgal/d", ascending=False, na_position="last", kind="stable")
            render_static_table(table)
        else:
            st.caption("No retained county records are available.")

    if not eia:
        return
    render_statline(
        [
            ("Reported withdrawal", fmt_number(eia.get("withdrawal_bgal_day"), 2, suffix=" Bgal/day"), "annual total converted to daily average"),
            ("Reported consumption", fmt_number(eia.get("consumption_bgal_day"), 2, suffix=" Bgal/day"), "water not returned to the source"),
            ("Withdrawal coverage", f"{int(eia.get('plants_with_withdrawal', 0) or 0):,}/{int(eia.get('plants', 0) or 0):,}", "reporting plants"),
            ("Consumption coverage", f"{int(eia.get('plants_with_consumption', 0) or 0):,}/{int(eia.get('plants', 0) or 0):,}", "reporting plants"),
        ],
        key_prefix="water-utilization-thermoelectric-summary",
    )
    controls = st.columns(2)
    with controls[0]:
        grouping_label = st.selectbox(
            "Thermoelectric grouping",
            ["Water type", "Water source", "Cooling system"],
            key="water-utilization-eia-grouping",
        )
    with controls[1]:
        metric = st.selectbox(
            "Thermoelectric measure",
            ["Withdrawal", "Consumption"],
            key="water-utilization-eia-measure",
        )
    grouping_map = {
        "Water type": "Water Type",
        "Water source": "Water Source",
        "Cooling system": "Cooling System Type",
    }
    group_field = grouping_map[grouping_label]
    selected_groups = eia_groups.loc[eia_groups["Grouping"].eq(group_field)].copy() if isinstance(eia_groups, pd.DataFrame) and not eia_groups.empty else pd.DataFrame()
    with st.container(border=True):
        render_panel_heading("Thermoelectric cooling water", f"EIA 2024 · reported {metric.lower()}")
        st.plotly_chart(
            thermoelectric_water_groups(selected_groups, metric=metric),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="water-utilization-eia-groups",
        )
    with st.expander("Thermoelectric plant records", expanded=False):
        if isinstance(eia_plants, pd.DataFrame) and not eia_plants.empty:
            metric_column = f"{metric} Bgal/day"
            table = eia_plants.sort_values(metric_column, ascending=False, na_position="last", kind="stable") if metric_column in eia_plants.columns else eia_plants
            columns = [
                "Plant Name", "State", "Withdrawal Bgal/day", "Consumption Bgal/day",
                "Water Type", "Water Source", "Cooling System", "Quality Flags",
            ]
            render_static_table(table[[column for column in columns if column in table.columns]].head(100))
        else:
            st.caption("No retained plant records are available.")

def _render_ai_water_linkage(water_data, infrastructure_data):
    context = (water_data or {}).get("facility_context")
    if not isinstance(context, pd.DataFrame):
        context = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(context, pd.DataFrame) or context.empty:
        st.info("No facility records are available for water-system linkage.")
        return
    summary = (water_data or {}).get("facility_context_summary", {}) or {}
    render_statline(
        [
            ("Mapped facilities", f"{int(summary.get('facilities', len(context)) or 0):,}", "canonical registry"),
            ("County water context", f"{int(summary.get('county_context_records', 0) or 0):,}", "matched to USGS county accounts"),
            ("Direct water evidence", f"{int(summary.get('direct_water_evidence_records', 0) or 0):,}", "permit, utility, cooling, or quantity"),
            ("Quantified use", f"{int(summary.get('quantified_withdrawal_records', 0) or 0):,} / {int(summary.get('quantified_consumption_records', 0) or 0):,}", "withdrawal / consumption"),
        ],
        key_prefix="water-ai-facility-linkage",
    )



def render_water_tab(water_data, infrastructure_data=None):
    render_tab_header(
        "Water",
        "National water use, local system context, and direct evidence of AI facility withdrawal, consumption, and cooling design.",
        "USGS / EIA / facility registry",
    )
    render_line_break()
    _render_tab_metric_registry("water")
    render_section(
        "U.S. Water Utilization",
        "Retained national withdrawal and thermoelectric cooling-water records by source, use, and geography.",
    )
    _render_water_utilization(water_data)
    render_section(
        "AI water linkage",
        "Data-center facilities joined to county water accounts, followed by direct facility evidence where available.",
    )
    _render_ai_water_linkage(water_data, infrastructure_data or {})
