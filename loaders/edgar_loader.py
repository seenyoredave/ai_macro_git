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
        "AI Macro Dashboard contact@example.com"
    )

    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def sec_ticker_headers():
    user_agent = st.secrets.get(
        "SEC_USER_AGENT",
        "AI Macro Dashboard contact@example.com"
    )

    return {
        "User-Agent": user_agent,
        "Accept-Encoding": "gzip, deflate",
    }

#################################################
# EDGAR ARCHIVE CALL
#################################################

EDGAR_FRESHNESS_DAYS = 7

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
    "Market Cap",
    "CapEx",
    "CapEx Growth",
    "Revenue FY",
    "CapEx FY",
    "CIK",
    "EDGAR Status",
]


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


def _has_any_edgar_core_value(payload) -> bool:
    for field in EDGAR_CORE_FIELDS:
        value = payload.get(field) if isinstance(payload, dict) else None

        try:
            if pd.notna(value) and str(value).strip() != "":
                return True
        except Exception:
            pass

    return False


def _latest_edgar_rows(
    tickers,
    *,
    max_age_days=None,
):
    df = load_edgar_history()

    if df is None or df.empty:
        return pd.DataFrame()

    required = {"Date", "Ticker"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    expected = _expected_ticker_set(tickers)
    filtered = filter_expected_tickers(df, expected)

    if filtered.empty:
        return pd.DataFrame()

    parsed = parse_archive_dates(filtered["Date"])
    filtered = filtered.loc[parsed.notna()].copy()

    if filtered.empty:
        return pd.DataFrame()

    filtered["_parsed_date"] = parsed.loc[filtered.index]

    if max_age_days is not None:
        cutoff = date.today() - timedelta(days=int(max_age_days))
        filtered = filtered[filtered["_parsed_date"] >= cutoff].copy()

        if filtered.empty:
            return pd.DataFrame()

    filtered = filtered.sort_values(["_parsed_date"], kind="stable")
    latest = filtered.groupby("Ticker", dropna=False, sort=False).tail(1)

    return latest.drop(columns=["_parsed_date"], errors="ignore").copy()


def _usable_tickers_from_rows(rows):
    if rows is None or rows.empty or "Ticker" not in rows.columns:
        return set()

    usable = set()

    for _, row in rows.iterrows():
        ticker = str(row.get("Ticker", "")).upper().strip()

        if not ticker:
            continue

        if _has_any_edgar_core_value(row.to_dict()):
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
    """
    Loads SEC ticker -> CIK mapping.

    Returns:
        dict like {"MSFT": "0000789019"}
    """

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
    """
    Fetches SEC Company Facts for one CIK.
    """

    url = SEC_COMPANY_FACTS_URL.format(cik=cik)

    response = requests.get(
        url,
        headers=sec_headers(),
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_us_gaap_facts(company_facts):
    return (
        company_facts
        .get("facts", {})
        .get("us-gaap", {})
    )


def get_usd_unit_facts(us_gaap, concept):
    """
    Returns USD-denominated fact rows for a given us-gaap concept.
    """

    concept_payload = us_gaap.get(concept, {})

    units = concept_payload.get("units", {})

    if "USD" not in units:
        return []

    return units["USD"]


def annual_fact_series(us_gaap, concepts):
    """
    Extracts annual 10-K / 10-K/A values for the first usable concept.

    Returns:
        dataframe with columns:
        Concept, FY, FP, Form, Filed, End, Value
    """

    for concept in concepts:
        rows = []

        facts = get_usd_unit_facts(us_gaap, concept)

        for fact in facts:
            form = str(fact.get("form", "")).upper()
            fp = str(fact.get("fp", "")).upper()
            fy = fact.get("fy", None)
            val = fact.get("val", np.nan)

            if form not in {"10-K", "10-K/A"}:
                continue

            if fp != "FY":
                continue

            if fy is None:
                continue

            try:
                val = float(val)
            except Exception:
                continue

            rows.append({
                "Concept": concept,
                "FY": int(fy),
                "FP": fp,
                "Form": form,
                "Filed": fact.get("filed", None),
                "End": fact.get("end", None),
                "Value": val,
            })

        if not rows:
            continue

        df = pd.DataFrame(rows)

        if df.empty:
            continue

        # Keep latest filing per fiscal year.
        df = df.sort_values(["FY", "Filed", "End"])
        df = df.drop_duplicates(subset=["FY"], keep="last")
        df = df.sort_values("FY")

        # Need at least one value to be usable.
        if len(df) >= 1:
            return df

    return pd.DataFrame()


def latest_and_growth(series_df, use_abs=False):
    """
    Returns latest annual value and YoY growth.

    If use_abs=True, converts values to absolute values.
    Useful for capex because cash-flow facts may be represented as outflows.
    """

    if series_df is None or series_df.empty:
        return np.nan, np.nan, None

    df = series_df.copy()

    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")

    if use_abs:
        df["Value"] = df["Value"].abs()

    df = df.dropna(subset=["Value", "FY"])
    df = df.sort_values("FY")

    if df.empty:
        return np.nan, np.nan, None

    latest = df.iloc[-1]
    latest_value = float(latest["Value"])
    latest_fy = int(latest["FY"])

    prior_df = df[df["FY"] < latest_fy]

    if prior_df.empty:
        return latest_value, np.nan, latest_fy

    prior_value = float(prior_df.iloc[-1]["Value"])

    if prior_value == 0 or pd.isna(prior_value):
        growth = np.nan
    else:
        growth = (latest_value / prior_value) - 1

    return latest_value, growth, latest_fy


#################################################
# METRIC EXTRACTION
#################################################

REVENUE_CONCEPTS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]

CAPEX_CONCEPTS = [
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "PaymentsToAcquireBusinessesAndProductiveAssets",
    "CapitalExpenditures",
]


def extract_company_metrics(company_facts):
    """
    Extracts annual revenue, revenue growth, capex, and capex growth.
    """

    us_gaap = get_us_gaap_facts(company_facts)

    revenue_series = annual_fact_series(
        us_gaap,
        REVENUE_CONCEPTS,
    )

    capex_series = annual_fact_series(
        us_gaap,
        CAPEX_CONCEPTS,
    )

    revenue, revenue_growth, revenue_fy = latest_and_growth(
        revenue_series,
        use_abs=False,
    )

    capex, capex_growth, capex_fy = latest_and_growth(
        capex_series,
        use_abs=True,
    )

    return {
        "Revenue": revenue,
        "Revenue Growth": revenue_growth,
        "CapEx": capex,
        "CapEx Growth": capex_growth,
        "Revenue FY": revenue_fy,
        "CapEx FY": capex_fy,
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
        "Market Cap": np.nan,
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
                "Market Cap": np.nan,
                "Revenue FY": metrics["Revenue FY"],
                "CapEx FY": metrics["CapEx FY"],
                "CIK": cik,
                "EDGAR Status": "OK",
                "EDGAR Source": "SEC Live",
                "EDGAR Archive Date": None,
            }
            succeeded.append(ticker_upper)

            # Be polite to SEC servers.
            time.sleep(0.12)

        except Exception as e:
            debug_print(f"EDGAR failed: {ticker_upper} -> {e}")
            failed.append(ticker_upper)

            fallback = archive_fallback_data.get(ticker_upper)

            if fallback:
                fallback = fallback.copy()
                fallback["EDGAR Status"] = f"Live Failed; Archive Fallback: {e}"
                fallback["EDGAR Source"] = "Archive Fallback"
                edgar_data[ticker_upper] = fallback
            else:
                edgar_data[ticker_upper] = _empty_edgar_payload(
                    f"Failed: {e}",
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

    recent_data = edgar_archive_rows_to_dict(
        recent_rows,
        source_label="Archive Recent",
    )
    archive_fallback_data = edgar_archive_rows_to_dict(
        latest_rows,
        source_label="Archive Fallback",
    )

    usable_recent = {
        ticker
        for ticker, payload in recent_data.items()
        if _has_any_edgar_core_value(payload)
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
    except Exception as e:
        debug_print(f"EDGAR ticker-CIK map failed -> {e}")
        report["source_mode"] = "archive_fallback_map_failed"
        report["live_failed_tickers"] = tickers_to_fetch

        for ticker_upper in tickers_to_fetch:
            edgar_data[ticker_upper] = archive_fallback_data.get(
                ticker_upper,
                _empty_edgar_payload(
                    f"Ticker-CIK map failed: {e}",
                    source="Failed",
                )
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
