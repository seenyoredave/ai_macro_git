from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from config.energy_config import ENERGY_SERIES
from rendering.labels import power_capacity_gap_label
from rendering.charts_common import COLORS, dual_history
from rendering.charts_finance import component_bars
from rendering.charts_infrastructure import power_utilization_history
from rendering.common import _metric_context, _render_tab_metric_registry, _value
from rendering.components import fmt_date, fmt_number, metric_card, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header

def _energy_item(energy_data, name):
    return (((energy_data or {}).get("series", {}) or {}).get(name, {}) or {})

def _energy_source_label(energy_data, name=None, item=None):
    del energy_data, item
    if name in ENERGY_SERIES:
        return str(ENERGY_SERIES[name].get("source") or "")
    raise KeyError(f"Unknown energy series: {name}")

def _energy_source_rows(energy_data):
    rows = []
    for name, spec in ENERGY_SERIES.items():
        item = _energy_item(energy_data, name)
        value = pd.to_numeric(item.get("value"), errors="coerce")
        change = pd.to_numeric(item.get("change_pct"), errors="coerce")
        unit = str(item.get("unit") or spec.get("unit") or "")

        if unit.startswith("$"):
            reading = f"${fmt_number(value, 2)}"
        elif unit == "%":
            reading = fmt_number(value, 1, suffix="%")
        elif unit == "¢/kWh":
            reading = fmt_number(value, 2, suffix="¢/kWh")
        else:
            reading = fmt_number(value, 1)

        if spec.get("change_days"):
            change_period = "4-week"
        elif int(spec.get("change_months") or 0) == 3:
            change_period = "3-month"
        else:
            change_period = "12-month"

        rows.append(
            {
                "Series": spec.get("display_name", name),
                "Reading": reading,
                "Change": f"{change_period} {fmt_number(change, 1, signed=True, suffix='%')}",
                "Observation Date": fmt_date(item.get("date")),
                "Source": _energy_source_label(energy_data, name, item),
            }
        )
    return pd.DataFrame(rows)

def _energy_change_text(item, period):
    change = pd.to_numeric((item or {}).get("change_pct"), errors="coerce")
    return f"{period} {fmt_number(change, 1, signed=True, suffix='%')}"

def _year_over_year_history(item):
    history = (item or {}).get("history")
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if not {"Date", "Value"}.issubset(history.columns):
        return pd.DataFrame(columns=["Date", "Value"])

    clean = history[["Date", "Value"]].copy()
    clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
    clean["Value"] = pd.to_numeric(clean["Value"], errors="coerce")
    clean = (
        clean.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
    )
    if clean.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    monthly = clean.set_index(clean["Date"].dt.to_period("M"))["Value"]
    growth = monthly.pct_change(periods=12, fill_method=None) * 100.0
    output = pd.DataFrame(
        {
            "Date": growth.index.to_timestamp(),
            "Value": growth.to_numpy(dtype=float),
        }
    )
    return output.replace([np.inf, -np.inf], np.nan).dropna(subset=["Value"])

def _historical_utilization_reference(item, *, quantile=0.90, fallback=80.0):
    history = (item or {}).get("history")
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Value" not in history.columns:
        return float(fallback)
    values = pd.to_numeric(history["Value"], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if len(values) < 24:
        return float(fallback)
    return float(values.quantile(quantile))

def _render_energy_supply(energy_data):
    specs = [
        ("energy-gas", "Natural Gas Price", "Henry Hub Natural Gas", (0, 15), "violet", "4-week change"),
        ("energy-oil", "WTI Crude Oil", "WTI Crude Oil", (20, 160), "blue", "4-week change"),
        ("energy-coal", "Coal Production", "Coal Production", (40, 140), "slate", "3-month change"),
        ("energy-renewables", "Renewable Power Output", "Renewable Power Output", (50, 300), "green", "3-month change"),
    ]
    for column, (key, series_name, label, scale, accent, period) in zip(st.columns(4), specs):
        item = _energy_item(energy_data, series_name)
        value = pd.to_numeric(item.get("value"), errors="coerce")
        if series_name in {"Natural Gas Price", "WTI Crude Oil"}:
            value_text = f"${fmt_number(value, 2)}"
        else:
            value_text = fmt_number(value, 1)
        with column:
            metric_card(
                key=key,
                label=label,
                value=value,
                value_text=value_text,
                context=_energy_change_text(item, period),
                history=item.get("history"),
                scale=scale,
                source=_energy_source_label(energy_data, series_name, item),
                fallback_date=item.get("date"),
                accent=accent,
                years=6,
            )

def _render_electricity_cost(energy_data):
    commercial = _energy_item(energy_data, "Commercial Electricity Price")
    industrial = _energy_item(energy_data, "Industrial Electricity Price")
    with st.container(border=True):
        render_statline(
            [
                (
                    "Commercial price",
                    fmt_number(commercial.get("value"), 2, suffix="¢/kWh"),
                    _energy_change_text(commercial, "12-month change"),
                ),
                (
                    "Industrial price",
                    fmt_number(industrial.get("value"), 2, suffix="¢/kWh"),
                    _energy_change_text(industrial, "12-month change"),
                ),
            ],
            key_prefix="energy-electricity-cost",
        )
        render_panel_heading("U.S. retail electricity prices", "EIA Electric Power Monthly")
        st.plotly_chart(
            dual_history(
                commercial.get("history"),
                industrial.get("history"),
                first_name="Commercial",
                second_name="Industrial",
                first_color=COLORS["violet"],
                second_color=COLORS["blue"],
                years=8,
                height=330,
                value_suffix="¢/kWh",
            ),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="energy-electricity-cost-history",
        )

def _render_power_production(energy_data, regime_metrics):
    output = _energy_item(energy_data, "Electric Power Output")
    capacity = _energy_item(energy_data, "Electric Power Capacity")
    utilization = _energy_item(energy_data, "Electric Power Utilization")
    utilization_value = pd.to_numeric(utilization.get("value"), errors="coerce")
    utilization_reference = _historical_utilization_reference(utilization)
    reference_gap = (
        utilization_value - utilization_reference
        if pd.notna(utilization_value) and pd.notna(utilization_reference)
        else np.nan
    )
    utilization_context = (
        f"{abs(reference_gap):.1f} pp {'above' if reference_gap >= 0 else 'below'} 90th-percentile reference"
        if pd.notna(reference_gap)
        else "90th-percentile reference unavailable"
    )
    with st.container(border=True):
        render_statline(
            [
                ("Electric-power output", fmt_number(output.get("value"), 1), "G.17 index · 2017=100"),
                ("Sustainable potential output", fmt_number(capacity.get("value"), 1), "G.17 index · 2017=100"),
                ("Utilization", fmt_number(utilization_value, 1, suffix="%"), utilization_context),
                ("Power Stress", fmt_number(_value(regime_metrics, "Power Stress Index"), 1, signed=True), _metric_context("Power Stress Index", _value(regime_metrics, "Power Stress Index"))),
            ],
            key_prefix="energy-power-production",
        )
        columns = st.columns(2)
        with columns[0]:
            render_panel_heading("Electric-power output and potential", "Federal Reserve G.17 · 2017=100")
            st.plotly_chart(
                dual_history(
                    output.get("history"),
                    capacity.get("history"),
                    first_name="Electric-power output",
                    second_name="Sustainable potential output",
                    first_color=COLORS["violet"],
                    second_color=COLORS["blue"],
                    years=8,
                    height=310,
                ),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="energy-power-production-history",
            )
        with columns[1]:
            render_panel_heading("Electric-power utilization", "Federal Reserve G.17 · percent of capacity")
            st.plotly_chart(
                power_utilization_history(
                    utilization.get("history"),
                    reference=utilization_reference,
                    height=310,
                ),
                width="stretch",
                config={"displayModeBar": True, "responsive": True},
                key="energy-power-utilization-history",
            )

def _render_grid_capacity(regime_metrics, dashboard_data, energy_data):
    value = _value(regime_metrics, "Power Capacity Gap")
    result = (regime_metrics or {}).get("Power Capacity Gap Components", {}) or {}
    components = result.get("components", {}) or {}

    output_component = components.get("Delivered Power Growth", {}) or {}
    capacity_component = components.get("Sustainable Capacity Growth", {}) or {}
    output_growth = pd.to_numeric(output_component.get("raw"), errors="coerce") * 100.0
    capacity_growth = pd.to_numeric(capacity_component.get("raw"), errors="coerce") * 100.0
    response_gap = output_growth - capacity_growth if pd.notna(output_growth) and pd.notna(capacity_growth) else np.nan
    deployment_score = pd.to_numeric(result.get("deployment_pressure_score"), errors="coerce")
    response_score = pd.to_numeric(result.get("power_response_score"), errors="coerce")

    del dashboard_data
    output_history = _year_over_year_history(
        _energy_item(energy_data, "Electric Power Output")
    )
    capacity_history = _year_over_year_history(
        _energy_item(energy_data, "Electric Power Capacity")
    )
    with st.container(border=True):
        render_statline(
            [
                ("Power Capacity Gap", fmt_number(value, 1, signed=True), power_capacity_gap_label(value)),
                ("Deployment pressure", fmt_number(deployment_score, 1), "construction + capital deployment"),
                ("Power-system response", fmt_number(response_score, 1), "output + sustainable potential"),
                ("Output–potential growth gap", fmt_number(response_gap, 1, signed=True, suffix=" pp"), "12-month"),
            ],
            key_prefix="energy-grid-capacity",
        )
        render_panel_heading("Power-system response", "Output growth · sustainable capacity growth")
        st.plotly_chart(
            dual_history(
                output_history,
                capacity_history,
                first_name="Electric-power output",
                second_name="Sustainable potential output",
                first_color=COLORS["violet"],
                second_color=COLORS["blue"],
                reference=0,
                years=8,
                height=310,
                value_suffix="%",
            ),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="energy-grid-capacity-growth",
        )

def _render_ai_energy_demand(regime_metrics):
    capacity_result = (regime_metrics or {}).get("Power Capacity Gap Components", {}) or {}
    capacity_components = capacity_result.get("components", {}) or {}
    power_result = (regime_metrics or {}).get("Power Stress Components", {}) or {}
    footprint_components = power_result.get("footprint_components", {}) or {}
    demand_components = {
        name: payload
        for name, payload in capacity_components.items()
        if (payload or {}).get("channel") == "Deployment Pressure"
    }
    demand_components.update(footprint_components)

    construction = demand_components.get("Data Center Construction", {}) or {}
    deployment = demand_components.get("Capital Deployment", {}) or {}
    commercial = demand_components.get("Commercial Load Growth", {}) or {}
    electric_output = demand_components.get("Electric Output Growth", {}) or {}
    render_statline(
        [
            ("Data-center construction", fmt_number(pd.to_numeric(construction.get("raw"), errors="coerce") * 100, 1, signed=True, suffix="%"), "year over year"),
            ("Capital deployment", fmt_number(pd.to_numeric(deployment.get("raw"), errors="coerce") * 100, 1, signed=True, suffix="%"), "year over year"),
            ("Commercial electricity sales", fmt_number(pd.to_numeric(commercial.get("raw"), errors="coerce") * 100, 1, signed=True, suffix="%"), "year over year"),
            ("Electric-power output", fmt_number(pd.to_numeric(electric_output.get("raw"), errors="coerce") * 100, 1, signed=True, suffix="%"), "year over year"),
        ],
        key_prefix="energy-ai-demand",
    )
    with st.container(border=True):
        render_panel_heading("Demand-growth indicators", "Construction · capital deployment · commercial load · power output")
        st.plotly_chart(
            component_bars(demand_components, signed=False, height=300, color=COLORS["violet"]),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="energy-ai-demand-indicators",
        )

def _render_facility_power_pipeline(infrastructure_data):
    registry = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(registry, pd.DataFrame) or registry.empty:
        st.info("No facility power records are available.")
        return
    record_type = registry.get("Record Type", pd.Series("", index=registry.index)).fillna("").astype(str).str.casefold()
    projects = registry.loc[record_type.eq("project")].copy()
    if projects.empty:
        st.info("No project records are available.")
        return
    status = projects.get("Status", pd.Series("", index=projects.index)).fillna("").astype(str).str.casefold()
    waiting = projects.loc[status.isin({"approved / permitted / under construction", "under construction", "construction", "announced", "planned", "proposed", "expanding"})].copy()
    fields = {
        "Published": "Published Capacity Estimate MW",
        "Planned": "Planned Data Center Capacity MW",
        "Contracted": "Contracted Utility Capacity MW",
        "Energized": "Energized Capacity MW",
    }
    counts = {}
    totals = {}
    for label, field in fields.items():
        values = pd.to_numeric(waiting.get(field, pd.Series(index=waiting.index, dtype=float)), errors="coerce")
        counts[label] = int(values.gt(0).sum())
        totals[label] = float(values.where(values.gt(0)).sum(min_count=1)) if values.gt(0).any() else np.nan
    render_statline(
        [
            ("Active project records", f"{len(waiting):,}", "construction, expansion, or planned"),
            ("Published estimate", fmt_number(totals["Published"] / 1000.0 if pd.notna(totals["Published"]) else np.nan, 1, suffix=" GW"), f"{counts['Published']:,} records"),
            ("Contracted utility", fmt_number(totals["Contracted"] / 1000.0 if pd.notna(totals["Contracted"]) else np.nan, 1, suffix=" GW"), f"{counts['Contracted']:,} records"),
            ("Energized", fmt_number(totals["Energized"] / 1000.0 if pd.notna(totals["Energized"]) else np.nan, 1, suffix=" GW"), f"{counts['Energized']:,} records"),
        ],
        key_prefix="energy-facility-power-pipeline",
    )



def render_energy_tab(fred_data, regime_metrics, energy_data, dashboard_data, infrastructure_data=None):
    del fred_data
    render_tab_header(
        "Energy",
        "Electricity demand, supply response, regional constraint signals, and the facility pipeline seeking power.",
        "EIA / FRED / facility registry",
    )
    render_line_break()
    _render_tab_metric_registry("energy")

    render_section("Demand", "AI-linked deployment indicators and commercial electricity demand.")
    _render_ai_energy_demand(regime_metrics)

    render_section("Supply response", "Fuel conditions, power production, sustainable potential output, and utilization.")
    _render_energy_supply(energy_data)
    _render_power_production(energy_data, regime_metrics)

    render_section("Regional constraint", "National power-response indicators and customer-class electricity prices.")
    _render_grid_capacity(regime_metrics, dashboard_data, energy_data)
    _render_electricity_cost(energy_data)

    render_section("Projects waiting for power", "Published, planned, contracted, and energized MW across active facility records.")
    _render_facility_power_pipeline(infrastructure_data or {})
