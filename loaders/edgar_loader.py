import time
from datetime import date, timedelta

import requests
import pandas as pd
import numpy as np
import streamlit as st

from archive.archive_reader import (
    filter_expected_tickers,
    has_expected_tickers,
    load_edgar_history,
    parse_archive_dates,
    rows_for_date,
)
from config.debug_config import debug_print


#################################################
# SEC / EDGAR SETTINGS
#################################################

SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

# SEC asks for a descriptive User-Agent.
# Better: add SEC_USER_AGENT to .streamlit/secrets.toml
# Example:
# SEC_USER_AGENT = "AI Macro Dashboard your_email@example.com"
def sec_headers():
    user_agent = st.secrets.get(
        "SEC_USER_AGENT",
        "AI Macro Dashboard contact@example.com",
    )

    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def sec_ticker_headers():
    user_agent = st.secrets.get(
        "SEC_USER_AGENT",
        "AI Macro Dashboard contact@example.com",
    )

    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }


#################################################
# EDGAR ARCHIVE CONTRACT
#################################################

EDGAR_FRESHNESS_DAYS = 7
EDGAR_MAX_ANNUAL_AGE_DAYS = 550
EDGAR_PERIOD_ALIGNMENT_DAYS = 7
EDGAR_PRIOR_PERIOD_MIN_DAYS = 300
EDGAR_PRIOR_PERIOD_MAX_DAYS = 430

EDGAR_CORE_FIELDS = [
    "Revenue",
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
    "Revenue FY",
    "CapEx FY",
]

EDGAR_RESTORE_FIELDS = [
    "Revenue",
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
    "Revenue FY",
    "CapEx FY",
    "CIK",
    "EDGAR Status",
]

TERMINAL_EDGAR_STATUS_PREFIXES = (
    "OK",
    "PARTIAL",
    "UNSUPPORTED",
    "UNAVAILABLE",
    "STALE",
)


def _expected_ticker_set(tickers):
    if isinstance(tickers, dict):
        raw = tickers.keys()
    else:
        raw = tickers

    return {str(t).upper().strip() for t in raw}


def _ticker_mapping(tickers):
    if isinstance(tickers, dict):
        return {
            str(ticker).upper().strip(): company
            for ticker, company in tickers.items()
        }

    return {
        str(ticker).upper().strip(): str(ticker).upper().strip()
        for ticker in tickers
    }


def _is_present(value) -> bool:
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass

    return str(value).strip() != ""


def _status_prefix(payload) -> str:
    if not isinstance(payload, dict):
        return ""

    return str(payload.get("EDGAR Status", "")).upper().strip()


def _edgar_quality_score(payload) -> int:
    """Score archive payload quality without confusing row presence with data quality."""
    if not isinstance(payload, dict):
        return 0

    status = _status_prefix(payload)
    has_cik = _is_present(payload.get("CIK"))
    has_revenue = _is_present(payload.get("Revenue"))
    has_revenue_fy = _is_present(payload.get("Revenue FY"))
    has_capex = _is_present(payload.get("CapEx"))
    has_capex_fy = _is_present(payload.get("CapEx FY"))
    has_revenue_growth = _is_present(payload.get("Revenue Growth"))
    has_capex_growth = _is_present(payload.get("CapEx Growth"))

    score = 0

    if has_cik:
        score += 10
    if has_revenue and has_revenue_fy:
        score += 40
    if has_capex and has_capex_fy:
        score += 40
    if has_revenue_growth:
        score += 4
    if has_capex_growth:
        score += 4

    if status.startswith("OK"):
        score += 20
    elif status.startswith("PARTIAL"):
        score += 10
    elif status.startswith(("UNSUPPORTED", "UNAVAILABLE", "STALE")):
        score += 5
    elif status.startswith("FAILED") or status.startswith("LIVE FAILED"):
        score -= 20

    return score


def _is_usable_edgar_row(payload) -> bool:
    """Return True when a recent archive row is a conclusive SEC result.

    A usable row may contain a full coherent Revenue/CapEx observation or an
    explicit terminal status explaining why standardized SEC facts were not
    available. Failed/network rows remain retryable.
    """
    if not isinstance(payload, dict):
        return False

    if not _is_present(payload.get("CIK")):
        return False

    status = _status_prefix(payload)

    if not status.startswith(TERMINAL_EDGAR_STATUS_PREFIXES):
        return False

    if status.startswith("OK"):
        return (
            _is_present(payload.get("Revenue"))
            and _is_present(payload.get("Revenue FY"))
            and _is_present(payload.get("CapEx"))
            and _is_present(payload.get("CapEx FY"))
        )

    if status.startswith("PARTIAL"):
        return _is_present(payload.get("Revenue")) and _is_present(payload.get("Revenue FY"))

    # Unsupported/unavailable/stale statuses are conclusive for the current
    # seven-day archive window and should not trigger a fresh SEC request on
    # every Streamlit rerun.
    return True


def _latest_edgar_rows(tickers, *, max_age_days=None):
    df = load_edgar_history()

    if df is None or df.empty:
        return pd.DataFrame()

    required = {"Date", "Ticker"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    expected = _expected_ticker_set(tickers)
    filtered = filter_expected_tickers(df, expected)

    if filtered.empty:
        return pd.DataFrame(columns=df.columns)

    parsed = parse_archive_dates(filtered["Date"])
    filtered = filtered.loc[parsed.notna()].copy()

    if filtered.empty:
        return pd.DataFrame(columns=df.columns)

    filtered["_parsed_date"] = parsed.loc[filtered.index]

    if max_age_days is not None:
        cutoff = date.today() - timedelta(days=int(max_age_days))
        filtered = filtered[filtered["_parsed_date"] >= cutoff].copy()

        if filtered.empty:
            return pd.DataFrame(columns=df.columns)

    # A ticker can move sectors. Archive identity for selecting the latest SEC
    # observation is therefore Ticker, not Sector + Ticker.
    filtered = filtered.sort_values(["_parsed_date"], kind="stable")
    latest = filtered.groupby("Ticker", dropna=False, sort=False).tail(1)

    return latest.drop(columns=["_parsed_date"], errors="ignore").copy()


def _usable_tickers_from_rows(rows):
    if rows is None or rows.empty or "Ticker" not in rows.columns:
        return set()

    usable = set()

    for _, row in rows.iterrows():
        ticker = str(row.get("Ticker", "")).upper().strip()

        if ticker and _is_usable_edgar_row(row.to_dict()):
            usable.add(ticker)

    return usable


def read_edgar_archive_for_today(tickers, require_complete=True):
    df = load_edgar_history()

    if df is None or df.empty:
        return None

    if "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    today_df = rows_for_date(df)

    if today_df.empty:
        return None

    filtered = filter_expected_tickers(today_df, tickers)

    if not has_expected_tickers(filtered, tickers):
        return None

    if require_complete:
        usable = _usable_tickers_from_rows(filtered)
        expected = _expected_ticker_set(tickers)

        if not expected.issubset(usable):
            return None

    return filtered


def read_recent_edgar_archive(tickers, max_age_days=EDGAR_FRESHNESS_DAYS, require_complete=True):
    recent = _latest_edgar_rows(tickers, max_age_days=max_age_days)

    if recent.empty:
        return None

    expected = _expected_ticker_set(tickers)
    usable = _usable_tickers_from_rows(recent)

    if require_complete and not expected.issubset(usable):
        return None

    return recent


def read_latest_edgar_archive(tickers, require_complete=False):
    latest = _latest_edgar_rows(tickers, max_age_days=None)

    if latest.empty:
        return None

    if require_complete:
        expected = _expected_ticker_set(tickers)
        usable = _usable_tickers_from_rows(latest)

        if not expected.issubset(usable):
            return None

    return latest


def edgar_archive_rows_to_dict(archived_rows, source_label="Archive"):
    data = {}

    if archived_rows is None or archived_rows.empty:
        return data

    for _, row in archived_rows.iterrows():
        ticker = str(row.get("Ticker", "")).upper().strip()

        if not ticker:
            continue

        restored = {
            field: row.get(field, np.nan)
            for field in EDGAR_RESTORE_FIELDS
        }
        restored["EDGAR Source"] = source_label
        restored["EDGAR Archive Date"] = row.get("Date", None)

        if not restored.get("EDGAR Status") or pd.isna(restored.get("EDGAR Status")):
            restored["EDGAR Status"] = source_label

        data[ticker] = restored

    return data


def describe_edgar_freshness_status(tickers, max_age_days=EDGAR_FRESHNESS_DAYS):
    expected = _expected_ticker_set(tickers)
    recent = read_recent_edgar_archive(
        tickers,
        max_age_days=max_age_days,
        require_complete=False,
    )
    latest = read_latest_edgar_archive(tickers, require_complete=False)

    recent_usable = _usable_tickers_from_rows(recent) if recent is not None else set()
    recent_found = set()

    if recent is not None and not recent.empty and "Ticker" in recent.columns:
        recent_found = set(recent["Ticker"].dropna().astype(str).str.upper().str.strip())

    latest_found = set()
    latest_date = None

    if latest is not None and not latest.empty and "Ticker" in latest.columns:
        latest_found = set(latest["Ticker"].dropna().astype(str).str.upper().str.strip())

        if "Date" in latest.columns:
            dates = pd.to_datetime(latest["Date"], errors="coerce", format="mixed").dropna()

            if not dates.empty:
                latest_date = dates.max().date().isoformat()

    return {
        "expected_tickers": len(expected),
        "freshness_days": int(max_age_days),
        "recent_archive_rows": 0 if recent is None else int(len(recent)),
        "recent_archive_tickers": int(len(recent_usable)),
        "recent_archive_tickers_found": int(len(recent_found)),
        "recent_archive_tickers_usable": int(len(recent_usable)),
        "recent_incomplete_tickers": sorted(recent_found - recent_usable),
        "recent_missing_tickers": sorted(expected - recent_usable),
        "recent_complete": expected.issubset(recent_usable),
        "latest_archive_tickers": int(len(latest_found)),
        "latest_complete_date": latest_date,
    }


#################################################
# SEC API HELPERS
#################################################

@st.cache_data(ttl=86400)
def load_ticker_cik_map():
    """Load the SEC ticker -> ten-digit CIK mapping."""
    response = requests.get(
        SEC_TICKER_URL,
        headers=sec_ticker_headers(),
        timeout=30,
    )
    response.raise_for_status()

    raw = response.json()
    ticker_map = {}

    for _, row in raw.items():
        ticker = str(row.get("ticker", "")).upper().strip()
        cik = str(row.get("cik_str", "")).zfill(10)

        if ticker and cik:
            ticker_map[ticker] = cik

    return ticker_map


@st.cache_data(ttl=86400)
def fetch_company_facts(cik):
    """Fetch SEC Company Facts for one CIK."""
    url = SEC_COMPANY_FACTS_URL.format(cik=cik)
    response = requests.get(url, headers=sec_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def get_taxonomy_facts(company_facts, taxonomy):
    return company_facts.get("facts", {}).get(taxonomy, {})


def get_us_gaap_facts(company_facts):
    # Public helper retained for compatibility.
    return get_taxonomy_facts(company_facts, "us-gaap")


def get_usd_unit_facts(taxonomy_facts, concept):
    """Return facts reported in a pure USD unit for one taxonomy concept."""
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
            # Retail and 52/53-week calendars can label a fiscal year one year
            # away from the calendar year in which the period ends. Anything
            # farther away is filing metadata, not a trustworthy period label.
            if end_year is None or abs(fy - end_year) <= 1:
                return fy
    except Exception:
        pass

    return end_year


ANNUAL_FORMS = {
    "10-K",
    "10-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}


def _is_annual_fact(fact):
    form = str(fact.get("form", "")).upper().strip()

    if form not in ANNUAL_FORMS:
        return False

    period_days = _fact_period_days(fact)

    if period_days is None:
        return False

    # Annual company facts can have fp values that are not perfectly uniform.
    # Duration plus annual form is the stable contract.
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

    # Company Facts repeats comparative periods in later annual filings. EndDate
    # is the economic period identity; FY belongs to filing metadata and cannot
    # be used as the dedupe key. For each period prefer the latest filing, then
    # an explicit FY context, then the curated concept priority.
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
    """Return one coherent USD annual fact per economic period.

    Public signature retained. Unlike the old implementation, this function
    combines concept transitions instead of accepting the first concept that
    ever reported a value.
    """
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


def latest_and_growth(series_df, use_abs=False):
    """Return latest annual value, comparable YoY growth, and fiscal year."""
    if series_df is None or series_df.empty:
        return np.nan, np.nan, None

    latest_end = max(series_df["EndDate"])
    value, growth, fiscal_year, _ = _value_and_growth_for_period(
        series_df,
        latest_end,
        use_abs=use_abs,
    )
    return value, growth, fiscal_year


#################################################
# METRIC EXTRACTION
#################################################

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

# Backward-compatible aliases used by earlier diagnostics.
REVENUE_CONCEPTS = US_GAAP_REVENUE_CONCEPTS
CAPEX_CONCEPTS = US_GAAP_CAPEX_CONCEPTS


def discover_capex_concepts(taxonomy_facts):
    """Conservatively discover standardized PPE/capital-expenditure concepts."""
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
    age_days = (date.today() - latest_revenue_end).days

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
    """Extract coherent latest annual Revenue and CapEx from SEC Company Facts.

    Revenue anchors the observation period. CapEx is accepted only when its
    annual period end aligns with that same Revenue period. This prevents stale
    concepts from combining different fiscal eras in one row.
    """
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


#################################################
# PUBLIC LOADER
#################################################

def _empty_edgar_payload(status, *, source="Failed"):
    return {
        "Revenue": np.nan,
        "Revenue Growth": np.nan,
        "CapEx": np.nan,
        "CapEx Growth": np.nan,
        "Revenue FY": None,
        "CapEx FY": None,
        "CIK": None,
        "EDGAR Status": status,
        "EDGAR Source": source,
        "EDGAR Archive Date": None,
    }


def _fetch_live_edgar_subset(tickers_to_fetch, ticker_cik_map, archive_fallback_data):
    edgar_data = {}
    attempted = []
    succeeded = []
    failed = []

    for ticker_upper in sorted(tickers_to_fetch):
        attempted.append(ticker_upper)

        try:
            cik = ticker_cik_map.get(ticker_upper)

            if not cik:
                raise ValueError(f"No CIK found for ticker {ticker_upper}")

            company_facts = fetch_company_facts(cik)
            metrics = extract_company_metrics(company_facts)

            edgar_data[ticker_upper] = {
                "Revenue": metrics["Revenue"],
                "Revenue Growth": metrics["Revenue Growth"],
                "CapEx": metrics["CapEx"],
                "CapEx Growth": metrics["CapEx Growth"],
                "Revenue FY": metrics["Revenue FY"],
                "CapEx FY": metrics["CapEx FY"],
                "CIK": cik,
                "EDGAR Status": metrics["EDGAR Status"],
                "EDGAR Source": "SEC Live",
                "EDGAR Archive Date": None,
                "EDGAR Taxonomy": metrics.get("EDGAR Taxonomy"),
                "Revenue Period End": metrics.get("Revenue Period End"),
                "CapEx Period End": metrics.get("CapEx Period End"),
                "CapEx Concept": metrics.get("CapEx Concept"),
            }
            succeeded.append(ticker_upper)

            # Be polite to SEC servers.
            time.sleep(0.12)

        except Exception as exc:
            debug_print(f"EDGAR failed: {ticker_upper} -> {exc}")
            failed.append(ticker_upper)

            fallback = archive_fallback_data.get(ticker_upper)

            if fallback:
                fallback = fallback.copy()
                fallback["EDGAR Status"] = f"Live Failed; Archive Fallback: {exc}"
                fallback["EDGAR Source"] = "Archive Fallback"
                edgar_data[ticker_upper] = fallback
            else:
                edgar_data[ticker_upper] = _empty_edgar_payload(
                    f"Failed: {exc}",
                    source="Failed",
                )

    return edgar_data, {
        "live_attempted_tickers": attempted,
        "live_succeeded_tickers": succeeded,
        "live_failed_tickers": failed,
    }


def load_edgar_with_report(tickers):
    expected = _expected_ticker_set(tickers)

    recent_rows = read_recent_edgar_archive(
        tickers,
        max_age_days=EDGAR_FRESHNESS_DAYS,
        require_complete=False,
    )
    latest_rows = read_latest_edgar_archive(tickers, require_complete=False)

    recent_data = edgar_archive_rows_to_dict(recent_rows, source_label="Archive Recent")
    archive_fallback_data = edgar_archive_rows_to_dict(
        latest_rows,
        source_label="Archive Fallback",
    )

    usable_recent = {
        ticker
        for ticker, payload in recent_data.items()
        if _is_usable_edgar_row(payload)
    }

    tickers_to_fetch = sorted(expected - usable_recent)

    edgar_data = {
        ticker: recent_data[ticker]
        for ticker in sorted(usable_recent)
        if ticker in recent_data
    }

    report = describe_edgar_freshness_status(tickers)
    report.update({
        "source_mode": "archive_recent" if not tickers_to_fetch else "partial_live",
        "archive_recent_tickers_used": int(len(edgar_data)),
        "live_needed_tickers": tickers_to_fetch,
        "live_attempted_tickers": [],
        "live_succeeded_tickers": [],
        "live_failed_tickers": [],
    })

    if not tickers_to_fetch:
        debug_print(
            f"Loading EDGAR rows from recent archive window "
            f"({EDGAR_FRESHNESS_DAYS} days)."
        )
        return edgar_data, report

    try:
        ticker_cik_map = load_ticker_cik_map()
    except Exception as exc:
        debug_print(f"EDGAR ticker-CIK map failed -> {exc}")
        report["source_mode"] = "archive_fallback_map_failed"
        report["live_failed_tickers"] = tickers_to_fetch

        for ticker_upper in tickers_to_fetch:
            edgar_data[ticker_upper] = archive_fallback_data.get(
                ticker_upper,
                _empty_edgar_payload(
                    f"Ticker-CIK map failed: {exc}",
                    source="Failed",
                ),
            )

        return edgar_data, report

    live_data, live_report = _fetch_live_edgar_subset(
        tickers_to_fetch,
        ticker_cik_map,
        archive_fallback_data,
    )
    edgar_data.update(live_data)
    report.update(live_report)

    if len(tickers_to_fetch) == len(expected):
        report["source_mode"] = "full_live"
    elif live_report.get("live_succeeded_tickers"):
        report["source_mode"] = "partial_live"
    else:
        report["source_mode"] = "archive_fallback"

    # Guarantee all expected tickers have a payload so field-by-field YFinance
    # fallback can fill holes downstream without losing the ticker row.
    for ticker_upper in sorted(expected):
        if ticker_upper not in edgar_data:
            edgar_data[ticker_upper] = archive_fallback_data.get(
                ticker_upper,
                _empty_edgar_payload("No EDGAR payload", source="Failed"),
            )

    return edgar_data, report


def load_edgar(tickers):
    edgar_data, _ = load_edgar_with_report(tickers)
    return edgar_data
