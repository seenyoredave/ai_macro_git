"""Model-safe evidence adapters for the AI Macro commentary overlay.

This module formats canonical analytical state, attaches evidence metadata, and
builds the bounded packets supplied to OpenAI.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import math
from typing import Any, Iterable


from analytics.dashboard_context import DashboardContext
from analytics.domain_state import DomainState

EVIDENCE_ARCHITECTURE_VERSION = "1.3.0"
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

DOMAIN_REFERENCES: dict[str, tuple[dict[str, str], ...]] = {
    "market": (
        {"source_label": "YFinance", "source_url": "https://finance.yahoo.com/"},
        {"source_label": "SEC EDGAR", "source_url": "https://www.sec.gov/edgar/search/"},
    ),
    "finance": (
        {"source_label": "FRED", "source_url": "https://fred.stlouisfed.org/"},
        {"source_label": "Chicago Fed NFCI", "source_url": "https://www.chicagofed.org/research/data/nfci/current-data"},
        {"source_label": "New York Fed CMDI", "source_url": "https://www.newyorkfed.org/research/policy/cmdi"},
        {"source_label": "SEC EDGAR", "source_url": "https://www.sec.gov/edgar/search/"},
        {"source_label": "CalSTRS PE Performance", "source_url": "https://www.calstrs.com/private-equity-portfolio-performance-table"},
        {"source_label": "Microsoft FY2026 Q3 AI disclosure", "source_url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast"},
        {"source_label": "OpenAI business scale disclosure", "source_url": "https://openai.com/index/a-business-that-scales-with-the-value-of-intelligence/"},
        {"source_label": "Alphabet Q2 2026 AI and Cloud disclosure", "source_url": "https://abc.xyz/investor/events/event-details/2026/2026-Q2-Earnings-Call-2026-GgTAq7Is0z/default.aspx"},
    ),
    "compute": (
        {"source_label": "Federal Reserve G.17", "source_url": "https://www.federalreserve.gov/releases/g17/current/"},
        {"source_label": "BEA Fixed Assets", "source_url": "https://www.bea.gov/data/investment-fixed-assets"},
        {"source_label": "Census Construction Spending", "source_url": "https://www.census.gov/constructionspending"},
        {"source_label": "Primary project disclosures", "source_url": ""},
        {"source_label": "OpenAI business scale disclosure", "source_url": "https://openai.com/index/a-business-that-scales-with-the-value-of-intelligence/"},
        {"source_label": "Alphabet AI serving economics", "source_url": "https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx"},
    ),
    "data_center": (
        {"source_label": "Pew / Data Center Map", "source_url": "https://www.pewresearch.org/short-reads/2026/04/13/most-new-data-centers-in-the-us-are-coming-to-rural-areas/"},
        {"source_label": "FracTracker Alliance", "source_url": "https://fractracker.org/2026/04/open-u-s-data-centers-tracker/"},
        {"source_label": "Deduplicated campus records", "source_url": ""},
        {"source_label": "Gigawatt Map", "source_url": "https://gigawattmap.com/"},
        {"source_label": "Primary project disclosures", "source_url": ""},
    ),
    "connectivity": (
        {"source_label": "FCC submarine cable records", "source_url": "https://www.fcc.gov/research-reports/guides/submarine-cable-landing-licenses"},
        {"source_label": "Internet Society Pulse / PeeringDB", "source_url": "https://pulse.internetsociety.org/en/ixp-tracker/country/US/"},
        {"source_label": "PeeringDB facility registry", "source_url": "https://www.peeringdb.com/advanced_search?country__in=US&reftag=fac"},
        {"source_label": "TeleGeography Submarine Cable Map", "source_url": "https://www.submarinecablemap.com/country/united-states"},
        {"source_label": "NTIA Middle Mile Program", "source_url": "https://broadbandusa.ntia.gov/news/latest-news/constructing-digital-landscape-highlights-ntias-middle-mile-program"},
    ),
    "power": (
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/electricity/data.php"},
        {"source_label": "FRED", "source_url": "https://fred.stlouisfed.org/"},
        {"source_label": "Data-center campus records", "source_url": ""},
    ),
    "grid_storage": (
        {"source_label": "Berkeley Lab Queued Up", "source_url": "https://emp.lbl.gov/queues"},
        {"source_label": "NERC Summer Reliability Assessment", "source_url": "https://www.nerc.com/pa/RAPA/ra/Reliability%20Assessments%20DL/2026-Summer-Reliability-Assessment.pdf"},
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/electricity/data.php"},
        {"source_label": "Census Construction Spending", "source_url": "https://www.census.gov/constructionspending"},
    ),
    "water": (
        {"source_label": "USGS Water Use", "source_url": "https://www.usgs.gov/mission-areas/water-resources/science/water-use-united-states"},
        {"source_label": "U.S. Drought Monitor county statistics", "source_url": "https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx"},
        {"source_label": "EPA Public Water System Service Areas", "source_url": "https://www.epa.gov/ground-water-and-drinking-water/public-water-system-service-areas"},
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/"},
        {"source_label": "Data-center campus records", "source_url": ""},
    ),
    "adoption": (
        {"source_label": "Real-Time Population Survey via FRED", "source_url": "https://fred.stlouisfed.org/release?rid=524"},
        {"source_label": "U.S. Census BTOS", "source_url": "https://www.census.gov/hfp/btos/"},
        {"source_label": "OpenAI business scale disclosure", "source_url": "https://openai.com/index/a-business-that-scales-with-the-value-of-intelligence/"},
        {"source_label": "Alphabet Q2 2026 AI and Cloud disclosure", "source_url": "https://abc.xyz/investor/events/event-details/2026/2026-Q2-Earnings-Call-2026-GgTAq7Is0z/default.aspx"},
    ),
    "workforce": (
        {"source_label": "GPTs are GPTs occupation benchmark", "source_url": "https://github.com/openai/GPTs-are-GPTs"},
        {"source_label": "BLS Current Employment Statistics", "source_url": "https://www.bls.gov/ces/"},
        {"source_label": "BLS JOLTS", "source_url": "https://www.bls.gov/jlt/"},
    ),
    "economic_impact": (
        {"source_label": "BLS Labor Productivity and Costs", "source_url": "https://www.bls.gov/productivity/"},
        {"source_label": "BLS Current Population Survey", "source_url": "https://www.bls.gov/cps/earnings.htm"},
        {"source_label": "BEA Investment Accounts", "source_url": "https://www.bea.gov/data/investment-fixed-assets"},
        {"source_label": "FRED", "source_url": "https://fred.stlouisfed.org/"},
        {"source_label": "Microsoft FY2026 Q3 AI disclosure", "source_url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast"},
        {"source_label": "OpenAI business scale disclosure", "source_url": "https://openai.com/index/a-business-that-scales-with-the-value-of-intelligence/"},
        {"source_label": "Alphabet Q2 2026 AI and Cloud disclosure", "source_url": "https://abc.xyz/investor/events/event-details/2026/2026-Q2-Earnings-Call-2026-GgTAq7Is0z/default.aspx"},
    ),
}

DOMAIN_BOUNDARIES: dict[str, tuple[str, ...]] = {
    "market": (
        "Covered-company market measures describe the configured AI equity universe.",
        "Concentration and breadth describe market participation and distribution.",
    ),
    "finance": (
        "Company funding metrics describe the covered issuers.",
        "Private-fund NAV represents remaining value; DPI represents realized cash distributions.",
        "Provider revenue measures paid demand at the reporting provider.",
    ),
    "compute": (
        "Announced projects represent investment commitments; operating capacity requires in-service evidence.",
        "Provider serving-cost disclosures apply to the reporting provider and disclosed workload scope.",
    ),
    "data_center": (
        "The project registry is a curated research universe of observed U.S. data-center campuses and projects.",
        "Published MW represents disclosed project scale; energized load requires explicit operating evidence.",
    ),
    "connectivity": (
        "Public IXP and cable records measure visible interconnection and route infrastructure.",
        "Campus-level capacity requires route, service, and deliverability evidence tied to the site.",
    ),
    "power": (
        "Planned generation represents the development pipeline; placed-in-service capacity is measured separately.",
        "Interconnection-queue maturity is measured in Grid & Storage.",
    ),
    "grid_storage": (
        "Queue capacity measures requested development; advanced-stage and historical conversion measures indicate maturity.",
        "Storage duration measures time-shifting capability alongside transmission and interconnection conditions.",
    ),
    "water": (),
    "adoption": (
        "Expected business use represents stated six-month intent.",
        "Provider subscriber counts are platform-specific reach measures.",
        "The implied OpenAI subscriber share divides separately disclosed subscriber and weekly-user floors; it is not a national adoption rate or a cohort conversion measure.",
        "The Census AI supplement covers November 17, 2025 through February 8, 2026 and is a dated structural benchmark, not a time series of adoption depth.",
    ),
    "workforce": (
        "Task-exposure estimates measure the share of occupational tasks technically exposed to AI capabilities.",
        "Tracked AI-linked channels are selected labor-market transmission channels.",
    ),
    "economic_impact": (
        "Economy-wide productivity and output measure aggregate economic performance.",
        "Provider revenue measures commercialization at the reporting provider.",
    ),
}

DOMAIN_LABELS = {
    "market": "Market",
    "finance": "Finance",
    "compute": "Compute",
    "data_center": "Data Centers",
    "connectivity": "Connectivity",
    "power": "Power",
    "grid_storage": "Grid & Storage",
    "water": "Water",
    "adoption": "Adoption",
    "workforce": "Workforce",
    "economic_impact": "Economic Outcomes",
    "macro": "AI Macro",
}


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    id: str
    label: str
    value: Any
    display: str
    context: str = ""

    def to_model_dict(self) -> dict[str, Any]:
        """Return the compact, unambiguous fact representation sent to OpenAI.

        Raw numeric values remain available to deterministic validation and
        snapshot hashing but are deliberately omitted from the model payload.
        ``display`` is the human-scale representation, so the model
        never has to infer whether a raw ratio such as ``0.681`` means 0.681 or
        68.1 percent.
        """
        payload: dict[str, Any] = {
            "id": self.id,
            "label": self.label,
            "display": self.display,
        }
        if self.context.strip():
            payload["context"] = self.context.strip()
        return payload


@dataclass(frozen=True, slots=True)
class EvidencePacket:
    domain: str
    label: str
    facts: tuple[EvidenceFact, ...]
    importance: float
    boundaries: tuple[str, ...]
    references: tuple[dict[str, str], ...]
    version: str = EVIDENCE_ARCHITECTURE_VERSION

    def to_dict(self) -> dict[str, Any]:
        """Return the complete deterministic packet used for audit/validation."""
        payload = asdict(self)
        payload["facts"] = [asdict(item) for item in self.facts]
        payload["references"] = [dict(item) for item in self.references]
        return _json_safe(payload)

    def to_model_dict(self) -> dict[str, Any]:
        """Return the smaller packet that is actually placed in the prompt."""
        sources = []
        for reference in self.references:
            label = str(reference.get("source_label") or "").strip()
            if label and label not in sources:
                sources.append(label)
        payload: dict[str, Any] = {
            "domain": self.domain,
            "label": self.label,
            "importance": round(float(self.importance), 1),
            "facts": [item.to_model_dict() for item in self.facts],
            "boundaries": list(self.boundaries),
        }
        if sources:
            payload["sources"] = sources
        return payload


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item") and callable(value.item):
        try:
            return _json_safe(value.item())
        except (TypeError, ValueError):
            pass
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            pass
    return value


def _num(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return math.nan
    return numeric if math.isfinite(numeric) else math.nan


def _fact(
    domain: str,
    key: str,
    label: str,
    value: Any,
    *,
    unit: str = "",
    scale: float = 1.0,
    digits: int = 1,
    context: str = "",
) -> EvidenceFact | None:
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return None
        return EvidenceFact(f"{domain}.{key}", label, clean, clean, context)
    numeric = _num(value)
    if not math.isfinite(numeric):
        return None
    shown = numeric * scale
    if unit == "%":
        display = f"{shown:.{digits}f}%"
    elif unit == "x":
        display = f"{shown:.{digits}f}x"
    elif unit == "$B":
        display = f"${shown:.{digits}f}B"
    elif unit == "GW":
        display = f"{shown:.{digits}f} GW"
    elif unit == "MW":
        display = f"{shown:,.{digits}f} MW"
    elif unit == "years":
        display = f"{shown:.{digits}f} years"
    elif unit == "hours":
        display = f"{shown:.{digits}f} hours"
    elif unit == "year":
        display = f"{int(shown)}" if float(shown).is_integer() else f"{shown:g}"
    elif unit == "miles":
        display = f"{shown:,.{digits}f} miles"
    elif unit:
        display = f"{shown:.{digits}f} {unit}"
    elif float(shown).is_integer():
        display = f"{int(shown):,}"
    else:
        display = f"{shown:.{digits}f}"
    return EvidenceFact(f"{domain}.{key}", label, numeric, display, context)


def _state(context: DashboardContext, domain: str) -> DomainState:
    state = (context.domain_states or {}).get(domain)
    if not isinstance(state, DomainState):
        raise ValueError(f"Evidence domain {domain} requires canonical deterministic domain state.")
    return state


def _packet(domain: str, state: DomainState, facts: Iterable[EvidenceFact | None]) -> EvidencePacket:
    clean = tuple(item for item in facts if item is not None)
    return EvidencePacket(
        domain=domain,
        label=DOMAIN_LABELS[domain],
        facts=clean,
        importance=max(0.0, min(100.0, _num(state.importance))),
        boundaries=DOMAIN_BOUNDARIES.get(domain, ()),
        references=DOMAIN_REFERENCES.get(domain, ()),
    )


def build_market_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "market")
    m = state.metrics
    return _packet("market", state, [
        _fact("market", "aei", "AI Equity Index", m.get("aei")),
        _fact("market", "pressure", "Average sector trading pressure", m.get("pressure")),
        _fact("market", "positive_breadth", "Covered companies with positive one-year returns", m.get("positive_breadth"), unit="%", scale=100),
        _fact("market", "median_return", "Median one-year return", m.get("median_return"), unit="%", scale=100),
        _fact("market", "equal_weight_return", "Equal-weight one-year return", m.get("equal_weight_return"), unit="%", scale=100),
        _fact("market", "top_10_share", "Top-ten share of covered market value", m.get("top_10_share"), unit="%", scale=100),
        _fact("market", "effective_firms", "Effective firm count", m.get("effective_firms")),
        _fact("market", "strong_sector_count", "Sectors above the strong-equity threshold", m.get("strong_sector_count")),
        _fact("market", "crowded_sector_count", "Sectors above the high-pressure threshold", m.get("crowded_sector_count")),
    ])


def build_finance_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "finance")
    m = state.metrics
    return _packet("finance", state, [
        _fact("finance", "borrower_strain", "Borrower strain", m.get("borrower_strain")),
        _fact("finance", "lender_strain", "Lender strain", m.get("lender_strain")),
        _fact("finance", "internal_funding_coverage", "Operating cash flow coverage of current CapEx", m.get("internal_funding_coverage"), unit="x", digits=2),
        _fact("finance", "cash_reserve_coverage_years", "Cash reserves relative to current CapEx", m.get("cash_reserve_coverage_years"), unit="years", digits=2),
        _fact("finance", "forward_commitment_load", "Forward commitments relative to current CapEx", m.get("forward_commitment_load"), unit="x", digits=2),
        _fact("finance", "debt_financing_pulse", "Definition-matched debt financing pulse", m.get("debt_financing_pulse")),
        _fact("finance", "nfci", "Chicago Fed NFCI", m.get("nfci"), digits=2),
        _fact("finance", "nfci_change", "Three-month change in NFCI", m.get("nfci_change"), digits=2),
        _fact("finance", "bond_distress", "Corporate bond market distress", m.get("bond_distress"), digits=2),
        _fact("finance", "private_capital_dpi", "Mature technology-fund DPI", m.get("private_capital_dpi"), unit="x", digits=2),
        _fact("finance", "private_capital_rvpi", "Mature technology-fund RVPI", m.get("private_capital_rvpi"), unit="x", digits=2),
        _fact("finance", "private_capital_tvpi", "Mature technology-fund TVPI", m.get("private_capital_tvpi"), unit="x", digits=2),
        _fact("finance", "private_capital_realized_share", "Share of private-fund value already realized", m.get("private_capital_realized_share"), unit="%", scale=100),
        _fact("finance", "private_capital_mature_funds", "Public-LP mature fund records", m.get("private_capital_mature_funds")),
        _fact("finance", "microsoft_ai_arr_b", "Microsoft reported AI annual revenue run rate", m.get("microsoft_ai_arr_b"), unit="$B"),
        _fact("finance", "microsoft_ai_arr_growth_pct", "Microsoft AI annual revenue run-rate growth", m.get("microsoft_ai_arr_growth_pct"), unit="%"),
        _fact("finance", "openai_arr_b", "OpenAI reported annualized revenue run rate", m.get("openai_arr_b"), unit="$B"),
        _fact("finance", "alphabet_cloud_backlog_b", "Alphabet reported Cloud backlog", m.get("alphabet_cloud_backlog_b"), unit="$B"),
    ])


def build_compute_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "compute")
    m = state.metrics
    return _packet("compute", state, [
        _fact("compute", "computer_output_growth", "Computer and peripheral equipment output growth", m.get("computer_output_growth"), unit="%", scale=100),
        _fact("compute", "semiconductor_output_growth", "Semiconductor and electronic component output growth", m.get("semiconductor_output_growth"), unit="%", scale=100),
        _fact("compute", "computer_utilization", "Computer and peripheral equipment capacity utilization", m.get("computer_utilization"), unit="%"),
        _fact("compute", "semiconductor_utilization", "Semiconductor capacity utilization", m.get("semiconductor_utilization"), unit="%"),
        _fact("compute", "information_processing_investment_growth", "Information-processing investment growth", m.get("information_processing_investment_growth"), unit="%", scale=100),
        _fact("compute", "project_capex_b", "Expected investment in announced U.S. compute-manufacturing projects", m.get("project_capex_b"), unit="$B"),
        _fact("compute", "project_sites", "Announced U.S. compute-manufacturing project sites", m.get("project_sites")),
        _fact("compute", "critical_layers_covered", "Tracked AI supply-chain layers with announced domestic projects", m.get("critical_layers_covered")),
        _fact("compute", "critical_layers_total", "Tracked critical AI supply-chain layers", m.get("critical_layers_total")),
        _fact("compute", "core_ai_sites", "Core-AI manufacturing project sites", m.get("core_ai_sites")),
        _fact("compute", "core_ai_capex_b", "Expected investment in core-AI manufacturing projects", m.get("core_ai_capex_b"), unit="$B"),
        _fact("compute", "available_compute_gw", "OpenAI reported available compute", m.get("available_compute_gw"), unit="GW"),
        _fact("compute", "serving_cost_reduction_pct", "Alphabet reported serving unit-cost reduction", m.get("serving_cost_reduction_pct"), unit="%"),
    ])


def build_data_center_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "data_center")
    m = state.metrics
    return _packet("data_center", state, [
        _fact("data_center", "operating_sites", "Operating sites in available project records", m.get("operating_sites")),
        _fact("data_center", "development_sites", "Sites in development in available project records", m.get("development_sites")),
        _fact("data_center", "development_to_operating", "Development sites relative to operating sites", m.get("development_to_operating"), unit="x", digits=2),
        _fact("data_center", "tracked_pipeline_sites", "Tracked active pipeline sites", m.get("tracked_pipeline_sites")),
        _fact("data_center", "pipeline_capacity_gw", "Published capacity associated with development sites", m.get("pipeline_capacity_gw"), unit="GW"),
        _fact("data_center", "operating_capacity_gw", "Published capacity associated with operating sites", m.get("operating_capacity_gw"), unit="GW"),
        _fact("data_center", "published_capacity_coverage", "Share of active campus records with published capacity", m.get("published_capacity_coverage"), unit="%", scale=100),
    ])


def build_connectivity_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "connectivity")
    m = state.metrics
    return _packet("connectivity", state, [
        _fact("connectivity", "active_ixps", "Active U.S. internet exchange points", m.get("active_ixps")),
        _fact("connectivity", "combined_ixp_members", "Combined reported IXP members", m.get("combined_ixp_members")),
        _fact("connectivity", "international_submarine_cable_systems", "U.S. international submarine cable systems", m.get("international_submarine_cable_systems")),
        _fact("connectivity", "us_connected_cable_catalog_entries", "U.S.-connected cable catalog entries", m.get("us_connected_cable_catalog_entries")),
        _fact("connectivity", "future_or_current_year_cable_entries", "Future or current-year cable entries", m.get("future_or_current_year_cable_entries")),
        _fact("connectivity", "interconnection_facilities_or_floor", "PeeringDB interconnection facilities or coverage floor", m.get("interconnection_facilities_or_floor")),
        _fact("connectivity", "middle_mile_new_fiber_miles", "Federally supported middle-mile new fiber", m.get("middle_mile_new_fiber_miles"), unit="miles", digits=0),
        _fact("connectivity", "high_capacity_low_public_connectivity_states", "States with data-center development but limited visible public interconnection depth", m.get("high_capacity_low_public_connectivity_states")),
        _fact("connectivity", "campuses_screened", "Data-center campuses screened for connectivity context", m.get("campuses_screened")),
        _fact("connectivity", "population_centers_with_ixp", "Population centers over 300k with an IXP", m.get("population_centers_with_ixp")),
        _fact("connectivity", "population_centers_total", "Population centers over 300k assessed", m.get("population_centers_total")),
    ])


def build_power_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "power")
    m = state.metrics
    return _packet("power", state, [
        _fact("power", "demand_growth", "Total retail electricity demand growth", m.get("demand_growth"), unit="%"),
        _fact("power", "commercial_growth", "Commercial electricity demand growth", m.get("commercial_growth"), unit="%"),
        _fact("power", "planned_net_gw", "Net planned generation additions through the pipeline horizon", m.get("planned_net_gw"), unit="GW"),
        _fact("power", "retail_price_growth", "Retail electricity price growth", m.get("retail_price_growth"), unit="%"),
        _fact("power", "large_load_capacity_mw", "Published capacity associated with large-load campus records", m.get("large_load_capacity_mw"), unit="MW", digits=0),
        _fact("power", "pipeline_end_year", "Planned-generation pipeline end year", m.get("pipeline_end_year"), unit="year"),
    ])


def build_grid_storage_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "grid_storage")
    m = state.metrics
    return _packet("grid_storage", state, [
        _fact("grid_storage", "queue_gw", "Active interconnection queue", m.get("queue_gw"), unit="GW", digits=0),
        _fact("grid_storage", "advanced_share", "Queue share in executed-agreement or construction stages", m.get("advanced_share"), unit="%"),
        _fact("grid_storage", "storage_queue_gw", "Storage capacity in the active queue", m.get("storage_queue_gw"), unit="GW"),
        _fact("grid_storage", "historical_operational_pct", "2000–2020 queue cohort that reached operation", m.get("historical_operational_pct"), unit="%", digits=0),
        _fact("grid_storage", "historical_withdrawn_pct", "2000–2020 queue cohort withdrawn", m.get("historical_withdrawn_pct"), unit="%", digits=0),
        _fact("grid_storage", "median_request_to_cod_years", "Median request-to-commercial-operation time for 2025 completions", m.get("median_request_to_cod_years"), unit="years"),
        _fact("grid_storage", "draft_or_executed_ia_gw", "Queue capacity with draft or executed interconnection agreements", m.get("draft_or_executed_ia_gw"), unit="GW"),
        _fact("grid_storage", "lowest_extreme_margin_pct", "Lowest NERC extreme-conditions reserve margin", m.get("lowest_extreme_margin_pct"), unit="%"),
        _fact("grid_storage", "lowest_extreme_margin_area", "Area with the lowest NERC extreme-conditions margin", m.get("lowest_extreme_margin_area")),
        _fact("grid_storage", "negative_extreme_margin_areas", "NERC assessment areas with negative extreme-conditions margins", m.get("negative_extreme_margin_areas")),
        _fact("grid_storage", "operating_storage_weighted_duration_hours", "Weighted average duration of operating storage", m.get("operating_storage_weighted_duration_hours"), unit="hours"),
        _fact("grid_storage", "operating_storage_four_hour_plus_share_pct", "Operating storage capacity with at least four hours duration", m.get("operating_storage_four_hour_plus_share_pct"), unit="%"),
        _fact("grid_storage", "electric_power_construction_growth", "Electric-power construction growth", m.get("electric_power_construction_growth"), unit="%", scale=100),
    ])


def build_water_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "water")
    m = state.metrics
    return _packet("water", state, [
        _fact("water", "campuses", "Data-center campuses", m.get("campuses")),
        _fact("water", "campuses_with_county_drought_data", "Campuses with current county drought data", m.get("campuses_with_county_drought_data")),
        _fact("water", "county_drought_coverage_share_pct", "Share of campuses with current county drought data", m.get("county_drought_coverage_share_pct"), unit="%", scale=100),
        _fact("water", "campuses_in_counties_with_d2_area", "Campuses in counties with some D2-or-worse drought area", m.get("campuses_in_counties_with_d2_area")),
        _fact("water", "campuses_in_counties_with_d2_share_pct", "Share of campuses with county drought data in counties with some D2-or-worse drought area", m.get("campuses_in_counties_with_d2_share_pct"), unit="%", scale=100),
        _fact("water", "campuses_in_counties_with_25pct_d2_area", "Campuses in counties with at least 25% D2-or-worse drought area", m.get("campuses_in_counties_with_25pct_d2_area")),
        _fact("water", "campuses_in_counties_with_25pct_d2_share_pct", "Share of campuses with county drought data in counties with at least 25% D2-or-worse drought area", m.get("campuses_in_counties_with_25pct_d2_share_pct"), unit="%", scale=100),
        _fact("water", "highest_county_d2_location", "Mapped county with the highest D2-or-worse drought-area share", m.get("highest_county_d2_location")),
        _fact("water", "highest_county_d2_area_pct", "Highest mapped county D2-or-worse drought-area share", m.get("highest_county_d2_area_pct"), unit="%"),
        _fact("water", "direct_evidence_campuses", "Campuses with direct water evidence", m.get("direct_evidence_campuses")),
        _fact("water", "direct_evidence_share_pct", "Campuses with direct water evidence", m.get("direct_evidence_share_pct"), unit="%"),
        _fact("water", "quantified_withdrawal_campuses", "Campuses with quantified withdrawal records", m.get("quantified_withdrawal_campuses")),
        _fact("water", "quantified_consumption_campuses", "Campuses with quantified consumption records", m.get("quantified_consumption_campuses")),
        _fact("water", "quantified_use_campuses", "Campuses with quantified withdrawal or consumption records", m.get("quantified_use_campuses")),
        _fact("water", "pws_query_resolved_campuses", "Campus points with a resolved EPA service-area query", m.get("pws_query_resolved_campuses")),
        _fact("water", "pws_query_resolution_share_pct", "Campus points with a resolved EPA service-area query", m.get("pws_query_resolution_share_pct"), unit="%", scale=100),
        _fact("water", "pws_service_area_overlap_campuses", "Campus points intersecting at least one EPA community-water service-area boundary", m.get("pws_service_area_overlap_campuses")),
        _fact("water", "pws_service_area_overlap_share_pct", "Campus points intersecting at least one EPA community-water service-area boundary", m.get("pws_service_area_overlap_share_pct"), unit="%", scale=100),
        _fact("water", "pws_provenance_classified_share_pct", "Share of EPA-overlap campuses with boundary provenance classified", m.get("pws_provenance_classified_share_pct"), unit="%", scale=100),
        _fact("water", "unclassified_pws_overlap_campuses", "Campus points with EPA service-area overlap and unclassified boundary provenance", m.get("unclassified_pws_overlap_campuses")),
        _fact("water", "authoritative_pws_overlap_campuses", "Campus points intersecting an EPA state/system-sourced community-water boundary", m.get("authoritative_pws_overlap_campuses")),
        _fact("water", "modeled_pws_overlap_campuses", "Campus points intersecting an EPA-modeled community-water boundary", m.get("modeled_pws_overlap_campuses")),
        _fact("water", "ambiguous_pws_overlap_campuses", "Campus points intersecting more than one EPA community-water boundary", m.get("ambiguous_pws_overlap_campuses")),
        _fact("water", "published_capacity_coverage_share_pct", "Campuses with usable published capacity", m.get("published_capacity_coverage_share_pct"), unit="%", scale=100),
        _fact("water", "published_capacity_in_counties_with_d2_gw", "Published data-center campus capacity in counties with D2-or-worse drought", m.get("published_capacity_in_counties_with_d2_gw"), unit="GW"),
        _fact("water", "published_capacity_in_counties_with_25pct_d2_gw", "Published data-center campus capacity in counties with at least 25% D2-or-worse drought", m.get("published_capacity_in_counties_with_25pct_d2_gw"), unit="GW"),
        _fact("water", "irrigation_withdrawal_bgal_day_2020", "U.S. crop-irrigation withdrawals in 2020", m.get("irrigation_withdrawal_bgal_day_2020"), unit="Bgal/day"),
        _fact("water", "thermoelectric_withdrawal_bgal_day_2020", "U.S. thermoelectric-power withdrawals in 2020", m.get("thermoelectric_withdrawal_bgal_day_2020"), unit="Bgal/day"),
        _fact("water", "public_supply_withdrawal_bgal_day_2020", "U.S. public-supply withdrawals in 2020", m.get("public_supply_withdrawal_bgal_day_2020"), unit="Bgal/day"),
        _fact("water", "thermoelectric_reported_withdrawal_bgal_day_2024", "Reported thermoelectric withdrawals in 2024", m.get("thermoelectric_reported_withdrawal_bgal_day_2024"), unit="Bgal/day"),
        _fact("water", "thermoelectric_reported_consumption_bgal_day_2024", "Reported thermoelectric consumption in 2024", m.get("thermoelectric_reported_consumption_bgal_day_2024"), unit="Bgal/day"),
    ])


def build_adoption_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "adoption")
    m = state.metrics
    return _packet("adoption", state, [
        _fact("adoption", "current_business_use_pct", "Businesses reporting current AI use", m.get("current_business_use_pct"), unit="%"),
        _fact("adoption", "expected_business_use_pct", "Businesses expecting AI use within six months", m.get("expected_business_use_pct"), unit="%"),
        _fact("adoption", "expected_adoption_gap_ppts", "Expected-minus-current business AI-use gap", m.get("expected_adoption_gap_ppts"), unit="percentage points"),
        _fact("adoption", "annual_change_ppts", "Annual change in current business AI use", m.get("annual_change_ppts"), unit="percentage points"),
        _fact("adoption", "consumer_overall_pct", "Adults age 18–64 reporting some generative-AI use", m.get("consumer_overall_pct"), unit="%"),
        _fact("adoption", "consumer_personal_pct", "Adults reporting personal generative-AI use", m.get("consumer_personal_pct"), unit="%"),
        _fact("adoption", "consumer_work_pct", "Adults reporting generative-AI use for work", m.get("consumer_work_pct"), unit="%"),
        _fact("adoption", "consumer_active_pct", "Adults reporting generative-AI use in the prior week", m.get("consumer_active_pct"), unit="%"),
        _fact("adoption", "consumer_daily_pct", "Adults reporting daily generative-AI use", m.get("consumer_daily_pct"), unit="%"),
        _fact("adoption", "consumer_change_ppts", "Change in overall consumer use across the retained series", m.get("consumer_change_ppts"), unit="percentage points"),
        _fact("adoption", "sector_coverage", "Share of BTOS sectors with a current-use reading", m.get("sector_coverage"), unit="%", scale=100),
        _fact("adoption", "leading_sector", "BTOS sector with the highest current AI-use reading", m.get("leading_sector")),
        _fact("adoption", "leading_sector_use_pct", "Highest BTOS sector current AI-use reading", m.get("leading_sector_use_pct"), unit="%"),
        _fact("adoption", "worker_ai_use_pct", "Businesses reporting employee AI use for work tasks", m.get("worker_ai_use_pct"), unit="%"),
        _fact("adoption", "worker_genai_use_pct", "Businesses reporting employee Generative AI use for work tasks", m.get("worker_genai_use_pct"), unit="%"),
        _fact("adoption", "function_le3_share_pct", "Functional AI adopters using three or fewer business functions", m.get("function_le3_share_pct"), unit="%"),
        _fact("adoption", "task_le3_share_pct", "Businesses reporting employee Generative AI use across three or fewer task categories", m.get("task_le3_share_pct"), unit="%"),
        _fact("adoption", "top_function", "Most common six-month AI business-function deployment among functional adopters", m.get("top_function")),
        _fact("adoption", "top_function_use_pct", "Functional adopters reporting AI deployment in the leading business function", m.get("top_function_use_pct"), unit="%"),
        _fact("adoption", "top_task", "Most common employee Generative AI task among businesses reporting employee Generative AI use", m.get("top_task")),
        _fact("adoption", "top_task_use_pct", "Businesses reporting employee Generative AI use in the leading task category", m.get("top_task_use_pct"), unit="%"),
        _fact("adoption", "organizational_change_share_pct", "AI-using businesses reporting an organizational adjustment", m.get("organizational_change_share_pct"), unit="%"),
        _fact("adoption", "task_augmentation_pct", "AI-using businesses reporting task augmentation", m.get("task_augmentation_pct"), unit="%"),
        _fact("adoption", "task_substitution_pct", "AI-using businesses reporting task substitution", m.get("task_substitution_pct"), unit="%"),
        _fact("adoption", "task_creation_pct", "AI-using businesses reporting new task creation", m.get("task_creation_pct"), unit="%"),
        _fact("adoption", "employment_decrease_pct", "Businesses reporting an AI-related employment decrease", m.get("employment_decrease_pct"), unit="%"),
        _fact("adoption", "employment_unchanged_pct", "AI-using businesses reporting no AI-related employment change", m.get("employment_unchanged_pct"), unit="%"),
        _fact("adoption", "chatgpt_subscribers_m", "OpenAI reported ChatGPT subscribers", m.get("chatgpt_subscribers_m"), unit="million"),
        _fact("adoption", "implied_subscriber_share_pct", "Implied OpenAI subscriber share of reported ChatGPT weekly users", m.get("implied_subscriber_share_pct"), unit="%"),
        _fact("adoption", "openai_paying_business_users_m", "OpenAI reported paying business users", m.get("openai_paying_business_users_m"), unit="million"),
        _fact("adoption", "gemini_enterprise_paid_seats_m", "Alphabet reported paid Gemini enterprise seats", m.get("gemini_enterprise_paid_seats_m"), unit="million"),
    ])


def build_workforce_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "workforce")
    m = state.metrics
    return _packet("workforce", state, [
        _fact("workforce", "employment_breadth", "Tracked AI-linked labor channels with positive employment growth", m.get("employment_breadth")),
        _fact("workforce", "real_earnings_breadth", "Tracked AI-linked labor channels with positive real-earnings growth", m.get("real_earnings_breadth")),
        _fact("workforce", "strongest_channel", "Tracked channel with the strongest employment growth", m.get("strongest_channel")),
        _fact("workforce", "strongest_channel_growth", "Strongest tracked-channel employment growth", m.get("strongest_channel_growth"), unit="%"),
        _fact("workforce", "weakest_channel", "Tracked channel with the weakest employment growth", m.get("weakest_channel")),
        _fact("workforce", "weakest_channel_growth", "Weakest tracked-channel employment growth", m.get("weakest_channel_growth"), unit="%"),
        _fact("workforce", "max_layoff_rate", "Highest layoff rate among tracked channels", m.get("max_layoff_rate"), unit="%"),
        _fact("workforce", "max_openings_rate", "Highest openings rate among tracked channels", m.get("max_openings_rate"), unit="%"),
        _fact("workforce", "occupation_exposure_count", "Occupations in the static task-exposure benchmark", m.get("occupation_exposure_count")),
        _fact("workforce", "median_llm_software_exposure_pct", "Median software-adjusted LLM task exposure in the benchmark", m.get("median_llm_software_exposure_pct"), unit="%"),
        _fact("workforce", "high_exposure_occupation_share_pct", "Benchmark occupations with at least 50% software-adjusted task exposure", m.get("high_exposure_occupation_share_pct"), unit="%"),
    ])


def build_economic_impact_evidence(context: DashboardContext) -> EvidencePacket:
    state = _state(context, "economic_impact")
    m = state.metrics
    return _packet("economic_impact", state, [
        _fact("economic_impact", "productivity_growth", "Nonfarm-business productivity growth", m.get("productivity_growth"), unit="%"),
        _fact("economic_impact", "real_output_growth", "Nonfarm-business real output growth", m.get("real_output_growth"), unit="%"),
        _fact("economic_impact", "real_compensation_growth", "Real hourly compensation growth", m.get("real_compensation_growth"), unit="%"),
        _fact("economic_impact", "unit_labor_cost_growth", "Unit labor cost growth", m.get("unit_labor_cost_growth"), unit="%"),
        _fact("economic_impact", "information_investment_growth", "Information-processing investment growth", m.get("information_investment_growth"), unit="%"),
        _fact("economic_impact", "productivity_since_2020", "Productivity change since 2020", m.get("productivity_since_2020"), unit="%"),
        _fact("economic_impact", "real_compensation_since_2020", "Real hourly compensation change since 2020", m.get("real_compensation_since_2020"), unit="%"),
        _fact("economic_impact", "productivity_real_comp_gap", "Productivity minus real-compensation change since 2020", m.get("productivity_real_comp_gap"), unit="percentage points"),
        _fact("economic_impact", "labor_share_since_2020", "Labor-share index change since 2020", m.get("labor_share_since_2020"), unit="%"),
        _fact("economic_impact", "median_real_earnings_growth", "Median real weekly earnings growth", m.get("median_real_earnings_growth"), unit="%"),
        _fact("economic_impact", "group_growth_spread_ppts", "Cross-group real-earnings growth spread", m.get("group_growth_spread_ppts"), unit="percentage points"),
        _fact("economic_impact", "microsoft_ai_arr_b", "Microsoft reported AI annual revenue run rate", m.get("microsoft_ai_arr_b"), unit="$B"),
        _fact("economic_impact", "openai_arr_b", "OpenAI reported annualized revenue run rate", m.get("openai_arr_b"), unit="$B"),
        _fact("economic_impact", "alphabet_cloud_growth_pct", "Alphabet Cloud revenue growth", m.get("alphabet_cloud_growth_pct"), unit="%"),
        _fact("economic_impact", "openai_enterprise_share_pct", "OpenAI enterprise share of revenue", m.get("openai_enterprise_share_pct"), unit="%"),
    ])


def build_evidence_packets(context: DashboardContext) -> dict[str, EvidencePacket]:
    builders = {
        "market": build_market_evidence,
        "finance": build_finance_evidence,
        "compute": build_compute_evidence,
        "data_center": build_data_center_evidence,
        "connectivity": build_connectivity_evidence,
        "power": build_power_evidence,
        "grid_storage": build_grid_storage_evidence,
        "water": build_water_evidence,
        "adoption": build_adoption_evidence,
        "workforce": build_workforce_evidence,
        "economic_impact": build_economic_impact_evidence,
    }
    return {domain: builders[domain](context) for domain in DOMAIN_ORDER}


def model_evidence_packets(packets: dict[str, EvidencePacket | dict]) -> dict[str, dict[str, Any]]:
    """Project full evidence packets into the compact model-facing contract.

    Dictionary packets are accepted for tests and tooling; they are normalized
    to the same field set so no raw ``value``, source URL, empty ``context``, or
    packet version leaks into a paid prompt.
    """
    output: dict[str, dict[str, Any]] = {}
    for domain in DOMAIN_ORDER:
        packet = packets.get(domain)
        if packet is None:
            continue
        if isinstance(packet, EvidencePacket):
            output[domain] = packet.to_model_dict()
            continue
        facts = []
        for fact in packet.get("facts", []) or []:
            if not isinstance(fact, dict):
                continue
            item = {
                "id": str(fact.get("id") or ""),
                "label": str(fact.get("label") or ""),
                "display": str(fact.get("display") or ""),
            }
            context = str(fact.get("context") or "").strip()
            if context:
                item["context"] = context
            facts.append(item)
        sources = []
        for reference in packet.get("references", []) or []:
            if not isinstance(reference, dict):
                continue
            label = str(reference.get("source_label") or reference.get("source_name") or "").strip()
            if label and label not in sources:
                sources.append(label)
        item = {
            "domain": str(packet.get("domain") or domain),
            "label": str(packet.get("label") or DOMAIN_LABELS.get(domain, domain.replace("_", " ").title())),
            "importance": round(float(packet.get("importance") or 0.0), 1),
            "facts": facts,
            "boundaries": [str(value) for value in packet.get("boundaries", []) or []],
        }
        if sources:
            item["sources"] = sources
        output[domain] = item
    return output


def evidence_snapshot_id(packets: dict[str, EvidencePacket | dict]) -> str:
    reference = {
        domain: packet.to_dict() if isinstance(packet, EvidencePacket) else _json_safe(packet)
        for domain, packet in sorted(packets.items())
    }
    raw = json.dumps(reference, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def evidence_fact_index(packets: dict[str, EvidencePacket | dict]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for packet in packets.values():
        payload = packet.to_dict() if isinstance(packet, EvidencePacket) else packet
        for fact in payload.get("facts", []) or []:
            if isinstance(fact, dict) and fact.get("id"):
                index[str(fact["id"])] = dict(fact)
    return index
