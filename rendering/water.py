from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.water_competition import (
    current_top_withdrawal_profile,
    evidence_ladder,
    state_facility_evidence_profile,
)
from rendering.charts_water import (
    thermoelectric_water_groups,
    water_evidence_ladder,
    water_state_evidence_profile,
    water_top_withdrawals_2020,
    wastewater_construction_history,
)
from rendering.common import _render_tab_metric_registry
from rendering.components import (
    fmt_number,
    inject_panel_height_rules,
    render_domain_read,
    render_line_break,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe


def _water_utilization_payload(water_data):
    return water_data or {}


def _render_water_pulse(water_data):
    water = _water_utilization_payload(water_data)
    linkage = water.get("facility_context_summary", {}) or {}
    profile = current_top_withdrawal_profile(water.get("usgs_2020_top_withdrawals"))
    values = profile.set_index("Use Category")["Withdrawal Bgal/day"].to_dict() if not profile.empty else {}
    quantified = int(linkage.get("quantified_withdrawal_records", 0) or 0) + int(
        linkage.get("quantified_consumption_records", 0) or 0
    )
    render_statline(
        [
            (
                "Crop irrigation",
                fmt_number(values.get("Crop irrigation"), 1, suffix=" Bgal/day"),
                "USGS 2020 modeled withdrawal",
            ),
            (
                "Thermoelectric power",
                fmt_number(values.get("Thermoelectric power"), 1, suffix=" Bgal/day"),
                "USGS 2020 modeled withdrawal",
            ),
            (
                "Public supply",
                fmt_number(values.get("Public supply"), 1, suffix=" Bgal/day"),
                "USGS 2020 modeled withdrawal",
            ),
            (
                "Quantified AI use",
                f"{quantified:,}",
                "facility withdrawal + consumption records",
            ),
        ],
        key_prefix="water-system-pulse",
    )


def _render_competing_claims(water_data):
    water = _water_utilization_payload(water_data)
    profile = water.get("usgs_2020_top_withdrawals")
    with st.container(border=True, key="water-panel-competing-claims"):
        render_panel_heading(
            "Who holds the largest national water claims?",
            "Conterminous U.S. · three largest modeled withdrawal categories · 2020",
        )
        st.plotly_chart(
            water_top_withdrawals_2020(profile),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="water-competing-uses-2020",
        )
        st.caption(
            "This retained USGS comparison covers crop irrigation, thermoelectric power, and public supply—the three largest modeled categories. "
            "It is a national allocation envelope, not a complete all-use account and not an estimate of data-center withdrawal."
        )


def _render_ai_water_exposure(water_data, infrastructure_data):
    water = _water_utilization_payload(water_data)
    context = water.get("facility_context")
    if not isinstance(context, pd.DataFrame):
        context = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(context, pd.DataFrame) or context.empty:
        st.info("No facility records are available for water-evidence review.")
        return

    summary = water.get("facility_context_summary", {}) or {}
    state_profile = state_facility_evidence_profile(context)
    mapped_states = int(state_profile["State"].nunique()) if not state_profile.empty else 0
    direct_states = int(state_profile.loc[state_profile["Direct Water Evidence"].gt(0), "State"].nunique()) if not state_profile.empty else 0
    quantified_states = int(state_profile.loc[state_profile["Quantified Use"].gt(0), "State"].nunique()) if not state_profile.empty else 0
    render_statline(
        [
            ("Mapped facilities", f"{int(summary.get('facilities', 0) or 0):,}", f"across {mapped_states} states"),
            ("Direct evidence", f"{int(summary.get('direct_water_evidence_records', 0) or 0):,}", f"across {direct_states} states"),
            ("Quantified use", f"{int(summary.get('quantified_withdrawal_records', 0) or 0) + int(summary.get('quantified_consumption_records', 0) or 0):,}", f"across {quantified_states} states"),
            ("Displacement finding", "Not established", "current public evidence is insufficient"),
        ],
        key_prefix="water-ai-evidence-pulse",
    )

    left, right = st.columns([1.2, 0.8])
    with left:
        with st.container(border=True, key="water-panel-state-evidence"):
            render_panel_heading(
                "Facility concentration & disclosure coverage",
                "Current facility registry · mapped sites and direct water evidence by state",
            )
            st.plotly_chart(
                water_state_evidence_profile(context),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="water-state-evidence-profile",
            )
            st.caption(
                "This view identifies where facilities and disclosures are concentrated. It does not estimate local water demand, scarcity, causation, or displacement."
            )
    with right:
        with st.container(border=True, key="water-panel-evidence-ladder"):
            render_panel_heading(
                "AI water evidence ladder",
                "How far public evidence progresses from location to quantified use",
            )
            st.plotly_chart(
                water_evidence_ladder(summary),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="water-evidence-ladder",
            )
            ladder = evidence_ladder(summary)
            quantified = int(ladder.loc[
                ladder["Evidence Stage"].isin(["Quantified withdrawal", "Quantified consumption"]),
                "Facilities",
            ].sum()) if not ladder.empty else 0
            if quantified == 0:
                st.caption(
                    "No retained facility record quantifies annual withdrawal or consumption. The platform therefore does not claim statistically established effects on communities or agriculture."
                )

    with st.expander("Facility water evidence ledger", expanded=False):
        columns = [
            "State", "Facility", "Operator", "County", "Status",
            "Direct Water Evidence", "Water Withdrawal Gallons/Year",
            "Water Consumption Gallons/Year", "Cooling System", "Water Source",
            "Water Evidence Grade", "Water Evidence Source", "Water Evidence URL",
        ]
        table = context[[column for column in columns if column in context.columns]].copy()
        sort_columns = [column for column in ["State", "Direct Water Evidence", "Facility"] if column in table.columns]
        ascending = [True, False, True][: len(sort_columns)]
        if sort_columns:
            table = table.sort_values(sort_columns, ascending=ascending, kind="stable", na_position="last")
        st.caption("Scrollable table. Select any column header—including State—to sort.")
        st.dataframe(
            arrow_safe_dataframe(table),
            width="stretch",
            height=460,
            hide_index=True,
        )



def _render_wastewater_context(infrastructure_data):
    series = (((infrastructure_data or {}).get("series", {}) or {}).get("Public Sewage and Waste Disposal Construction", {}) or {})
    value = pd.to_numeric(series.get("value"), errors="coerce")
    growth = pd.to_numeric(series.get("yoy_growth"), errors="coerce")
    date = pd.to_datetime(series.get("date"), errors="coerce", format="mixed")
    render_statline(
        [
            ("Public wastewater construction", "n/a" if pd.isna(value) else f"${value / 1000.0:.1f}B", "seasonally adjusted annual rate"),
            ("Year-over-year change", fmt_number(growth * 100.0, 1, signed=True, suffix="%"), "broad public-system investment"),
            ("Latest observation", "n/a" if pd.isna(date) else date.strftime("%Y-%m"), "U.S. Census construction spending"),
        ],
        key_prefix="water-wastewater-pulse",
    )
    with st.container(border=True, key="water-panel-wastewater-investment"):
        render_panel_heading("Wastewater-system investment", "Public sewage and waste-disposal construction · 2020-present")
        st.plotly_chart(
            wastewater_construction_history((infrastructure_data or {}).get("construction_history")),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="water-wastewater-construction-history",
        )
        st.caption(
            "This is public-system capital spending, not wastewater volume, treatment headroom, discharge capacity, or AI-attributed investment. "
            "Facility impacts require project- or utility-specific evidence."
        )

def _render_thermoelectric_detail(water_data):
    water = _water_utilization_payload(water_data)
    summary = water.get("summary", {}) or {}
    eia = summary.get("eia_2024_thermoelectric", {}) or {}
    eia_groups = water.get("eia_groups")
    eia_plants = water.get("eia_plants")
    if not eia:
        st.info("Thermoelectric cooling-water data are unavailable.")
        return

    render_statline(
        [
            ("Reported withdrawal", fmt_number(eia.get("withdrawal_bgal_day"), 2, suffix=" Bgal/day"), "annual total converted to daily average"),
            ("Reported consumption", fmt_number(eia.get("consumption_bgal_day"), 2, suffix=" Bgal/day"), "water not returned to the source"),
            ("Withdrawal coverage", f"{int(eia.get('plants_with_withdrawal', 0) or 0):,}/{int(eia.get('plants', 0) or 0):,}", "reporting plants"),
            ("Consumption coverage", f"{int(eia.get('plants_with_consumption', 0) or 0):,}/{int(eia.get('plants', 0) or 0):,}", "reporting plants"),
        ],
        key_prefix="water-thermoelectric-summary",
    )
    controls = st.columns(2)
    with controls[0]:
        grouping_label = st.selectbox(
            "Thermoelectric grouping",
            ["Water type", "Water source", "Cooling system"],
            key="water-thermoelectric-grouping",
        )
    with controls[1]:
        metric = st.selectbox(
            "Thermoelectric measure",
            ["Withdrawal", "Consumption"],
            key="water-thermoelectric-measure",
        )
    grouping_map = {
        "Water type": "Water Type",
        "Water source": "Water Source",
        "Cooling system": "Cooling System Type",
    }
    group_field = grouping_map[grouping_label]
    selected_groups = (
        eia_groups.loc[eia_groups["Grouping"].eq(group_field)].copy()
        if isinstance(eia_groups, pd.DataFrame) and not eia_groups.empty else pd.DataFrame()
    )
    with st.container(border=True, key="water-panel-thermoelectric"):
        render_panel_heading("Thermoelectric water", f"EIA 2024 · reported {metric.lower()} by {grouping_label.lower()}")
        st.plotly_chart(
            thermoelectric_water_groups(selected_groups, metric=metric),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="water-thermoelectric-groups",
        )
    with st.expander("Thermoelectric plant records", expanded=False):
        if isinstance(eia_plants, pd.DataFrame) and not eia_plants.empty:
            metric_column = f"{metric} Bgal/day"
            sort_columns = [column for column in ["State", metric_column, "Plant Name"] if column in eia_plants.columns]
            ascending = [True, False, True][: len(sort_columns)]
            table = eia_plants.sort_values(sort_columns, ascending=ascending, na_position="last", kind="stable") if sort_columns else eia_plants.copy()
            columns = [
                "State", "Plant Name", "Withdrawal Bgal/day", "Consumption Bgal/day",
                "Water Type", "Water Source", "Cooling System", "Quality Flags",
            ]
            st.caption("Scrollable table. Select any column header—including State—to sort.")
            st.dataframe(
                arrow_safe_dataframe(table[[column for column in columns if column in table.columns]]),
                width="stretch",
                height=460,
                hide_index=True,
            )
        else:
            st.caption("No retained plant records are available.")


def render_water_tab(water_data, infrastructure_data=None, tab_read=None):
    inject_panel_height_rules({
        "water-panel-state-evidence": 590,
        "water-panel-evidence-ladder": 590,
    })
    render_tab_header(
        "Water",
        "Competing freshwater claims, AI-facility evidence, and the conditions that could constrain communities, agriculture, and development.",
        "USGS 2020 / EIA 2024 / Census / facility registry",
    )
    render_line_break()
    _render_tab_metric_registry("water")
    render_domain_read(tab_read, label="Water Read", accent="blue")

    render_section(
        "Water system pulse",
        "The latest retained national comparison of major water claims and the present limit of direct AI-facility evidence.",
    )
    _render_water_pulse(water_data)

    render_section(
        "Competing claims",
        "The three largest modeled national withdrawal categories in the current evidence window.",
    )
    _render_competing_claims(water_data)

    render_section(
        "AI water evidence",
        "Where the facility footprint is concentrated, what is directly disclosed, and which conclusions the evidence does not yet support.",
    )
    _render_ai_water_exposure(water_data, infrastructure_data or {})

    render_section(
        "Wastewater systems",
        "Public treatment and disposal investment is tracked as system context, without attributing spending or capacity pressure to AI absent direct evidence.",
    )
    _render_wastewater_context(infrastructure_data or {})

    render_section(
        "Power-sector water demand",
        "Thermoelectric withdrawal and consumption remain a major competing claim and an indirect water channel for the AI buildout.",
    )
    _render_thermoelectric_detail(water_data)
