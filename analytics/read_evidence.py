"""Deterministic evidence packets for the AI Macro commentary layer.

This module owns facts, boundaries, importance heuristics, and source lineage.
It deliberately does not write Reader prose.  OpenAI receives these packets as
its exclusive factual record; generated commentary is audited against the fact
identifiers before it is published with those diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
from typing import Any, Iterable

import numpy as np
import pandas as pd

from analytics.dashboard_context import DashboardContext
from analytics.energy_pulse import demand_snapshot, development_snapshot, large_load_snapshot, price_snapshot
from analytics.financial_conditions import nfci_snapshot
from analytics.grid_deliverability import queue_outcome_snapshot, reserve_margin_profile, storage_duration_profile
from analytics.market_ledger import build_market_ledger
from analytics.private_capital import build_private_capital_realization
from analytics.water_competition import current_top_withdrawal_profile
from analytics.water_local import local_water_constraint_summary

EVIDENCE_ARCHITECTURE_VERSION = "1.2.0"
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
        "Covered-company market measures are not the entire U.S. equity market.",
        "Concentration and breadth describe participation; they do not establish causality.",
    ),
    "finance": (
        "Company funding metrics describe the covered issuers, not all AI investment.",
        "Private-fund NAV is not realized cash and should not be described as a realized return.",
        "Provider revenue demonstrates paid demand but not economy-wide return on AI investment.",
    ),
    "compute": (
        "Announced projects are commitments, not current operating capacity.",
        "Provider serving-cost disclosures must not be generalized to the whole market.",
    ),
    "data_center": (
        "The project registry is not a national census of the U.S. data-center fleet.",
        "Published MW describes disclosed project scale, not energized load.",
    ),
    "connectivity": (
        "Public IXP and cable records do not capture every private route or bilateral connection.",
        "National route totals do not establish usable capacity at a specific campus.",
    ),
    "power": (
        "Planned generation is not equivalent to capacity placed in service.",
        "Power ownership excludes interconnection-queue maturity, which belongs to Grid & Storage.",
    ),
    "grid_storage": (
        "Queue capacity measures developer interest, not near-term supply.",
        "Storage duration can address short peaks but does not remove transmission or interconnection constraints.",
    ),
    "water": (),
    "adoption": (
        "Expected business use is stated intent and must not be described as deployed use.",
        "Provider subscriber counts are not a national paid-adoption rate.",
    ),
    "workforce": (
        "Task-exposure estimates describe work AI could affect; they do not measure jobs lost or automated.",
        "Tracked AI-linked channels are not the entire labor market.",
    ),
    "economic_impact": (
        "Economy-wide productivity and output measures do not identify AI as the cause.",
        "Provider revenue does not establish economy-wide return on AI investment.",
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
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return value


def _num(value) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else np.nan


def _commercial_metric(payload: dict | None, provider: str, metric: str) -> float:
    ledger = (payload or {}).get("ledger")
    if not isinstance(ledger, pd.DataFrame) or ledger.empty or not {"Provider", "Metric", "Value"}.issubset(ledger.columns):
        return np.nan
    rows = ledger.loc[
        ledger["Provider"].astype(str).eq(str(provider))
        & ledger["Metric"].astype(str).eq(str(metric))
    ]
    if rows.empty:
        return np.nan
    return _num(rows.iloc[-1].get("Value"))


def _fact(domain: str, key: str, label: str, value: Any, *, unit: str = "", scale: float = 1.0, digits: int = 1, context: str = "") -> EvidenceFact | None:
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return None
        return EvidenceFact(f"{domain}.{key}", label, clean, clean, context)
    numeric = _num(value)
    if pd.isna(numeric):
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


def _packet(domain: str, facts: Iterable[EvidenceFact | None], *, importance: float) -> EvidencePacket:
    clean = tuple(item for item in facts if item is not None)
    return EvidencePacket(
        domain=domain,
        label=DOMAIN_LABELS[domain],
        facts=clean,
        importance=float(np.clip(importance, 0.0, 100.0)),
        boundaries=DOMAIN_BOUNDARIES.get(domain, ()),
        references=DOMAIN_REFERENCES.get(domain, ()),
    )


def _active_campuses(infrastructure_data: dict) -> pd.DataFrame:
    campuses = (infrastructure_data or {}).get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        return pd.DataFrame()
    if "Campus ID" not in campuses.columns or campuses["Campus ID"].duplicated().any():
        raise ValueError("Data-center evidence requires the Universal Data Center Registry")
    frame = campuses.copy()
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    active = {
        "operational", "under construction", "approved / permitted / under construction",
        "announced", "planned", "proposed", "expanding",
    }
    return frame.loc[status.isin(active)].copy()


def build_market_evidence(context: DashboardContext) -> EvidencePacket:
    ledger = build_market_ledger(context.sector_data)
    metrics = ledger.get("metrics", {}) or {}
    macro_df = (context.dashboard_data or {}).get("macro_df")
    aei = _num((context.regime_metrics or {}).get("AI Equity Index"))
    pressure = _num((context.regime_metrics or {}).get("Avg Sector Pressure"))
    breadth = _num(metrics.get("positive_breadth"))
    median_return = _num(metrics.get("median_return"))
    equal_return = _num(metrics.get("equal_weight_return"))
    top10 = _num(metrics.get("top_10_share"))
    effective = _num(metrics.get("effective_firms"))
    strong_sectors = crowded_sectors = 0
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
    return _packet("market", [
        _fact("market", "aei", "AI Equity Index", aei),
        _fact("market", "pressure", "Average sector trading pressure", pressure),
        _fact("market", "positive_breadth", "Covered companies with positive one-year returns", breadth, unit="%", scale=100),
        _fact("market", "median_return", "Median one-year return", median_return, unit="%", scale=100),
        _fact("market", "equal_weight_return", "Equal-weight one-year return", equal_return, unit="%", scale=100),
        _fact("market", "top_10_share", "Top-ten share of covered market value", top10, unit="%", scale=100),
        _fact("market", "effective_firms", "Effective firm count", effective),
        _fact("market", "strong_sector_count", "Sectors above the strong-equity threshold", strong_sectors),
        _fact("market", "crowded_sector_count", "Sectors above the high-pressure threshold", crowded_sectors),
    ], importance=importance)


def build_finance_evidence(context: DashboardContext) -> EvidencePacket:
    regime_metrics = context.regime_metrics or {}
    funding = (regime_metrics.get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}
    borrower = _num(regime_metrics.get("Borrower Strain")); lender = _num(regime_metrics.get("Lender Strain"))
    internal = _num(funding.get("internal_funding_coverage")); cash_runway = _num(funding.get("cash_reserve_coverage_years"))
    commitments = _num(funding.get("forward_commitment_load")); debt_pulse = _num(funding.get("debt_financing_pulse"))
    nfci = nfci_snapshot(context.fred_data or {}, context.nfci_history)
    nfci_value = _num(nfci.get("value")); nfci_change = _num(nfci.get("three_month_change"))
    cmdi = _num((((context.debt_markets_data or {}).get("series", {}) or {}).get("Corporate Bond Market Distress", {}) or {}).get("value"))
    private_metrics = build_private_capital_realization().get("metrics", {}) or {}
    dpi = _num(private_metrics.get("dpi")); rvpi = _num(private_metrics.get("rvpi")); tvpi = _num(private_metrics.get("tvpi")); realized = _num(private_metrics.get("realized_share"))
    funds = int(private_metrics.get("fund_count", 0) or 0)
    commercial = context.commercialization_data
    ms_arr = _commercial_metric(commercial, "Microsoft", "Annual revenue run rate")
    ms_growth = _commercial_metric(commercial, "Microsoft", "Annual revenue run-rate growth")
    openai_arr = _commercial_metric(commercial, "OpenAI", "Annualized revenue run rate")
    alphabet_backlog = _commercial_metric(commercial, "Alphabet", "Backlog")
    realization_imbalance = abs(0.5 - realized) * 70 if pd.notna(realized) else 0
    importance = max(abs(borrower) if pd.notna(borrower) else 0, abs(lender) if pd.notna(lender) else 0, max(0, (1-internal)*45) if pd.notna(internal) else 0, min(75, max(0, commitments-1)*25) if pd.notna(commitments) else 0, realization_imbalance)
    return _packet("finance", [
        _fact("finance", "borrower_strain", "Borrower strain", borrower),
        _fact("finance", "lender_strain", "Lender strain", lender),
        _fact("finance", "internal_funding_coverage", "Operating cash flow coverage of current CapEx", internal, unit="x", digits=2),
        _fact("finance", "cash_reserve_coverage_years", "Cash reserves relative to current CapEx", cash_runway, unit="years", digits=2),
        _fact("finance", "forward_commitment_load", "Forward commitments relative to current CapEx", commitments, unit="x", digits=2),
        _fact("finance", "debt_financing_pulse", "Definition-matched debt financing pulse", debt_pulse),
        _fact("finance", "nfci", "Chicago Fed NFCI", nfci_value, digits=2),
        _fact("finance", "nfci_change", "Three-month change in NFCI", nfci_change, digits=2),
        _fact("finance", "bond_distress", "Corporate bond market distress", cmdi, digits=2),
        _fact("finance", "private_capital_dpi", "Mature technology-fund DPI", dpi, unit="x", digits=2),
        _fact("finance", "private_capital_rvpi", "Mature technology-fund RVPI", rvpi, unit="x", digits=2),
        _fact("finance", "private_capital_tvpi", "Mature technology-fund TVPI", tvpi, unit="x", digits=2),
        _fact("finance", "private_capital_realized_share", "Share of private-fund value already realized", realized, unit="%", scale=100),
        _fact("finance", "private_capital_mature_funds", "Public-LP mature fund records", funds),
        _fact("finance", "microsoft_ai_arr_b", "Microsoft reported AI annual revenue run rate", ms_arr, unit="$B"),
        _fact("finance", "microsoft_ai_arr_growth_pct", "Microsoft AI annual revenue run-rate growth", ms_growth, unit="%"),
        _fact("finance", "openai_arr_b", "OpenAI reported annualized revenue run rate", openai_arr, unit="$B"),
        _fact("finance", "alphabet_cloud_backlog_b", "Alphabet reported Cloud backlog", alphabet_backlog, unit="$B"),
    ], importance=importance)


def build_compute_evidence(context: DashboardContext) -> EvidencePacket:
    compute = (context.infrastructure_data or {}).get("compute_manufacturing", {}) or {}; series = compute.get("series", {}) or {}
    def item(name): return series.get(name, {}) or {}
    computer_growth = _num(item("Computer and Peripheral Equipment Output").get("yoy_growth"))
    semiconductor_growth = _num(item("Semiconductor and Electronic Component Output").get("yoy_growth"))
    computer_util = _num(item("Computer and Peripheral Equipment Capacity Utilization").get("value"))
    semiconductor_util = _num(item("Semiconductor and Electronic Component Capacity Utilization").get("value"))
    investment_growth = _num(item("Info Processing Investment Level").get("yoy_growth"))
    projects = compute.get("project_summary", {}) or {}; capex = _num(projects.get("expected_capex_usd_b")); sites = int(projects.get("projects",0) or 0)
    critical = compute.get("critical_supply_chain", {}) or {}; covered = int(critical.get("covered_layers",0) or 0); total = int(critical.get("critical_layers",0) or 0); core_sites=int(critical.get("core_ai_sites",0) or 0); core_capex=_num(critical.get("core_ai_capex_usd_b"))
    available_compute = _commercial_metric(context.commercialization_data, "OpenAI", "Available compute")
    serving_cost = _commercial_metric(context.commercialization_data, "Alphabet", "Serving unit-cost reduction")
    growths=[v for v in (computer_growth, semiconductor_growth, investment_growth) if pd.notna(v)]; strongest=max(growths) if growths else np.nan
    importance=max(abs(strongest*100) if pd.notna(strongest) else 0, min(capex/5,35) if pd.notna(capex) else 0)
    return _packet("compute", [
        _fact("compute","computer_output_growth","Computer and peripheral equipment output growth",computer_growth,unit="%",scale=100),
        _fact("compute","semiconductor_output_growth","Semiconductor and electronic component output growth",semiconductor_growth,unit="%",scale=100),
        _fact("compute","computer_utilization","Computer and peripheral equipment capacity utilization",computer_util,unit="%"),
        _fact("compute","semiconductor_utilization","Semiconductor capacity utilization",semiconductor_util,unit="%"),
        _fact("compute","information_processing_investment_growth","Information-processing investment growth",investment_growth,unit="%",scale=100),
        _fact("compute","project_capex_b","Expected investment in announced U.S. compute-manufacturing projects",capex,unit="$B"),
        _fact("compute","project_sites","Announced U.S. compute-manufacturing project sites",sites),
        _fact("compute","critical_layers_covered","Tracked AI supply-chain layers with announced domestic projects",covered),
        _fact("compute","critical_layers_total","Tracked critical AI supply-chain layers",total),
        _fact("compute","core_ai_sites","Core-AI manufacturing project sites",core_sites),
        _fact("compute","core_ai_capex_b","Expected investment in core-AI manufacturing projects",core_capex,unit="$B"),
        _fact("compute","available_compute_gw","OpenAI reported available compute",available_compute,unit="GW"),
        _fact("compute","serving_cost_reduction_pct","Alphabet reported serving unit-cost reduction",serving_cost,unit="%"),
    ], importance=importance)


def build_data_center_evidence(context: DashboardContext) -> EvidencePacket:
    infrastructure=context.infrastructure_data or {}; inventory=infrastructure.get("data_center_inventory") or {}; broad=inventory.get("broad_summary",{}) or {}; tracker=inventory.get("open_tracker_summary",{}) or {}; campuses=_active_campuses(infrastructure)
    status=campuses.get("Status",pd.Series("",index=campuses.index)).fillna("").astype(str).str.casefold() if not campuses.empty else pd.Series(dtype=str)
    operating_mask=status.eq("operational"); development_mask=status.isin({"under construction","approved / permitted / under construction","announced","planned","proposed","expanding"})
    registry_operating=int(operating_mask.sum()) if len(status) else 0; registry_development=int(development_mask.sum()) if len(status) else 0
    operating=int(broad.get("operating",0) or 0) or registry_operating; development=int(broad.get("development",0) or 0) or registry_development
    ratio=_num(broad.get("development_to_operating")); ratio=development/operating if pd.isna(ratio) and operating else ratio
    reference=pd.to_numeric(campuses.get("Planned Data Center Capacity MW"),errors="coerce").combine_first(pd.to_numeric(campuses.get("Published Capacity Estimate MW"),errors="coerce")).where(lambda x:x>0) if not campuses.empty else pd.Series(dtype=float)
    coverage=float(reference.notna().mean()) if len(campuses) else np.nan
    registry_pipeline=_num(reference.loc[development_mask].sum(min_count=1)/1000) if len(reference) else np.nan; registry_operating_capacity=_num(reference.loc[operating_mask].sum(min_count=1)/1000) if len(reference) else np.nan
    tracked=int(tracker.get("active_pipeline",0) or 0) or registry_development
    pipeline_capacity=_num(tracker.get("active_pipeline_published_mw"))/1000; pipeline_capacity=registry_pipeline if pd.isna(pipeline_capacity) else pipeline_capacity
    operating_capacity=_num(tracker.get("operating_published_mw"))/1000; operating_capacity=registry_operating_capacity if pd.isna(operating_capacity) else operating_capacity
    importance=min(90,(ratio*45 if pd.notna(ratio) else 0)+(min(pipeline_capacity/8,35) if pd.notna(pipeline_capacity) else 0))
    return _packet("data_center", [
        _fact("data_center","operating_sites","Operating sites in available project records",operating),
        _fact("data_center","development_sites","Sites in development in available project records",development),
        _fact("data_center","development_to_operating","Development sites relative to operating sites",ratio,unit="x",digits=2),
        _fact("data_center","tracked_pipeline_sites","Tracked active pipeline sites",tracked),
        _fact("data_center","pipeline_capacity_gw","Published capacity associated with development sites",pipeline_capacity,unit="GW"),
        _fact("data_center","operating_capacity_gw","Published capacity associated with operating sites",operating_capacity,unit="GW"),
        _fact("data_center","published_capacity_coverage","Share of active campus records with published capacity",coverage,unit="%",scale=100),
    ], importance=importance)


def build_connectivity_evidence(context: DashboardContext) -> EvidencePacket:
    payload=context.connectivity_data or (context.infrastructure_data or {}).get("connectivity",{}) or {}; national=payload.get("national_summary",{}) or {}; coverage=payload.get("coverage",{}) or {}
    vals={
        "active_ixps":_num(national.get("Active IXPs")), "combined_ixp_members":_num(national.get("Combined Reported Members")),
        "international_submarine_cable_systems":_num(national.get("U.S. International Submarine Cable Systems")), "us_connected_cable_catalog_entries":_num(national.get("U.S.-Connected Cable Catalog Entries")),
        "future_or_current_year_cable_entries":_num(national.get("Future / Current-Year Cable Entries")), "selected_landing_markets":_num(national.get("Selected Landing Markets")),
        "peeringdb_facilities":_num(national.get("PeeringDB Facilities")), "peeringdb_facility_floor":_num(national.get("PeeringDB Facility Coverage Floor")),
        "middle_mile_new_fiber_miles":_num(national.get("Middle-Mile New Fiber Miles")), "middle_mile_award_records":_num(national.get("Middle-Mile Award Records")),
        "mismatch_states":_num(coverage.get("mismatch_states")), "campuses_screened":_num(coverage.get("campuses_screened")),
        "population_centers_with_ixp":_num(national.get("Population Centers With IXP")), "population_centers_total":_num(national.get("Population Centers Over 300k")),
    }
    importance=min(94,(vals["mismatch_states"]*7 if pd.notna(vals["mismatch_states"]) else 0)+(vals["future_or_current_year_cable_entries"]*1.5 if pd.notna(vals["future_or_current_year_cable_entries"]) else 0)+(vals["middle_mile_new_fiber_miles"]/1000 if pd.notna(vals["middle_mile_new_fiber_miles"]) else 0))
    facility=vals["peeringdb_facilities"] if pd.notna(vals["peeringdb_facilities"]) and vals["peeringdb_facilities"]>0 else vals["peeringdb_facility_floor"]
    return _packet("connectivity", [
        _fact("connectivity","active_ixps","Active U.S. internet exchange points",vals["active_ixps"]),
        _fact("connectivity","combined_ixp_members","Combined reported IXP members",vals["combined_ixp_members"]),
        _fact("connectivity","international_submarine_cable_systems","U.S. international submarine cable systems",vals["international_submarine_cable_systems"]),
        _fact("connectivity","us_connected_cable_catalog_entries","U.S.-connected cable catalog entries",vals["us_connected_cable_catalog_entries"]),
        _fact("connectivity","future_or_current_year_cable_entries","Future or current-year cable entries",vals["future_or_current_year_cable_entries"]),
        _fact("connectivity","interconnection_facilities_or_floor","PeeringDB interconnection facilities or coverage floor",facility),
        _fact("connectivity","middle_mile_new_fiber_miles","Federally supported middle-mile new fiber",vals["middle_mile_new_fiber_miles"],unit="miles",digits=0),
        _fact("connectivity","high_capacity_low_public_connectivity_states","States with data-center development but limited visible public interconnection depth",vals["mismatch_states"]),
        _fact("connectivity","campuses_screened","Data-center campuses screened for connectivity context",vals["campuses_screened"]),
        _fact("connectivity","population_centers_with_ixp","Population centers over 300k with an IXP",vals["population_centers_with_ixp"]),
        _fact("connectivity","population_centers_total","Population centers over 300k assessed",vals["population_centers_total"]),
    ], importance=importance)


def build_power_evidence(context: DashboardContext) -> EvidencePacket:
    energy=context.energy_data or {}; retail=energy.get("retail_history"); pipeline=energy.get("generator_pipeline"); campuses=_active_campuses(context.infrastructure_data or {})
    demand=demand_snapshot(retail if isinstance(retail,pd.DataFrame) else pd.DataFrame()); large=large_load_snapshot(campuses)
    development=development_snapshot(pipeline if isinstance(pipeline,pd.DataFrame) else pd.DataFrame(),pd.DataFrame(),pd.DataFrame())
    prices=price_snapshot(retail if isinstance(retail,pd.DataFrame) else pd.DataFrame(),((energy.get("series",{}) or {}).get("Natural Gas Price",{}) or {}))
    demand_growth=_num(demand.get("total_growth")); commercial_growth=_num(demand.get("commercial_growth")); planned_net=_num(development.get("planned_net_gw")); price_growth=_num(prices.get("total_growth")); load_mw=_num(large.get("published_total_mw"))
    importance=max(abs(demand_growth)*8 if pd.notna(demand_growth) else 0,abs(price_growth)*5 if pd.notna(price_growth) else 0,abs(planned_net) if pd.notna(planned_net) else 0)
    return _packet("power", [
        _fact("power","demand_growth","Total retail electricity demand growth",demand_growth,unit="%"),
        _fact("power","commercial_growth","Commercial electricity demand growth",commercial_growth,unit="%"),
        _fact("power","planned_net_gw","Net planned generation additions through the pipeline horizon",planned_net,unit="GW"),
        _fact("power","retail_price_growth","Retail electricity price growth",price_growth,unit="%"),
        _fact("power","large_load_capacity_mw","Published capacity associated with large-load campus records",load_mw,unit="MW",digits=0),
        _fact("power","pipeline_end_year","Planned-generation pipeline end year",development.get("end_year"),unit="year"),
    ], importance=importance)


def build_grid_storage_evidence(context: DashboardContext) -> EvidencePacket:
    energy=context.energy_data or {}; queue=energy.get("interconnection_queue"); summary=energy.get("interconnection_queue_summary"); pipeline=energy.get("generator_pipeline")
    development=development_snapshot(pipeline if isinstance(pipeline,pd.DataFrame) else pd.DataFrame(),queue if isinstance(queue,pd.DataFrame) else pd.DataFrame(),summary if isinstance(summary,pd.DataFrame) else pd.DataFrame())
    active=development.get("active_queue"); storage_gw=np.nan
    if isinstance(active,pd.DataFrame) and not active.empty: storage_gw=pd.to_numeric(active.get("Storage MW"),errors="coerce").sum(min_count=1)/1000
    outcomes=queue_outcome_snapshot(energy.get("queue_outcomes_summary")); reserves=reserve_margin_profile(energy.get("reliability_reserve_margins")); _,duration=storage_duration_profile(energy.get("operating_generators"))
    queue_gw=_num(development.get("headline_queue_gw")); advanced=_num(development.get("advanced_share")); operational=_num(outcomes.get("Historical Operational Share Percent")); withdrawn=_num(outcomes.get("Historical Withdrawn Share Percent")); median_years=_num(outcomes.get("Median Request to COD Years")); agreement=_num(outcomes.get("Draft or Executed IA GW")); weighted=_num(duration.get("weighted_duration_hours")); four_hour=_num(duration.get("four_hour_plus_share")); power_growth=_num(((((context.infrastructure_data or {}).get("series",{}) or {}).get("Electric Power Construction",{}) or {}).get("yoy_growth")))
    extreme=pd.to_numeric(reserves.get("Extreme Conditions Margin Percent"),errors="coerce") if not reserves.empty else pd.Series(dtype=float); lowest=reserves.loc[extreme.idxmin()] if not extreme.dropna().empty else pd.Series(dtype=object); lowest_area=str(lowest.get("Assessment Area") or ""); lowest_margin=_num(lowest.get("Extreme Conditions Margin Percent")); negative=int(extreme.lt(0).sum()) if not extreme.empty else 0; under5=int(extreme.lt(5).sum()) if not extreme.empty else 0
    importance=max(50-advanced if pd.notna(advanced) else 0,min(queue_gw/25,70) if pd.notna(queue_gw) else 0,75-operational if pd.notna(operational) else 0,abs(min(lowest_margin,0))*8+60 if pd.notna(lowest_margin) and lowest_margin<0 else 0)
    return _packet("grid_storage", [
        _fact("grid_storage","queue_gw","Active interconnection queue",queue_gw,unit="GW",digits=0),
        _fact("grid_storage","advanced_share","Queue share in executed-agreement or construction stages",advanced,unit="%"),
        _fact("grid_storage","storage_queue_gw","Storage capacity in the active queue",storage_gw,unit="GW"),
        _fact("grid_storage","historical_operational_pct","2000–2020 queue cohort that reached operation",operational,unit="%",digits=0),
        _fact("grid_storage","historical_withdrawn_pct","2000–2020 queue cohort withdrawn",withdrawn,unit="%",digits=0),
        _fact("grid_storage","median_request_to_cod_years","Median request-to-commercial-operation time for 2025 completions",median_years,unit="years"),
        _fact("grid_storage","draft_or_executed_ia_gw","Queue capacity with draft or executed interconnection agreements",agreement,unit="GW"),
        _fact("grid_storage","lowest_extreme_margin_pct","Lowest NERC extreme-conditions reserve margin",lowest_margin,unit="%"),
        _fact("grid_storage","lowest_extreme_margin_area","Area with the lowest NERC extreme-conditions margin",lowest_area),
        _fact("grid_storage","negative_extreme_margin_areas","NERC assessment areas with negative extreme-conditions margins",negative),
        _fact("grid_storage","operating_storage_weighted_duration_hours","Weighted average duration of operating storage",weighted,unit="hours"),
        _fact("grid_storage","operating_storage_four_hour_plus_share_pct","Operating storage capacity with at least four hours duration",four_hour,unit="%"),
        _fact("grid_storage","electric_power_construction_growth","Electric-power construction growth",power_growth,unit="%",scale=100),
    ], importance=importance)


def build_water_evidence(context: DashboardContext) -> EvidencePacket:
    water=context.water_data or {}; summary=water.get("summary",{}) or {}; eia=summary.get("eia_2024_thermoelectric",{}) or {}; campus_frame=water.get("campus_context")
    profile=current_top_withdrawal_profile(water.get("usgs_2020_top_withdrawals")); values=profile.set_index("Use Category")["Withdrawal Bgal/day"].to_dict() if not profile.empty else {}
    local=local_water_constraint_summary(campus_frame if isinstance(campus_frame,pd.DataFrame) else pd.DataFrame())
    campuses=int(local.get("campuses",0) or 0); county_resolved=int(local.get("campuses_with_county_drought_data",0) or 0); county_share=_num(local.get("county_drought_coverage_share"))
    d2_campuses=int(local.get("campuses_in_counties_with_d2",0) or 0); d2_share=_num(local.get("campuses_in_counties_with_d2_share")); material_campuses=int(local.get("campuses_in_counties_with_25pct_d2",0) or 0); material_share=_num(local.get("campuses_in_counties_with_25pct_d2_share")); highest_location=str(local.get("highest_county_d2_location") or ""); highest_d2=_num(local.get("highest_county_d2_area_pct"))
    direct=int(local.get("direct_water_evidence",0) or 0); quantified_withdrawal=int(local.get("quantified_withdrawal",0) or 0); quantified_consumption=int(local.get("quantified_consumption",0) or 0); quantified=quantified_withdrawal+quantified_consumption; direct_share=direct/campuses*100 if campuses else np.nan
    pws_resolved=int(local.get("service_area_query_resolved",0) or 0); pws_resolution_share=_num(local.get("service_area_query_resolution_share")); pws_overlap=int(local.get("service_area_overlap",0) or 0); pws_share=_num(local.get("service_area_overlap_share")); authoritative=int(local.get("authoritative_service_area_overlap",0) or 0); modeled=int(local.get("modeled_service_area_overlap",0) or 0); unclassified=int(local.get("unclassified_service_area_overlap",0) or 0); provenance_share=_num(local.get("service_area_provenance_classified_share")); ambiguous=int(local.get("ambiguous_service_area_overlap",0) or 0)
    use_provenance_split=bool(pws_overlap>0 and pd.notna(provenance_share) and provenance_share>=0.8)
    capacity_coverage=_num(local.get("published_capacity_coverage_share")); d2_capacity=_num(local.get("published_capacity_in_counties_with_d2_gw")); material_capacity=_num(local.get("published_capacity_in_counties_with_25pct_d2_gw")); use_capacity=bool(pd.notna(capacity_coverage) and capacity_coverage>=0.25)
    irrigation=_num(values.get("Crop irrigation")); thermo=_num(values.get("Thermoelectric power")); public=_num(values.get("Public supply")); withdrawal=_num(eia.get("withdrawal_bgal_day")); consumption=_num(eia.get("consumption_bgal_day"))
    exposure_score=(35*(material_share if pd.notna(material_share) else 0))+(15*(d2_share if pd.notna(d2_share) else 0)); resolution_factor=min(1.0,(county_share/0.8)) if pd.notna(county_share) and county_share>0 else 0.0; disclosure_gap=(1-(direct/campuses)) if campuses else 0.0; importance=min(85,35+(exposure_score*resolution_factor)+(10*disclosure_gap))
    return _packet("water", [
        _fact("water","campuses","Data-center campuses",campuses),
        _fact("water","campuses_with_county_drought_data","Campuses with current county drought data",county_resolved),
        _fact("water","county_drought_coverage_share_pct","Share of campuses with current county drought data",county_share,unit="%",scale=100),
        _fact("water","campuses_in_counties_with_d2_area","Campuses in counties with some D2-or-worse drought area",d2_campuses),
        _fact("water","campuses_in_counties_with_d2_share_pct","Share of campuses with county drought data in counties with some D2-or-worse drought area",d2_share,unit="%",scale=100),
        _fact("water","campuses_in_counties_with_25pct_d2_area","Campuses in counties with at least 25% D2-or-worse drought area",material_campuses),
        _fact("water","campuses_in_counties_with_25pct_d2_share_pct","Share of campuses with county drought data in counties with at least 25% D2-or-worse drought area",material_share,unit="%",scale=100),
        _fact("water","highest_county_d2_location","Mapped county with the highest D2-or-worse drought-area share",highest_location),
        _fact("water","highest_county_d2_area_pct","Highest mapped county D2-or-worse drought-area share",highest_d2,unit="%"),
        _fact("water","direct_evidence_campuses","Campuses with direct water evidence",direct),
        _fact("water","direct_evidence_share_pct","Campuses with direct water evidence",direct_share,unit="%"),
        _fact("water","quantified_withdrawal_campuses","Campuses with quantified withdrawal records",quantified_withdrawal),
        _fact("water","quantified_consumption_campuses","Campuses with quantified consumption records",quantified_consumption),
        _fact("water","quantified_use_campuses","Campuses with quantified withdrawal or consumption records",quantified),
        _fact("water","pws_query_resolved_campuses","Campus points with a resolved EPA service-area query",pws_resolved),
        _fact("water","pws_query_resolution_share_pct","Campus points with a resolved EPA service-area query",pws_resolution_share,unit="%",scale=100),
        _fact("water","pws_service_area_overlap_campuses","Campus points intersecting at least one EPA community-water service-area boundary",pws_overlap),
        _fact("water","pws_service_area_overlap_share_pct","Campus points intersecting at least one EPA community-water service-area boundary",pws_share,unit="%",scale=100),
        _fact("water","pws_provenance_classified_share_pct","Share of EPA-overlap campuses with boundary provenance classified",provenance_share,unit="%",scale=100),
        _fact("water","unclassified_pws_overlap_campuses","Campus points with EPA service-area overlap and unclassified boundary provenance",unclassified),
        _fact("water","authoritative_pws_overlap_campuses","Campus points intersecting an EPA state/system-sourced community-water boundary",authoritative if use_provenance_split else np.nan),
        _fact("water","modeled_pws_overlap_campuses","Campus points intersecting an EPA-modeled community-water boundary",modeled if use_provenance_split else np.nan),
        _fact("water","ambiguous_pws_overlap_campuses","Campus points intersecting more than one EPA community-water boundary",ambiguous),
        _fact("water","published_capacity_coverage_share_pct","Campuses with usable published capacity",capacity_coverage if use_capacity else np.nan,unit="%",scale=100),
        _fact("water","published_capacity_in_counties_with_d2_gw","Published data-center campus capacity in counties with D2-or-worse drought",d2_capacity if use_capacity else np.nan,unit="GW"),
        _fact("water","published_capacity_in_counties_with_25pct_d2_gw","Published data-center campus capacity in counties with at least 25% D2-or-worse drought",material_capacity if use_capacity else np.nan,unit="GW"),
        _fact("water","irrigation_withdrawal_bgal_day_2020","U.S. crop-irrigation withdrawals in 2020",irrigation,unit="Bgal/day"),
        _fact("water","thermoelectric_withdrawal_bgal_day_2020","U.S. thermoelectric-power withdrawals in 2020",thermo,unit="Bgal/day"),
        _fact("water","public_supply_withdrawal_bgal_day_2020","U.S. public-supply withdrawals in 2020",public,unit="Bgal/day"),
        _fact("water","thermoelectric_reported_withdrawal_bgal_day_2024","Reported thermoelectric withdrawals in 2024",withdrawal,unit="Bgal/day"),
        _fact("water","thermoelectric_reported_consumption_bgal_day_2024","Reported thermoelectric consumption in 2024",consumption,unit="Bgal/day"),
    ], importance=importance)

def build_adoption_evidence(context: DashboardContext) -> EvidencePacket:
    a=context.adoption_data or {}; current=_num(a.get("current_use")); expected=_num(a.get("expected_use")); gap=_num(a.get("expected_adoption_gap")); annual=_num(a.get("annual_change")); consumer_overall=_num((a.get("consumer_overall",{}) or {}).get("value")); consumer_personal=_num((a.get("consumer_personal",{}) or {}).get("value")); consumer_work=_num((a.get("consumer_work",{}) or {}).get("value")); active=_num((a.get("consumer_active",{}) or {}).get("value")); daily=_num((a.get("consumer_daily",{}) or {}).get("value")); commercial=context.commercialization_data; subscribers=_commercial_metric(commercial,"OpenAI","Consumer subscribers"); subscriber_share=_commercial_metric(commercial,"OpenAI","Implied subscriber share"); business_users=_commercial_metric(commercial,"OpenAI","Paying business users"); gemini=_commercial_metric(commercial,"Alphabet","Paid seats")
    history=a.get("consumer_history"); change=np.nan
    if isinstance(history,pd.DataFrame) and not history.empty:
        rows=history.loc[history.get("Series",pd.Series("",index=history.index)).astype(str).eq("Overall use")].copy(); rows["Date"]=pd.to_datetime(rows.get("Date"),errors="coerce",format="mixed"); rows["Value"]=pd.to_numeric(rows.get("Value"),errors="coerce"); rows=rows.dropna(subset=["Date","Value"]).sort_values("Date",kind="stable"); change=float(rows.iloc[-1]["Value"]-rows.iloc[0]["Value"]) if len(rows)>=2 else np.nan
    sectors=a.get("sector_snapshot"); breadth=np.nan; top_sector=""; top_value=np.nan
    if isinstance(sectors,pd.DataFrame) and not sectors.empty:
        sv=pd.to_numeric(sectors.get("Current AI Use"),errors="coerce"); breadth=float(sv.notna().mean());
        if sv.notna().any(): idx=sv.idxmax(); top_sector=str(sectors.loc[idx].get("Sector", "")); top_value=float(sv.loc[idx])
    importance=max(abs(annual)*8 if pd.notna(annual) else 0,gap*4 if pd.notna(gap) else 0,abs(change)*5 if pd.notna(change) else 0)
    return _packet("adoption", [
        _fact("adoption","current_business_use_pct","Businesses reporting current AI use",current,unit="%"),
        _fact("adoption","expected_business_use_pct","Businesses expecting AI use within six months",expected,unit="%"),
        _fact("adoption","expected_adoption_gap_ppts","Expected-minus-current business AI-use gap",gap,unit="percentage points"),
        _fact("adoption","annual_change_ppts","Annual change in current business AI use",annual,unit="percentage points"),
        _fact("adoption","consumer_overall_pct","Adults age 18–64 reporting some generative-AI use",consumer_overall,unit="%"),
        _fact("adoption","consumer_personal_pct","Adults reporting personal generative-AI use",consumer_personal,unit="%"),
        _fact("adoption","consumer_work_pct","Adults reporting generative-AI use for work",consumer_work,unit="%"),
        _fact("adoption","consumer_active_pct","Adults reporting generative-AI use in the prior week",active,unit="%"),
        _fact("adoption","consumer_daily_pct","Adults reporting daily generative-AI use",daily,unit="%"),
        _fact("adoption","consumer_change_ppts","Change in overall consumer use across the retained series",change,unit="percentage points"),
        _fact("adoption","sector_coverage","Share of BTOS sectors with a current-use reading",breadth,unit="%",scale=100),
        _fact("adoption","leading_sector","BTOS sector with the highest current AI-use reading",top_sector),
        _fact("adoption","leading_sector_use_pct","Highest BTOS sector current AI-use reading",top_value,unit="%"),
        _fact("adoption","chatgpt_subscribers_m","OpenAI reported ChatGPT subscribers",subscribers,unit="million"),
        _fact("adoption","implied_subscriber_share_pct","Implied subscriber share of working-age U.S. adults",subscriber_share,unit="%"),
        _fact("adoption","openai_paying_business_users_m","OpenAI reported paying business users",business_users,unit="million"),
        _fact("adoption","gemini_enterprise_paid_seats_m","Alphabet reported paid Gemini enterprise seats",gemini,unit="million"),
    ], importance=importance)


def build_workforce_evidence(context: DashboardContext) -> EvidencePacket:
    w=context.workforce_data or {}; matrix=w.get("transmission_matrix")
    if not isinstance(matrix,pd.DataFrame) or matrix.empty: return _packet("workforce",[],importance=0)
    exposure=w.get("exposure_summary",{}) or {}; occupations=_num(exposure.get("occupations")); median_exposure=_num(exposure.get("median_llm_software_exposure")); high_share=_num(exposure.get("share_at_least_50_pct")); employment=pd.to_numeric(matrix.get("Employment YoY"),errors="coerce"); earnings=pd.to_numeric(matrix.get("Real earnings YoY"),errors="coerce"); layoffs=pd.to_numeric(matrix.get("Layoffs rate"),errors="coerce"); openings=pd.to_numeric(matrix.get("Openings rate"),errors="coerce"); positive_jobs=int((employment>0).sum()); positive_real=int((earnings>0).sum()); strongest_idx=employment.idxmax() if employment.notna().any() else None; weakest_idx=employment.idxmin() if employment.notna().any() else None; strongest=matrix.loc[strongest_idx].to_dict() if strongest_idx is not None else {}; weakest=matrix.loc[weakest_idx].to_dict() if weakest_idx is not None else {}; strongest_name=str(strongest.get("Channel") or ""); weakest_name=str(weakest.get("Channel") or ""); strongest_growth=_num(strongest.get("Employment YoY")); weakest_growth=_num(weakest.get("Employment YoY")); importance=max([abs(float(v)) for v in employment.dropna().tolist()+earnings.dropna().tolist()]+[0])*10
    return _packet("workforce", [
        _fact("workforce","employment_breadth","Tracked AI-linked labor channels with positive employment growth",positive_jobs),
        _fact("workforce","real_earnings_breadth","Tracked AI-linked labor channels with positive real-earnings growth",positive_real),
        _fact("workforce","strongest_channel","Tracked channel with the strongest employment growth",strongest_name),
        _fact("workforce","strongest_channel_growth","Strongest tracked-channel employment growth",strongest_growth,unit="%"),
        _fact("workforce","weakest_channel","Tracked channel with the weakest employment growth",weakest_name),
        _fact("workforce","weakest_channel_growth","Weakest tracked-channel employment growth",weakest_growth,unit="%"),
        _fact("workforce","max_layoff_rate","Highest layoff rate among tracked channels",float(layoffs.max()) if layoffs.notna().any() else np.nan,unit="%"),
        _fact("workforce","max_openings_rate","Highest openings rate among tracked channels",float(openings.max()) if openings.notna().any() else np.nan,unit="%"),
        _fact("workforce","occupation_exposure_count","Occupations in the static task-exposure benchmark",occupations),
        _fact("workforce","median_llm_software_exposure_pct","Median software-adjusted LLM task exposure in the benchmark",median_exposure,unit="%"),
        _fact("workforce","high_exposure_occupation_share_pct","Benchmark occupations with at least 50% software-adjusted task exposure",high_share,unit="%"),
    ], importance=importance)


def build_economic_impact_evidence(context: DashboardContext) -> EvidencePacket:
    e=context.economic_impact_data or {}; capture=e.get("capture_summary",{}) or {}; productivity=_num((e.get("nonfarm_productivity",{}) or {}).get("value")); output=_num((e.get("nonfarm_output",{}) or {}).get("value")); unit_cost=_num((e.get("nonfarm_unit_labor_cost",{}) or {}).get("value")); investment=_num((e.get("information_investment",{}) or {}).get("yoy")); real_comp=_num((capture.get("real_compensation",{}) or {}).get("yoy")); real_comp_since=_num((capture.get("real_compensation",{}) or {}).get("since_2020")); productivity_since=_num((capture.get("productivity",{}) or {}).get("since_2020")); labor_share_since=_num((capture.get("labor_share",{}) or {}).get("since_2020")); median_earnings=_num((capture.get("median_real_earnings",{}) or {}).get("YoY")); gap=_num(capture.get("productivity_real_comp_gap")); spread=_num(capture.get("group_growth_spread_ppts")); commercial=context.commercialization_data; ms=_commercial_metric(commercial,"Microsoft","Annual revenue run rate"); oa=_commercial_metric(commercial,"OpenAI","Annualized revenue run rate"); alphabet=_commercial_metric(commercial,"Alphabet","Revenue growth"); enterprise=_commercial_metric(commercial,"OpenAI","Enterprise share of revenue"); importance=max(abs(gap)*5 if pd.notna(gap) else 0,abs(labor_share_since)*4 if pd.notna(labor_share_since) else 0,abs(productivity)*8 if pd.notna(productivity) else 0)
    return _packet("economic_impact", [
        _fact("economic_impact","productivity_growth","Nonfarm-business productivity growth",productivity,unit="%"),
        _fact("economic_impact","real_output_growth","Nonfarm-business real output growth",output,unit="%"),
        _fact("economic_impact","real_compensation_growth","Real hourly compensation growth",real_comp,unit="%"),
        _fact("economic_impact","unit_labor_cost_growth","Unit labor cost growth",unit_cost,unit="%"),
        _fact("economic_impact","information_investment_growth","Information-processing investment growth",investment,unit="%"),
        _fact("economic_impact","productivity_since_2020","Productivity change since 2020",productivity_since,unit="%"),
        _fact("economic_impact","real_compensation_since_2020","Real hourly compensation change since 2020",real_comp_since,unit="%"),
        _fact("economic_impact","productivity_real_comp_gap","Productivity minus real-compensation change since 2020",gap,unit="percentage points"),
        _fact("economic_impact","labor_share_since_2020","Labor-share index change since 2020",labor_share_since,unit="%"),
        _fact("economic_impact","median_real_earnings_growth","Median real weekly earnings growth",median_earnings,unit="%"),
        _fact("economic_impact","group_growth_spread_ppts","Cross-group real-earnings growth spread",spread,unit="percentage points"),
        _fact("economic_impact","microsoft_ai_arr_b","Microsoft reported AI annual revenue run rate",ms,unit="$B"),
        _fact("economic_impact","openai_arr_b","OpenAI reported annualized revenue run rate",oa,unit="$B"),
        _fact("economic_impact","alphabet_cloud_growth_pct","Alphabet Cloud revenue growth",alphabet,unit="%"),
        _fact("economic_impact","openai_enterprise_share_pct","OpenAI enterprise share of revenue",enterprise,unit="%"),
    ], importance=importance)


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
