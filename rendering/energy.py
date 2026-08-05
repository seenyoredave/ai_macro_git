from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

from analytics.energy_pulse import (
    build_energy_read,
    demand_snapshot,
    development_snapshot,
    large_load_snapshot,
    price_snapshot,
    supply_snapshot,
)
from config.energy_config import ENERGY_SERIES
from rendering.charts_data_center import ACTIVE_CAMPUS_STATUSES
from rendering.charts_energy import (
    capacity_changes,
    commercial_markets,
    electricity_demand_history,
    energy_supply_profile,
    gas_pipeline_capacity,
    generation_change,
    generation_mix,
    lng_capacity,
    operating_capacity,
    planned_capacity,
    queue_by_region,
    queue_by_technology,
    retail_price_history,
    wholesale_price_history,
)
from rendering.common import _render_tab_metric_registry
from rendering.components import (
    inject_panel_height_rules,
    fmt_date,
    fmt_number,
    render_domain_read,
    render_line_break,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)


def _energy_item(energy_data, name):
    return (((energy_data or {}).get("series", {}) or {}).get(name, {}) or {})


def _market_frame(energy_data, name):
    frame = (energy_data or {}).get(name)
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _energy_source_label(name):
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


def _energy_source_rows(energy_data):
    datasets = [
        ("Retail sales, customers, and prices", "retail_history", "Date", "EIA-861M"),
        ("Electricity generation", "generation_history", "Date", "EIA Electric Power Monthly / EIA-923"),
        ("Operating generators", "operating_generators", None, "EIA-860M"),
        ("Operating capacity", "capacity_snapshot", None, "EIA-860M"),
        ("Generator additions and retirements", "generator_pipeline", "Expected Year", "EIA-860M"),
        ("Current-year capacity changes", "capacity_changes", "Date", "EIA Electric Power Monthly"),
        ("Interconnection requests", "interconnection_queue", "q_date", "Berkeley Lab Interconnection Queue Dataset"),
        ("Wholesale electricity prices", "wholesale_prices", "Trade Date", "EIA / ICE"),
        ("Natural-gas pipeline source records", "gas_pipeline_projects", "Last Updated Date", "EIA Natural Gas Pipeline Projects"),
        ("Natural-gas pipeline projects", "gas_pipeline_canonical", "Last Updated Date", "EIA Natural Gas Pipeline Projects"),
        ("LNG liquefaction projects", "lng_projects", "In-service Date", "EIA LNG Capacity"),
        ("Natural-gas storage projects", "gas_storage_projects", "Year in Service", "EIA Natural Gas Storage Projects"),
    ]
    rows = []
    for dataset, key, date_column, source in datasets:
        frame = _market_frame(energy_data, key)
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
        item = _energy_item(energy_data, name)
        rows.append({
            "Dataset": spec.get("display_name", name),
            "Records": f"{len(item.get('history')):,}" if isinstance(item.get("history"), pd.DataFrame) else "0",
            "Latest observation": fmt_date(item.get("date")),
            "Coverage": _date_range(item.get("history")) if isinstance(item.get("history"), pd.DataFrame) else "n/a",
            "Source": _energy_source_label(name),
        })
    return pd.DataFrame(rows)


def _latest_date(frame, column="Date"):
    if frame.empty or column not in frame:
        return "n/a"
    dates = pd.to_datetime(frame[column], errors="coerce", format="mixed").dropna()
    return "n/a" if dates.empty else dates.max().strftime("%Y-%m")


def _active_campuses(infrastructure_data):
    campuses = (infrastructure_data or {}).get("campus_registry")
    if not isinstance(campuses, pd.DataFrame):
        campuses = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(campuses, pd.DataFrame):
        return pd.DataFrame()
    clean = campuses.copy()
    status = clean.get("Status", pd.Series("", index=clean.index)).fillna("").astype(str).str.casefold()
    active_statuses = {value.casefold() for value in ACTIVE_CAMPUS_STATUSES}
    return clean.loc[status.eq("operational") | status.isin(active_statuses)].copy()


def _inject_energy_page_theme() -> None:
    st.markdown(
        """
        <style>
        div[class*="st-key-energy-panel-"] {
            border-color: rgba(148, 163, 184, 0.15) !important;
            background: rgba(17, 24, 39, 0.72) !important;
            box-shadow: inset 0 1px 0 rgba(52, 211, 153, 0.035) !important;
        }
        div[class*="st-key-energy-panel-"] [data-testid="stPlotlyChart"] {
            margin-top: -0.15rem;
        }
        div[class*="st-key-statline-energy-pulse-"] {
            border-top-color: rgba(52, 211, 153, 0.82) !important;
        }
        div[class*="st-key-statline-energy-demand-"] ,
        div[class*="st-key-statline-energy-supply-"] ,
        div[class*="st-key-statline-energy-buildout-"] ,
        div[class*="st-key-statline-energy-prices-"] {
            border-top-color: rgba(96, 165, 250, 0.72) !important;
        }
        .rm-energy-read {
            border: 1px solid rgba(52, 211, 153, 0.18);
            border-left: 3px solid #34d399;
            border-radius: 0 13px 13px 0;
            background: linear-gradient(90deg, rgba(5, 150, 105, 0.10), rgba(17, 24, 39, 0.61));
            padding: 0.82rem 1rem 0.88rem 1rem;
            margin: 0.18rem 0 1.05rem 0;
        }
        .rm-energy-read-kicker {
            color: #6ee7b7;
            font-size: 0.64rem;
            font-weight: 800;
            letter-spacing: 0.11em;
            text-transform: uppercase;
        }
        .rm-energy-read-title {
            color: #f8fafc;
            font-size: 1.02rem;
            font-weight: 760;
            margin-top: 0.18rem;
        }
        .rm-energy-read-copy {
            color: #b9c3d2;
            font-size: 0.82rem;
            line-height: 1.5;
            margin-top: 0.22rem;
            max-width: 1120px;
        }
        .rm-energy-load-profile {
            padding: 0.15rem 0 0.25rem 0;
        }
        .rm-energy-load-metrics {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.35rem 0 0.85rem 0;
        }
        .rm-energy-load-metric {
            border: 1px solid rgba(148, 163, 184, 0.13);
            border-radius: 10px;
            background: rgba(15, 23, 42, 0.46);
            padding: 0.58rem 0.62rem;
        }
        .rm-energy-load-metric span {
            display: block;
            color: #8793a8;
            font-size: 0.61rem;
            font-weight: 800;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .rm-energy-load-metric b {
            display: block;
            color: #eef2ff;
            font-size: 1.02rem;
            margin-top: 0.16rem;
        }
        .rm-energy-load-rank {
            display: grid;
            grid-template-columns: 2rem minmax(0, 1fr) 3.6rem;
            gap: 0.5rem;
            align-items: center;
            margin: 0.54rem 0;
            color: #cbd5e1;
            font-size: 0.74rem;
        }
        .rm-energy-load-rank strong {
            color: #e2e8f0;
            font-size: 0.72rem;
        }
        .rm-energy-load-track {
            height: 8px;
            border-radius: 999px;
            background: rgba(51, 65, 85, 0.64);
            overflow: hidden;
        }
        .rm-energy-load-fill {
            display: block;
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #60a5fa, #8b5cf6);
        }
        .rm-energy-load-note {
            color: #7f8ba1;
            font-size: 0.68rem;
            line-height: 1.4;
            margin-top: 0.72rem;
        }
        div[class*="st-key-energy-view-"] [role="radiogroup"] {
            gap: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _energy_context(energy_data, infrastructure_data) -> dict:
    retail = _market_frame(energy_data, "retail_history")
    generation = _market_frame(energy_data, "generation_history")
    capacity = _market_frame(energy_data, "capacity_snapshot")
    changes = _market_frame(energy_data, "capacity_changes")
    pipeline = _market_frame(energy_data, "generator_pipeline")
    queue = _market_frame(energy_data, "interconnection_queue")
    queue_summary = _market_frame(energy_data, "interconnection_queue_summary")
    wholesale = _market_frame(energy_data, "wholesale_prices")
    campuses = _active_campuses(infrastructure_data)
    context = {
        "retail": retail,
        "generation": generation,
        "capacity": capacity,
        "changes": changes,
        "pipeline": pipeline,
        "queue": queue,
        "queue_summary": queue_summary,
        "wholesale": wholesale,
        "campuses": campuses,
        "demand": demand_snapshot(retail),
        "large_loads": large_load_snapshot(campuses),
        "supply": supply_snapshot(generation, capacity, changes),
        "development": development_snapshot(pipeline, queue, queue_summary),
        "prices": price_snapshot(retail, _energy_item(energy_data, "Natural Gas Price")),
    }
    context["read"] = build_energy_read(
        context["demand"], context["large_loads"], context["development"], context["prices"]
    )
    return context


def _render_energy_pulse(context: dict) -> None:
    demand = context["demand"]
    large = context["large_loads"]
    development = context["development"]
    prices = context["prices"]

    published_total = pd.to_numeric(large.get("published_total_mw"), errors="coerce")
    if pd.notna(published_total) and published_total > 0:
        large_value = fmt_number(published_total / 1000.0, 1, suffix=" GW")
        coverage = pd.to_numeric(large.get("published_coverage"), errors="coerce")
        large_context = (
            f"published estimates · {fmt_number(coverage * 100.0, 0, suffix='%')} campus coverage"
            if pd.notna(coverage)
            else "published active-campus estimates"
        )
    else:
        large_value = f"{int(large.get('active_campuses', 0) or 0):,}"
        large_context = "active campuses · undisclosed capacity excluded"

    render_section(
        "Energy pulse",
        "The four signals that frame the rest of the page.",
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
        key_prefix="energy-pulse",
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
            '<div class="rm-energy-load-rank">'
            f'<strong>{html.escape(str(row["State"]))}</strong>'
            f'<div class="rm-energy-load-track"><span class="rm-energy-load-fill" style="width:{width:.1f}%"></span></div>'
            f'<span>{float(row["GW"]):.1f} GW</span>'
            '</div>'
        )
    ranking = "".join(rows) if rows else '<div class="rm-energy-load-note">No published state-level load estimates are available.</div>'
    coverage = fmt_number(
        pd.to_numeric(large.get("published_coverage"), errors="coerce") * 100.0,
        1,
        suffix="%",
    )
    markup = f'''<div class="rm-energy-load-profile">
        <div class="rm-energy-load-metrics">
            <div class="rm-energy-load-metric"><span>Total sales</span><b>{html.escape(fmt_number(demand.get("total_twh"), 0, suffix=" TWh"))}</b></div>
            <div class="rm-energy-load-metric"><span>Commercial YoY</span><b>{html.escape(fmt_number(demand.get("commercial_growth"), 1, signed=True, suffix="%"))}</b></div>
            <div class="rm-energy-load-metric"><span>Industrial YoY</span><b>{html.escape(fmt_number(demand.get("industrial_growth"), 1, signed=True, suffix="%"))}</b></div>
        </div>
        {ranking}
        <div class="rm-energy-load-note">Top states by published active-campus capacity estimate. Undisclosed load is excluded; national published coverage is {html.escape(coverage)}.</div>
    </div>'''
    st.markdown(markup, unsafe_allow_html=True)


def _render_demand(context: dict) -> None:
    retail = context["retail"]
    campuses = context["campuses"]
    demand = context["demand"]
    large = context["large_loads"]
    through = _latest_date(retail)

    render_section(
        "Demand & large loads",
        "The national demand trend, paired with a compact view of where disclosed data-center load is concentrating.",
    )
    left, right = st.columns([1.55, 0.85])
    with left:
        with st.container(border=True, key="energy-panel-demand-history"):
            render_panel_heading("Electricity demand by customer class", "Rolling 12-month sales")
            st.plotly_chart(
                electricity_demand_history(retail, height=410),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="energy-demand-history",
            )
    with right:
        with st.container(border=True, key="energy-panel-large-load-profile"):
            render_panel_heading("Large-load concentration", "Published active-campus estimates")
            _render_large_load_profile(context)

    if campuses.empty:
        st.caption("Large-load state exposure is unavailable because no active campus registry was supplied.")

    with st.expander("View commercial markets and customer detail", expanded=False):
        render_statline(
            [
                ("Customer accounts", fmt_number(demand.get("customers_m"), 1, suffix="M"), through),
                ("Active campuses", f"{int(large.get('active_campuses', 0) or 0):,}", f"{int(large.get('operating_campuses', 0) or 0):,} operating"),
                ("Published coverage", f"{int(large.get('published_records', 0) or 0):,} / {int(large.get('active_campuses', 0) or 0):,}", fmt_number(pd.to_numeric(large.get("published_coverage"), errors="coerce") * 100.0, 1, suffix="%")),
                ("Median disclosed load", fmt_number(large.get("published_median_mw"), 1, suffix=" MW"), "published estimates only"),
            ],
            key_prefix="energy-demand-detail",
        )
        with st.container(border=True, key="energy-panel-commercial-markets"):
            render_panel_heading("Largest commercial electricity markets", "Rolling 12-month sales")
            st.plotly_chart(
                commercial_markets(retail, height=390),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="energy-commercial-markets",
            )


def _render_supply(context: dict) -> None:
    generation = context["generation"]
    capacity = context["capacity"]
    changes = context["changes"]
    supply = context["supply"]
    through = _latest_date(generation)

    render_section(
        "Supply & fleet",
        "The generation base and the technologies entering or leaving the operating fleet.",
    )
    render_statline(
        [
            ("Natural gas share", fmt_number(supply.get("gas_share"), 1, suffix="%"), "rolling 12 months"),
            ("Nuclear share", fmt_number(supply.get("nuclear_share"), 1, suffix="%"), "rolling 12 months"),
            ("Renewable share", fmt_number(supply.get("renewable_share"), 1, suffix="%"), "hydro, wind, solar, and other"),
            ("Operating capacity", fmt_number(supply.get("capacity_gw"), 1, suffix=" GW"), f"latest fleet snapshot · {through}"),
        ],
        key_prefix="energy-supply",
    )

    with st.container(border=True, key="energy-panel-supply-profile"):
        render_panel_heading("Power-system supply profile", "Annual generation mix above · current-year fleet changes below")
        st.plotly_chart(
            energy_supply_profile(generation, changes, height=600),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="energy-supply-profile",
        )

    with st.expander("View generation and installed-capacity detail", expanded=False):
        render_statline(
            [
                ("Electricity generated", fmt_number(supply.get("total_twh"), 0, suffix=" TWh"), "rolling 12 months"),
                ("Battery capacity", fmt_number(supply.get("battery_gw"), 1, suffix=" GW"), fmt_number(supply.get("storage_gwh"), 1, suffix=" GWh")),
                ("Current additions", fmt_number(supply.get("current_additions_gw"), 1, suffix=" GW"), "through latest EIA release"),
                ("Current retirements", fmt_number(supply.get("current_retirements_gw"), 1, suffix=" GW"), "through latest EIA release"),
            ],
            key_prefix="energy-supply-detail",
        )
        detail_view = st.radio(
            "Supply detail view",
            ["Generation change", "Operating capacity"],
            horizontal=True,
            label_visibility="collapsed",
            key="energy-view-supply-detail",
        )
        with st.container(border=True, key="energy-panel-supply-detail-selected"):
            if detail_view == "Operating capacity":
                render_panel_heading("Operating capacity by technology", "Net summer capacity")
                figure = operating_capacity(capacity, height=430)
                chart_key = "energy-operating-capacity-chart"
            else:
                render_panel_heading("Generation change by source", "Rolling 12-month change")
                figure = generation_change(generation, height=430)
                chart_key = "energy-generation-change"
            st.plotly_chart(
                figure,
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key=chart_key,
            )


def _render_buildout(context: dict) -> None:
    development = context["development"]
    render_section(
        "Buildout",
        "How much capacity is planned, how large the queue is, and how far projects have progressed.",
    )
    render_statline(
        [
            ("Planned additions", fmt_number(development.get("planned_additions_gw"), 1, suffix=" GW"), f"{development.get('current_year')}–{development.get('end_year')}"),
            ("Planned retirements", fmt_number(development.get("planned_retirements_gw"), 1, suffix=" GW"), f"{development.get('current_year')}–{development.get('end_year')}"),
            ("Active queue", fmt_number(development.get("headline_queue_gw"), 0, suffix=" GW"), development.get("queue_context", "")),
            ("Advanced-stage queue", fmt_number(development.get("advanced_gw"), 0, suffix=" GW"), fmt_number(development.get("advanced_share"), 1, suffix="% of submitted capacity")),
        ],
        key_prefix="energy-buildout",
    )

    view = st.radio(
        "Buildout view",
        ["Planned capacity", "Queue by technology", "Queue by region"],
        horizontal=True,
        label_visibility="collapsed",
        key="energy-view-buildout",
    )
    with st.container(border=True, key="energy-panel-buildout-selected"):
        if view == "Queue by technology":
            render_panel_heading("Interconnection queue by technology", development.get("technology_note"))
            figure = queue_by_technology(development.get("technology_frame"), height=430)
            chart_key = "energy-queue-technology"
        elif view == "Queue by region":
            render_panel_heading("Interconnection queue by region", "Submitted components; storage imputation excluded")
            figure = queue_by_region(development.get("active_queue"), height=430)
            chart_key = "energy-queue-region"
        else:
            render_panel_heading(
                "Planned capacity additions and retirements",
                f"{development.get('current_year')}–{development.get('end_year')}",
            )
            figure = planned_capacity(
                development.get("pipeline"),
                height=430,
                end_year=int(development.get("end_year", 2030)),
            )
            chart_key = "energy-planned-capacity"
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=chart_key,
        )


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


def _render_fuel_infrastructure(energy_data) -> None:
    gas = _market_frame(energy_data, "gas_pipeline_canonical")
    if gas.empty:
        gas = _market_frame(energy_data, "gas_pipeline_projects")
    lng = _market_frame(energy_data, "lng_projects")
    storage = _market_frame(energy_data, "gas_storage_projects")
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
        key_prefix="energy-fuel-infrastructure",
    )
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="energy-panel-gas-pipeline"):
            render_panel_heading("Natural-gas pipeline development", "Additional delivery capacity")
            st.plotly_chart(
                gas_pipeline_capacity(gas),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="energy-gas-pipeline",
            )
    with right:
        with st.container(border=True, key="energy-panel-lng"):
            render_panel_heading("U.S. LNG liquefaction capacity", "Operating and development stages")
            st.plotly_chart(
                lng_capacity(lng),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="energy-lng-capacity",
            )


def _render_prices(context: dict, energy_data) -> None:
    retail = context["retail"]
    wholesale = context["wholesale"]
    prices = context["prices"]
    through = _latest_date(retail)
    render_section(
        "Prices & delivery",
        "Retail and wholesale power prices, with fuel infrastructure available on demand.",
    )
    render_statline(
        [
            ("Residential", fmt_number(prices.get("residential"), 2, suffix="¢/kWh"), through),
            ("Commercial", fmt_number(prices.get("commercial"), 2, suffix="¢/kWh"), through),
            ("Industrial", fmt_number(prices.get("industrial"), 2, suffix="¢/kWh"), through),
            ("Henry Hub", "$" + fmt_number(prices.get("gas_value"), 2, suffix="/MMBtu"), fmt_date(prices.get("gas_date"))),
        ],
        key_prefix="energy-prices",
    )

    view = st.radio(
        "Price view",
        ["Retail prices", "Wholesale hubs"],
        horizontal=True,
        label_visibility="collapsed",
        key="energy-view-prices",
    )
    with st.container(border=True, key="energy-panel-price-selected"):
        if view == "Wholesale hubs":
            render_panel_heading("Wholesale power prices", "Major trading hubs")
            figure = wholesale_price_history(wholesale, height=400)
            chart_key = "energy-wholesale-prices"
        else:
            render_panel_heading("Retail electricity prices", "United States")
            figure = retail_price_history(retail, height=400)
            chart_key = "energy-retail-prices"
        st.plotly_chart(
            figure,
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key=chart_key,
        )

    with st.expander("View gas, LNG, and storage infrastructure", expanded=False):
        _render_fuel_infrastructure(energy_data)


def render_energy_tab(fred_data, regime_metrics, energy_data, dashboard_data, infrastructure_data=None, tab_read=None):
    del fred_data, regime_metrics, dashboard_data
    _inject_energy_page_theme()
    inject_panel_height_rules({
        "energy-panel-demand-history": 500,
        "energy-panel-large-load-profile": 500,
        "energy-panel-gas-pipeline": 455,
        "energy-panel-lng": 455,
    })
    render_tab_header(
        "Energy",
        "U.S. power demand, system supply, capacity conversion, and prices—organized around the decisions that matter.",
        "EIA / Berkeley Lab / FRED / facility registry",
    )
    render_line_break()
    _render_tab_metric_registry("energy")
    context = _energy_context(energy_data, infrastructure_data or {})
    render_domain_read(tab_read or context.get("read"), label="Energy Read", accent="green")
    _render_energy_pulse(context)
    _render_demand(context)
    _render_supply(context)
    _render_buildout(context)
    _render_prices(context, energy_data)
