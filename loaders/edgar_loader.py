import time
import requests
import pandas as pd
import numpy as np
import streamlit as st

from datetime import date
from archive.archive_reader import load_edgar_history
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

def read_edgar_archive_for_today(tickers):
    try:
        df = load_edgar_history()
    except Exception:
        return None

    if df is None or df.empty:
        return None

    if "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    today = str(date.today())
    ticker_set = {str(t).upper().strip() for t in tickers.keys()}

    df = df.copy()
    df["Date"] = df["Date"].astype(str)
    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()

    today_df = df[
        (df["Date"] == today)
        &
        (df["Ticker"].isin(ticker_set))
    ].copy()

    found = set(today_df["Ticker"].dropna())

    if not ticker_set.issubset(found):
        return None

    return today_df

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

def load_edgar(tickers):

    archived_today = read_edgar_archive_for_today(tickers)

    if archived_today is not None:
        debug_print("Loading today's EDGAR rows from edgar_history.csv")

        return {
            row["Ticker"]: {
                "Revenue": row.get("Revenue", np.nan),
                "Revenue Growth": row.get("Revenue Growth", np.nan),
                "Market Cap": row.get("Market Cap", np.nan),
                "CapEx": row.get("CapEx", np.nan),
                "CapEx Growth": row.get("CapEx Growth", np.nan),
                "EDGAR Status": "Archive",
            }
            for _, row in archived_today.iterrows()
        }

    edgar_data = {}

    try:
        ticker_cik_map = load_ticker_cik_map()
    except Exception as e:
        debug_print(f"EDGAR ticker-CIK map failed -> {e}")

        for ticker in tickers.keys():
            edgar_data[ticker] = {
                "Revenue": np.nan,
                "Revenue Growth": np.nan,
                "CapEx": np.nan,
                "CapEx Growth": np.nan,
                "Market Cap": np.nan,
                "Revenue FY": None,
                "CapEx FY": None,
                "EDGAR Status": "Ticker-CIK map failed",
            }

        return edgar_data

    for ticker in tickers.keys():

        ticker_upper = str(ticker).upper().strip()

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

                # SEC Company Facts does not provide market cap.
                # Keep this as NaN and let YFinance remain the source.
                "Market Cap": np.nan,

                "Revenue FY": metrics["Revenue FY"],
                "CapEx FY": metrics["CapEx FY"],
                "CIK": cik,
                "EDGAR Status": "OK",
            }

            # Be polite to SEC servers.
            time.sleep(0.12)

        except Exception as e:
            debug_print(f"EDGAR failed: {ticker_upper} -> {e}")

            edgar_data[ticker_upper] = {
                "Revenue": np.nan,
                "Revenue Growth": np.nan,
                "CapEx": np.nan,
                "CapEx Growth": np.nan,
                "Market Cap": np.nan,
                "Revenue FY": None,
                "CapEx FY": None,
                "CIK": None,
                "EDGAR Status": f"Failed: {e}",
            }

    return edgar_data