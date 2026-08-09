"""Deterministic platform-wide narrative architecture.

Each domain emits a compact, structured read.  The AI Macro read synthesizes
only the most material cross-domain signals rather than concatenating domain
copy.  All language is generated from explicit thresholds and retained facts.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analytics.dashboard_context import DashboardContext
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
from analytics.grid_deliverability import (
    queue_outcome_snapshot,
    reserve_margin_profile,
    storage_duration_profile,
)
from analytics.water_competition import (
    current_top_withdrawal_profile,
    state_water_exposure_profile,
)

READ_ARCHITECTURE_VERSION = "7.0.0"
DOMAIN_ORDER = (
    "market",
    "finance",
    "compute",
    "data_center",
    "connectivity",
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
        {"source_label": "Microsoft FY2026 Q3 AI disclosure", "source_url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast"},
        {"source_label": "OpenAI business scale disclosure", "source_url": "https://openai.com/index/a-business-that-scales-with-the-value-of-intelligence/"},
        {"source_label": "Alphabet Q2 2026 AI and Cloud disclosure", "source_url": "https://abc.xyz/investor/events/event-details/2026/2026-Q2-Earnings-Call-2026-GgTAq7Is0z/default.aspx"},
    ),
    "compute": (
        {"source_label": "Federal Reserve G.17", "source_url": "https://www.federalreserve.gov/releases/g17/current/"},
        {"source_label": "BEA Fixed Assets", "source_url": "https://www.bea.gov/data/investment-fixed-assets"},
        {"source_label": "Census Construction Spending", "source_url": "https://www.census.gov/constructionspending"},
        {"source_label": "Primary project disclosures", "source_url": ""},
        {"source_label": "Microsoft FY2026 Q3 AI disclosure", "source_url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast"},
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
        {"source_label": "Deduplicated campus records", "source_url": ""},
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
        {"source_label": "U.S. Drought Monitor / NOAA NCEI", "source_url": "https://www.ncei.noaa.gov/pub/data/nidis/geojson/state/stateranks/"},
        {"source_label": "U.S. EIA", "source_url": "https://www.eia.gov/"},
        {"source_label": "Data-center campus records", "source_url": ""},
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
        {"source_label": "Alphabet AI serving economics", "source_url": "https://abc.xyz/investor/events/event-details/2026/2025-Q4-Earnings-Call-2026-Dr_C033hS6/default.aspx"},
    ),
    "adaptation": (
        {"source_label": "Real-Time Population Survey via FRED", "source_url": "https://fred.stlouisfed.org/release?rid=524"},
        {"source_label": "U.S. Census BTOS", "source_url": "https://www.census.gov/hfp/btos/"},
        {"source_label": "Microsoft FY2026 Q3 AI disclosure", "source_url": "https://www.microsoft.com/en-us/investor/earnings/FY-2026-Q3/press-release-webcast"},
        {"source_label": "OpenAI business scale disclosure", "source_url": "https://openai.com/index/a-business-that-scales-with-the-value-of-intelligence/"},
        {"source_label": "Alphabet Q2 2026 AI and Cloud disclosure", "source_url": "https://abc.xyz/investor/events/event-details/2026/2026-Q2-Earnings-Call-2026-GgTAq7Is0z/default.aspx"},
    ),
}


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
    events = [
        dict(item)
        for item in context_payload.get("events", []) or []
        if isinstance(item, dict)
        and str(item.get("verification_status") or item.get("status") or "")
        .strip()
        .lower()
        != "no_match"
    ][:2]
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
        if pd.notna(top10) else "the top-ten market-value share is n/a"
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


def build_finance_read(regime_metrics: dict, fred_data: dict, nfci_history, debt_markets_data: dict, commercialization_data: dict | None = None) -> dict:
    borrower = _num((regime_metrics or {}).get("Borrower Strain"))
    lender = _num((regime_metrics or {}).get("Lender Strain"))
    funding = ((regime_metrics or {}).get("Deployment Funding Mix", {}) or {}).get("current", {}) or {}
    internal = _num(funding.get("internal_funding_coverage"))
    cash_runway = _num(funding.get("cash_reserve_coverage_years"))
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
    microsoft_ai_arr = _commercial_metric(commercialization_data, "Microsoft", "Annual revenue run rate")
    microsoft_ai_growth = _commercial_metric(commercialization_data, "Microsoft", "Annual revenue run-rate growth")
    openai_arr = _commercial_metric(commercialization_data, "OpenAI", "Annualized revenue run rate")
    alphabet_backlog = _commercial_metric(commercialization_data, "Alphabet", "Backlog")

    if (pd.notna(borrower) and borrower >= 35) or (pd.notna(lender) and lender >= 35):
        headline = "Financing strain is becoming material."
    elif pd.notna(internal) and internal >= 1 and pd.notna(commitments) and commitments >= 2:
        headline = "Covered firms fund current CapEx internally; forward commitments are much larger."
    elif pd.notna(dpi) and dpi >= 1 and pd.notna(internal) and internal >= 1:
        headline = "Covered firms self-fund current CapEx; mature observed funds are realizing value."
    elif pd.notna(dpi) and dpi < 0.5 and pd.notna(rvpi) and rvpi >= 1:
        headline = "Private-market value remains concentrated in unrealized NAV."
    elif pd.notna(nfci_value) and nfci_value < 0 and pd.notna(borrower) and borrower < 20 and pd.notna(lender) and lender < 20:
        headline = "Financial conditions remain broadly supportive."
    elif pd.notna(internal) and internal < 1:
        headline = "Capital deployment is leaning on external funding."
    else:
        headline = "Funding conditions are mixed but manageable."

    funding_parts = []
    if pd.notna(internal):
        funding_parts.append(f"internal cash flow covers {internal:.2f}x current capital spending")
    if pd.notna(cash_runway):
        funding_parts.append(f"cash reserves cover {cash_runway:.2f} years at that pace")
    if pd.notna(commitments):
        funding_parts.append(f"forward commitments equal {commitments:.2f}x current spending")
    funding_clause = "; ".join(funding_parts) if funding_parts else "funding coverage is n/a"
    funding_clause = funding_clause[:1].upper() + funding_clause[1:]
    realization_clause = (
        f"the mature public-LP technology cohort has returned {dpi:.2f}x paid-in capital and retains {rvpi:.2f}x at NAV"
        if pd.notna(dpi) and pd.notna(rvpi) else "private-capital realization is n/a"
    )
    condition_clause = (
        f"NFCI is {nfci_value:+.2f} and borrower/lender strain are {borrower:+.1f}/{lender:+.1f}"
        if pd.notna(nfci_value) and pd.notna(borrower) and pd.notna(lender)
        else "the combined financial-condition reading is n/a"
    )
    commercial_clause = (
        f"AI revenue disclosures have reached ${microsoft_ai_arr:.0f}B at Microsoft and more than ${openai_arr:.0f}B at OpenAI"
        if pd.notna(microsoft_ai_arr) and pd.notna(openai_arr)
        else "commercial-revenue disclosure remains selective"
    )
    summary = _sentence(f"{funding_clause}; {realization_clause}", commercial_clause, condition_clause)
    if pd.notna(realized_share) and realized_share < 0.45:
        watchpoint = "Watch whether private-fund distributions begin to convert marked value into returned capital."
    elif pd.notna(commitments) and commitments >= 2:
        watchpoint = "Watch whether forward commitments begin to outrun internal funding and cash reserves."
    elif pd.notna(nfci_change) and nfci_change > 0.1:
        watchpoint = "Watch recent financial-condition tightening for confirmation in borrower and bond-market stress."
    else:
        watchpoint = "Watch younger private vintages for improving DPI without a deterioration in credit conditions."

    valid = sum(pd.notna(v) for v in [borrower, lender, internal, cash_runway, commitments, debt_pulse, nfci_value, cmdi, dpi, tvpi, microsoft_ai_arr, openai_arr, alphabet_backlog])
    realization_imbalance = abs(0.5 - realized_share) * 70 if pd.notna(realized_share) else 0
    importance = max(
        abs(borrower) if pd.notna(borrower) else 0,
        abs(lender) if pd.notna(lender) else 0,
        max(0, (1 - internal) * 45) if pd.notna(internal) else 0,
        min(75, max(0, commitments - 1) * 25) if pd.notna(commitments) else 0,
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
        {
            "score": 63 + min(20, (microsoft_ai_growth / 10 if pd.notna(microsoft_ai_growth) else 0)),
            "kind": "commercial",
            "text": f"Microsoft reports ${microsoft_ai_arr:.0f}B of AI annualized revenue, up {microsoft_ai_growth:.0f}% year over year, while OpenAI reports more than ${openai_arr:.0f}B." if pd.notna(microsoft_ai_arr) and pd.notna(microsoft_ai_growth) and pd.notna(openai_arr) else commercial_clause,
        },
    ]
    return _read(
        "finance", headline, summary, watchpoint,
        confidence=_confidence(valid, 13), importance=importance,
        signals={
            "borrower_strain": borrower, "lender_strain": lender,
            "internal_funding_coverage": internal, "forward_commitment_load": commitments,
            "cash_reserve_coverage_years": cash_runway,
            "debt_financing_pulse": debt_pulse, "nfci": nfci_value,
            "nfci_change": nfci_change, "bond_distress": cmdi,
            "private_capital_dpi": dpi, "private_capital_rvpi": rvpi,
            "private_capital_tvpi": tvpi, "private_capital_realized_share": realized_share,
            "private_capital_mature_funds": private_funds,
            "microsoft_ai_arr_b": microsoft_ai_arr,
            "microsoft_ai_arr_growth_pct": microsoft_ai_growth,
            "openai_arr_b": openai_arr,
            "alphabet_cloud_backlog_b": alphabet_backlog,
        },
        highlights=highlights,
    )


def build_compute_read(infrastructure_data: dict, commercialization_data: dict | None = None) -> dict:
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
    critical = compute.get("critical_supply_chain", {}) or {}
    covered_layers = int(critical.get("covered_layers", 0) or 0)
    critical_layers = int(critical.get("critical_layers", 0) or 0)
    core_ai_sites = int(critical.get("core_ai_sites", 0) or 0)
    core_ai_capex = _num(critical.get("core_ai_capex_usd_b"))
    available_compute_gw = _commercial_metric(commercialization_data, "OpenAI", "Available compute")
    serving_cost_reduction = _commercial_metric(commercialization_data, "Alphabet", "Serving unit-cost reduction")

    strongest_growth = np.nanmax([computer_growth, semiconductor_growth, investment_growth]) if any(pd.notna(v) for v in [computer_growth, semiconductor_growth, investment_growth]) else np.nan
    if pd.notna(strongest_growth) and strongest_growth >= 0.08:
        headline = "Compute-related production and investment indicators are expanding quickly."
    elif pd.notna(strongest_growth) and strongest_growth > 0:
        headline = "Compute-related indicators are expanding at a measured pace."
    elif pd.notna(strongest_growth):
        headline = "Compute production is soft despite the buildout pipeline."
    else:
        headline = "Compute production data are n/a."
    growth_bits = []
    if pd.notna(computer_growth): growth_bits.append(f"computer output {computer_growth * 100:+.1f}%")
    if pd.notna(semiconductor_growth): growth_bits.append(f"semiconductor output {semiconductor_growth * 100:+.1f}%")
    if pd.notna(investment_growth): growth_bits.append(f"information-processing investment {investment_growth * 100:+.1f}%")
    summary = _sentence(
        "Year-over-year readings show " + ", ".join(growth_bits) if growth_bits else "Current production growth is n/a",
        f"Announced domestic projects cover {sites} sites and ${capex:.1f}B of expected investment" if sites and pd.notna(capex) else f"Announced domestic projects cover {sites} sites" if sites else "No announced domestic project total is available",
        f"Announced projects span {covered_layers} of {critical_layers} AI supply-chain layers, while one provider reports lower serving costs as physical capacity expands" if critical_layers and pd.notna(serving_cost_reduction) else f"Announced projects span {covered_layers} of {critical_layers} AI supply-chain layers" if critical_layers else "No supply-chain layer total is available",
    )
    avg_util = np.nanmean([v for v in [computer_util, semiconductor_util] if pd.notna(v)]) if any(pd.notna(v) for v in [computer_util, semiconductor_util]) else np.nan
    watchpoint = "Watch whether manufacturing utilization rises with the project pipeline rather than leaving capacity ahead of realized demand." if pd.notna(avg_util) and avg_util < 80 else "Watch whether output growth can hold as manufacturing utilization tightens."
    valid = sum(pd.notna(v) for v in [computer_growth, semiconductor_growth, computer_util, semiconductor_util, investment_growth, capex, core_ai_capex, available_compute_gw, serving_cost_reduction])
    importance = max(abs(strongest_growth * 100) if pd.notna(strongest_growth) else 0, min(capex / 5, 35) if pd.notna(capex) else 0)
    return _read(
        "compute", headline, summary, watchpoint,
        confidence=_confidence(valid, 9), importance=importance,
        signals={"computer_growth": computer_growth, "semiconductor_growth": semiconductor_growth, "computer_utilization": computer_util, "semiconductor_utilization": semiconductor_util, "investment_growth": investment_growth, "project_capex_b": capex, "project_sites": sites, "critical_layers_covered": covered_layers, "critical_layers_total": critical_layers, "core_ai_sites": core_ai_sites, "core_ai_capex_b": core_ai_capex, "available_compute_gw": available_compute_gw, "serving_cost_reduction_pct": serving_cost_reduction},
        highlights=[
            {"score": 56 + min(25, importance / 2), "kind": "physical", "text": f"Compute buildout spans {sites} announced manufacturing sites and ${capex:.1f}B of expected investment." if sites and pd.notna(capex) else headline},
            {"score": 60 + covered_layers * 4, "kind": "physical", "text": f"Announced domestic projects span {covered_layers} of {critical_layers} defined AI supply-chain layers, including {core_ai_sites} core-AI sites." if critical_layers else headline},
        ],
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
        headline = "National data-center totals are n/a."

    broad_clause = f"The national estimate includes {operating:,} operating facilities and {development:,} in development" if operating or development else "National facility counts are n/a"
    tracker_clause = (
        f"Published project records include {tracked_pipeline:,} active pipeline sites with {pipeline_capacity_gw:.1f} GW of capacity, versus {operating_capacity_gw:.1f} GW across operating sites"
        if tracked_pipeline and pd.notna(pipeline_capacity_gw) and pd.notna(operating_capacity_gw)
        else "Published pipeline capacity is n/a"
    )
    summary = _sentence(broad_clause, tracker_clause)
    watchpoint = "Watch whether proposed and approved projects convert into energized capacity with sufficient grid, transport, water, and community support rather than remaining published capacity on paper."
    valid = sum([bool(operating or development), pd.notna(ratio), bool(tracked_pipeline), pd.notna(pipeline_capacity_gw), pd.notna(canonical_coverage)])
    importance = min(90, (ratio * 45 if pd.notna(ratio) else 0) + (min(pipeline_capacity_gw / 8.0, 35) if pd.notna(pipeline_capacity_gw) else 0))
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
            "text": f"The U.S. footprint includes {development:,} facilities in development, while active project records carry {pipeline_capacity_gw:.1f} GW of published capacity." if development and pd.notna(pipeline_capacity_gw) else headline,
        }],
    )


def build_connectivity_read(connectivity_data: dict, infrastructure_data: dict | None = None) -> dict:
    payload = connectivity_data or ((infrastructure_data or {}).get("connectivity", {}) or {})
    national = payload.get("national_summary", {}) or {}
    coverage = payload.get("coverage", {}) or {}
    active_ixps = _num(national.get("Active IXPs"))
    reported_members = _num(national.get("Combined Reported Members"))
    licensed_systems = _num(national.get("U.S. International Submarine Cable Systems"))
    catalog_systems = _num(national.get("U.S.-Connected Cable Catalog Entries"))
    future_systems = _num(national.get("Future / Current-Year Cable Entries"))
    landing_markets = _num(national.get("Selected Landing Markets"))
    facility_rows = _num(national.get("PeeringDB Facilities"))
    facility_floor = _num(national.get("PeeringDB Facility Coverage Floor"))
    middle_mile_miles = _num(national.get("Middle-Mile New Fiber Miles"))
    middle_mile_awards = _num(national.get("Middle-Mile Award Records"))
    mismatch_states = _num(coverage.get("mismatch_states"))
    campuses_screened = _num(coverage.get("campuses_screened"))
    centers_with_ixp = _num(national.get("Population Centers With IXP"))
    centers_total = _num(national.get("Population Centers Over 300k"))

    if pd.notna(mismatch_states) and mismatch_states > 0 and pd.notna(middle_mile_miles):
        headline = "Transport depth is expanding, but compute-network mismatches remain visible."
    elif pd.notna(active_ixps) and active_ixps >= 150 and pd.notna(catalog_systems):
        headline = "The national transport layer is broad, with uneven regional depth."
    elif pd.notna(active_ixps):
        headline = "Public interconnection evidence is substantial but geographically uneven."
    else:
        headline = "National connectivity totals are n/a."

    ixp_clause = f"PeeringDB reports {active_ixps:.0f} active IXPs and {reported_members:.0f} memberships" if pd.notna(active_ixps) and pd.notna(reported_members) else "National IXP totals are n/a"
    cable_clause = f"Published records list {catalog_systems:.0f} U.S.-connected cable entries across {landing_markets:.0f} selected landing markets, while the FCC reports {licensed_systems:.0f} licensed international systems" if pd.notna(catalog_systems) and pd.notna(landing_markets) and pd.notna(licensed_systems) else "Submarine-system and landing-market totals are n/a"
    terrestrial_clause = f"Federal middle-mile awards support more than {middle_mile_miles:,.0f} new fiber miles across {middle_mile_awards:.0f} awards" if pd.notna(middle_mile_miles) and pd.notna(middle_mile_awards) else "Middle-mile award totals are n/a"
    mismatch_clause = f"{mismatch_states:.0f} states combine published data-center development with limited visible interconnection depth" if pd.notna(mismatch_states) else "The capacity-to-connectivity state count is n/a"
    summary = _sentence(ixp_clause, cable_clause, terrestrial_clause, mismatch_clause)
    watchpoint = "Watch whether high-capacity development markets gain deeper interconnection, terrestrial backhaul, and independently evidenced routes—and whether disclosed capacity becomes activated transport rather than theoretical reach."
    values = [active_ixps, reported_members, licensed_systems, catalog_systems, future_systems, landing_markets, middle_mile_miles, middle_mile_awards, mismatch_states, campuses_screened, centers_with_ixp, centers_total]
    valid = sum(pd.notna(value) for value in values)
    importance = min(94, (mismatch_states * 7 if pd.notna(mismatch_states) else 0) + (future_systems * 1.5 if pd.notna(future_systems) else 0) + (middle_mile_miles / 1000 if pd.notna(middle_mile_miles) else 0))
    facility_measure = facility_rows if pd.notna(facility_rows) and facility_rows > 0 else facility_floor
    return _read(
        "connectivity", headline, summary, watchpoint,
        confidence=_confidence(valid, 12), importance=importance,
        signals={
            "active_ixps": active_ixps,
            "combined_ixp_members": reported_members,
            "international_submarine_cable_systems": licensed_systems,
            "us_connected_cable_catalog_entries": catalog_systems,
            "future_or_current_year_cable_entries": future_systems,
            "selected_landing_markets": landing_markets,
            "interconnection_facilities_or_floor": facility_measure,
            "middle_mile_new_fiber_miles": middle_mile_miles,
            "middle_mile_award_records": middle_mile_awards,
            "high_capacity_low_public_connectivity_states": mismatch_states,
            "campuses_screened": campuses_screened,
            "population_centers_with_ixp": centers_with_ixp,
            "population_centers_total": centers_total,
        },
        highlights=[
            {
                "score": 66 + min(22, (future_systems or 0) * 1.5),
                "kind": "connectivity",
                "text": f"Published records include {active_ixps:.0f} active IXPs, {catalog_systems:.0f} U.S.-connected cable entries, and more than {middle_mile_miles:,.0f} federally supported middle-mile fiber miles." if pd.notna(active_ixps) and pd.notna(catalog_systems) and pd.notna(middle_mile_miles) else headline,
            },
            {
                "score": 70 + min(20, (mismatch_states or 0) * 4),
                "kind": "constraint",
                "text": f"{mismatch_states:.0f} states with published data-center development have limited public interconnection depth, keeping transport conversion a live regional constraint." if pd.notna(mismatch_states) and mismatch_states > 0 else "Public transport depth remains uneven across development markets.",
            },
        ],
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
    facilities_frame = (water_data or {}).get("facility_context")
    state_profile = state_water_exposure_profile(
        facilities_frame if isinstance(facilities_frame, pd.DataFrame) else pd.DataFrame(),
        (water_data or {}).get("usgs_state_categories"),
    )
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
    direct_share = direct / facilities * 100.0 if facilities else np.nan

    d2 = pd.to_numeric(state_profile.get("D2+ Area Percent"), errors="coerce") if not state_profile.empty else pd.Series(dtype=float)
    capacity = pd.to_numeric(state_profile.get("Published Capacity MW"), errors="coerce") if not state_profile.empty else pd.Series(dtype=float)
    severe_mask = d2.gt(0)
    material_mask = d2.ge(25)
    drought_states = int(severe_mask.sum())
    material_states = int(material_mask.sum())
    drought_capacity_gw = _num(capacity.loc[severe_mask].sum(min_count=1) / 1000.0) if not capacity.empty else np.nan
    material_capacity_gw = _num(capacity.loc[material_mask].sum(min_count=1) / 1000.0) if not capacity.empty else np.nan
    highest = state_profile.iloc[0] if not state_profile.empty else pd.Series(dtype=object)
    highest_state = str(highest.get("State") or "")
    highest_d2 = _num(highest.get("D2+ Area Percent"))

    if material_states and pd.notna(material_capacity_gw) and material_capacity_gw > 0:
        headline = "Large data-center pipelines overlap active water stress in several states."
    elif drought_states:
        headline = "Water exposure is local, uneven, and lightly disclosed."
    elif facilities and direct_share < 10:
        headline = "Facility-level water disclosure remains sparse."
    else:
        headline = "Water exposure varies sharply by location and cooling design."

    summary_text = _sentence(
        f"{material_states} mapped states have at least one-quarter of their area in D2-or-worse drought, covering {material_capacity_gw:.1f} GW of published data-center capacity" if material_states and pd.notna(material_capacity_gw) else f"{drought_states} mapped states report some D2-or-worse drought area" if drought_states else "No D2-or-worse state overlap appears in the July 2026 snapshot",
        f"{direct:,} of {facilities:,} facilities carry direct water evidence and {quantified:,} quantify annual withdrawal or consumption" if facilities else "Facility-linked water totals are n/a",
        f"The national comparison places crop irrigation at {irrigation:.1f}, thermoelectric power at {thermoelectric_2020:.1f}, and public supply at {public_supply:.1f} billion gallons per day" if all(pd.notna(v) for v in [irrigation, thermoelectric_2020, public_supply]) else "National competing-use totals are n/a",
    )
    watchpoint = "Next signals: quantified campus use, reclaimed-water delivery, utility capacity, cooling design, and local infrastructure costs."
    values_for_confidence = [irrigation, thermoelectric_2020, public_supply, withdrawal, consumption, direct_share, drought_capacity_gw, material_capacity_gw, highest_d2]
    valid = sum(pd.notna(v) for v in values_for_confidence)
    importance = max(
        48.0,
        min(80.0, material_capacity_gw / 150.0) if pd.notna(material_capacity_gw) else 0.0,
        55.0 + min(20.0, highest_d2 / 5.0) if pd.notna(highest_d2) else 0.0,
    )
    return _read(
        "water", headline, summary_text, watchpoint,
        confidence=_confidence(valid, len(values_for_confidence)), importance=importance,
        signals={
            "irrigation_withdrawal_bgal_day_2020": irrigation,
            "thermoelectric_withdrawal_bgal_day_2020": thermoelectric_2020,
            "public_supply_withdrawal_bgal_day_2020": public_supply,
            "thermoelectric_reported_withdrawal_bgal_day_2024": withdrawal,
            "thermoelectric_reported_consumption_bgal_day_2024": consumption,
            "mapped_facilities": facilities,
            "direct_evidence_records": direct,
            "quantified_use_records": quantified,
            "direct_evidence_share_pct": direct_share,
            "states_with_d2_area": drought_states,
            "states_with_25pct_d2_area": material_states,
            "published_capacity_in_d2_states_gw": drought_capacity_gw,
            "published_capacity_in_25pct_d2_states_gw": material_capacity_gw,
            "highest_d2_state": highest_state,
            "highest_d2_area_pct": highest_d2,
        },
        highlights=[{
            "score": 66 + min(20, material_states * 2),
            "kind": "resource",
            "text": (
                f"{material_states} mapped states combine material D2-or-worse drought area with {material_capacity_gw:.1f} GW of published data-center capacity; {direct_share:.1f}% of facilities have direct water records."
                if material_states and pd.notna(material_capacity_gw) and pd.notna(direct_share) else headline
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

    outcomes = queue_outcome_snapshot((energy_data or {}).get("queue_outcomes_summary"))
    reserves = reserve_margin_profile((energy_data or {}).get("reliability_reserve_margins"))
    _, duration_summary = storage_duration_profile((energy_data or {}).get("operating_generators"))

    queue_gw = _num(development.get("headline_queue_gw"))
    advanced = _num(development.get("advanced_share"))
    historical_operational = _num(outcomes.get("Historical Operational Share Percent"))
    historical_withdrawn = _num(outcomes.get("Historical Withdrawn Share Percent"))
    median_years = _num(outcomes.get("Median Request to COD Years"))
    agreement_gw = _num(outcomes.get("Draft or Executed IA GW"))
    weighted_duration = _num(duration_summary.get("weighted_duration_hours"))
    four_hour_share = _num(duration_summary.get("four_hour_plus_share"))
    power_growth = _num(((((infrastructure_data or {}).get("series", {}) or {}).get("Electric Power Construction", {}) or {}).get("yoy_growth")))

    extreme = pd.to_numeric(reserves.get("Extreme Conditions Margin Percent"), errors="coerce") if not reserves.empty else pd.Series(dtype=float)
    lowest = reserves.loc[extreme.idxmin()] if not extreme.dropna().empty else pd.Series(dtype=object)
    lowest_area = str(lowest.get("Assessment Area") or "")
    lowest_margin = _num(lowest.get("Extreme Conditions Margin Percent"))
    negative_areas = int(extreme.lt(0).sum()) if not extreme.empty else 0
    under_five_areas = int(extreme.lt(5).sum()) if not extreme.empty else 0

    if pd.notna(historical_operational) and historical_operational < 20 and pd.notna(median_years) and median_years >= 5:
        headline = "Grid conversion remains far behind project demand."
    elif pd.notna(lowest_margin) and lowest_margin < 0:
        headline = "Summer reliability tightens sharply under extreme conditions."
    elif pd.notna(queue_gw) and pd.notna(advanced) and advanced < 30:
        headline = "The connection pipeline is large, but most capacity remains early-stage."
    elif pd.notna(queue_gw):
        headline = "Grid delivery remains the main conversion test for proposed capacity."
    else:
        headline = "Grid-delivery data are n/a."

    summary_text = _sentence(
        f"The active interconnection pipeline exceeds {queue_gw:.0f} GW, with {advanced:.1f}% in executed-agreement or construction stages" if pd.notna(queue_gw) and pd.notna(advanced) else "Queue scale and maturity are n/a",
        f"Among 2000–2020 submissions, {historical_operational:.0f}% reached operation and {historical_withdrawn:.0f}% withdrew; projects completed in 2025 took more than {median_years:.0f} years from request to operation" if all(pd.notna(v) for v in [historical_operational, historical_withdrawn, median_years]) else "Historical conversion totals are n/a",
        f"{lowest_area} falls to {lowest_margin:+.1f}% under NERC's extreme summer case, with {negative_areas} U.S. assessment area below zero" if pd.notna(lowest_margin) else "Seasonal reserve margins are n/a",
        f"Operating batteries average {weighted_duration:.1f} hours, and {four_hour_share:.1f}% of reported power capacity is rated for four hours or more" if pd.notna(weighted_duration) and pd.notna(four_hour_share) else "Operating storage duration is n/a",
    )
    watchpoint = "Next signals: executed agreements, construction-stage capacity, withdrawals, transmission readiness, and projects reaching commercial operation."
    values = [queue_gw, advanced, storage_gw, historical_operational, historical_withdrawn, median_years, agreement_gw, lowest_margin, weighted_duration, four_hour_share, power_growth]
    valid = sum(pd.notna(value) for value in values)
    importance = max(
        50 - advanced if pd.notna(advanced) else 0,
        min(queue_gw / 25, 70) if pd.notna(queue_gw) else 0,
        75 - historical_operational if pd.notna(historical_operational) else 0,
        abs(min(lowest_margin, 0)) * 8 + 60 if pd.notna(lowest_margin) and lowest_margin < 0 else 0,
    )
    return _read(
        "grid_storage", headline, summary_text, watchpoint,
        confidence=_confidence(valid, len(values)), importance=importance,
        signals={
            "queue_gw": queue_gw,
            "advanced_share": advanced,
            "storage_queue_gw": storage_gw,
            "historical_operational_pct": historical_operational,
            "historical_withdrawn_pct": historical_withdrawn,
            "median_request_to_cod_years": median_years,
            "draft_or_executed_ia_gw": agreement_gw,
            "lowest_extreme_margin_pct": lowest_margin,
            "lowest_extreme_margin_area": lowest_area,
            "negative_extreme_margin_areas": negative_areas,
            "extreme_margin_under_5pct_areas": under_five_areas,
            "operating_storage_weighted_duration_hours": weighted_duration,
            "operating_storage_four_hour_plus_share_pct": four_hour_share,
            "electric_power_construction_growth": power_growth,
        },
        highlights=[{
            "score": 72 + max(0, 20 - historical_operational) if pd.notna(historical_operational) else 64,
            "kind": "energy",
            "text": (
                f"Only {historical_operational:.0f}% of the 2000–2020 queue cohort reached operation, while the active pipeline now exceeds {queue_gw:.0f} GW and median completion time has stretched beyond {median_years:.0f} years."
                if all(pd.notna(v) for v in [historical_operational, queue_gw, median_years]) else headline
            ),
        }],
    )

def _latest_row(frame: pd.DataFrame | None, series: str) -> dict:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    rows = frame.loc[frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq(series)]
    return rows.iloc[-1].to_dict() if not rows.empty else {}


def build_workforce_read(workforce_data: dict) -> dict:
    matrix = (workforce_data or {}).get("transmission_matrix")
    if not isinstance(matrix, pd.DataFrame) or matrix.empty:
        return _read(
            "workforce",
            "Workforce data are n/a.",
            "No current employment, real-earnings, or labor-flow readings are available.",
            "Next update: BLS employment, earnings, openings, hires, quits, and layoffs.",
            confidence="Low", importance=0, signals={}, highlights=[],
        )

    exposure = (workforce_data or {}).get("exposure_summary", {}) or {}
    occupation_count = _num(exposure.get("occupations"))
    median_software_exposure = _num(exposure.get("median_llm_software_exposure"))
    high_exposure_share = _num(exposure.get("share_at_least_50_pct"))
    employment = pd.to_numeric(matrix.get("Employment YoY"), errors="coerce")
    real_earnings = pd.to_numeric(matrix.get("Real earnings YoY"), errors="coerce")
    layoffs = pd.to_numeric(matrix.get("Layoffs rate"), errors="coerce")
    openings = pd.to_numeric(matrix.get("Openings rate"), errors="coerce")
    positive_jobs = int((employment > 0).sum())
    positive_real = int((real_earnings > 0).sum())
    strongest_idx = employment.idxmax() if employment.notna().any() else None
    weakest_idx = employment.idxmin() if employment.notna().any() else None
    strongest = matrix.loc[strongest_idx].to_dict() if strongest_idx is not None else {}
    weakest = matrix.loc[weakest_idx].to_dict() if weakest_idx is not None else {}

    if positive_jobs >= 3 and positive_real >= 3:
        headline = "Observed labor-market transmission is broadening with worker purchasing-power gains."
    elif positive_jobs >= 2 and positive_real < positive_jobs:
        headline = "Employment transmission is broader than worker capture."
    elif positive_jobs <= 1 and pd.notna(layoffs.max()) and layoffs.max() >= 2:
        headline = "Theoretical exposure is broad, while observed labor demand has softened."
    else:
        headline = "Theoretical exposure is broad, but observed workforce transmission remains uneven."

    strongest_name = str(strongest.get("Channel", "the strongest channel"))
    weakest_name = str(weakest.get("Channel", "the weakest channel"))
    strongest_growth = _num(strongest.get("Employment YoY"))
    weakest_growth = _num(weakest.get("Employment YoY"))
    summary_text = _sentence(
        f"The static exposure benchmark includes {int(occupation_count):,} occupations, with a median {median_software_exposure:.1f}% of tasks exposed to LLMs or LLM-powered software" if pd.notna(occupation_count) and pd.notna(median_software_exposure) else "Theoretical occupation exposure is n/a",
        f"Employment is growing in {positive_jobs} of 4 directly relevant channels, while real earnings are rising in {positive_real} of 4",
        f"{strongest_name} leads at {strongest_growth:+.1f}% year over year and {weakest_name} trails at {weakest_growth:+.1f}%" if pd.notna(strongest_growth) and pd.notna(weakest_growth) else "Channel leadership is n/a",
        f"Supporting labor markets currently span {openings.min():.1f}% to {openings.max():.1f}% openings rates and {layoffs.min():.1f}% to {layoffs.max():.1f}% layoffs rates" if openings.notna().any() and layoffs.notna().any() else "Labor-flow ranges are n/a",
    )
    watchpoint = "Watch whether employment and real earnings broaden together, and whether openings and hires recover without a corresponding rise in layoffs and discharges."
    valid = int(employment.notna().sum() + real_earnings.notna().sum() + openings.notna().sum() + layoffs.notna().sum())
    valid += int(pd.notna(median_software_exposure))
    importance = max(
        [abs(float(value)) for value in employment.dropna().tolist() + real_earnings.dropna().tolist()] + [0]
    )
    return _read(
        "workforce", headline, summary_text, watchpoint,
        confidence=_confidence(valid, 17), importance=importance * 10,
        signals={
            "employment_breadth": positive_jobs,
            "real_earnings_breadth": positive_real,
            "strongest_channel_growth": strongest_growth,
            "weakest_channel_growth": weakest_growth,
            "max_layoff_rate": float(layoffs.max()) if layoffs.notna().any() else np.nan,
            "max_openings_rate": float(openings.max()) if openings.notna().any() else np.nan,
            "occupation_exposure_count": occupation_count,
            "median_llm_software_exposure_pct": median_software_exposure,
            "high_exposure_occupation_share_pct": high_exposure_share,
        },
        highlights=[{
            "score": 64 + min(20, importance * 4),
            "kind": "labor",
            "text": f"A static benchmark finds broad theoretical task exposure, while employment is growing in {positive_jobs} of 4 AI-linked channels and real purchasing-power earnings are rising in {positive_real} of 4.",
        }],
    )

def build_economic_impact_read(economic_impact_data: dict, commercialization_data: dict | None = None) -> dict:
    productivity = _num(((economic_impact_data or {}).get("nonfarm_productivity", {}) or {}).get("value"))
    output = _num(((economic_impact_data or {}).get("nonfarm_output", {}) or {}).get("value"))
    unit_cost = _num(((economic_impact_data or {}).get("nonfarm_unit_labor_cost", {}) or {}).get("value"))
    investment = _num(((economic_impact_data or {}).get("information_investment", {}) or {}).get("yoy"))
    capture = ((economic_impact_data or {}).get("capture_summary", {}) or {})
    real_comp = _num((capture.get("real_compensation", {}) or {}).get("yoy"))
    real_comp_since = _num((capture.get("real_compensation", {}) or {}).get("since_2020"))
    productivity_since = _num((capture.get("productivity", {}) or {}).get("since_2020"))
    labor_share_since = _num((capture.get("labor_share", {}) or {}).get("since_2020"))
    median_earnings = _num((capture.get("median_real_earnings", {}) or {}).get("YoY"))
    capture_gap = _num(capture.get("productivity_real_comp_gap"))
    group_spread = _num(capture.get("group_growth_spread_ppts"))
    microsoft_ai_arr = _commercial_metric(commercialization_data, "Microsoft", "Annual revenue run rate")
    openai_arr = _commercial_metric(commercialization_data, "OpenAI", "Annualized revenue run rate")
    alphabet_cloud_growth = _commercial_metric(commercialization_data, "Alphabet", "Revenue growth")
    openai_enterprise_share = _commercial_metric(commercialization_data, "OpenAI", "Enterprise share of revenue")

    if pd.notna(productivity) and productivity > 0 and pd.notna(real_comp) and real_comp > 0 and pd.notna(labor_share_since) and labor_share_since >= 0:
        headline = "Aggregate productivity and worker measures are both improving."
    elif pd.notna(productivity) and productivity > 0 and pd.notna(capture_gap) and capture_gap > 3:
        headline = "Aggregate productivity is improving faster than worker capture."
    elif pd.notna(investment) and investment > 10 and (pd.isna(productivity) or productivity < 1):
        headline = "Information investment is still outrunning aggregate productivity growth."
    elif pd.notna(output) and output > 0:
        headline = "Output is expanding, but broad value transmission remains mixed."
    else:
        headline = "Economic outcome data are n/a."

    summary_text = _sentence(
        f"Nonfarm-business productivity is {productivity:+.1f}% and real output is {output:+.1f}% year over year" if pd.notna(productivity) and pd.notna(output) else "Productivity or output growth is unavailable",
        f"Since 2020, productivity is {productivity_since:+.1f}% versus {real_comp_since:+.1f}% real hourly compensation, a {capture_gap:.1f}-point transmission gap" if all(pd.notna(v) for v in [productivity_since, real_comp_since, capture_gap]) else "The productivity-to-real-compensation transmission gap is unavailable",
        f"The labor-share index is {labor_share_since:+.1f}% since 2020 and median real weekly earnings are {median_earnings:+.1f}% year over year" if pd.notna(labor_share_since) and pd.notna(median_earnings) else "Labor share and median earnings are n/a",
        f"Provider disclosures show commercial scale, including ${microsoft_ai_arr:.0f}B of Microsoft AI annualized revenue and more than ${openai_arr:.0f}B at OpenAI" if pd.notna(microsoft_ai_arr) and pd.notna(openai_arr) else "Commercial validation remains selectively disclosed",
    )
    watchpoint = "Watch whether real compensation, labor share, median earnings, and demographic participation begin to close the gap with productivity as adoption broadens."
    values = [productivity, output, unit_cost, investment, real_comp, real_comp_since, productivity_since, labor_share_since, median_earnings, capture_gap, group_spread, microsoft_ai_arr, openai_arr, alphabet_cloud_growth, openai_enterprise_share]
    valid = sum(pd.notna(value) for value in values)
    importance = max(abs(capture_gap) * 5 if pd.notna(capture_gap) else 0, abs(labor_share_since) * 4 if pd.notna(labor_share_since) else 0, abs(productivity) * 8 if pd.notna(productivity) else 0)
    return _read(
        "economic_impact", headline, summary_text, watchpoint,
        confidence=_confidence(valid, len(values)), importance=importance,
        signals={
            "productivity_growth": productivity,
            "real_output_growth": output,
            "real_compensation_growth": real_comp,
            "unit_labor_cost_growth": unit_cost,
            "information_investment_growth": investment,
            "productivity_since_2020": productivity_since,
            "real_compensation_since_2020": real_comp_since,
            "productivity_real_comp_gap": capture_gap,
            "labor_share_since_2020": labor_share_since,
            "median_real_earnings_growth": median_earnings,
            "group_growth_spread_ppts": group_spread,
            "microsoft_ai_arr_b": microsoft_ai_arr,
            "openai_arr_b": openai_arr,
            "alphabet_cloud_growth_pct": alphabet_cloud_growth,
            "openai_enterprise_share_pct": openai_enterprise_share,
        },
        highlights=[
            {
                "score": 68 + min(20, abs(capture_gap) if pd.notna(capture_gap) else 0),
                "kind": "distribution",
                "text": f"Productivity has risen {productivity_since:+.1f}% since 2020 versus {real_comp_since:+.1f}% real compensation, while the labor-share index is {labor_share_since:+.1f}%." if all(pd.notna(v) for v in [productivity_since, real_comp_since, labor_share_since]) else headline,
            },
            {
                "score": 62 + min(20, alphabet_cloud_growth / 8 if pd.notna(alphabet_cloud_growth) else 0),
                "kind": "commercial",
                "text": f"Provider disclosures show material commercial demand, while median real earnings are {median_earnings:+.1f}% year over year." if pd.notna(median_earnings) else "Provider revenue disclosures show growing commercial scale.",
            },
        ],
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
        headline = "Physical investment momentum is n/a."

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

def build_adaptation_read(adaptation_data: dict, commercialization_data: dict | None = None) -> dict:
    current = _num((adaptation_data or {}).get("current_use"))
    expected = _num((adaptation_data or {}).get("expected_use"))
    gap = _num((adaptation_data or {}).get("expected_adoption_gap"))
    annual = _num((adaptation_data or {}).get("annual_change"))
    consumer_overall = _num(((adaptation_data or {}).get("consumer_overall", {}) or {}).get("value"))
    consumer_personal = _num(((adaptation_data or {}).get("consumer_personal", {}) or {}).get("value"))
    consumer_work = _num(((adaptation_data or {}).get("consumer_work", {}) or {}).get("value"))
    consumer_active = _num(((adaptation_data or {}).get("consumer_active", {}) or {}).get("value"))
    consumer_daily = _num(((adaptation_data or {}).get("consumer_daily", {}) or {}).get("value"))
    chatgpt_subscribers = _commercial_metric(commercialization_data, "OpenAI", "Consumer subscribers")
    subscriber_share = _commercial_metric(commercialization_data, "OpenAI", "Implied subscriber share")
    paying_business_users = _commercial_metric(commercialization_data, "OpenAI", "Paying business users")
    gemini_enterprise_seats = _commercial_metric(commercialization_data, "Alphabet", "Paid seats")
    consumer_history = (adaptation_data or {}).get("consumer_history")
    consumer_change = np.nan
    if isinstance(consumer_history, pd.DataFrame) and not consumer_history.empty:
        overall_rows = consumer_history.loc[
            consumer_history.get("Series", pd.Series("", index=consumer_history.index)).astype(str).eq("Overall use")
        ].copy()
        overall_rows["Date"] = pd.to_datetime(overall_rows.get("Date"), errors="coerce", format="mixed")
        overall_rows["Value"] = pd.to_numeric(overall_rows.get("Value"), errors="coerce")
        overall_rows = overall_rows.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
        if len(overall_rows) >= 2:
            consumer_change = float(overall_rows.iloc[-1]["Value"] - overall_rows.iloc[0]["Value"])

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

    if pd.notna(consumer_overall) and consumer_overall >= 60 and pd.notna(current) and current < 25:
        headline = "Consumer use is broad, while employer-reported use remains selective."
    elif pd.notna(consumer_personal) and consumer_personal >= 50 and pd.notna(consumer_work) and consumer_work >= 40:
        headline = "AI use is spreading across personal life and work."
    elif pd.notna(annual) and annual >= 2:
        headline = "Employer-reported AI use is broadening at a meaningful pace."
    elif pd.notna(current) and pd.notna(expected) and expected - current >= 5:
        headline = "Expected employer use remains higher than current reported use."
    elif pd.notna(current):
        headline = "Measured AI adoption is advancing unevenly."
    else:
        headline = "Adoption data are n/a."

    summary = _sentence(
        (
            f"Any-purpose use among adults age 18–64 is {consumer_overall:.1f}%, including {consumer_personal:.1f}% outside work and {consumer_work:.1f}% at work"
            if all(pd.notna(v) for v in [consumer_overall, consumer_personal, consumer_work])
            else "Consumer and worker adoption is n/a"
        ),
        (
            f"Employer-business use is {current:.1f}% and expected six-month use is {expected:.1f}%, leaving a {gap:.1f}-point intention gap"
            if all(pd.notna(v) for v in [current, expected, gap])
            else "Current and expected business use is n/a"
        ),
        (
            f"Paid demand is visible but narrower than reach, with more than {chatgpt_subscribers:.0f} million ChatGPT subscribers and {paying_business_users:.0f} million paying OpenAI business users"
            if pd.notna(chatgpt_subscribers) and pd.notna(paying_business_users)
            else "Paid-demand disclosure remains selective"
        ),
    )
    watchpoint = "Watch whether broad consumer use converts into paid engagement and whether expected employer use becomes reported current use."
    valid = sum(pd.notna(v) for v in [current, expected, gap, annual, breadth, consumer_overall, consumer_personal, consumer_work, consumer_active, consumer_daily, chatgpt_subscribers, subscriber_share, paying_business_users, gemini_enterprise_seats])
    importance = max(
        abs(annual) * 8 if pd.notna(annual) else 0,
        gap * 4 if pd.notna(gap) else 0,
        abs(consumer_change) * 5 if pd.notna(consumer_change) else 0,
    )
    return _read(
        "adaptation", headline, summary, watchpoint,
        confidence=_confidence(valid, 14), importance=importance,
        signals={
            "current_use": current,
            "expected_use": expected,
            "expected_gap": gap,
            "annual_change": annual,
            "consumer_overall": consumer_overall,
            "consumer_personal": consumer_personal,
            "consumer_work": consumer_work,
            "consumer_active": consumer_active,
            "consumer_daily": consumer_daily,
            "consumer_change": consumer_change,
            "sector_coverage": breadth,
            "leading_sector": top_sector,
            "leading_sector_use": top_value,
            "chatgpt_subscribers_m": chatgpt_subscribers,
            "implied_subscriber_share_pct": subscriber_share,
            "openai_paying_business_users_m": paying_business_users,
            "gemini_enterprise_paid_seats_m": gemini_enterprise_seats,
        },
        highlights=[
            {
                "score": 58 + min(25, importance / 2),
                "kind": "adoption",
                "text": (
                    f"Generative-AI use reaches {consumer_overall:.1f}% of working-age adults, with {consumer_active:.1f}% using it in the prior week; employer-business use is {current:.1f}%."
                    if pd.notna(consumer_overall) and pd.notna(consumer_active) and pd.notna(current)
                    else headline
                ),
            },
            {
                "score": 63 + min(18, subscriber_share if pd.notna(subscriber_share) else 0),
                "kind": "commercial",
                "text": f"Paid AI demand is now visible at scale, including more than {chatgpt_subscribers:.0f} million ChatGPT subscribers and {paying_business_users:.0f} million paying OpenAI business users." if pd.notna(chatgpt_subscribers) and pd.notna(paying_business_users) else "Paid-demand disclosure remains selective.",
            },
        ],
    )


def _macro_headline(reads: dict[str, dict]) -> str:
    market = reads.get("market", {}).get("signals", {})
    data_center = reads.get("data_center", {}).get("signals", {})
    connectivity = reads.get("connectivity", {}).get("signals", {})
    grid = reads.get("grid_storage", {}).get("signals", {})
    adoption = reads.get("adaptation", {}).get("signals", {})
    impact = reads.get("economic_impact", {}).get("signals", {})
    aei = _num(market.get("aei"))
    pipeline_gw = _num(data_center.get("tracked_pipeline_capacity_gw"))
    advanced = _num(grid.get("advanced_share"))
    active_use = _num(adoption.get("consumer_active"))
    microsoft_arr = _num(impact.get("microsoft_ai_arr_b"))
    openai_arr = _num(impact.get("openai_arr_b"))
    productivity = _num(impact.get("productivity_growth"))
    capture_gap = _num(impact.get("productivity_real_comp_gap"))
    labor_share = _num(impact.get("labor_share_since_2020"))
    median_earnings = _num(impact.get("median_real_earnings_growth"))
    commercial_scale = pd.notna(microsoft_arr) and microsoft_arr >= 20 and pd.notna(openai_arr) and openai_arr >= 10
    broad_use = pd.notna(active_use) and active_use >= 40
    positive_productivity = pd.notna(productivity) and productivity > 0
    weak_capture = (
        (pd.notna(capture_gap) and capture_gap > 3)
        or (pd.notna(labor_share) and labor_share < 0)
        or (pd.notna(median_earnings) and median_earnings <= 0)
    )
    if commercial_scale and broad_use and positive_productivity and weak_capture:
        return "The AI buildout is gaining commercial scale, while broad value capture still trails."
    if commercial_scale and broad_use and positive_productivity:
        return "The AI buildout is gaining commercial scale and broader economic support."
    if commercial_scale and not positive_productivity:
        return "Leading-provider commercial demand is material, but broad economic support still trails."
    if pd.notna(advanced) and advanced < 30 and pd.notna(pipeline_gw) and pipeline_gw > 0:
        return "AI expansion is broadening, but delivery systems remain the binding test."
    if pd.notna(aei) and aei < 50 and pd.notna(pipeline_gw) and pipeline_gw > 0:
        return "Physical buildout is outrunning market validation."
    return "The AI economy is moving from buildout to the harder tests of use and value."


def _macro_narrative(reads: dict[str, dict]) -> tuple[str, str, list[dict[str, str]], str]:
    compute = reads.get("compute", {}).get("signals", {})
    data_center = reads.get("data_center", {}).get("signals", {})
    connectivity = reads.get("connectivity", {}).get("signals", {})
    grid = reads.get("grid_storage", {}).get("signals", {})
    adoption = reads.get("adaptation", {}).get("signals", {})
    impact = reads.get("economic_impact", {}).get("signals", {})

    pipeline_gw = _num(data_center.get("tracked_pipeline_capacity_gw"))
    active_ixps = _num(connectivity.get("active_ixps"))
    cable_systems = _num(connectivity.get("international_submarine_cable_systems"))
    cable_catalog = _num(connectivity.get("us_connected_cable_catalog_entries"))
    middle_mile_miles = _num(connectivity.get("middle_mile_new_fiber_miles"))
    low_depth_states = _num(connectivity.get("high_capacity_low_public_connectivity_states"))
    critical_covered = _num(compute.get("critical_layers_covered"))
    critical_total = _num(compute.get("critical_layers_total"))
    active_use = _num(adoption.get("consumer_active"))
    business_use = _num(adoption.get("current_use"))
    subscriber_share = _num(adoption.get("implied_subscriber_share_pct"))
    microsoft_arr = _num(impact.get("microsoft_ai_arr_b"))
    openai_arr = _num(impact.get("openai_arr_b"))
    productivity = _num(impact.get("productivity_growth"))
    real_compensation = _num(impact.get("real_compensation_growth"))
    capture_gap = _num(impact.get("productivity_real_comp_gap"))
    labor_share = _num(impact.get("labor_share_since_2020"))
    median_earnings = _num(impact.get("median_real_earnings_growth"))
    advanced = _num(grid.get("advanced_share"))

    commercial_scale = pd.notna(microsoft_arr) and pd.notna(openai_arr)
    broad_use = pd.notna(active_use) and active_use >= 40
    positive_productivity = pd.notna(productivity) and productivity > 0
    weak_capture = (
        (pd.notna(capture_gap) and capture_gap > 3)
        or (pd.notna(labor_share) and labor_share < 0)
        or (pd.notna(median_earnings) and median_earnings <= 0)
    )

    first = "Capital deployment and physical expansion still set the pace of the AI economy."
    if broad_use and commercial_scale:
        second = "The downstream case is strengthening: reported active use is broad and leading-provider disclosures show meaningful paid demand and revenue scale."
    elif broad_use:
        second = "Active use is broadening faster than reported paid conversion and durable revenue."
    elif commercial_scale:
        second = "Commercial scale is visible at leading providers, while societal and business use remain narrower."
    else:
        second = "Installed capacity continues to outpace reported durable use and revenue."

    if positive_productivity and weak_capture:
        third = "Productivity is improving, but real compensation, labor share, and median worker earnings show that broad value capture is not keeping pace."
    elif positive_productivity:
        third = "Productivity is improving alongside worker-capture measures, while grid conversion, network depth, and household distribution remain the next tests."
    else:
        third = "The next test is whether commercialization translates into productivity, real compensation, and broad household value faster than infrastructure burdens accumulate."
    summary = _sentence(first, second, third)

    relevance = (
        "The question is no longer only whether AI infrastructure can be financed and built. "
        "It is whether that system can connect, serve paying users efficiently, and convert private gains into durable economic value."
    )
    watchpoint = (
        "Watch whether paid adoption, productivity, and compensation broaden faster than grid conversion, connectivity gaps, and the capital burden required to support them."
    )

    evidence: list[dict[str, str]] = []
    if pd.notna(pipeline_gw):
        context = []
        if pd.notna(critical_covered) and pd.notna(critical_total):
            context.append(f"{int(critical_covered)}/{int(critical_total)} supply layers represented")
        if pd.notna(active_ixps):
            context.append(f"{int(active_ixps)} active IXPs")
        if pd.notna(cable_systems):
            context.append(f"{int(cable_systems)} licensed international cable systems")
        if pd.notna(cable_catalog):
            context.append(f"{int(cable_catalog)} U.S.-connected catalog entries")
        if pd.notna(middle_mile_miles):
            context.append(f"{int(middle_mile_miles):,}+ middle-mile fiber miles")
        evidence.append({
            "label": "Buildout & transport",
            "value": f"{pipeline_gw:.1f} GW published",
            "context": " · ".join(context) or "published development capacity",
            "reference_specs": [
                {"domain": "data_center", "source_label": "FracTracker Alliance"},
                {"domain": "connectivity", "source_label": "Internet Society Pulse / PeeringDB"},
                {"domain": "connectivity", "source_label": "FCC submarine cable records"},
                {"domain": "connectivity", "source_label": "NTIA Middle Mile Program"},
            ],
        })
    if pd.notna(active_use) or commercial_scale:
        value = f"{active_use:.1f}% active use" if pd.notna(active_use) else "Paid demand visible"
        context = []
        if pd.notna(business_use):
            context.append(f"{business_use:.1f}% business use")
        if pd.notna(microsoft_arr) and pd.notna(openai_arr):
            context.append(f"${microsoft_arr:.0f}B Microsoft AI ARR · ${openai_arr:.0f}B+ OpenAI ARR")
        elif pd.notna(subscriber_share):
            context.append(f"{subscriber_share:.1f}% rough subscriber share")
        evidence.append({
            "label": "Use & revenue",
            "value": value,
            "context": " · ".join(context) or "reported paid demand",
            "reference_specs": [
                {"domain": "adaptation", "source_label": "Real-Time Population Survey via FRED"},
                {"domain": "economic_impact", "source_label": "Microsoft FY2026 Q3 AI disclosure"},
                {"domain": "economic_impact", "source_label": "OpenAI business scale disclosure"},
            ],
        })
    if pd.notna(productivity):
        context = []
        if pd.notna(real_compensation):
            context.append(f"{real_compensation:+.1f}% real hourly compensation")
        if pd.notna(labor_share):
            context.append(f"{labor_share:+.1f}% labor-share index since 2020")
        if pd.notna(median_earnings):
            context.append(f"{median_earnings:+.1f}% median real earnings")
        if pd.notna(advanced):
            context.append(f"{advanced:.0f}% advanced queue share")
        if pd.notna(low_depth_states) and low_depth_states > 0:
            context.append(f"{int(low_depth_states)} high-capacity states with limited public IXP depth")
        evidence.append({
            "label": "Realized economy",
            "value": f"{productivity:+.1f}% productivity",
            "context": " · ".join(context) or "nonfarm business",
            "reference_specs": [
                {"domain": "economic_impact", "source_label": "BLS Labor Productivity and Costs"},
                {"domain": "economic_impact", "source_label": "BLS Current Population Survey"},
                {"domain": "grid_storage", "source_label": "Berkeley Lab Queued Up"},
            ],
        })
    return summary, relevance, evidence[:3], watchpoint

def build_macro_read(reads: dict[str, dict], current_context: dict | None = None) -> dict:
    # One anchor per lifecycle stage. Domain-local highlight scores are useful
    # inside a tab, but they are not comparable units across unrelated domains.
    lifecycle_slots = (
        ("market", "finance"),
        ("data_center", "compute", "power", "grid_storage", "connectivity", "water"),
        ("economic_impact", "adaptation", "workforce"),
    )
    selected = []
    for slot in lifecycle_slots:
        selected_item = None
        for domain in slot:
            highlights = (reads.get(domain, {}) or {}).get("highlights", []) or []
            selected_item = next(
                (
                    {**item, "domain": domain}
                    for item in highlights
                    if isinstance(item, dict) and str(item.get("text") or "").strip()
                ),
                None,
            )
            if selected_item is not None:
                break
        if selected_item is not None:
            selected.append(selected_item)

    headline = _macro_headline(reads)
    summary, relevance, evidence, watchpoint = _macro_narrative(reads)

    # Current Context is selected only from domains that actually contribute to
    # the macro synthesis.  It is never a one-item-per-tab digest.
    selected_domains = [str(item.get("domain") or "") for item in selected]
    event_candidates: list[dict[str, Any]] = []
    for domain in selected_domains:
        domain_context = (reads.get(domain, {}) or {}).get("current_context", {}) or {}
        for event in domain_context.get("events", []) or []:
            if (
                isinstance(event, dict)
                and str(event.get("verification_status") or event.get("status") or "").strip().lower() != "no_match"
                and str(event.get("source_url") or "").startswith("https://")
            ):
                event_candidates.append({**event, "domain": domain})
    if not event_candidates:
        for event in (current_context or {}).get("events", []) or []:
            if (
                isinstance(event, dict)
                and str(event.get("verification_status") or event.get("status") or "").strip().lower() != "no_match"
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

    # References follow the evidence anchors actually selected for the macro
    # narrative. First give each anchor one source, then use remaining budget
    # for secondary sources. This prevents a fixed reference list from drifting
    # away from the claims shown on the page.
    evidence_spec_groups = [
        [dict(spec) for spec in item.get("reference_specs", []) if isinstance(spec, dict)]
        for item in evidence
    ]
    ordered_specs: list[dict[str, str]] = []
    max_specs = max((len(group) for group in evidence_spec_groups), default=0)
    for index in range(max_specs):
        for group in evidence_spec_groups:
            if index < len(group):
                ordered_specs.append(group[index])
    for spec in ordered_specs:
        if len(references) >= 5:
            break
        domain = str(spec.get("domain") or "")
        source_label = str(spec.get("source_label") or "")
        domain_refs = (reads.get(domain, {}) or {}).get("references", []) or DOMAIN_REFERENCES.get(domain, ())
        candidate = next(
            (dict(ref) for ref in domain_refs if str(ref.get("source_label") or ref.get("source_name") or "") == source_label),
            None,
        )
        if candidate is None:
            continue
        key = (str(candidate.get("source_label") or candidate.get("source_name") or ""), str(candidate.get("source_url") or ""))
        if key not in source_keys:
            references.append(candidate)
            source_keys.add(key)

    for item in selected:
        if len(references) >= 5:
            break
        domain = str(item.get("domain") or "")
        domain_refs = (reads.get(domain, {}) or {}).get("references", []) or []
        static_ref = next((dict(ref) for ref in domain_refs if isinstance(ref, dict) and not ref.get("event_id")), None)
        if static_ref is None:
            continue
        key = (str(static_ref.get("source_label") or static_ref.get("source_name") or ""), str(static_ref.get("source_url") or ""))
        if key not in source_keys:
            references.append(static_ref)
            source_keys.add(key)
        if len(references) >= 5:
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
        "constraint_factors": constraints,
        "current_context": current_context or {},
        "domains": {key: value.get("headline") for key, value in reads.items()},
        "snapshot_context": {key: value.get("signals", {}) for key, value in reads.items()},
        "relevance": relevance,
        "evidence": evidence,
    })
    return macro


def build_platform_reads(
    context: DashboardContext | None = None,
    **legacy_payload,
) -> dict:
    """Build all domain Reads from one assembled application context.

    Keyword payloads remain accepted for compatibility with existing focused
    smoke checks and external callers while the application itself uses the
    typed boundary object.
    """
    if context is None:
        weekly_context = legacy_payload.pop("weekly_context", None)
        if not legacy_payload.get("current_context") and weekly_context:
            legacy_payload["current_context"] = weekly_context
        context = DashboardContext(**legacy_payload)
    reads = {
        "market": build_market_read(
            context.sector_data,
            context.dashboard_data or {},
            context.regime_metrics,
        ),
        "finance": build_finance_read(
            context.regime_metrics,
            context.fred_data,
            context.nfci_history,
            context.debt_markets_data,
            context.commercialization_data,
        ),
        "compute": build_compute_read(context.infrastructure_data, context.commercialization_data),
        "data_center": build_data_center_read(context.infrastructure_data),
        "connectivity": build_connectivity_read(context.connectivity_data, context.infrastructure_data),
        "power": build_power_domain_read(context.energy_data, context.infrastructure_data),
        "grid_storage": build_grid_storage_read(context.energy_data, context.infrastructure_data),
        "water": build_water_read(context.water_data),
        "adaptation": build_adaptation_read(context.adaptation_data, context.commercialization_data),
        "workforce": build_workforce_read(context.workforce_data),
        "economic_impact": build_economic_impact_read(context.economic_impact_data, context.commercialization_data),
    }
    context_payload = context.current_context
    by_domain = context_payload.get("by_domain", {}) or {}
    for domain in DOMAIN_ORDER:
        reads[domain] = _attach_current_context(reads[domain], by_domain.get(domain, {}))
    reads["macro"] = build_macro_read(reads, current_context=context_payload)
    return reads
