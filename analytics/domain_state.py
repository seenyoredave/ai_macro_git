"""Canonical deterministic domain state shared by rendering and commentary.

Domain summaries are computed from loaded research inputs and reused across the
application.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np
import pandas as pd

from analytics.dashboard_context import DashboardContext
from analytics.energy_pulse import (
    demand_snapshot,
    development_snapshot,
    large_load_snapshot,
    price_snapshot,
)
from analytics.financial_conditions import nfci_snapshot
from analytics.grid_deliverability import (
    queue_outcome_snapshot,
    reserve_margin_profile,
    storage_duration_profile,
)
from analytics.market_ledger import build_market_ledger
from analytics.private_capital import build_private_capital_realization
from analytics.water_competition import current_top_withdrawal_profile
from analytics.water_local import local_water_constraint_summary


DOMAIN_ORDER = (
    "market",
    "finance",
    "compute",
    "data_center",
    "connectivity",
    "power",
    "grid_storage",
    "water",
    "adoption",
    "workforce",
    "economic_impact",
)

_ACTIVE_CAMPUS_STATUSES = {
    "operational",
    "under construction",
    "approved / permitted / under construction",
    "announced",
    "planned",
    "proposed",
    "expanding",
}
_DEVELOPMENT_CAMPUS_STATUSES = _ACTIVE_CAMPUS_STATUSES - {"operational"}


@dataclass(frozen=True, slots=True)
class DomainState:
    """One domain's finished deterministic summary and reusable analytical views."""

    metrics: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.0


def _num(value: Any) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else np.nan


def _commercial_metric(payload: dict | None, provider: str, metric: str) -> float:
    ledger = (payload or {}).get("ledger")
    if not isinstance(ledger, pd.DataFrame) or ledger.empty:
        return np.nan
    required = {"Provider", "Metric", "Value"}
    if not required.issubset(ledger.columns):
        return np.nan
    rows = ledger.loc[
        ledger["Provider"].astype(str).eq(str(provider))
        & ledger["Metric"].astype(str).eq(str(metric))
    ]
    return _num(rows.iloc[-1].get("Value")) if not rows.empty else np.nan


def _active_campuses(infrastructure_data: dict) -> pd.DataFrame:
    campuses = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        return pd.DataFrame()
    if "Campus ID" not in campuses.columns or campuses["Campus ID"].duplicated().any():
        raise ValueError("Deterministic domain state requires the Universal Data Center Registry")
    status = campuses.get("Status", pd.Series("", index=campuses.index)).fillna("").astype(str).str.casefold()
    return campuses.loc[status.isin(_ACTIVE_CAMPUS_STATUSES)].copy()


def build_market_state(context: DashboardContext) -> DomainState:
    ledger = build_market_ledger(context.sector_data)
    ledger_metrics = ledger.get("metrics", {}) or {}
    macro_df = (context.dashboard_data or {}).get("macro_df")

    aei = _num((context.regime_metrics or {}).get("AI Equity Index"))
    pressure = _num((context.regime_metrics or {}).get("Avg Sector Pressure"))
    breadth = _num(ledger_metrics.get("positive_breadth"))
    median_return = _num(ledger_metrics.get("median_return"))
    equal_return = _num(ledger_metrics.get("equal_weight_return"))
    top10 = _num(ledger_metrics.get("top_10_share"))
    effective = _num(ledger_metrics.get("effective_firms"))

    strong_sectors = 0
    crowded_sectors = 0
    if isinstance(macro_df, pd.DataFrame) and not macro_df.empty:
        scores = pd.to_numeric(macro_df.get("Sector Score"), errors="coerce")
        pressures = pd.to_numeric(macro_df.get("Pressure"), errors="coerce")
        strong_sectors = int(scores.ge(60).sum())
        crowded_sectors = int(pressures.ge(70).sum())

    importance = max(
        abs((aei if pd.notna(aei) else 50) - 50),
        abs((breadth * 100 if pd.notna(breadth) else 50) - 50),
        (top10 * 100 - 45) if pd.notna(top10) else 0,
        pressure - 50 if pd.notna(pressure) else 0,
    )
    return DomainState(
        metrics={
            "aei": aei,
            "pressure": pressure,
            "positive_breadth": breadth,
            "median_return": median_return,
            "equal_weight_return": equal_return,
            "top_10_share": top10,
            "effective_firms": effective,
            "strong_sector_count": strong_sectors,
            "crowded_sector_count": crowded_sectors,
        },
        importance=importance,
    )


def build_finance_state(context: DashboardContext) -> DomainState:
    regime = context.regime_metrics or {}
    funding = (regime.get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}
    nfci = nfci_snapshot(context.fred_data or {}, context.nfci_history)
    private_capital = build_private_capital_realization()
    private_metrics = private_capital.get("metrics", {}) or {}

    borrower = _num(regime.get("Borrower Strain"))
    lender = _num(regime.get("Lender Strain"))
    internal = _num(funding.get("internal_funding_coverage"))
    cash_runway = _num(funding.get("cash_reserve_coverage_years"))
    commitments = _num(funding.get("forward_commitment_load"))
    debt_pulse = _num(funding.get("debt_financing_pulse"))
    nfci_value = _num(nfci.get("value"))
    nfci_change = _num(nfci.get("three_month_change"))
    bond_distress = _num(
        ((((context.debt_markets_data or {}).get("series", {}) or {}).get("Corporate Bond Market Distress", {}) or {}).get("value"))
    )
    dpi = _num(private_metrics.get("dpi"))
    rvpi = _num(private_metrics.get("rvpi"))
    tvpi = _num(private_metrics.get("tvpi"))
    realized_share = _num(private_metrics.get("realized_share"))
    fund_count = int(private_metrics.get("fund_count", 0) or 0)

    commercial = context.commercialization_data
    microsoft_arr = _commercial_metric(commercial, "Microsoft", "Annual revenue run rate")
    microsoft_growth = _commercial_metric(commercial, "Microsoft", "Annual revenue run-rate growth")
    openai_arr = _commercial_metric(commercial, "OpenAI", "Annualized revenue run rate")
    alphabet_backlog = _commercial_metric(commercial, "Alphabet", "Backlog")

    realization_imbalance = abs(0.5 - realized_share) * 70 if pd.notna(realized_share) else 0
    importance = max(
        abs(borrower) if pd.notna(borrower) else 0,
        abs(lender) if pd.notna(lender) else 0,
        max(0, (1 - internal) * 45) if pd.notna(internal) else 0,
        min(75, max(0, commitments - 1) * 25) if pd.notna(commitments) else 0,
        realization_imbalance,
    )
    return DomainState(
        metrics={
            "borrower_strain": borrower,
            "lender_strain": lender,
            "internal_funding_coverage": internal,
            "cash_reserve_coverage_years": cash_runway,
            "forward_commitment_load": commitments,
            "debt_financing_pulse": debt_pulse,
            "nfci": nfci_value,
            "nfci_change": nfci_change,
            "bond_distress": bond_distress,
            "private_capital_dpi": dpi,
            "private_capital_rvpi": rvpi,
            "private_capital_tvpi": tvpi,
            "private_capital_realized_share": realized_share,
            "private_capital_mature_funds": fund_count,
            "microsoft_ai_arr_b": microsoft_arr,
            "microsoft_ai_arr_growth_pct": microsoft_growth,
            "openai_arr_b": openai_arr,
            "alphabet_cloud_backlog_b": alphabet_backlog,
        },
        importance=importance,
    )


def build_compute_state(context: DashboardContext) -> DomainState:
    compute = (context.infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    series = compute.get("series", {}) or {}

    def item(name: str) -> dict:
        return series.get(name, {}) or {}

    computer_growth = _num(item("Computer and Peripheral Equipment Output").get("yoy_growth"))
    semiconductor_growth = _num(item("Semiconductor and Electronic Component Output").get("yoy_growth"))
    computer_utilization = _num(item("Computer and Peripheral Equipment Capacity Utilization").get("value"))
    semiconductor_utilization = _num(item("Semiconductor and Electronic Component Capacity Utilization").get("value"))
    investment_growth = _num(item("Info Processing Investment Level").get("yoy_growth"))

    projects = compute.get("project_summary", {}) or {}
    capex = _num(projects.get("expected_capex_usd_b"))
    sites = int(projects.get("projects", 0) or 0)
    critical = compute.get("critical_supply_chain", {}) or {}
    covered = int(critical.get("covered_layers", 0) or 0)
    total = int(critical.get("critical_layers", 0) or 0)
    core_sites = int(critical.get("core_ai_sites", 0) or 0)
    core_capex = _num(critical.get("core_ai_capex_usd_b"))

    available_compute = _commercial_metric(context.commercialization_data, "OpenAI", "Available compute")
    serving_cost = _commercial_metric(context.commercialization_data, "Alphabet", "Serving unit-cost reduction")
    growths = [value for value in (computer_growth, semiconductor_growth, investment_growth) if pd.notna(value)]
    strongest = max(growths) if growths else np.nan
    importance = max(
        abs(strongest * 100) if pd.notna(strongest) else 0,
        min(capex / 5, 35) if pd.notna(capex) else 0,
    )
    return DomainState(
        metrics={
            "computer_output_growth": computer_growth,
            "semiconductor_output_growth": semiconductor_growth,
            "computer_utilization": computer_utilization,
            "semiconductor_utilization": semiconductor_utilization,
            "information_processing_investment_growth": investment_growth,
            "project_capex_b": capex,
            "project_sites": sites,
            "critical_layers_covered": covered,
            "critical_layers_total": total,
            "core_ai_sites": core_sites,
            "core_ai_capex_b": core_capex,
            "available_compute_gw": available_compute,
            "serving_cost_reduction_pct": serving_cost,
        },
        importance=importance,
    )


def build_data_center_state(context: DashboardContext) -> DomainState:
    infrastructure = context.infrastructure_data or {}
    inventory = infrastructure.get("data_center_inventory") or {}
    broad = inventory.get("broad_summary", {}) or {}
    tracker = inventory.get("open_tracker_summary", {}) or {}
    campuses = _active_campuses(infrastructure)

    status = campuses.get("Status", pd.Series("", index=campuses.index)).fillna("").astype(str).str.casefold()
    operating_mask = status.eq("operational")
    development_mask = status.isin(_DEVELOPMENT_CAMPUS_STATUSES)
    registry_operating = int(operating_mask.sum()) if len(status) else 0
    registry_development = int(development_mask.sum()) if len(status) else 0

    operating = int(broad.get("operating", 0) or 0) or registry_operating
    development = int(broad.get("development", 0) or 0) or registry_development
    ratio = _num(broad.get("development_to_operating"))
    if pd.isna(ratio) and operating:
        ratio = development / operating

    if campuses.empty:
        reference = pd.Series(dtype=float)
    else:
        reference = pd.to_numeric(campuses.get("Planned Data Center Capacity MW"), errors="coerce")
        reference = reference.combine_first(
            pd.to_numeric(campuses.get("Published Capacity Estimate MW"), errors="coerce")
        ).where(lambda values: values > 0)
    coverage = float(reference.notna().mean()) if len(campuses) else np.nan
    registry_pipeline = _num(reference.loc[development_mask].sum(min_count=1) / 1000) if len(reference) else np.nan
    registry_operating_capacity = _num(reference.loc[operating_mask].sum(min_count=1) / 1000) if len(reference) else np.nan

    tracked = int(tracker.get("active_pipeline", 0) or 0) or registry_development
    pipeline_capacity = _num(tracker.get("active_pipeline_published_mw")) / 1000
    if pd.isna(pipeline_capacity):
        pipeline_capacity = registry_pipeline
    operating_capacity = _num(tracker.get("operating_published_mw")) / 1000
    if pd.isna(operating_capacity):
        operating_capacity = registry_operating_capacity

    importance = min(
        90,
        (ratio * 45 if pd.notna(ratio) else 0)
        + (min(pipeline_capacity / 8, 35) if pd.notna(pipeline_capacity) else 0),
    )
    return DomainState(
        metrics={
            "operating_sites": operating,
            "development_sites": development,
            "development_to_operating": ratio,
            "tracked_pipeline_sites": tracked,
            "pipeline_capacity_gw": pipeline_capacity,
            "operating_capacity_gw": operating_capacity,
            "published_capacity_coverage": coverage,
        },
        importance=importance,
    )


def build_connectivity_state(context: DashboardContext) -> DomainState:
    payload = context.connectivity_data or (context.infrastructure_data or {}).get("connectivity", {}) or {}
    national = payload.get("national_summary", {}) or {}
    coverage = payload.get("coverage", {}) or {}

    active_ixps = _num(national.get("Active IXPs"))
    combined_members = _num(national.get("Combined Reported Members"))
    international_cables = _num(national.get("U.S. International Submarine Cable Systems"))
    cable_entries = _num(national.get("U.S.-Connected Cable Catalog Entries"))
    future_cables = _num(national.get("Future / Current-Year Cable Entries"))
    peering_facilities = _num(national.get("PeeringDB Facilities"))
    peering_floor = _num(national.get("PeeringDB Facility Coverage Floor"))
    middle_mile = _num(national.get("Middle-Mile New Fiber Miles"))
    mismatch_states = _num(coverage.get("mismatch_states"))
    campuses_screened = _num(coverage.get("campuses_screened"))
    population_ixp = _num(national.get("Population Centers With IXP"))
    population_total = _num(national.get("Population Centers Over 300k"))
    facility = peering_facilities if pd.notna(peering_facilities) and peering_facilities > 0 else peering_floor

    importance = min(
        94,
        (mismatch_states * 7 if pd.notna(mismatch_states) else 0)
        + (future_cables * 1.5 if pd.notna(future_cables) else 0)
        + (middle_mile / 1000 if pd.notna(middle_mile) else 0),
    )
    return DomainState(
        metrics={
            "active_ixps": active_ixps,
            "combined_ixp_members": combined_members,
            "international_submarine_cable_systems": international_cables,
            "us_connected_cable_catalog_entries": cable_entries,
            "future_or_current_year_cable_entries": future_cables,
            "interconnection_facilities_or_floor": facility,
            "middle_mile_new_fiber_miles": middle_mile,
            "high_capacity_low_public_connectivity_states": mismatch_states,
            "campuses_screened": campuses_screened,
            "population_centers_with_ixp": population_ixp,
            "population_centers_total": population_total,
        },
        importance=importance,
    )


def build_power_state(context: DashboardContext) -> DomainState:
    energy = context.energy_data or {}
    retail = energy.get("retail_history")
    pipeline = energy.get("generator_pipeline")
    campuses = _active_campuses(context.infrastructure_data or {})
    demand = demand_snapshot(retail if isinstance(retail, pd.DataFrame) else pd.DataFrame())
    large_loads = large_load_snapshot(campuses)
    development = development_snapshot(
        pipeline if isinstance(pipeline, pd.DataFrame) else pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    prices = price_snapshot(
        retail if isinstance(retail, pd.DataFrame) else pd.DataFrame(),
        ((energy.get("series", {}) or {}).get("Natural Gas Price", {}) or {}),
    )

    demand_growth = _num(demand.get("total_growth"))
    commercial_growth = _num(demand.get("commercial_growth"))
    planned_net = _num(development.get("planned_net_gw"))
    price_growth = _num(prices.get("total_growth"))
    load_mw = _num(large_loads.get("published_total_mw"))
    importance = max(
        abs(demand_growth) * 8 if pd.notna(demand_growth) else 0,
        abs(price_growth) * 5 if pd.notna(price_growth) else 0,
        abs(planned_net) if pd.notna(planned_net) else 0,
    )
    return DomainState(
        metrics={
            "demand_growth": demand_growth,
            "commercial_growth": commercial_growth,
            "planned_net_gw": planned_net,
            "retail_price_growth": price_growth,
            "large_load_capacity_mw": load_mw,
            "pipeline_end_year": development.get("end_year"),
        },
        importance=importance,
    )


def build_grid_storage_state(context: DashboardContext) -> DomainState:
    energy = context.energy_data or {}
    queue = energy.get("interconnection_queue")
    summary = energy.get("interconnection_queue_summary")
    pipeline = energy.get("generator_pipeline")
    development = development_snapshot(
        pipeline if isinstance(pipeline, pd.DataFrame) else pd.DataFrame(),
        queue if isinstance(queue, pd.DataFrame) else pd.DataFrame(),
        summary if isinstance(summary, pd.DataFrame) else pd.DataFrame(),
    )
    active = development.get("active_queue")
    storage_gw = np.nan
    if isinstance(active, pd.DataFrame) and not active.empty:
        storage_gw = pd.to_numeric(active.get("Storage MW"), errors="coerce").sum(min_count=1) / 1000

    outcomes_frame = energy.get("queue_outcomes_summary")
    outcomes = queue_outcome_snapshot(outcomes_frame)
    reserves = reserve_margin_profile(energy.get("reliability_reserve_margins"))
    duration_frame, duration = storage_duration_profile(energy.get("operating_generators"))

    queue_gw = _num(development.get("headline_queue_gw"))
    advanced = _num(development.get("advanced_share"))
    operational = _num(outcomes.get("Historical Operational Share Percent"))
    withdrawn = _num(outcomes.get("Historical Withdrawn Share Percent"))
    median_years = _num(outcomes.get("Median Request to COD Years"))
    agreement = _num(outcomes.get("Draft or Executed IA GW"))
    weighted_duration = _num(duration.get("weighted_duration_hours"))
    four_hour_share = _num(duration.get("four_hour_plus_share"))
    power_growth = _num(
        (((context.infrastructure_data or {}).get("series", {}) or {}).get("Electric Power Construction", {}) or {}).get("yoy_growth")
    )

    extreme = (
        pd.to_numeric(reserves.get("Extreme Conditions Margin Percent"), errors="coerce")
        if isinstance(reserves, pd.DataFrame) and not reserves.empty
        else pd.Series(dtype=float)
    )
    lowest = reserves.loc[extreme.idxmin()] if not extreme.dropna().empty else pd.Series(dtype=object)
    lowest_area = str(lowest.get("Assessment Area") or "")
    lowest_margin = _num(lowest.get("Extreme Conditions Margin Percent"))
    negative_areas = int(extreme.lt(0).sum()) if not extreme.empty else 0

    importance = max(
        50 - advanced if pd.notna(advanced) else 0,
        min(queue_gw / 25, 70) if pd.notna(queue_gw) else 0,
        75 - operational if pd.notna(operational) else 0,
        abs(min(lowest_margin, 0)) * 8 + 60 if pd.notna(lowest_margin) and lowest_margin < 0 else 0,
    )

    return DomainState(
        metrics={
            "queue_gw": queue_gw,
            "advanced_share": advanced,
            "storage_queue_gw": storage_gw,
            "historical_operational_pct": operational,
            "historical_withdrawn_pct": withdrawn,
            "median_request_to_cod_years": median_years,
            "draft_or_executed_ia_gw": agreement,
            "lowest_extreme_margin_pct": lowest_margin,
            "lowest_extreme_margin_area": lowest_area,
            "negative_extreme_margin_areas": negative_areas,
            "operating_storage_weighted_duration_hours": weighted_duration,
            "operating_storage_four_hour_plus_share_pct": four_hour_share,
            "electric_power_construction_growth": power_growth,
        },
        importance=importance,
    )


def build_water_state(context: DashboardContext) -> DomainState:
    water = context.water_data or {}
    summary = water.get("summary", {}) or {}
    eia = summary.get("eia_2024_thermoelectric", {}) or {}
    campuses = water.get("campus_context")
    if not isinstance(campuses, pd.DataFrame):
        campuses = (context.infrastructure_data or {}).get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        campuses = pd.DataFrame()

    local = local_water_constraint_summary(campuses)
    national_profile = current_top_withdrawal_profile(water.get("usgs_2020_top_withdrawals"))
    values = (
        national_profile.set_index("Use Category")["Withdrawal Bgal/day"].to_dict()
        if not national_profile.empty
        else {}
    )

    campus_count = int(local.get("campuses", 0) or 0)
    county_resolved = int(local.get("campuses_with_county_drought_data", 0) or 0)
    county_share = _num(local.get("county_drought_coverage_share"))
    d2_campuses = int(local.get("campuses_in_counties_with_d2", 0) or 0)
    d2_share = _num(local.get("campuses_in_counties_with_d2_share"))
    material_campuses = int(local.get("campuses_in_counties_with_25pct_d2", 0) or 0)
    material_share = _num(local.get("campuses_in_counties_with_25pct_d2_share"))
    highest_location = str(local.get("highest_county_d2_location") or "")
    highest_d2 = _num(local.get("highest_county_d2_area_pct"))

    direct = int(local.get("direct_water_evidence", 0) or 0)
    quantified_withdrawal = int(local.get("quantified_withdrawal", 0) or 0)
    quantified_consumption = int(local.get("quantified_consumption", 0) or 0)
    quantified_use = quantified_withdrawal + quantified_consumption
    direct_share = direct / campus_count * 100 if campus_count else np.nan

    pws_resolved = int(local.get("service_area_query_resolved", 0) or 0)
    pws_resolution_share = _num(local.get("service_area_query_resolution_share"))
    pws_overlap = int(local.get("service_area_overlap", 0) or 0)
    pws_share = _num(local.get("service_area_overlap_share"))
    authoritative = int(local.get("authoritative_service_area_overlap", 0) or 0)
    modeled = int(local.get("modeled_service_area_overlap", 0) or 0)
    unclassified = int(local.get("unclassified_service_area_overlap", 0) or 0)
    provenance_share = _num(local.get("service_area_provenance_classified_share"))
    ambiguous = int(local.get("ambiguous_service_area_overlap", 0) or 0)
    use_provenance_split = bool(pws_overlap > 0 and pd.notna(provenance_share) and provenance_share >= 0.8)

    capacity_coverage = _num(local.get("published_capacity_coverage_share"))
    d2_capacity = _num(local.get("published_capacity_in_counties_with_d2_gw"))
    material_capacity = _num(local.get("published_capacity_in_counties_with_25pct_d2_gw"))
    use_capacity = bool(pd.notna(capacity_coverage) and capacity_coverage >= 0.25)

    irrigation = _num(values.get("Crop irrigation"))
    thermoelectric = _num(values.get("Thermoelectric power"))
    public_supply = _num(values.get("Public supply"))
    reported_withdrawal = _num(eia.get("withdrawal_bgal_day"))
    reported_consumption = _num(eia.get("consumption_bgal_day"))

    exposure_score = 35 * (material_share if pd.notna(material_share) else 0) + 15 * (d2_share if pd.notna(d2_share) else 0)
    resolution_factor = min(1.0, county_share / 0.8) if pd.notna(county_share) and county_share > 0 else 0.0
    disclosure_gap = 1 - (direct / campus_count) if campus_count else 0.0
    importance = min(85, 35 + exposure_score * resolution_factor + 10 * disclosure_gap)

    return DomainState(
        metrics={
            "campuses": campus_count,
            "campuses_with_county_drought_data": county_resolved,
            "county_drought_coverage_share_pct": county_share,
            "campuses_in_counties_with_d2_area": d2_campuses,
            "campuses_in_counties_with_d2_share_pct": d2_share,
            "campuses_in_counties_with_25pct_d2_area": material_campuses,
            "campuses_in_counties_with_25pct_d2_share_pct": material_share,
            "highest_county_d2_location": highest_location,
            "highest_county_d2_area_pct": highest_d2,
            "direct_evidence_campuses": direct,
            "direct_evidence_share_pct": direct_share,
            "quantified_withdrawal_campuses": quantified_withdrawal,
            "quantified_consumption_campuses": quantified_consumption,
            "quantified_use_campuses": quantified_use,
            "pws_query_resolved_campuses": pws_resolved,
            "pws_query_resolution_share_pct": pws_resolution_share,
            "pws_service_area_overlap_campuses": pws_overlap,
            "pws_service_area_overlap_share_pct": pws_share,
            "pws_provenance_classified_share_pct": provenance_share,
            "unclassified_pws_overlap_campuses": unclassified,
            "authoritative_pws_overlap_campuses": authoritative if use_provenance_split else np.nan,
            "modeled_pws_overlap_campuses": modeled if use_provenance_split else np.nan,
            "ambiguous_pws_overlap_campuses": ambiguous,
            "published_capacity_coverage_share_pct": capacity_coverage if use_capacity else np.nan,
            "published_capacity_in_counties_with_d2_gw": d2_capacity if use_capacity else np.nan,
            "published_capacity_in_counties_with_25pct_d2_gw": material_capacity if use_capacity else np.nan,
            "irrigation_withdrawal_bgal_day_2020": irrigation,
            "thermoelectric_withdrawal_bgal_day_2020": thermoelectric,
            "public_supply_withdrawal_bgal_day_2020": public_supply,
            "thermoelectric_reported_withdrawal_bgal_day_2024": reported_withdrawal,
            "thermoelectric_reported_consumption_bgal_day_2024": reported_consumption,
        },
        importance=importance,
    )


def build_adoption_state(context: DashboardContext) -> DomainState:
    adoption = context.adoption_data or {}
    current = _num(adoption.get("current_use"))
    expected = _num(adoption.get("expected_use"))
    gap = _num(adoption.get("expected_adoption_gap"))
    annual = _num(adoption.get("annual_change"))
    consumer_overall = _num((adoption.get("consumer_overall", {}) or {}).get("value"))
    consumer_personal = _num((adoption.get("consumer_personal", {}) or {}).get("value"))
    consumer_work = _num((adoption.get("consumer_work", {}) or {}).get("value"))
    consumer_active = _num((adoption.get("consumer_active", {}) or {}).get("value"))
    consumer_daily = _num((adoption.get("consumer_daily", {}) or {}).get("value"))
    depth = ((adoption.get("depth") or {}).get("snapshot") or {})
    worker_ai_use = _num(depth.get("worker_ai_use_pct"))
    worker_genai_use = _num(depth.get("worker_genai_use_pct"))
    function_le3 = _num(depth.get("function_le3_share_pct"))
    task_le3 = _num(depth.get("task_le3_share_pct"))
    top_function = str(depth.get("top_function") or "")
    top_function_use = _num(depth.get("top_function_use_pct"))
    top_task = str(depth.get("top_task") or "")
    top_task_use = _num(depth.get("top_task_use_pct"))
    organizational_change = _num(depth.get("organizational_change_share_pct"))
    task_augmentation = _num(depth.get("task_augmentation_pct"))
    task_substitution = _num(depth.get("task_substitution_pct"))
    task_creation = _num(depth.get("task_creation_pct"))
    employment_decrease = _num(depth.get("employment_decrease_pct"))
    employment_unchanged = _num(depth.get("employment_unchanged_pct"))

    change = np.nan
    history = adoption.get("consumer_history")
    if isinstance(history, pd.DataFrame) and not history.empty:
        rows = history.loc[
            history.get("Series", pd.Series("", index=history.index)).astype(str).eq("Overall use")
        ].copy()
        rows["Date"] = pd.to_datetime(rows.get("Date"), errors="coerce", format="mixed")
        rows["Value"] = pd.to_numeric(rows.get("Value"), errors="coerce")
        rows = rows.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
        if len(rows) >= 2:
            change = float(rows.iloc[-1]["Value"] - rows.iloc[0]["Value"])

    sector_coverage = np.nan
    leading_sector = ""
    leading_sector_use = np.nan
    sectors = adoption.get("sector_snapshot")
    if isinstance(sectors, pd.DataFrame) and not sectors.empty:
        values = pd.to_numeric(sectors.get("Current AI Use"), errors="coerce")
        sector_coverage = float(values.notna().mean())
        if values.notna().any():
            index = values.idxmax()
            leading_sector = str(sectors.loc[index].get("Sector", ""))
            leading_sector_use = float(values.loc[index])

    commercial = context.commercialization_data
    subscribers = _commercial_metric(commercial, "OpenAI", "Consumer subscribers")
    subscriber_share = _commercial_metric(commercial, "OpenAI", "Implied subscriber share")
    business_users = _commercial_metric(commercial, "OpenAI", "Paying business users")
    gemini_seats = _commercial_metric(commercial, "Alphabet", "Paid seats")

    importance = max(
        abs(annual) * 8 if pd.notna(annual) else 0,
        gap * 4 if pd.notna(gap) else 0,
        abs(change) * 5 if pd.notna(change) else 0,
    )
    return DomainState(
        metrics={
            "current_business_use_pct": current,
            "expected_business_use_pct": expected,
            "expected_adoption_gap_ppts": gap,
            "annual_change_ppts": annual,
            "consumer_overall_pct": consumer_overall,
            "consumer_personal_pct": consumer_personal,
            "consumer_work_pct": consumer_work,
            "consumer_active_pct": consumer_active,
            "consumer_daily_pct": consumer_daily,
            "consumer_change_ppts": change,
            "sector_coverage": sector_coverage,
            "leading_sector": leading_sector,
            "leading_sector_use_pct": leading_sector_use,
            "worker_ai_use_pct": worker_ai_use,
            "worker_genai_use_pct": worker_genai_use,
            "function_le3_share_pct": function_le3,
            "task_le3_share_pct": task_le3,
            "top_function": top_function,
            "top_function_use_pct": top_function_use,
            "top_task": top_task,
            "top_task_use_pct": top_task_use,
            "organizational_change_share_pct": organizational_change,
            "task_augmentation_pct": task_augmentation,
            "task_substitution_pct": task_substitution,
            "task_creation_pct": task_creation,
            "employment_decrease_pct": employment_decrease,
            "employment_unchanged_pct": employment_unchanged,
            "chatgpt_subscribers_m": subscribers,
            "implied_subscriber_share_pct": subscriber_share,
            "openai_paying_business_users_m": business_users,
            "gemini_enterprise_paid_seats_m": gemini_seats,
        },
        importance=importance,
    )


def build_workforce_state(context: DashboardContext) -> DomainState:
    workforce = context.workforce_data or {}
    matrix = workforce.get("transmission_matrix")
    if not isinstance(matrix, pd.DataFrame) or matrix.empty:
        return DomainState()

    exposure = workforce.get("exposure_summary", {}) or {}
    employment = pd.to_numeric(matrix.get("Employment YoY"), errors="coerce")
    earnings = pd.to_numeric(matrix.get("Real earnings YoY"), errors="coerce")
    layoffs = pd.to_numeric(matrix.get("Layoffs rate"), errors="coerce")
    openings = pd.to_numeric(matrix.get("Openings rate"), errors="coerce")

    positive_jobs = int((employment > 0).sum())
    positive_real = int((earnings > 0).sum())
    strongest_index = employment.idxmax() if employment.notna().any() else None
    weakest_index = employment.idxmin() if employment.notna().any() else None
    strongest = matrix.loc[strongest_index].to_dict() if strongest_index is not None else {}
    weakest = matrix.loc[weakest_index].to_dict() if weakest_index is not None else {}
    importance = max(
        [abs(float(value)) for value in employment.dropna().tolist() + earnings.dropna().tolist()] + [0]
    ) * 10

    return DomainState(
        metrics={
            "employment_breadth": positive_jobs,
            "real_earnings_breadth": positive_real,
            "strongest_channel": str(strongest.get("Channel") or ""),
            "strongest_channel_growth": _num(strongest.get("Employment YoY")),
            "weakest_channel": str(weakest.get("Channel") or ""),
            "weakest_channel_growth": _num(weakest.get("Employment YoY")),
            "max_layoff_rate": float(layoffs.max()) if layoffs.notna().any() else np.nan,
            "max_openings_rate": float(openings.max()) if openings.notna().any() else np.nan,
            "occupation_exposure_count": _num(exposure.get("occupations")),
            "median_llm_software_exposure_pct": _num(exposure.get("median_llm_software_exposure")),
            "high_exposure_occupation_share_pct": _num(exposure.get("share_at_least_50_pct")),
        },
        importance=importance,
    )


def build_economic_impact_state(context: DashboardContext) -> DomainState:
    economic = context.economic_impact_data or {}
    capture = economic.get("capture_summary", {}) or {}
    productivity = _num((economic.get("nonfarm_productivity", {}) or {}).get("value"))
    output = _num((economic.get("nonfarm_output", {}) or {}).get("value"))
    unit_cost = _num((economic.get("nonfarm_unit_labor_cost", {}) or {}).get("value"))
    investment = _num((economic.get("information_investment", {}) or {}).get("yoy"))
    real_comp = _num((capture.get("real_compensation", {}) or {}).get("yoy"))
    real_comp_since = _num((capture.get("real_compensation", {}) or {}).get("since_2020"))
    productivity_since = _num((capture.get("productivity", {}) or {}).get("since_2020"))
    labor_share_since = _num((capture.get("labor_share", {}) or {}).get("since_2020"))
    median_earnings = _num((capture.get("median_real_earnings", {}) or {}).get("YoY"))
    gap = _num(capture.get("productivity_real_comp_gap"))
    spread = _num(capture.get("group_growth_spread_ppts"))

    commercial = context.commercialization_data
    microsoft_arr = _commercial_metric(commercial, "Microsoft", "Annual revenue run rate")
    openai_arr = _commercial_metric(commercial, "OpenAI", "Annualized revenue run rate")
    alphabet_growth = _commercial_metric(commercial, "Alphabet", "Revenue growth")
    enterprise_share = _commercial_metric(commercial, "OpenAI", "Enterprise share of revenue")

    importance = max(
        abs(gap) * 5 if pd.notna(gap) else 0,
        abs(labor_share_since) * 4 if pd.notna(labor_share_since) else 0,
        abs(productivity) * 8 if pd.notna(productivity) else 0,
    )
    return DomainState(
        metrics={
            "productivity_growth": productivity,
            "real_output_growth": output,
            "real_compensation_growth": real_comp,
            "unit_labor_cost_growth": unit_cost,
            "information_investment_growth": investment,
            "productivity_since_2020": productivity_since,
            "real_compensation_since_2020": real_comp_since,
            "productivity_real_comp_gap": gap,
            "labor_share_since_2020": labor_share_since,
            "median_real_earnings_growth": median_earnings,
            "group_growth_spread_ppts": spread,
            "microsoft_ai_arr_b": microsoft_arr,
            "openai_arr_b": openai_arr,
            "alphabet_cloud_growth_pct": alphabet_growth,
            "openai_enterprise_share_pct": enterprise_share,
        },
        importance=importance,
    )


_STATE_BUILDERS = {
    "market": build_market_state,
    "finance": build_finance_state,
    "compute": build_compute_state,
    "data_center": build_data_center_state,
    "connectivity": build_connectivity_state,
    "power": build_power_state,
    "grid_storage": build_grid_storage_state,
    "water": build_water_state,
    "adoption": build_adoption_state,
    "workforce": build_workforce_state,
    "economic_impact": build_economic_impact_state,
}


def build_domain_states(context: DashboardContext) -> dict[str, DomainState]:
    """Build the canonical deterministic domain summary set exactly once."""
    return {domain: _STATE_BUILDERS[domain](context) for domain in DOMAIN_ORDER}


def with_domain_states(context: DashboardContext) -> DashboardContext:
    """Return a context carrying canonical deterministic domain state."""
    return replace(context, domain_states=build_domain_states(context))


def with_domain_state(context: DashboardContext, domain: str) -> DashboardContext:
    """Return a context carrying one freshly computed canonical domain state."""
    if domain not in _STATE_BUILDERS:
        raise KeyError(f"Unknown domain state: {domain}")
    states = dict(context.domain_states or {})
    states[domain] = _STATE_BUILDERS[domain](context)
    return replace(context, domain_states=states)
