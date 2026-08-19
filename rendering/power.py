from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

from analytics.energy_pulse import (
    demand_snapshot,
    development_snapshot,
    large_load_snapshot,
    price_snapshot,
    supply_snapshot,
)
from config.energy_config import ENERGY_SERIES
from rendering.visual_system import render_plotly_chart
from rendering.charts_data_center import ACTIVE_CAMPUS_STATUSES
from rendering.charts_energy import (
    capacity_changes,
    commercial_markets,
    electricity_demand_history,
    gas_pipeline_capacity,
    generation_change,
    generation_mix,
    lng_capacity,
    planned_capacity,
    retail_price_history,
    wholesale_price_history,
)
from rendering.common import _render_floating_terms
from rendering.dataframe import arrow_safe_dataframe
from rendering.components import (
    inject_panel_height_rules,
    fmt_date,
    fmt_number,
    render_compact_chart_rail,
    render_domain_read,
    render_metric_stack,
    render_panel_heading,
    render_section,
    render_statline,
    render_summary_row,
    render_tab_header,
)


def _power_item(power_data, name):
    return (((power_data or {}).get("series", {}) or {}).get(name, {}) or {})


def _market_frame(power_data, name):
    frame = (power_data or {}).get(name)
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _power_source_label(name):
    if name in ENERGY_SERIES:
        return str(ENERGY_SERIES[name].get("source") or "")
    raise KeyError(f"Unknown energy series: {name}")


def _date_range(frame, column="Date"):
    if not isinstance(frame, pd.DataFrame) or frame.empty or column not in frame:
        return "n/a"
    dates = pd.to_datetime(frame[column], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return "n/a"
    return f"{dates.min():%Y-%m} to {dates.max():%Y-%m}"


def _power_source_rows(power_data):
    datasets = [
        ("Retail sales, customers, and prices", "retail_history", "Date", "EIA-861M"),
        ("Electricity generation", "generation_history", "Date", "EIA Electric Power Monthly / EIA-923"),
        ("Operating generators", "operating_generators", None, "EIA-860M"),
        ("Operating capacity", "capacity_snapshot", None, "EIA-860M"),
        ("Generator additions and retirements", "generator_pipeline", "Expected Year", "EIA-860M"),
        ("Current-year capacity changes", "capacity_changes", "Date", "EIA Electric Power Monthly"),
        ("Wholesale electricity prices", "wholesale_prices", "Trade Date", "EIA / ICE"),
        ("Natural-gas pipeline source records", "gas_pipeline_projects", "Last Updated Date", "EIA Natural Gas Pipeline Projects"),
        ("Natural-gas pipeline projects", "gas_pipeline_projects", "Last Updated Date", "EIA Natural Gas Pipeline Projects"),
        ("LNG liquefaction projects", "lng_projects", "In-service Date", "EIA LNG Capacity"),
        ("Natural-gas storage projects", "gas_storage_projects", "Year in Service", "EIA Natural Gas Storage Projects"),
    ]
    rows = []
    for dataset, key, date_column, source in datasets:
        frame = _market_frame(power_data, key)
        coverage = "n/a"
        latest = "n/a"
        if date_column and not frame.empty and date_column in frame:
            if date_column in {"Expected Year", "Year in Service"}:
                years = pd.to_numeric(frame[date_column], errors="coerce").dropna()
                if not years.empty:
                    coverage = f"{int(years.min())} to {int(years.max())}"
                    latest = str(int(years.max()))
            else:
                dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed").dropna()
                if not dates.empty:
                    coverage = f"{dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}"
                    latest = f"{dates.max():%Y-%m-%d}"
        rows.append({
            "Dataset": dataset,
            "Records": f"{len(frame):,}",
            "Latest observation": latest,
            "Coverage": coverage,
            "Source": source,
        })
    for name, spec in ENERGY_SERIES.items():
        item = _power_item(power_data, name)
        rows.append({
            "Dataset": spec.get("display_name", name),
            "Records": f"{len(item.get('history')):,}" if isinstance(item.get("history"), pd.DataFrame) else "0",
            "Latest observation": fmt_date(item.get("date")),
            "Coverage": _date_range(item.get("history")) if isinstance(item.get("history"), pd.DataFrame) else "n/a",
            "Source": _power_source_label(name),
        })
    return pd.DataFrame(rows)


def _latest_date(frame, column="Date"):
    if frame.empty or column not in frame:
        return "n/a"
    dates = pd.to_datetime(frame[column], errors="coerce", format="mixed").dropna()
    return "n/a" if dates.empty else dates.max().strftime("%Y-%m")


def _active_campuses(infrastructure_data):
    campuses = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        return pd.DataFrame()
    if not campuses.empty:
        if "Campus ID" not in campuses.columns:
            raise ValueError("Power requires Universal Data Center Registry Campus IDs")
        if campuses["Campus ID"].astype(str).duplicated().any():
            raise ValueError("Power requires one row per Universal Data Center Registry Campus ID")
    clean = campuses.copy()
    status = clean.get("Status", pd.Series("", index=clean.index)).fillna("").astype(str).str.casefold()
    active_statuses = {value.casefold() for value in ACTIVE_CAMPUS_STATUSES}
    return clean.loc[status.eq("operational") | status.isin(active_statuses)].copy()

def _inject_power_page_theme() -> None:
    st.markdown(
        """
        <style>
        div[class*="st-key-power-panel-"] {
            border-color: rgba(148, 163, 184, 0.15) !important;
            background: rgba(17, 24, 39, 0.72) !important;
            box-shadow: inset 0 1px 0 rgba(52, 211, 153, 0.035) !important;
        }
        div[class*="st-key-power-panel-"] [data-testid="stPlotlyChart"] {
            margin-top: -0.15rem;
        }
        div[class*="st-key-statline-power-pulse-"] {
            border-top-color: rgba(52, 211, 153, 0.82) !important;
        }
        div[class*="st-key-statline-power-demand-"] ,
        div[class*="st-key-statline-power-supply-"] ,
        div[class*="st-key-statline-power-buildout-"] ,
        div[class*="st-key-statline-power-prices-"] {
            border-top-color: rgba(96, 165, 250, 0.72) !important;
        }
        .rm-power-read {
            border: 1px solid rgba(52, 211, 153, 0.18);
            border-left: 3px solid #34d399;
            border-radius: 0;
            background: linear-gradient(90deg, rgba(5, 150, 105, 0.10), rgba(17, 24, 39, 0.61));
            padding: 0.82rem 1rem 0.88rem 1rem;
            margin: 0.18rem 0 1.05rem 0;
        }
        .rm-power-read-kicker {
            color: #6ee7b7;
            font-size: 0.64rem;
            font-weight: 800;
            letter-spacing: 0.11em;
            text-transform: uppercase;
        }
        .rm-power-read-title {
            color: #f8fafc;
            font-size: 1.02rem;
            font-weight: 760;
            margin-top: 0.18rem;
        }
        .rm-power-read-copy {
            color: #b9c3d2;
            font-size: 0.82rem;
            line-height: 1.5;
            margin-top: 0.22rem;
            max-width: 1120px;
        }
        .rm-power-load-profile {
            padding: 0.15rem 0 0.25rem 0;
        }
        .rm-power-load-metrics {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.35rem 0 0.85rem 0;
        }
        .rm-power-load-metric {
            border: 1px solid rgba(148, 163, 184, 0.13);
            border-radius: 0;
            background: rgba(15, 23, 42, 0.46);
            padding: 0.58rem 0.62rem;
        }
        .rm-power-load-metric span {
            display: block;
            color: #8793a8;
            font-size: 0.61rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .rm-power-load-metric b {
            display: block;
            color: #eef2ff;
            font-size: 1.02rem;
            margin-top: 0.16rem;
        }
        .rm-power-load-rank {
            display: grid;
            grid-template-columns: 2rem minmax(0, 1fr) 3.6rem;
            gap: 0.5rem;
            align-items: center;
            margin: 0.54rem 0;
            color: #cbd5e1;
            font-size: 0.74rem;
        }
        .rm-power-load-rank strong {
            color: #e2e8f0;
            font-size: 0.72rem;
        }
        .rm-power-load-track {
            height: 8px;
            border-radius: 999px;
            background: rgba(51, 65, 85, 0.64);
            overflow: hidden;
        }
        .rm-power-load-fill {
            display: block;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #60a5fa, #8b5cf6);
        }
        .rm-power-load-note {
            color: #7f8ba1;
            font-size: 0.68rem;
            line-height: 1.4;
            margin-top: 0.72rem;
        }
        div[class*="st-key-power-view-"] [role="radiogroup"] {
            gap: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _power_context(power_data, infrastructure_data) -> dict:
    retail = _market_frame(power_data, "retail_history")
    generation = _market_frame(power_data, "generation_history")
    capacity = _market_frame(power_data, "capacity_snapshot")
    changes = _market_frame(power_data, "capacity_changes")
    pipeline = _market_frame(power_data, "generator_pipeline")
    wholesale = _market_frame(power_data, "wholesale_prices")
    campuses = _active_campuses(infrastructure_data)
    context = {
        "retail": retail,
        "generation": generation,
        "capacity": capacity,
        "changes": changes,
        "pipeline": pipeline,
        "wholesale": wholesale,
        "campuses": campuses,
        "demand": demand_snapshot(retail),
        "large_loads": large_load_snapshot(campuses),
        "supply": supply_snapshot(generation, capacity, changes),
        "development": development_snapshot(pipeline, pd.DataFrame(), pd.DataFrame()),
        "prices": price_snapshot(retail, _power_item(power_data, "Natural Gas Price")),
    }
    return context


def _render_power_pulse(context: dict) -> None:
    demand = context["demand"]
    large = context["large_loads"]
    development = context["development"]
    prices = context["prices"]

    published_total = pd.to_numeric(large.get("published_total_mw"), errors="coerce")
    if pd.notna(published_total) and published_total > 0:
        large_value = fmt_number(published_total / 1000.0, 1, suffix=" GW")
        large_context = "published active-campus estimates"
    else:
        large_value = f"{int(large.get('active_campuses', 0) or 0):,}"
        large_context = "active campuses"

    render_section(
        "Current power conditions",
        "Demand growth, disclosed large loads, planned generation, and prices.",
        first=True,
        compact=True,
    )
    render_statline(
        [
            ("Electricity demand", fmt_number(demand.get("total_growth"), 1, signed=True, suffix="%"), "rolling 12-month growth"),
            ("Large-load pipeline", large_value, large_context),
            ("Net capacity build", fmt_number(development.get("planned_net_gw"), 1, signed=True, suffix=" GW"), f"{development.get('current_year')}–{development.get('end_year')}"),
            ("Retail price growth", fmt_number(prices.get("total_growth"), 1, signed=True, suffix="%"), "United States · year over year"),
        ],
        key_prefix="power-pulse",
    )





def _large_load_state_summary(campuses: pd.DataFrame, *, top_n: int = 6) -> pd.DataFrame:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame(columns=["State", "GW", "Campuses"])
    clean = campuses.copy()
    published = pd.to_numeric(clean.get("Published Capacity Estimate MW"), errors="coerce")
    clean["Capacity MW"] = published.where(published > 0)
    clean = clean.loc[
        clean["Capacity MW"].notna()
        & clean.get("State", "").fillna("").astype(str).ne("")
    ].copy()
    if clean.empty:
        return pd.DataFrame(columns=["State", "GW", "Campuses"])
    summary = (
        clean.groupby("State", as_index=False)
        .agg(**{"Capacity MW": ("Capacity MW", "sum"), "Campuses": ("Capacity MW", "size")})
        .sort_values("Capacity MW", ascending=False, kind="stable")
        .head(top_n)
    )
    summary["GW"] = summary["Capacity MW"] / 1000.0
    return summary.reset_index(drop=True)


def _render_large_load_profile(context: dict) -> None:
    demand = context["demand"]
    large = context["large_loads"]
    states = _large_load_state_summary(context["campuses"])
    maximum = pd.to_numeric(states.get("GW"), errors="coerce").max() if not states.empty else np.nan
    rows = []
    for _, row in states.iterrows():
        width = float(row["GW"] / maximum * 100.0) if pd.notna(maximum) and maximum > 0 else 0.0
        rows.append(
            '<div class="rm-power-load-rank">'
            f'<strong>{html.escape(str(row["State"]))}</strong>'
            f'<div class="rm-power-load-track"><span class="rm-power-load-fill" style="width:{width:.1f}%"></span></div>'
            f'<span>{float(row["GW"]):.1f} GW</span>'
            '</div>'
        )
    ranking = "".join(rows) if rows else '<div class="rm-power-load-note">No published state-level load estimates are available.</div>'
    markup = f'''<div class="rm-power-load-profile">
        <div class="rm-power-load-metrics">
            <div class="rm-power-load-metric"><span>Total sales</span><b>{html.escape(fmt_number(demand.get("total_twh"), 0, suffix=" TWh"))}</b></div>
            <div class="rm-power-load-metric"><span>Commercial YoY</span><b>{html.escape(fmt_number(demand.get("commercial_growth"), 1, signed=True, suffix="%"))}</b></div>
            <div class="rm-power-load-metric"><span>Industrial YoY</span><b>{html.escape(fmt_number(demand.get("industrial_growth"), 1, signed=True, suffix="%"))}</b></div>
        </div>
        {ranking}
    </div>'''
    st.markdown(markup, unsafe_allow_html=True)


def _render_demand(context: dict) -> None:
    retail = context["retail"]
    campuses = context["campuses"]
    demand = context["demand"]
    large = context["large_loads"]
    through = _latest_date(retail)
    render_section("Electricity demand and large loads", "U.S. electricity demand by customer class and published data-center load.")
    render_summary_row([
        ("Customer accounts", fmt_number(demand.get("customers_m"), 1, suffix="M"), through),
        ("Active campuses", f"{int(large.get('active_campuses', 0) or 0):,}", f"{int(large.get('operating_campuses', 0) or 0):,} operating"),
        ("Published coverage", f"{int(large.get('published_records', 0) or 0):,} / {int(large.get('active_campuses', 0) or 0):,}", fmt_number(pd.to_numeric(large.get("published_coverage"), errors="coerce") * 100.0, 1, suffix="%")),
        ("Median disclosed load", fmt_number(large.get("published_median_mw"), 1, suffix=" MW"), "published estimates only"),
    ], key_prefix="power-demand-detail")
    left, right = st.columns([1.55, 0.85])
    with left:
        with st.container(border=True, key="power-panel-demand-history"):
            render_panel_heading("Electricity demand by customer class", "Rolling 12-month sales")
            render_plotly_chart(electricity_demand_history(retail, height=430), width="stretch", config={"displayModeBar": False, "responsive": True}, key="power-demand-history")
    with right:
        with st.container(border=True, key="power-panel-large-load-profile"):
            render_panel_heading("Large-load concentration", "Published active-campus estimates")
            _render_large_load_profile(context)
    if campuses.empty:
        st.caption("No active campuses with published state and capacity data are available.")

def _render_supply(context: dict) -> None:
    generation = context["generation"]; capacity = context["capacity"]; changes = context["changes"]; supply = context["supply"]; through = _latest_date(generation)
    render_section("Electricity supply", "Generation mix, output changes, and fleet additions and retirements.")
    render_summary_row([
        ("Natural gas share", fmt_number(supply.get("gas_share"), 1, suffix="%"), "rolling 12 months"),
        ("Nuclear share", fmt_number(supply.get("nuclear_share"), 1, suffix="%"), "rolling 12 months"),
        ("Renewable share", fmt_number(supply.get("renewable_share"), 1, suffix="%"), "hydro, wind, solar, and other"),
        ("Operating capacity", fmt_number(supply.get("capacity_gw"), 1, suffix=" GW"), f"latest fleet snapshot · {through}"),
    ], key_prefix="power-supply")
    with st.container(key="full-width-layout-power-generation-supply"):
        with st.container(border=True, key="power-panel-supply-selected"):
            view = st.radio("Supply view", ["Generation mix", "Generation change", "Fleet changes"], horizontal=True, label_visibility="collapsed", key="power-view-supply")
            if view == "Generation change":
                render_panel_heading("Generation change", "Rolling 12-month change by source"); figure, chart_key = generation_change(generation, height=490), "power-generation-change"
            elif view == "Fleet changes":
                render_panel_heading("Current fleet changes", "Capacity additions and retirements through the latest EIA release"); figure, chart_key = capacity_changes(changes, height=490), "power-capacity-changes"
            else:
                render_panel_heading("Generation mix", "Annual electricity generation by source · 2020-present"); figure, chart_key = generation_mix(generation, height=490), "power-generation-mix"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=chart_key)

def _render_buildout(context: dict) -> None:
    development = context["development"]
    render_section("Planned generation", "Planned generation additions and retirements. Interconnection queues and storage are covered in Grid & Storage.")
    render_summary_row([
        ("Planned additions", fmt_number(development.get("planned_additions_gw"), 1, suffix=" GW"), f"{development.get('current_year')}–{development.get('end_year')}"),
        ("Planned retirements", fmt_number(development.get("planned_retirements_gw"), 1, suffix=" GW"), f"{development.get('current_year')}–{development.get('end_year')}"),
        ("Net planned build", fmt_number(development.get("planned_net_gw"), 1, signed=True, suffix=" GW"), "additions less retirements"),
    ], key_prefix="power-buildout")
    with st.container(key="full-width-layout-power-generation-buildout"):
        with st.container(border=True, key="power-panel-buildout-selected"):
            render_panel_heading("Planned capacity additions and retirements", f"{development.get('current_year')}–{development.get('end_year')}")
            render_plotly_chart(planned_capacity(development.get("pipeline"), height=450, end_year=int(development.get("end_year", 2030))), width="stretch", config={"displayModeBar": False, "responsive": True}, key="power-planned-capacity")

def _lng_capacity_total(frame, stages):
    clean = frame.copy()
    for column in ["Baseload Bcf/d", "Design Bcf/d"]:
        clean[column] = pd.to_numeric(clean.get(column), errors="coerce")
    clean["Capacity"] = clean["Baseload Bcf/d"].combine_first(clean["Design Bcf/d"])
    status = clean.get("Status", pd.Series("", index=clean.index)).fillna("").astype(str).str.casefold()
    selected = pd.Series(False, index=clean.index)
    for stage in stages:
        selected |= status.str.contains(stage, na=False)
    return clean.loc[selected, "Capacity"].sum(min_count=1)


def _render_fuel_infrastructure(power_data) -> None:
    gas = _market_frame(power_data, "gas_pipeline_projects")
    if gas.empty:
        gas = _market_frame(power_data, "gas_pipeline_projects")
    lng = _market_frame(power_data, "lng_projects")
    storage = _market_frame(power_data, "gas_storage_projects")
    gas["Additional Capacity (MMcf/d)"] = pd.to_numeric(gas.get("Additional Capacity (MMcf/d)"), errors="coerce")
    active_statuses = {
        "Construction", "Approved", "Announced", "Applied", "Pre-applied",
        "Proposed", "Part Completed (Phased Project)",
    }
    active = gas.loc[gas.get("Status", "").isin(active_statuses)]
    storage["Working Capacity (Bcf)"] = pd.to_numeric(storage.get("Working Capacity (Bcf)"), errors="coerce")
    storage_active = storage.loc[
        storage.get("Development Status", "").isin(["Planned", "On Hold"]),
        "Working Capacity (Bcf)",
    ].sum(min_count=1)
    render_statline(
        [
            ("Pipeline projects", f"{len(active):,}", "active development stages"),
            ("Pipeline capacity", fmt_number(active["Additional Capacity (MMcf/d)"].sum(min_count=1) / 1000.0, 1, suffix=" Bcf/d"), "active stages"),
            ("LNG construction / commissioning", fmt_number(_lng_capacity_total(lng, ["construction", "commission"]), 1, suffix=" Bcf/d"), "liquefaction capacity"),
            ("Storage development", fmt_number(storage_active, 1, suffix=" Bcf"), "working-gas capacity"),
        ],
        key_prefix="power-fuel-infrastructure",
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="power-panel-gas-pipeline"):
            render_panel_heading("Natural-gas pipeline development", "Additional delivery capacity")
            render_plotly_chart(
                gas_pipeline_capacity(gas),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="power-gas-pipeline",
            )
    with right:
        with st.container(border=True, key="power-panel-lng"):
            render_panel_heading("U.S. LNG liquefaction capacity", "Operating and development stages")
            render_plotly_chart(
                lng_capacity(lng),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="power-lng-capacity",
            )


def _render_prices(context: dict, power_data) -> None:
    retail = context["retail"]; wholesale = context["wholesale"]; prices = context["prices"]; through = _latest_date(retail)
    render_section("Power prices and fuel infrastructure", "Retail and wholesale electricity prices, with major fuel-infrastructure projects available as an alternate view.")
    render_summary_row([
        ("Residential", fmt_number(prices.get("residential"), 2, suffix="¢/kWh"), through),
        ("Commercial", fmt_number(prices.get("commercial"), 2, suffix="¢/kWh"), through),
        ("Industrial", fmt_number(prices.get("industrial"), 2, suffix="¢/kWh"), through),
        ("Henry Hub", "$" + fmt_number(prices.get("gas_value"), 2, suffix="/MMBtu"), fmt_date(prices.get("gas_date"))),
    ], key_prefix="power-prices")
    with st.container(key="full-width-layout-power-prices"):
        with st.container(border=True, key="power-panel-price-selected"):
            view = st.radio("Price and fuel view", ["Retail prices", "Wholesale hubs", "Fuel infrastructure"], horizontal=True, label_visibility="collapsed", key="power-view-prices")
            if view == "Fuel infrastructure":
                render_panel_heading("Generation-fuel infrastructure", "Natural-gas delivery, LNG export capacity, and storage development")
                _render_fuel_infrastructure(power_data)
            else:
                if view == "Wholesale hubs":
                    render_panel_heading("Wholesale power prices", "Major trading hubs"); figure, chart_key = wholesale_price_history(wholesale, height=450), "power-wholesale-prices"
                else:
                    render_panel_heading("Retail electricity prices", "United States"); figure, chart_key = retail_price_history(retail, height=450), "power-retail-prices"
                render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=chart_key)


def _render_power_ledger(context: dict, power_data) -> None:
    datasets = {
        "Retail demand & prices": context.get("retail"),
        "Generation": context.get("generation"),
        "Capacity snapshot": context.get("capacity"),
        "Generator pipeline": context.get("pipeline"),
        "Wholesale prices": context.get("wholesale"),
        "Large-load campuses": context.get("campuses"),
        "Gas pipelines": _market_frame(power_data, "gas_pipeline_projects"),
        "LNG projects": _market_frame(power_data, "lng_projects"),
    }
    with st.expander("Power data", expanded=False):
        view = st.radio("Dataset", list(datasets), horizontal=True, key="power-ledger-view")
        st.dataframe(arrow_safe_dataframe(datasets.get(view)), width="stretch", hide_index=True, height=460)

def render_power_tab(fred_data, regime_metrics, power_data, dashboard_data, infrastructure_data=None, tab_read=None):
    del fred_data, regime_metrics, dashboard_data
    _inject_power_page_theme()
    inject_panel_height_rules({"power-panel-demand-history": 520, "power-panel-large-load-profile": 520, "power-panel-gas-pipeline": 455, "power-panel-lng": 455})
    render_tab_header("Power", "Electricity demand, generation, planned capacity, prices, and major fuel infrastructure.", "EIA / FRED / facility registry")
    _render_floating_terms("power")
    context = _power_context(power_data, infrastructure_data or {})
    render_domain_read(tab_read, label="Read", domain="power")
    _render_power_pulse(context)
    _render_demand(context)
    _render_supply(context)
    _render_buildout(context)
    _render_prices(context, power_data)
    _render_power_ledger(context, power_data)

