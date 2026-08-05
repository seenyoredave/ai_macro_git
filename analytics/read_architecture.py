"""Deterministic platform-wide narrative architecture.

Each domain emits a compact, structured read.  The AI Macro read synthesizes
only the most material cross-domain signals rather than concatenating domain
copy.  All language is generated from explicit thresholds and retained facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from analytics.energy_pulse import (
    build_power_read,
    demand_snapshot,
    development_snapshot,
    large_load_snapshot,
    price_snapshot,
)
from analytics.financial_conditions import nfci_snapshot
from analytics.market_ledger import build_market_ledger
from analytics.private_capital import build_private_capital_realization
from analytics.infrastructure_cycle import current_buildout_momentum, supporting_balance
from analytics.water_competition import current_top_withdrawal_profile

READ_ARCHITECTURE_VERSION = "6.5.1"
DOMAIN_ORDER = (
    "market",
    "finance",
    "compute",
    "data_center",
    "power",
    "grid_storage",
    "water",
    "adaptation",
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
        {"source_label": "ILPA Performance Template", "source_url": "https://ilpa.org/industry-guidance/templates-standards-model-documents/ilpa-templates-hub/ilpa-performance-template/"},
    ),
    "compute": (
        {"source_label": "Federal Reserve G.17", "source_url": "https://www.federalreserve.gov/releases/g17/current/"},
        {"source_label": "BEA Fixed Assets", "source_url": "https://www.bea.gov/data/investment-fixed-assets"},
        {"source_label": "Census Construction Spending", "source_url": "https://www.census.gov/constructionspending"},
        {"source_label": "Primary project disclosures", "source_url": ""},
    ),
    "data_center": (
        {"source_label": "Pew / Data Center Map", "source_url": "https://www.pewresearch.org/short-reads/2026/04/13/most-new-data-centers-in-the-us-are-coming-to-rural-areas/"},
        {"source_label": "FracTracker Alliance", "source_url": "https://fractracker.org/2026/04/open-u-s-data-centers-tracker/"},
        {"source_label": "Canonical facility registry", "source_url": ""},
        {"source_label": "Gigawatt Map", "source_url": "https://gigawattmap.com/"},
        {"source_label": "Primary project disclosures", "source_url": ""},
    ),
    "power": (
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/electricity/data.php"},
        {"source_label": "FRED", "source_url": "https://fred.stlouisfed.org/"},
        {"source_label": "Facility registry", "source_url": ""},
    ),
    "grid_storage": (
        {"source_label": "Berkeley Lab Queued Up", "source_url": "https://emp.lbl.gov/queues"},
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/electricity/data.php"},
        {"source_label": "Census Construction Spending", "source_url": "https://www.census.gov/constructionspending"},
    ),
    "water": (
        {"source_label": "USGS Water Use", "source_url": "https://www.usgs.gov/mission-areas/water-resources/science/water-use-united-states"},
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/"},
        {"source_label": "Facility registry", "source_url": ""},
    ),
    "workforce": (
        {"source_label": "BLS Current Employment Statistics", "source_url": "https://www.bls.gov/ces/"},
        {"source_label": "BLS JOLTS", "source_url": "https://www.bls.gov/jlt/"},
    ),
    "economic_impact": (
        {"source_label": "BLS Labor Productivity and Costs", "source_url": "https://www.bls.gov/productivity/"},
        {"source_label": "BEA Investment Accounts", "source_url": "https://www.bea.gov/data/investment-fixed-assets"},
        {"source_label": "FRED", "source_url": "https://fred.stlouisfed.org/"},
    ),
    "adaptation": (
        {"source_label": "U.S. Census BTOS", "source_url": "https://www.census.gov/hfp/btos/"},
    ),
}


def _num(value) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else np.nan


def _pct(value, digits=1, *, signed=False) -> str:
    numeric = _num(value)
    if pd.isna(numeric):
        return "n/a"
    sign = "+" if signed and numeric > 0 else ""
    return f"{sign}{numeric:.{digits}f}%"


def _value(value, digits=1, suffix="", *, signed=False) -> str:
    numeric = _num(value)
    if pd.isna(numeric):
        return "n/a"
    sign = "+" if signed and numeric > 0 else ""
    return f"{sign}{numeric:.{digits}f}{suffix}"


def _sentence(*parts: str) -> str:
    clean = [str(part).strip().rstrip(".") for part in parts if str(part).strip()]
    return ". ".join(clean) + ("." if clean else "")


def _confidence(valid: int, expected: int) -> str:
    ratio = valid / expected if expected else 0.0
    return "high" if ratio >= 0.80 else "moderate" if ratio >= 0.50 else "limited"


def _read(
    domain: str,
    headline: str,
    summary: str,
    watchpoint: str,
    *,
    confidence: str,
    importance: float,
    signals: dict[str, Any],
    highlights: list[dict[str, Any]],
    references: list[dict[str, Any]] | None = None,
) -> dict:
    return {
        "domain": domain,
        "label": domain.replace("_", " ").title(),
        "headline": headline,
        "summary": summary,
        "watchpoint": watchpoint,
        "confidence": confidence,
        "importance": float(np.clip(importance, 0.0, 100.0)),
        "signals": signals,
        "highlights": highlights,
        "references": [dict(item) for item in (references if references is not None else DOMAIN_REFERENCES.get(domain, ()))],
        "version": READ_ARCHITECTURE_VERSION,
    }


def _attach_current_context(read: dict, context: dict | None) -> dict:
    """Attach one or two sourced developments without turning a read into a feed."""
    payload = dict(read or {})
    context_payload = context or {}
    events = [dict(item) for item in context_payload.get("events", []) or [] if isinstance(item, dict)][:2]
    event_references = [dict(item) for item in context_payload.get("references", []) or [] if isinstance(item, dict)]
    static_references = [dict(item) for item in payload.get("references", []) or [] if isinstance(item, dict)]

    references: list[dict[str, Any]] = []
    source_keys: dict[tuple[str, str], int] = {}
    for reference in [*event_references, *static_references]:
        label = str(reference.get("source_label") or reference.get("source_name") or "").strip()
        url = str(reference.get("source_url") or "").strip()
        if not label:
            continue
        key = (label, url)
        number = source_keys.get(key)
        if number is None:
            number = len(references) + 1
            source_keys[key] = number
            item = dict(reference)
            item["reference_number"] = number
            references.append(item)

    context_items: list[dict[str, Any]] = []
    for event in events:
        label = str(event.get("source_label") or event.get("source_name") or "").strip()
        url = str(event.get("source_url") or "").strip()
        number = source_keys.get((label, url))
        context_items.append({
            "event_id": str(event.get("event_id") or ""),
            "text": str(event.get("display") or event.get("verified_fact") or "").strip(),
            "reference_number": number,
            "source_url": url,
            "status": str(event.get("status") or "").strip(),
            "legal_status": str(event.get("legal_status") or "").strip(),
            "resolution_status": str(event.get("resolution_status") or "").strip(),
            "priority": float(event.get("priority", 0) or 0),
        })
    context_items = [item for item in context_items if item["text"]]

    payload["references"] = references
    payload["current_context_items"] = context_items
    payload["recent_context"] = context_items[0]["text"] if context_items else ""
    payload["current_context"] = context_payload
    return payload


def _active_campuses(infrastructure_data: dict) -> pd.DataFrame:
    campuses = (infrastructure_data or {}).get("campus_registry")
    if not isinstance(campuses, pd.DataFrame):
        campuses = (infrastructure_data or {}).get("facility_registry")
    if not isinstance(campuses, pd.DataFrame):
        return pd.DataFrame()
    frame = campuses.copy()
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str).str.casefold()
    active = {
        "operational", "expanding", "under construction",
        "approved / permitted / under construction", "proposed", "planned", "announced",
    }
    return frame.loc[status.isin(active)].copy()


def build_market_read(sector_data: dict, dashboard_data: dict, regime_metrics: dict) -> dict:
    ledger = build_market_ledger(sector_data)
    metrics = ledger.get("metrics", {}) or {}
    macro_df = (dashboard_data or {}).get("macro_df")
    aei = _num((regime_metrics or {}).get("AI Equity Index"))
    pressure = _num((regime_metrics or {}).get("Avg Sector Pressure"))
    breadth = _num(metrics.get("positive_breadth"))
    median_return = _num(metrics.get("median_return"))
    equal_return = _num(metrics.get("equal_weight_return"))
    top10 = _num(metrics.get("top_10_share"))
    effective = _num(metrics.get("effective_firms"))

    crowded_sectors = 0
    strong_sectors = 0
    if isinstance(macro_df, pd.DataFrame) and not macro_df.empty:
        scores = pd.to_numeric(macro_df.get("Sector Score"), errors="coerce")
        pressures = pd.to_numeric(macro_df.get("Pressure"), errors="coerce")
        strong_sectors = int(scores.ge(60).sum())
        crowded_sectors = int(pressures.ge(70).sum())

    if pd.notna(aei) and aei >= 65 and pd.notna(breadth) and breadth >= 0.60:
        headline = "Leadership is broad and constructive."
    elif pd.notna(equal_return) and equal_return > 0 and pd.notna(top10) and top10 >= 0.55:
        headline = "Positive returns remain concentrated at the top."
    elif pd.notna(breadth) and breadth < 0.45:
        headline = "Market participation is thinning."
    elif pd.notna(aei) and aei < 45:
        headline = "Equity validation remains subdued."
    else:
        headline = "Leadership is positive but uneven."

    breadth_clause = (
        f"{breadth * 100:.0f}% of covered companies have positive trailing returns"
        if pd.notna(breadth) else "company-level breadth is not fully available"
    )
    concentration_clause = (
        f"the top ten account for {top10 * 100:.0f}% of market value"
        if pd.notna(top10) else "concentration coverage is incomplete"
    )
    pressure_clause = (
        f"{crowded_sectors} sectors are in high-pressure territory"
        if crowded_sectors else "no sector currently clears the high-pressure threshold"
    )
    summary = _sentence(
        f"{breadth_clause}, while {concentration_clause}",
        f"{strong_sectors} sectors clear the strong-equity threshold and {pressure_clause}",
    )
    watchpoint = (
        "Watch whether participation broadens beyond the largest companies without a parallel rise in sector pressure."
        if pd.notna(top10) and top10 >= 0.50
        else "Watch whether positive breadth can hold as sector leadership rotates."
    )
    valid = sum(pd.notna(v) for v in [aei, pressure, breadth, median_return, equal_return, top10, effective])
    importance = max(
        abs((aei if pd.notna(aei) else 50) - 50),
        abs((breadth * 100 if pd.notna(breadth) else 50) - 50),
        (top10 * 100 - 45) if pd.notna(top10) else 0,
        pressure - 50 if pd.notna(pressure) else 0,
    )
    highlights = [
        {
            "score": 62 + max(0, (top10 * 100 - 50) if pd.notna(top10) else 0),
            "kind": "market",
            "text": f"Market leadership remains concentrated, with the top ten representing {top10 * 100:.0f}% of covered market value." if pd.notna(top10) else headline,
        },
        {
            "score": 55 + abs((breadth * 100 if pd.notna(breadth) else 50) - 50),
            "kind": "market",
            "text": f"Company breadth is {breadth * 100:.0f}% positive on a trailing one-year basis." if pd.notna(breadth) else summary,
        },
    ]
    return _read(
        "market", headline, summary, watchpoint,
        confidence=_confidence(valid, 7), importance=importance,
        signals={
            "aei": aei, "pressure": pressure, "positive_breadth": breadth,
            "median_return": median_return, "equal_weight_return": equal_return,
            "top_10_share": top10, "effective_firms": effective,
            "strong_sector_count": strong_sectors, "crowded_sector_count": crowded_sectors,
        },
        highlights=highlights,
    )


def build_finance_read(regime_metrics: dict, fred_data: dict, nfci_history, debt_markets_data: dict) -> dict:
    borrower = _num((regime_metrics or {}).get("Borrower Strain"))
    lender = _num((regime_metrics or {}).get("Lender Strain"))
    funding = ((regime_metrics or {}).get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}
    internal = _num(funding.get("internal_funding_coverage"))
    commitments = _num(funding.get("forward_commitment_load"))
    debt_pulse = _num(funding.get("debt_financing_pulse"))
    nfci = nfci_snapshot(fred_data or {}, nfci_history)
    nfci_value = _num(nfci.get("value"))
    nfci_change = _num(nfci.get("three_month_change"))
    cmdi = _num((((debt_markets_data or {}).get("series", {}) or {}).get("Corporate Bond Market Distress", {}) or {}).get("value"))
    private_metrics = (build_private_capital_realization().get("metrics", {}) or {})
    dpi = _num(private_metrics.get("dpi"))
    rvpi = _num(private_metrics.get("rvpi"))
    tvpi = _num(private_metrics.get("tvpi"))
    realized_share = _num(private_metrics.get("realized_share"))
    private_funds = int(private_metrics.get("fund_count", 0) or 0)

    if (pd.notna(borrower) and borrower >= 35) or (pd.notna(lender) and lender >= 35):
        headline = "Financing strain is becoming material."
    elif pd.notna(dpi) and dpi >= 1 and pd.notna(internal) and internal >= 1:
        headline = "Capital remains available and mature private vintages are realizing value."
    elif pd.notna(dpi) and dpi < 0.5 and pd.notna(rvpi) and rvpi >= 1:
        headline = "Private-market value remains concentrated in unrealized NAV."
    elif pd.notna(nfci_value) and nfci_value < 0 and pd.notna(borrower) and borrower < 20 and pd.notna(lender) and lender < 20:
        headline = "Financial conditions remain broadly supportive."
    elif pd.notna(internal) and internal < 1:
        headline = "Capital deployment is leaning on external funding."
    else:
        headline = "Funding conditions are mixed but manageable."

    funding_clause = (
        f"Internal cash flow covers {internal:.2f}x current capital spending"
        if pd.notna(internal) else "internal-funding coverage is incomplete"
    )
    realization_clause = (
        f"the mature public-LP technology cohort has returned {dpi:.2f}x paid-in capital and retains {rvpi:.2f}x at NAV"
        if pd.notna(dpi) and pd.notna(rvpi) else "private-capital realization coverage is incomplete"
    )
    condition_clause = (
        f"NFCI is {nfci_value:+.2f} and borrower/lender strain are {borrower:+.1f}/{lender:+.1f}"
        if pd.notna(nfci_value) and pd.notna(borrower) and pd.notna(lender)
        else "broad financial-condition confirmation is limited"
    )
    summary = _sentence(f"{funding_clause}; {realization_clause}", condition_clause)
    if pd.notna(realized_share) and realized_share < 0.45:
        watchpoint = "Watch whether private-fund distributions begin to convert marked value into returned capital."
    elif pd.notna(commitments) and commitments >= 2:
        watchpoint = "Watch whether forward commitments begin to outrun internal funding and cash reserves."
    elif pd.notna(nfci_change) and nfci_change > 0.1:
        watchpoint = "Watch recent financial-condition tightening for confirmation in borrower and bond-market stress."
    else:
        watchpoint = "Watch younger private vintages for improving DPI without a deterioration in credit conditions."

    valid = sum(pd.notna(v) for v in [borrower, lender, internal, commitments, debt_pulse, nfci_value, cmdi, dpi, tvpi])
    realization_imbalance = abs(0.5 - realized_share) * 70 if pd.notna(realized_share) else 0
    importance = max(
        abs(borrower) if pd.notna(borrower) else 0,
        abs(lender) if pd.notna(lender) else 0,
        max(0, (1 - internal) * 45) if pd.notna(internal) else 0,
        realization_imbalance,
    )
    highlights = [
        {
            "score": 54 + max(abs(borrower) if pd.notna(borrower) else 0, abs(lender) if pd.notna(lender) else 0) / 2,
            "kind": "finance",
            "text": f"Borrower and lender strain remain contained at {borrower:+.1f} and {lender:+.1f}, respectively." if pd.notna(borrower) and pd.notna(lender) and max(borrower, lender) < 25 else headline,
        },
        {
            "score": 56 + (abs(tvpi - 1.5) * 10 if pd.notna(tvpi) else 0),
            "kind": "finance",
            "text": f"Mature technology and AI-adjacent private vintages show {dpi:.2f}x DPI and {tvpi:.2f}x TVPI across {private_funds} public-LP fund records." if pd.notna(dpi) and pd.notna(tvpi) else summary,
        },
        {
            "score": 50 + (abs(nfci_value) * 10 if pd.notna(nfci_value) else 0),
            "kind": "finance",
            "text": f"Broad financial conditions remain {'looser' if nfci_value < 0 else 'tighter'} than average, with NFCI at {nfci_value:+.2f}." if pd.notna(nfci_value) else summary,
        },
    ]
    return _read(
        "finance", headline, summary, watchpoint,
        confidence=_confidence(valid, 7), importance=importance,
        signals={
            "borrower_strain": borrower, "lender_strain": lender,
            "internal_funding_coverage": internal, "forward_commitment_load": commitments,
            "debt_financing_pulse": debt_pulse, "nfci": nfci_value,
            "nfci_change": nfci_change, "bond_distress": cmdi,
            "private_capital_dpi": dpi, "private_capital_rvpi": rvpi,
            "private_capital_tvpi": tvpi, "private_capital_realized_share": realized_share,
            "private_capital_mature_funds": private_funds,
        },
        highlights=highlights,
    )


def build_compute_read(infrastructure_data: dict) -> dict:
    compute = (infrastructure_data or {}).get("compute_manufacturing", {}) or {}
    series = compute.get("series", {}) or {}
    def item(name):
        return (series.get(name, {}) or {})
    computer_growth = _num(item("Computer and Peripheral Equipment Output").get("yoy_growth"))
    semiconductor_growth = _num(item("Semiconductor and Electronic Component Output").get("yoy_growth"))
    computer_util = _num(item("Computer and Peripheral Equipment Capacity Utilization").get("value"))
    semiconductor_util = _num(item("Semiconductor and Electronic Component Capacity Utilization").get("value"))
    investment_growth = _num(item("Info Processing Investment Level").get("yoy_growth"))
    projects = compute.get("project_summary", {}) or {}
    capex = _num(projects.get("expected_capex_usd_b"))
    sites = int(projects.get("projects", 0) or 0)

    strongest_growth = np.nanmax([computer_growth, semiconductor_growth, investment_growth]) if any(pd.notna(v) for v in [computer_growth, semiconductor_growth, investment_growth]) else np.nan
    if pd.notna(strongest_growth) and strongest_growth >= 0.08:
        headline = "Compute supply and investment are expanding quickly."
    elif pd.notna(strongest_growth) and strongest_growth > 0:
        headline = "Compute activity is expanding at a measured pace."
    elif pd.notna(strongest_growth):
        headline = "Compute production is soft despite the buildout pipeline."
    else:
        headline = "Compute conditions are only partially observed."
    growth_bits = []
    if pd.notna(computer_growth): growth_bits.append(f"computer output {computer_growth * 100:+.1f}%")
    if pd.notna(semiconductor_growth): growth_bits.append(f"semiconductor output {semiconductor_growth * 100:+.1f}%")
    if pd.notna(investment_growth): growth_bits.append(f"information-processing investment {investment_growth * 100:+.1f}%")
    summary = _sentence(
        "Year-over-year readings show " + ", ".join(growth_bits) if growth_bits else "Current production-growth readings are incomplete",
        f"The tracked domestic buildout covers {sites} sites and ${capex:.1f}B of announced investment" if sites and pd.notna(capex) else f"The tracked domestic buildout covers {sites} sites" if sites else "Project-ledger coverage is limited",
    )
    avg_util = np.nanmean([v for v in [computer_util, semiconductor_util] if pd.notna(v)]) if any(pd.notna(v) for v in [computer_util, semiconductor_util]) else np.nan
    watchpoint = "Watch whether manufacturing utilization rises with the project pipeline rather than leaving capacity ahead of realized demand." if pd.notna(avg_util) and avg_util < 80 else "Watch whether output growth can hold as manufacturing utilization tightens."
    valid = sum(pd.notna(v) for v in [computer_growth, semiconductor_growth, computer_util, semiconductor_util, investment_growth, capex])
    importance = max(abs(strongest_growth * 100) if pd.notna(strongest_growth) else 0, min(capex / 5, 35) if pd.notna(capex) else 0)
    return _read(
        "compute", headline, summary, watchpoint,
        confidence=_confidence(valid, 6), importance=importance,
        signals={"computer_growth": computer_growth, "semiconductor_growth": semiconductor_growth, "computer_utilization": computer_util, "semiconductor_utilization": semiconductor_util, "investment_growth": investment_growth, "project_capex_b": capex, "project_sites": sites},
        highlights=[{"score": 56 + min(25, importance / 2), "kind": "physical", "text": f"Compute buildout spans {sites} tracked manufacturing sites and ${capex:.1f}B of announced investment." if sites and pd.notna(capex) else headline}],
    )


def build_data_center_read(infrastructure_data: dict) -> dict:
    inventory = (infrastructure_data or {}).get("data_center_inventory")
    inventory = inventory if isinstance(inventory, dict) else {}
    broad = inventory.get("broad_summary", {}) or {}
    tracker = inventory.get("open_tracker_summary", {}) or {}
    campuses = _active_campuses(infrastructure_data)

    operating = int(broad.get("operating", 0) or 0)
    development = int(broad.get("development", 0) or 0)
    ratio = _num(broad.get("development_to_operating"))
    tracked_pipeline = int(tracker.get("active_pipeline", 0) or 0)
    pipeline_capacity_gw = _num(tracker.get("active_pipeline_published_mw")) / 1000.0
    operating_capacity_gw = _num(tracker.get("operating_published_mw")) / 1000.0

    canonical_capacity = pd.to_numeric(campuses.get("Planned Data Center Capacity MW"), errors="coerce") if not campuses.empty else pd.Series(dtype=float)
    canonical_published = pd.to_numeric(campuses.get("Published Capacity Estimate MW"), errors="coerce") if not campuses.empty else pd.Series(dtype=float)
    canonical_combined = canonical_capacity.combine_first(canonical_published).where(lambda x: x > 0) if not campuses.empty else pd.Series(dtype=float)
    canonical_coverage = float(canonical_combined.notna().mean()) if len(campuses) else np.nan

    if pd.notna(ratio) and ratio >= 0.75:
        headline = "Development is approaching the scale of the operating base."
    elif pd.notna(ratio) and ratio >= 0.40:
        headline = "The operating footprint is large, with a substantial next wave behind it."
    elif operating:
        headline = "The operating base remains much larger than the visible development pipeline."
    else:
        headline = "The national data-center footprint is only partially observed."

    broad_clause = (
        f"The broad national estimate includes {operating:,} operating facilities and {development:,} in development"
        if operating or development else "Broad national facility counts are unavailable"
    )
    tracker_clause = (
        f"The stage-tracked pipeline covers {tracked_pipeline:,} sites with {pipeline_capacity_gw:.1f} GW of published capacity, versus {operating_capacity_gw:.1f} GW across tracked operating sites"
        if tracked_pipeline and pd.notna(pipeline_capacity_gw) and pd.notna(operating_capacity_gw)
        else "Stage and published-capacity coverage remain incomplete"
    )
    summary = _sentence(broad_clause, tracker_clause)
    watchpoint = "Watch whether proposed and approved projects convert into construction and energized capacity without deepening geographic concentration."
    valid = sum([
        bool(operating or development),
        pd.notna(ratio),
        bool(tracked_pipeline),
        pd.notna(pipeline_capacity_gw),
        pd.notna(canonical_coverage),
    ])
    importance = min(
        90,
        (ratio * 45 if pd.notna(ratio) else 0)
        + (min(pipeline_capacity_gw / 8.0, 35) if pd.notna(pipeline_capacity_gw) else 0),
    )
    return _read(
        "data_center", headline, summary, watchpoint,
        confidence=_confidence(valid, 5), importance=importance,
        signals={
            "broad_operating": operating,
            "broad_development": development,
            "development_to_operating": ratio,
            "tracked_pipeline_sites": tracked_pipeline,
            "tracked_pipeline_capacity_gw": pipeline_capacity_gw,
            "tracked_operating_capacity_gw": operating_capacity_gw,
            "canonical_capacity_coverage": canonical_coverage,
        },
        highlights=[{
            "score": 68 + min(20, ratio * 20 if pd.notna(ratio) else 0),
            "kind": "physical",
            "text": f"The broad U.S. footprint includes {development:,} facilities in development, while the stage-tracked pipeline carries {pipeline_capacity_gw:.1f} GW of published capacity." if development and pd.notna(pipeline_capacity_gw) else headline,
        }],
    )


def build_power_domain_read(energy_data: dict, infrastructure_data: dict) -> dict:
    retail = (energy_data or {}).get("retail_history")
    pipeline = (energy_data or {}).get("generator_pipeline")
    campuses = _active_campuses(infrastructure_data)
    demand = demand_snapshot(retail if isinstance(retail, pd.DataFrame) else pd.DataFrame())
    large = large_load_snapshot(campuses)
    development = development_snapshot(
        pipeline if isinstance(pipeline, pd.DataFrame) else pd.DataFrame(),
        pd.DataFrame(),
        pd.DataFrame(),
    )
    prices = price_snapshot(
        retail if isinstance(retail, pd.DataFrame) else pd.DataFrame(),
        (((energy_data or {}).get("series", {}) or {}).get("Natural Gas Price", {}) or {}),
    )
    base = build_power_read(demand, large, development, prices)
    demand_growth = _num(demand.get("total_growth"))
    commercial_growth = _num(demand.get("commercial_growth"))
    planned_net = _num(development.get("planned_net_gw"))
    price_growth = _num(prices.get("total_growth"))
    importance = max(
        abs(demand_growth) * 8 if pd.notna(demand_growth) else 0,
        abs(price_growth) * 5 if pd.notna(price_growth) else 0,
        abs(planned_net) if pd.notna(planned_net) else 0,
    )
    watchpoint = "Watch whether planned generation additions outpace retirements as commercial-load growth and large-load commitments increase."
    highlights = [
        {
            "score": 58 + min(abs(planned_net), 25) if pd.notna(planned_net) else 55,
            "kind": "energy",
            "text": f"The planned generation pipeline carries a net {planned_net:+.0f} GW through {development.get('end_year')}." if pd.notna(planned_net) else base.get("headline", "Power conditions are mixed."),
        },
        {
            "score": 52 + abs(commercial_growth) * 4 if pd.notna(commercial_growth) else 50,
            "kind": "energy",
            "text": f"Commercial electricity demand is growing {commercial_growth:+.1f}% year over year." if pd.notna(commercial_growth) else base.get("body", ""),
        },
    ]
    valid = sum(pd.notna(v) for v in [demand_growth, commercial_growth, planned_net, price_growth])
    return _read(
        "power", str(base.get("headline") or "Power conditions are mixed."), str(base.get("body") or ""), watchpoint,
        confidence=_confidence(valid, 4), importance=importance,
        signals={
            "demand_growth": demand_growth,
            "commercial_growth": commercial_growth,
            "planned_net_gw": planned_net,
            "retail_price_growth": price_growth,
            "large_load_capacity_mw": _num(large.get("published_total_mw")),
        },
        highlights=highlights,
    )


def build_water_read(water_data: dict) -> dict:
    summary = (water_data or {}).get("summary", {}) or {}
    eia = summary.get("eia_2024_thermoelectric", {}) or {}
    linkage = (water_data or {}).get("facility_context_summary", {}) or {}
    profile = current_top_withdrawal_profile((water_data or {}).get("usgs_2020_top_withdrawals"))
    values = profile.set_index("Use Category")["Withdrawal Bgal/day"].to_dict() if not profile.empty else {}

    irrigation = _num(values.get("Crop irrigation"))
    thermoelectric_2020 = _num(values.get("Thermoelectric power"))
    public_supply = _num(values.get("Public supply"))
    withdrawal = _num(eia.get("withdrawal_bgal_day"))
    consumption = _num(eia.get("consumption_bgal_day"))
    facilities = int(linkage.get("facilities", 0) or 0)
    direct = int(linkage.get("direct_water_evidence_records", 0) or 0)
    quantified = int(linkage.get("quantified_withdrawal_records", 0) or 0) + int(
        linkage.get("quantified_consumption_records", 0) or 0
    )
    direct_share = direct / facilities if facilities else np.nan

    if facilities and quantified == 0:
        headline = "Major water claims are visible; AI attribution remains unquantified."
    elif facilities and pd.notna(direct_share) and direct_share < 0.25:
        headline = "Water competition is locally important, but AI evidence remains thin."
    elif facilities and direct_share >= 0.50:
        headline = "Facility-level water evidence is becoming decision-useful."
    else:
        headline = "Water-system coverage remains incomplete."

    allocation_clause = (
        f"The latest retained national comparison shows crop irrigation at {irrigation:.1f} Bgal/day, thermoelectric power at {thermoelectric_2020:.1f}, and public supply at {public_supply:.1f} in 2020"
        if all(pd.notna(value) for value in [irrigation, thermoelectric_2020, public_supply])
        else "The current national competing-use envelope is only partially observed"
    )
    evidence_clause = (
        f"{direct:,} of {facilities:,} mapped facilities have direct water evidence, but none quantify annual withdrawal or consumption"
        if facilities and quantified == 0
        else f"{direct:,} of {facilities:,} mapped facilities have direct evidence and {quantified:,} quantify annual withdrawal or consumption"
        if facilities else "No facility-linked water cohort is available"
    )
    summary_text = _sentence(allocation_clause, evidence_clause)
    watchpoint = (
        "Watch for quantified facility use, utility-capacity limits, water-right commitments, and documented community or agricultural effects in high-footprint locations."
    )
    valid = sum(pd.notna(v) for v in [irrigation, thermoelectric_2020, public_supply, withdrawal, consumption, direct_share])
    importance = 58.0 if facilities and quantified == 0 else 48.0
    return _read(
        "water", headline, summary_text, watchpoint,
        confidence=_confidence(valid, 6), importance=importance,
        signals={
            "irrigation_withdrawal_bgal_day_2020": irrigation,
            "thermoelectric_withdrawal_bgal_day_2020": thermoelectric_2020,
            "public_supply_withdrawal_bgal_day_2020": public_supply,
            "thermoelectric_reported_withdrawal_bgal_day_2024": withdrawal,
            "thermoelectric_reported_consumption_bgal_day_2024": consumption,
            "mapped_facilities": facilities,
            "direct_evidence_records": direct,
            "quantified_use_records": quantified,
            "direct_evidence_share": direct_share,
        },
        highlights=[{
            "score": 64 if facilities and quantified == 0 else 54,
            "kind": "resource",
            "text": (
                f"The facility footprint intersects major agricultural, public-supply, and power-sector claims, but none of {facilities} mapped facilities currently quantify annual withdrawal or consumption."
                if facilities and quantified == 0 else headline
            ),
        }],
    )


def build_grid_storage_read(energy_data: dict, infrastructure_data: dict) -> dict:
    queue = (energy_data or {}).get("interconnection_queue")
    summary = (energy_data or {}).get("interconnection_queue_summary")
    pipeline = (energy_data or {}).get("generator_pipeline")
    development = development_snapshot(
        pipeline if isinstance(pipeline, pd.DataFrame) else pd.DataFrame(),
        queue if isinstance(queue, pd.DataFrame) else pd.DataFrame(),
        summary if isinstance(summary, pd.DataFrame) else pd.DataFrame(),
    )
    active = development.get("active_queue")
    storage_gw = np.nan
    if isinstance(active, pd.DataFrame) and not active.empty:
        storage_gw = pd.to_numeric(active.get("Storage MW"), errors="coerce").sum(min_count=1) / 1000.0
    queue_gw = _num(development.get("headline_queue_gw"))
    advanced = _num(development.get("advanced_share"))
    power_growth = _num(((((infrastructure_data or {}).get("series", {}) or {}).get("Electric Power Construction", {}) or {}).get("yoy_growth")))
    if pd.notna(queue_gw) and pd.notna(advanced) and advanced < 30:
        headline = "The connection pipeline is large, but most capacity remains early-stage."
    elif pd.notna(queue_gw):
        headline = "Grid access remains the central conversion test for proposed capacity."
    else:
        headline = "Grid-delivery coverage is incomplete."
    summary_text = _sentence(
        f"The active interconnection pipeline totals {queue_gw:.0f} GW, with {advanced:.1f}% in executed-agreement or construction stages" if pd.notna(queue_gw) and pd.notna(advanced) else "Queue scale or maturity is unavailable",
        f"Submitted storage components total {storage_gw:.0f} GW" if pd.notna(storage_gw) else "Storage-pipeline coverage is unavailable",
        f"Broad electric-power construction is {power_growth * 100:+.1f}% year over year" if pd.notna(power_growth) else "Grid-specific construction cannot be isolated from the broad Census power category",
    )
    watchpoint = "Watch executed interconnection agreements, construction-stage capacity, withdrawals, and storage projects that convert from requested to operating capacity."
    valid = sum(pd.notna(value) for value in [queue_gw, advanced, storage_gw, power_growth])
    importance = max(50 - advanced if pd.notna(advanced) else 0, min(queue_gw / 25, 70) if pd.notna(queue_gw) else 0)
    return _read(
        "grid_storage", headline, summary_text, watchpoint,
        confidence=_confidence(valid, 4), importance=importance,
        signals={"queue_gw": queue_gw, "advanced_share": advanced, "storage_queue_gw": storage_gw, "electric_power_construction_growth": power_growth},
        highlights=[{"score": 68 + max(0, 30 - advanced) if pd.notna(advanced) else 58, "kind": "energy", "text": f"The interconnection pipeline totals {queue_gw:.0f} GW, but only {advanced:.0f}% is in executed-agreement or construction stages." if pd.notna(queue_gw) and pd.notna(advanced) else headline}],
    )


def _latest_row(frame: pd.DataFrame | None, series: str) -> dict:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    rows = frame.loc[frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq(series)]
    return rows.iloc[-1].to_dict() if not rows.empty else {}


def build_workforce_read(workforce_data: dict) -> dict:
    employment = (workforce_data or {}).get("employment_latest")
    openings = (workforce_data or {}).get("job_openings_latest")
    systems = _latest_row(employment, "Computer systems design")
    hosting = _latest_row(employment, "Computing infrastructure")
    semis = _latest_row(employment, "Semiconductor manufacturing")
    information = _latest_row(openings, "Information")
    values = [_num(item.get("YoY Change")) for item in [systems, hosting, semis]]
    valid_values = [value for value in values if pd.notna(value)]
    leader_index = int(np.nanargmax(values)) if valid_values and any(pd.notna(v) for v in values) else None
    labels = ["computer-systems employment", "computing-infrastructure employment", "semiconductor employment"]
    leader = labels[leader_index] if leader_index is not None else "relevant employment"
    leader_growth = values[leader_index] if leader_index is not None else np.nan
    info_openings_growth = _num(information.get("YoY Change"))
    if pd.notna(leader_growth) and leader_growth > 0.03:
        headline = f"{leader.title()} currently leads labor-market momentum."
    elif valid_values and max(valid_values) > 0:
        headline = "AI-linked labor demand is expanding unevenly."
    elif valid_values:
        headline = "Employment momentum has softened across the production stack."
    else:
        headline = "Workforce coverage is incomplete."
    summary_text = _sentence(
        "; ".join(f"{label}: {value * 100:+.1f}% YoY" for label, value in zip(["Computer systems", "Computing infrastructure", "Semiconductors"], values) if pd.notna(value)),
        f"Information-sector job openings are {info_openings_growth * 100:+.1f}% year over year" if pd.notna(info_openings_growth) else "Information-sector openings growth is unavailable",
    )
    watchpoint = "Watch whether employment, openings, and compensation broaden beyond a narrow set of technical and construction occupations as business use expands."
    importance = max([abs(value * 100) for value in valid_values] + ([abs(info_openings_growth * 100)] if pd.notna(info_openings_growth) else [0]))
    return _read(
        "workforce", headline, summary_text, watchpoint,
        confidence=_confidence(len(valid_values) + int(pd.notna(info_openings_growth)), 4), importance=importance,
        signals={"computer_systems_growth": values[0], "computing_infrastructure_growth": values[1], "semiconductor_growth": values[2], "information_openings_growth": info_openings_growth},
        highlights=[{"score": 58 + min(25, importance), "kind": "labor", "text": f"{leader.title()} is {leader_growth * 100:+.1f}% year over year, while information-sector openings are {info_openings_growth * 100:+.1f}%." if pd.notna(leader_growth) and pd.notna(info_openings_growth) else headline}],
    )


def build_economic_impact_read(economic_impact_data: dict) -> dict:
    productivity = _num(((economic_impact_data or {}).get("nonfarm_productivity", {}) or {}).get("value"))
    output = _num(((economic_impact_data or {}).get("nonfarm_output", {}) or {}).get("value"))
    compensation = _num(((economic_impact_data or {}).get("nonfarm_compensation", {}) or {}).get("value"))
    unit_cost = _num(((economic_impact_data or {}).get("nonfarm_unit_labor_cost", {}) or {}).get("value"))
    investment = _num(((economic_impact_data or {}).get("information_investment", {}) or {}).get("yoy"))
    if pd.notna(productivity) and productivity >= 2 and pd.notna(output) and output > 0:
        headline = "Investment is receiving measurable productivity and output confirmation."
    elif pd.notna(investment) and investment > 10 and (pd.isna(productivity) or productivity < 1):
        headline = "Information investment is still outrunning realized productivity gains."
    elif pd.notna(output) and output > 0:
        headline = "Output is expanding, but the productivity signal remains mixed."
    else:
        headline = "Real-economy validation remains incomplete."
    summary_text = _sentence(
        f"Nonfarm-business productivity is {productivity:+.1f}% and real output is {output:+.1f}% year over year" if pd.notna(productivity) and pd.notna(output) else "Productivity or output growth is unavailable",
        f"Hourly compensation is {compensation:+.1f}% and unit labor costs are {unit_cost:+.1f}%" if pd.notna(compensation) and pd.notna(unit_cost) else "Compensation or unit-cost growth is unavailable",
        f"Information-processing investment is {investment:+.1f}% year over year" if pd.notna(investment) else "Investment growth is unavailable",
    )
    watchpoint = "Watch whether productivity and real output continue to improve as business adoption broadens, and whether compensation shares in those gains."
    valid = sum(pd.notna(value) for value in [productivity, output, compensation, unit_cost, investment])
    validation_gap = investment - productivity if pd.notna(investment) and pd.notna(productivity) else np.nan
    importance = max(abs(validation_gap) if pd.notna(validation_gap) else 0, abs(productivity) * 8 if pd.notna(productivity) else 0)
    return _read(
        "economic_impact", headline, summary_text, watchpoint,
        confidence=_confidence(valid, 5), importance=importance,
        signals={"productivity_growth": productivity, "real_output_growth": output, "compensation_growth": compensation, "unit_labor_cost_growth": unit_cost, "information_investment_growth": investment, "investment_productivity_gap": validation_gap},
        highlights=[{"score": 62 + min(24, importance / 2), "kind": "validation", "text": f"Information-processing investment is {investment:+.1f}% year over year versus {productivity:+.1f}% labor-productivity growth." if pd.notna(investment) and pd.notna(productivity) else headline}],
    )

def build_infrastructure_read(infrastructure_data: dict) -> dict:
    series = (infrastructure_data or {}).get("series", {}) or {}
    def growth(name): return _num((series.get(name, {}) or {}).get("yoy_growth"))
    dc_growth = growth("Data Center Construction")
    compute_growth = growth("Computer, Electronic & Electrical Manufacturing Construction")
    power_growth = growth("Electric Power Construction")
    communications_growth = growth("Communication Construction")
    water_growth = growth("Public Water Supply Construction")
    history = (infrastructure_data or {}).get("construction_history")
    momentum = current_buildout_momentum(history)
    leader = str(momentum.iloc[0]["Series"]) if not momentum.empty else ""
    leader_growth = _num(momentum.iloc[0]["YoY Growth"]) if not momentum.empty else np.nan

    attribution = (infrastructure_data or {}).get("infrastructure_attribution", {}) or {}
    latest = attribution.get("latest", {}) or {}
    components = attribution.get("components")
    balance = supporting_balance(components)
    direct = _num(latest.get("direct_ai_construction"))
    supporting = _num(latest.get("supporting_construction"))
    gross_excess = _num(balance.get("gross_positive_excess"))
    net_balance = _num(latest.get("net_support_balance"))
    if pd.isna(net_balance):
        net_balance = _num(balance.get("net_support_balance"))

    if leader == "Data centers" and pd.notna(dc_growth) and dc_growth > 0:
        headline = "Data centers now lead the physical investment cycle."
    elif leader:
        headline = f"{leader} currently leads physical investment momentum."
    else:
        headline = "Physical investment leadership is only partially observed."

    summary_sentences = []
    if pd.notna(leader_growth):
        subject = "Data-center construction" if leader == "Data centers" else leader
        summary_sentences.append(
            f"{subject} leads current momentum at {leader_growth * 100:+.1f}% year over year"
        )
    if pd.notna(compute_growth) and compute_growth < -0.15:
        sentence = f"Compute-manufacturing investment is normalizing at {compute_growth * 100:+.1f}% after the prior surge"
        if pd.notna(power_growth) and pd.notna(communications_growth):
            sentence += f", while electric power and communications are {power_growth * 100:+.1f}% and {communications_growth * 100:+.1f}%"
        summary_sentences.append(sentence)
    elif pd.notna(compute_growth):
        summary_sentences.append(f"Compute-manufacturing construction is {compute_growth * 100:+.1f}%")
    if pd.notna(net_balance):
        balance_text = f"+${abs(net_balance) / 1000:.1f}B" if net_balance >= 0 else f"−${abs(net_balance) / 1000:.1f}B"
        summary_sentences.append(f"The net supporting-system balance is {balance_text} versus baseline")
    summary = _sentence(*summary_sentences)
    watchpoint = "Watch whether power, communications, water, roads, and transit keep pace as data-center construction absorbs the next wave of capital."
    values = [dc_growth, compute_growth, power_growth, communications_growth, water_growth, direct, supporting, gross_excess, net_balance]
    valid = sum(pd.notna(value) for value in values)
    growths = [value for value in [dc_growth, compute_growth, power_growth, communications_growth, water_growth] if pd.notna(value)]
    importance = max([abs(value * 100) for value in growths] + [abs(net_balance / 1000) if pd.notna(net_balance) else 0])
    return _read(
        "infrastructure", headline, summary, watchpoint,
        confidence=_confidence(valid, 9), importance=importance,
        signals={
            "data_center_growth": dc_growth,
            "compute_construction_growth": compute_growth,
            "power_construction_growth": power_growth,
            "communications_growth": communications_growth,
            "public_water_growth": water_growth,
            "current_leader": leader,
            "leader_growth": leader_growth,
            "direct_ai_construction": direct,
            "supporting_construction": supporting,
            "gross_positive_excess": gross_excess,
            "net_support_balance": net_balance,
        },
        highlights=[{
            "score": 66 + min(22, importance / 3),
            "kind": "physical",
            "text": (
                f"Physical-investment leadership has rotated to data centers at {dc_growth * 100:+.1f}% year over year, while compute-manufacturing construction normalizes from the prior surge at {compute_growth * 100:+.1f}%."
                if leader == "Data centers" and pd.notna(dc_growth) and pd.notna(compute_growth)
                else headline
            ),
        }],
    )

def build_adaptation_read(adaptation_data: dict) -> dict:
    current = _num((adaptation_data or {}).get("current_use"))
    expected = _num((adaptation_data or {}).get("expected_use"))
    gap = _num((adaptation_data or {}).get("expected_adoption_gap"))
    annual = _num((adaptation_data or {}).get("annual_change"))
    sectors = (adaptation_data or {}).get("sector_snapshot")
    breadth = np.nan
    top_sector = ""
    top_value = np.nan
    if isinstance(sectors, pd.DataFrame) and not sectors.empty:
        values = pd.to_numeric(sectors.get("Current AI Use"), errors="coerce")
        breadth = float(values.notna().mean())
        if values.notna().any():
            idx = values.idxmax()
            top_sector = str(sectors.loc[idx].get("Sector", ""))
            top_value = float(values.loc[idx])

    if pd.notna(annual) and annual >= 2:
        headline = "Business adoption is broadening at a meaningful pace."
    elif pd.notna(current) and pd.notna(expected) and expected - current >= 5:
        headline = "The adoption pipeline remains larger than realized use."
    elif pd.notna(annual) and annual > 0:
        headline = "Business AI use is rising gradually."
    elif pd.notna(current):
        headline = "Reported business AI use has stalled."
    else:
        headline = "Business-adoption coverage is incomplete."
    summary = _sentence(
        f"Current use is {current:.1f}% and expected six-month use is {expected:.1f}%, leaving a {gap:.1f}-point adoption pipeline" if all(pd.notna(v) for v in [current, expected, gap]) else "Current and expected-use coverage is incomplete",
        f"The 12-month change is {annual:+.1f} points" if pd.notna(annual) else "The annual change is unavailable",
    )
    watchpoint = "Watch whether expected use converts into observed deployment across industries rather than remaining an intention gap."
    valid = sum(pd.notna(v) for v in [current, expected, gap, annual, breadth])
    importance = max(abs(annual) * 8 if pd.notna(annual) else 0, gap * 4 if pd.notna(gap) else 0)
    return _read(
        "adaptation", headline, summary, watchpoint,
        confidence=_confidence(valid, 5), importance=importance,
        signals={"current_use": current, "expected_use": expected, "expected_gap": gap, "annual_change": annual, "sector_coverage": breadth, "leading_sector": top_sector, "leading_sector_use": top_value},
        highlights=[{"score": 58 + min(25, importance / 2), "kind": "adoption", "text": f"Business AI use is {current:.1f}%, with expected use at {expected:.1f}% and a {gap:.1f}-point conversion pipeline." if all(pd.notna(v) for v in [current, expected, gap]) else headline}],
    )


def _macro_headline(reads: dict[str, dict]) -> str:
    market = reads.get("market", {}).get("signals", {})
    data_center = reads.get("data_center", {}).get("signals", {})
    grid = reads.get("grid_storage", {}).get("signals", {})
    adaptation = reads.get("adaptation", {}).get("signals", {})
    impact = reads.get("economic_impact", {}).get("signals", {})
    aei = _num(market.get("aei"))
    pipeline_gw = _num(data_center.get("tracked_pipeline_capacity_gw"))
    advanced = _num(grid.get("advanced_share"))
    annual_adoption = _num(adaptation.get("annual_change"))
    productivity = _num(impact.get("productivity_growth"))
    if pd.notna(aei) and aei < 50 and pd.notna(pipeline_gw) and pipeline_gw > 0:
        return "Physical buildout is outrunning market validation."
    if pd.notna(advanced) and advanced < 30 and pd.notna(pipeline_gw) and pipeline_gw > 0:
        return "Expansion continues, but grid conversion remains a material constraint."
    if pd.notna(aei) and aei >= 60 and pd.notna(annual_adoption) and annual_adoption > 0 and pd.notna(productivity) and productivity > 0:
        return "Market strength is gaining adoption and productivity confirmation."
    return "The AI economy is expanding unevenly across markets, physical systems, and realized outcomes."


def build_macro_read(reads: dict[str, dict], current_context: dict | None = None) -> dict:
    candidates = []
    for domain in DOMAIN_ORDER:
        for item in (reads.get(domain, {}) or {}).get("highlights", []) or []:
            text = str(item.get("text") or "").strip()
            score = _num(item.get("score"))
            if text and pd.notna(score):
                candidates.append({**item, "domain": domain, "score": score})
    candidates.sort(key=lambda item: item["score"], reverse=True)

    selected = []
    domain_counts: dict[str, int] = {}
    kind_counts: dict[str, int] = {}
    for item in candidates:
        domain = item["domain"]
        kind = str(item.get("kind") or domain)
        if domain_counts.get(domain, 0) >= 1:
            continue
        if kind_counts.get(kind, 0) >= 2:
            continue
        selected.append(item)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        if len(selected) >= 3:
            break

    headline = _macro_headline(reads)
    summary = " ".join(str(item["text"]).strip() for item in selected)
    if summary and not summary.endswith("."):
        summary += "."

    selected_constraint = next(
        (item for item in selected if item.get("kind") in {"energy", "finance", "resource", "labor", "validation"}),
        selected[0] if selected else None,
    )
    selected_domain = str((selected_constraint or {}).get("domain") or "")
    watchpoint = str((reads.get(selected_domain, {}) or {}).get("watchpoint") or "Watch for confirmation across markets, financing, physical delivery, and adoption.")

    # Current Context is selected only from domains that actually contribute to
    # the macro synthesis.  It is never a one-item-per-tab digest.
    selected_domains = [str(item.get("domain") or "") for item in selected]
    event_candidates: list[dict[str, Any]] = []
    for domain in selected_domains:
        domain_context = (reads.get(domain, {}) or {}).get("current_context", {}) or {}
        for event in domain_context.get("events", []) or []:
            if (
                isinstance(event, dict)
                and str(event.get("verification_status") or "").strip().lower() != "no_match"
                and str(event.get("source_url") or "").startswith("https://")
            ):
                event_candidates.append({**event, "domain": domain})
    if not event_candidates:
        for event in (current_context or {}).get("events", []) or []:
            if (
                isinstance(event, dict)
                and str(event.get("verification_status") or "").strip().lower() != "no_match"
                and str(event.get("source_url") or "").startswith("https://")
            ):
                event_candidates.append(dict(event))
    event_candidates.sort(
        key=lambda item: (float(item.get("rank_score", item.get("priority", 0)) or 0), str(item.get("event_date", ""))),
        reverse=True,
    )
    macro_event = dict(event_candidates[0]) if event_candidates else None

    references: list[dict[str, Any]] = []
    source_keys: set[tuple[str, str]] = set()
    if macro_event:
        ref = {
            "event_id": macro_event.get("event_id", ""),
            "source_name": macro_event.get("source_name", ""),
            "source_label": macro_event.get("source_label") or macro_event.get("source_name") or "Source",
            "source_url": macro_event.get("source_url", ""),
            "event_date": macro_event.get("event_date", ""),
        }
        key = (str(ref["source_label"]), str(ref["source_url"]))
        references.append(ref)
        source_keys.add(key)

    for item in selected:
        domain = str(item.get("domain") or "")
        domain_refs = (reads.get(domain, {}) or {}).get("references", []) or []
        static_ref = next((dict(ref) for ref in domain_refs if isinstance(ref, dict) and not ref.get("event_id")), None)
        if static_ref is None:
            continue
        key = (str(static_ref.get("source_label") or static_ref.get("source_name") or ""), str(static_ref.get("source_url") or ""))
        if key not in source_keys:
            references.append(static_ref)
            source_keys.add(key)
        if len(references) >= 4:
            break
    for index, reference in enumerate(references, start=1):
        reference["reference_number"] = index

    current_context_items = []
    if macro_event:
        current_context_items.append({
            "event_id": str(macro_event.get("event_id") or ""),
            "text": str(macro_event.get("display") or macro_event.get("verified_fact") or "").strip(),
            "reference_number": 1,
            "source_url": str(macro_event.get("source_url") or ""),
            "status": str(macro_event.get("status") or "").strip(),
            "legal_status": str(macro_event.get("legal_status") or "").strip(),
            "resolution_status": str(macro_event.get("resolution_status") or "").strip(),
        })

    confidence_values = [read.get("confidence") for read in reads.values()]
    confidence = "high" if confidence_values.count("high") >= 5 else "moderate" if confidence_values.count("limited") <= 2 else "limited"

    expansion = [item["text"] for item in selected if item.get("kind") in {"physical", "adoption", "market"}][:3]
    constraints = [item["text"] for item in selected if item.get("kind") in {"energy", "finance", "resource", "labor", "validation"}][:3]
    macro = _read(
        "macro", headline, summary, watchpoint,
        confidence=confidence,
        importance=max((float(read.get("importance", 0) or 0) for read in reads.values()), default=0),
        signals={"selected_domains": selected_domains, "domain_importance": {key: float(value.get("importance", 0) or 0) for key, value in reads.items()}},
        highlights=selected,
        references=references,
    )
    macro.update({
        "current_context_items": current_context_items,
        "recent_context": current_context_items[0]["text"] if current_context_items else "",
        "expansion_factors": expansion,
        "resilience_factors": expansion,
        "constraint_factors": constraints,
        "pressure_factors": constraints,
        "changes": [],
        "weekly_references": references,
        "weekly_context": current_context or {},
        "current_context": current_context or {},
        "domains": {key: value.get("headline") for key, value in reads.items()},
        "snapshot_context": {key: value.get("signals", {}) for key, value in reads.items()},
        "metric_changes": [],
    })
    return macro


def build_platform_reads(
    *,
    sector_data: dict,
    dashboard_data: dict,
    regime_metrics: dict,
    fred_data: dict,
    nfci_history,
    energy_data: dict,
    debt_markets_data: dict,
    infrastructure_data: dict,
    water_data: dict,
    adaptation_data: dict,
    workforce_data: dict,
    economic_impact_data: dict,
    current_context: dict | None = None,
    weekly_context: dict | None = None,
) -> dict:
    reads = {
        "market": build_market_read(sector_data, dashboard_data, regime_metrics),
        "finance": build_finance_read(regime_metrics, fred_data, nfci_history, debt_markets_data),
        "compute": build_compute_read(infrastructure_data),
        "data_center": build_data_center_read(infrastructure_data),
        "power": build_power_domain_read(energy_data, infrastructure_data),
        "grid_storage": build_grid_storage_read(energy_data, infrastructure_data),
        "water": build_water_read(water_data),
        "adaptation": build_adaptation_read(adaptation_data),
        "workforce": build_workforce_read(workforce_data),
        "economic_impact": build_economic_impact_read(economic_impact_data),
    }
    context_payload = current_context or weekly_context or {}
    by_domain = context_payload.get("by_domain", {}) or {}
    for domain in DOMAIN_ORDER:
        reads[domain] = _attach_current_context(reads[domain], by_domain.get(domain, {}))
    reads["macro"] = build_macro_read(reads, current_context=context_payload)
    return reads
