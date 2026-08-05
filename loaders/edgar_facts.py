from __future__ import annotations

import numpy as np
import pandas as pd

from config.market_clock import market_date
from loaders.edgar_archive import (
    EDGAR_MAX_ANNUAL_AGE_DAYS,
    EDGAR_PERIOD_ALIGNMENT_DAYS,
    EDGAR_PRIOR_PERIOD_MAX_DAYS,
    EDGAR_PRIOR_PERIOD_MIN_DAYS,
)

ANNUAL_FORMS = {
    "10-K",
    "10-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}


US_GAAP_REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]


US_GAAP_CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
    "PaymentsToAcquirePropertyPlantAndEquipmentIntangibleAssetsAndOtherLongLivedAssets",
    "PaymentsToAcquirePropertyPlantAndEquipmentAndOtherProductiveAssets",
    "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PropertyPlantAndEquipmentAdditions",
    "AdditionsToPropertyPlantAndEquipment",
    "CapitalExpenditures",
    "CapitalExpenditure",
]


IFRS_REVENUE_CONCEPTS = [
    "Revenue",
    "RevenueFromContractsWithCustomers",
]


IFRS_CAPEX_CONCEPTS = [
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfPropertyPlantAndEquipment",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "AdditionsToPropertyPlantAndEquipment",
    "CapitalExpenditures",
]


def get_taxonomy_facts(company_facts, taxonomy):
    return company_facts.get("facts", {}).get(taxonomy, {})


def get_usd_unit_facts(taxonomy_facts, concept):
    concept_payload = taxonomy_facts.get(concept, {})
    units = concept_payload.get("units", {})

    for unit_name, rows in units.items():
        if str(unit_name).upper().strip() == "USD":
            return rows

    return []


def _all_monetary_unit_facts(taxonomy_facts, concept):
    concept_payload = taxonomy_facts.get(concept, {})
    units = concept_payload.get("units", {})

    return {
        str(unit_name): rows
        for unit_name, rows in units.items()
        if isinstance(rows, list)
    }


def _fact_period_days(fact):
    try:
        start = pd.to_datetime(fact.get("start"), errors="coerce")
        end = pd.to_datetime(fact.get("end"), errors="coerce")

        if pd.isna(start) or pd.isna(end):
            return None

        return int((end - start).days)
    except Exception:
        return None


def _fact_end_date(fact):
    try:
        parsed = pd.to_datetime(fact.get("end"), errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _fact_fiscal_year(fact):
    end_date = _fact_end_date(fact)
    end_year = end_date.year if end_date is not None else None
    fy = fact.get("fy", None)

    try:
        if fy is not None and not pd.isna(fy):
            fy = int(fy)

            if end_year is None or abs(fy - end_year) <= 1:
                return fy
    except Exception:
        pass

    return end_year


def _is_annual_fact(fact):
    form = str(fact.get("form", "")).upper().strip()

    if form not in ANNUAL_FORMS:
        return False

    period_days = _fact_period_days(fact)

    if period_days is None:
        return False

    return 300 <= period_days <= 380


def _annual_fact_rows(taxonomy_facts, concepts, *, unit="USD"):
    rows = []

    for concept_priority, concept in enumerate(concepts):
        if unit == "USD":
            facts = get_usd_unit_facts(taxonomy_facts, concept)
        else:
            facts = _all_monetary_unit_facts(taxonomy_facts, concept).get(unit, [])

        for fact in facts:
            if not _is_annual_fact(fact):
                continue

            end_date = _fact_end_date(fact)
            fiscal_year = _fact_fiscal_year(fact)

            if end_date is None or fiscal_year is None:
                continue

            try:
                value = float(fact.get("val", np.nan))
            except Exception:
                continue

            filed = pd.to_datetime(fact.get("filed"), errors="coerce")
            fp = str(fact.get("fp", "")).upper().strip()

            rows.append({
                "Concept": concept,
                "ConceptPriority": int(concept_priority),
                "FY": int(fiscal_year),
                "FP": fp,
                "Form": str(fact.get("form", "")).upper().strip(),
                "Filed": filed,
                "End": end_date.isoformat(),
                "EndDate": end_date,
                "Value": value,
                "Accession": fact.get("accn", None),
                "AnnualConfidence": 0 if fp == "FY" else 1,
                "Unit": unit,
            })

    if not rows:
        return pd.DataFrame()

    raw = pd.DataFrame(rows)

    selected = []

    for _, group in raw.groupby("EndDate", sort=True):
        group = group.copy()
        group["FiledSort"] = group["Filed"].fillna(pd.Timestamp.min)
        group = group.sort_values(
            ["FiledSort", "AnnualConfidence", "ConceptPriority"],
            ascending=[False, True, True],
            kind="stable",
        )
        selected.append(group.iloc[0])

    result = pd.DataFrame(selected)
    result = result.drop(columns=["FiledSort"], errors="ignore")
    result = result.sort_values("EndDate", kind="stable").reset_index(drop=True)
    return result


def annual_fact_series(taxonomy_facts, concepts):
    return _annual_fact_rows(taxonomy_facts, concepts, unit="USD")


def _row_for_end(series_df, target_end, tolerance_days=0):
    if series_df is None or series_df.empty or target_end is None:
        return None

    df = series_df.copy()
    df["EndDate"] = pd.to_datetime(df["EndDate"], errors="coerce").dt.date
    df = df.dropna(subset=["EndDate", "Value"])

    if df.empty:
        return None

    df["Distance"] = df["EndDate"].map(lambda value: abs((value - target_end).days))
    df = df[df["Distance"] <= int(tolerance_days)].copy()

    if df.empty:
        return None

    return df.sort_values(["Distance", "EndDate"], ascending=[True, False]).iloc[0]


def _value_and_growth_for_period(series_df, target_end, *, use_abs=False):
    selected = _row_for_end(series_df, target_end, tolerance_days=EDGAR_PERIOD_ALIGNMENT_DAYS)

    if selected is None:
        return np.nan, np.nan, None, None

    value = float(selected["Value"])
    if use_abs:
        value = abs(value)

    selected_end = selected["EndDate"]
    selected_fy = int(selected["FY"])

    candidates = series_df.copy()
    candidates["EndDate"] = pd.to_datetime(candidates["EndDate"], errors="coerce").dt.date
    candidates["DaysBefore"] = candidates["EndDate"].map(
        lambda end: (selected_end - end).days if end is not None else np.nan
    )
    candidates = candidates[
        candidates["DaysBefore"].between(
            EDGAR_PRIOR_PERIOD_MIN_DAYS,
            EDGAR_PRIOR_PERIOD_MAX_DAYS,
            inclusive="both",
        )
    ].copy()

    growth = np.nan

    if not candidates.empty:
        candidates["DistanceFromYear"] = (candidates["DaysBefore"] - 365).abs()
        prior = candidates.sort_values(
            ["DistanceFromYear", "EndDate"],
            ascending=[True, False],
        ).iloc[0]
        prior_value = float(prior["Value"])

        if use_abs:
            prior_value = abs(prior_value)

        if prior_value != 0 and not pd.isna(prior_value):
            growth = (value / prior_value) - 1

    return value, growth, selected_fy, selected_end


def discover_capex_concepts(taxonomy_facts):
    discovered = []
    include_markers = [
        "PROPERTYPLANTANDEQUIPMENT",
        "PRODUCTIVEASSETS",
        "CAPITALEXPENDITURE",
    ]
    action_markers = [
        "PAYMENT",
        "PURCHASE",
        "ACQUIRE",
        "ADDITION",
        "EXPENDITURE",
    ]
    exclude_markers = [
        "INVESTMENT",
        "SECURITIES",
        "BUSINESS",
        "BUSINESSES",
        "ACQUISITION",
        "ACQUISITIONS",
        "DISPOSAL",
        "PROCEEDS",
    ]

    for concept in taxonomy_facts.keys():
        normalized = str(concept).upper().replace("_", "")

        if not any(marker in normalized for marker in include_markers):
            continue
        if not any(marker in normalized for marker in action_markers):
            continue
        if any(marker in normalized for marker in exclude_markers):
            continue
        if annual_fact_series(taxonomy_facts, [concept]).empty:
            continue

        discovered.append(concept)

    return discovered


def _has_non_usd_annual_facts(taxonomy_facts, concepts):
    for concept in concepts:
        for unit_name, facts in _all_monetary_unit_facts(taxonomy_facts, concept).items():
            if str(unit_name).upper().strip() == "USD":
                continue

            if any(_is_annual_fact(fact) for fact in facts):
                return True

    return False


def _extract_taxonomy_metrics(company_facts, taxonomy, revenue_concepts, capex_concepts):
    taxonomy_facts = get_taxonomy_facts(company_facts, taxonomy)

    if not taxonomy_facts:
        return {
            "Taxonomy": taxonomy,
            "Status": "Unavailable: taxonomy absent",
            "Revenue": np.nan,
            "Revenue Growth": np.nan,
            "CapEx": np.nan,
            "CapEx Growth": np.nan,
            "Revenue FY": None,
            "CapEx FY": None,
            "Revenue Period End": None,
            "CapEx Period End": None,
            "CapEx Concept": None,
            "NonUSDAnnualFacts": False,
        }

    revenue_series = annual_fact_series(taxonomy_facts, revenue_concepts)

    curated_capex = list(capex_concepts)
    discovered_capex = [
        concept
        for concept in discover_capex_concepts(taxonomy_facts)
        if concept not in curated_capex
    ]
    capex_series = annual_fact_series(taxonomy_facts, curated_capex + discovered_capex)

    non_usd = _has_non_usd_annual_facts(taxonomy_facts, revenue_concepts)

    if revenue_series is None or revenue_series.empty:
        status = (
            "Unsupported: standardized annual revenue facts are not reported in USD"
            if non_usd
            else "Unavailable: standardized annual revenue fact not found"
        )
        return {
            "Taxonomy": taxonomy,
            "Status": status,
            "Revenue": np.nan,
            "Revenue Growth": np.nan,
            "CapEx": np.nan,
            "CapEx Growth": np.nan,
            "Revenue FY": None,
            "CapEx FY": None,
            "Revenue Period End": None,
            "CapEx Period End": None,
            "CapEx Concept": None,
            "NonUSDAnnualFacts": non_usd,
        }

    latest_revenue_end = max(revenue_series["EndDate"])
    age_days = (market_date() - latest_revenue_end).days

    if age_days > EDGAR_MAX_ANNUAL_AGE_DAYS:
        return {
            "Taxonomy": taxonomy,
            "Status": f"Stale: latest annual revenue period ended {latest_revenue_end.isoformat()}",
            "Revenue": np.nan,
            "Revenue Growth": np.nan,
            "CapEx": np.nan,
            "CapEx Growth": np.nan,
            "Revenue FY": None,
            "CapEx FY": None,
            "Revenue Period End": latest_revenue_end,
            "CapEx Period End": None,
            "CapEx Concept": None,
            "NonUSDAnnualFacts": non_usd,
        }

    revenue, revenue_growth, revenue_fy, revenue_end = _value_and_growth_for_period(
        revenue_series,
        latest_revenue_end,
        use_abs=False,
    )
    capex, capex_growth, capex_fy, capex_end = _value_and_growth_for_period(
        capex_series,
        latest_revenue_end,
        use_abs=True,
    )

    capex_concept = None
    capex_row = _row_for_end(capex_series, latest_revenue_end, EDGAR_PERIOD_ALIGNMENT_DAYS)
    if capex_row is not None:
        capex_concept = str(capex_row.get("Concept", "")) or None

    if pd.notna(capex) and capex_end is not None:
        status = "OK"
    elif capex_series is not None and not capex_series.empty:
        latest_capex_end = max(capex_series["EndDate"])
        status = (
            "Partial: CapEx not aligned to latest annual revenue period "
            f"(Revenue {revenue_end.isoformat()}, CapEx {latest_capex_end.isoformat()})"
        )
    else:
        status = "Partial: CapEx unavailable for latest annual revenue period"

    return {
        "Taxonomy": taxonomy,
        "Status": status,
        "Revenue": revenue,
        "Revenue Growth": revenue_growth,
        "CapEx": capex,
        "CapEx Growth": capex_growth,
        "Revenue FY": revenue_fy,
        "CapEx FY": capex_fy,
        "Revenue Period End": revenue_end,
        "CapEx Period End": capex_end,
        "CapEx Concept": capex_concept,
        "NonUSDAnnualFacts": non_usd,
    }


def _taxonomy_result_rank(result):
    revenue_end = result.get("Revenue Period End")
    ordinal = revenue_end.toordinal() if hasattr(revenue_end, "toordinal") else -1
    status = str(result.get("Status", "")).upper()

    if status.startswith("OK"):
        status_rank = 5
    elif status.startswith("PARTIAL"):
        status_rank = 4
    elif status.startswith("UNSUPPORTED"):
        status_rank = 3
    elif status.startswith("STALE"):
        status_rank = 2
    elif status.startswith("UNAVAILABLE") and "TAXONOMY ABSENT" not in status:
        status_rank = 1
    else:
        status_rank = 0

    return ordinal, status_rank


def extract_company_metrics(company_facts):
    candidates = [
        _extract_taxonomy_metrics(
            company_facts,
            "us-gaap",
            US_GAAP_REVENUE_CONCEPTS,
            US_GAAP_CAPEX_CONCEPTS,
        ),
        _extract_taxonomy_metrics(
            company_facts,
            "ifrs-full",
            IFRS_REVENUE_CONCEPTS,
            IFRS_CAPEX_CONCEPTS,
        ),
    ]

    selected = max(candidates, key=_taxonomy_result_rank)

    return {
        "Revenue": selected["Revenue"],
        "Revenue Growth": selected["Revenue Growth"],
        "CapEx": selected["CapEx"],
        "CapEx Growth": selected["CapEx Growth"],
        "Revenue FY": selected["Revenue FY"],
        "CapEx FY": selected["CapEx FY"],
        "EDGAR Status": selected["Status"],
        "EDGAR Taxonomy": selected["Taxonomy"],
        "Revenue Period End": selected["Revenue Period End"],
        "CapEx Period End": selected["CapEx Period End"],
        "CapEx Concept": selected["CapEx Concept"],
    }
