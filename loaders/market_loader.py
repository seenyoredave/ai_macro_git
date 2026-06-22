import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor

from loaders.edgar_loader import load_edgar


#################################################
# CAPEX HELPERS
#################################################

def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return np.nan
        return float(value)
    except Exception:
        return np.nan


def get_cashflow_row(cashflow_df, possible_names):
    """
    yfinance row names are annoyingly inconsistent.
    This tries several possible capital-expenditure labels.
    """
    if cashflow_df is None or cashflow_df.empty:
        return None

    index_lookup = {str(idx).lower().strip(): idx for idx in cashflow_df.index}

    for name in possible_names:
        key = name.lower().strip()
        if key in index_lookup:
            return cashflow_df.loc[index_lookup[key]]

    return None


def calc_capex_metrics(ticker_obj):
    """
    Returns:
      capex_ttm: absolute value of latest trailing capex
      capex_growth: YoY growth in capex, as decimal
                    e.g. 0.35 = +35%
    """

    row_names = [
        "Capital Expenditure",
        "Capital Expenditures",
        "CapitalExpenditures",
        "Capital Expenditure Reported",
        "Purchase Of Property Plant Equipment",
        "Purchase Of PPE",
        "Purchase of Property Plant and Equipment",
    ]

    # Prefer quarterly cash flow for TTM calculation
    try:
        q_cf = ticker_obj.quarterly_cashflow
    except Exception:
        q_cf = pd.DataFrame()

    capex_row = get_cashflow_row(q_cf, row_names)

    if capex_row is not None:
        values = pd.to_numeric(capex_row, errors="coerce").dropna()

        # yfinance usually returns most recent periods first
        if len(values) >= 8:
            latest_ttm = values.iloc[:4].sum()
            prior_ttm = values.iloc[4:8].sum()

            latest_abs = abs(float(latest_ttm))
            prior_abs = abs(float(prior_ttm))

            if prior_abs > 0:
                return latest_abs, (latest_abs / prior_abs) - 1

            return latest_abs, np.nan

    # Fallback: annual cashflow
    try:
        a_cf = ticker_obj.cashflow
    except Exception:
        a_cf = pd.DataFrame()

    capex_row = get_cashflow_row(a_cf, row_names)

    if capex_row is not None:
        values = pd.to_numeric(capex_row, errors="coerce").dropna()

        if len(values) >= 2:
            latest_abs = abs(float(values.iloc[0]))
            prior_abs = abs(float(values.iloc[1]))

            if prior_abs > 0:
                return latest_abs, (latest_abs / prior_abs) - 1

            return latest_abs, np.nan

    return np.nan, np.nan


EVG_REQUIRED_COLUMNS = [
    "Revenue Growth",
    "CapEx",
    "CapEx Growth",
]

def calc_revenue_growth(ticker_obj, info):
    """
    Prefer yfinance info['revenueGrowth'].
    Fallback to quarterly income statement TTM revenue growth.
    """

    direct_growth = safe_float(info.get("revenueGrowth"))

    if not pd.isna(direct_growth):
        return direct_growth

    revenue_row_names = [
        "Total Revenue",
        "Operating Revenue",
        "Revenue",
    ]

    try:
        q_income = ticker_obj.quarterly_income_stmt
    except Exception:
        q_income = pd.DataFrame()

    revenue_row = get_cashflow_row(q_income, revenue_row_names)

    if revenue_row is not None:
        values = pd.to_numeric(revenue_row, errors="coerce").dropna()

        if len(values) >= 8:
            latest_ttm = values.iloc[:4].sum()
            prior_ttm = values.iloc[4:8].sum()

            if prior_ttm != 0:
                return (float(latest_ttm) / float(prior_ttm)) - 1

    return np.nan


def has_usable_evg_fields(df, min_valid_rows=1):
    """
    Returns True only if archived/live YFinance data contains usable EVG fields.

    This prevents old yf_history.csv rows from silently blocking newly added
    capex/revenue-growth logic.
    """
    if df is None or df.empty:
        return False

    missing = [col for col in EVG_REQUIRED_COLUMNS if col not in df.columns]

    if missing:
        return False

    valid_counts = {
        col: pd.to_numeric(df[col], errors="coerce").dropna().shape[0]
        for col in EVG_REQUIRED_COLUMNS
    }

    return all(count >= min_valid_rows for count in valid_counts.values())


#################################################
# YF HISTORY SETTINGS
#################################################

YF_HISTORY_PATH = Path("archive/yf_history.csv")


def read_yf_history_for_date(tickers, sector=None, target_date=None):
    if not YF_HISTORY_PATH.exists():
        return None

    df = pd.read_csv(YF_HISTORY_PATH)

    if df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    target_date = str(target_date or date.today())
    ticker_set = set(tickers.keys())

    df["Date"] = df["Date"].astype(str)

    filtered = df[
        (df["Date"] == target_date)
        &
        (df["Ticker"].isin(ticker_set))
    ].copy()

    if sector is not None and "Sector" in filtered.columns:
        filtered = filtered[filtered["Sector"] == sector].copy()

    found = set(filtered["Ticker"].dropna())

    if not ticker_set.issubset(found):
        return None

    return filtered


def read_latest_yf_history(tickers, sector=None):
    if not YF_HISTORY_PATH.exists():
        return None

    df = pd.read_csv(YF_HISTORY_PATH)

    if df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    ticker_set = set(tickers.keys())

    df["Date"] = df["Date"].astype(str)

    filtered = df[df["Ticker"].isin(ticker_set)].copy()

    if sector is not None and "Sector" in filtered.columns:
        filtered = filtered[filtered["Sector"] == sector].copy()

    if filtered.empty:
        return None

    latest_date = filtered["Date"].max()
    latest = filtered[filtered["Date"] == latest_date].copy()

    found = set(latest["Ticker"].dropna())

    if not ticker_set.issubset(found):
        return None

    return latest


#################################################
# RAW YFINANCE PULL
#################################################

def pull_yfinance(ticker_tuple):
    tickers = dict(ticker_tuple)

    def fetch_company(ticker, company):
        try:
            t = yf.Ticker(ticker)

            capex, capex_growth = calc_capex_metrics(t)
            
            f_info = getattr(t, "fast_info", {}) or {}
            info = getattr(t, "info", {}) or {}
            
            revenue_growth = calc_revenue_growth(t, info)

            hist = t.history(
                period="2y",
                auto_adjust=True
            )

            if hist.empty:
                return None

            hist = hist.dropna(subset=["Close"])

            def safe_num(*keys):
                for key in keys:
                    val = f_info.get(key)

                    if val is None:
                        val = info.get(key)

                    if val is not None and not pd.isna(val):
                        return float(val)

                return np.nan

            clean_close = hist["Close"].dropna()

            if len(clean_close) < 252:
                one_year_return = np.nan
            else:
                end_price = clean_close.iloc[-1]
                start_price = clean_close.iloc[-252]
                one_year_return = (end_price / start_price) - 1

            return {
                "Ticker": ticker,
                "Company": company,
                "Price": safe_num("last_price", "regularMarketPrice"),
                "Beta": safe_num("beta"),
                "P/E": safe_num("trailing_pe", "trailingPE"),
                "Forward P/E": safe_num("forward_pe", "forwardPE"),
                "Market Cap": safe_num("market_cap", "marketCap"),
                "Revenue": safe_num("total_revenue", "totalRevenue"),
                "Revenue Growth": revenue_growth,
                "CapEx": capex,
                "CapEx Growth": capex_growth,
                "52W High": safe_num("year_high", "fiftyTwoWeekHigh"),
                "52W Low": safe_num("year_low", "fiftyTwoWeekLow"),
                "1Y Return": one_year_return,
            }

        except Exception as e:
            print(f"{ticker} failed -> {e}")
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(
            executor.map(
                lambda x: fetch_company(*x),
                tickers.items()
            )
        )

    rows = [r for r in results if r]

    return pd.DataFrame(rows)


#################################################
# YFINANCE LOADER
#################################################

@st.cache_data(ttl=3600)
def load_yfinance(ticker_tuple, sector=None):
    tickers = dict(ticker_tuple)

    archived_today = read_yf_history_for_date(
        tickers,
        sector=sector
    )

    if archived_today is not None and has_usable_evg_fields(archived_today):
        print(f"Loading today's yfinance rows from yf_history.csv: {sector}")
        return archived_today

    if archived_today is not None:
        print(f"yf_history rows found but missing usable EVG fields. Pulling fresh yfinance: {sector}")

    try:
        print(f"No yf_history rows found for today. Pulling yfinance: {sector}")

        df = pull_yfinance(ticker_tuple)

        if df.empty:
            raise ValueError("yfinance returned an empty DataFrame")

        return df

    except Exception as e:
        print(f"yfinance pull failed -> {e}")

        fallback = read_latest_yf_history(
            tickers,
            sector=sector
        )

        if fallback is not None:
            print(f"Using latest yf_history.csv fallback: {sector}")
            return fallback

        raise RuntimeError(
            "yfinance failed and no usable yf_history fallback exists."
        ) from e


#################################################
# MASTER DATA LOADER
#################################################

@st.cache_data(ttl=3600)
def load_sector_data(tickers, sector=None):
    raw_yf = load_yfinance(
        tuple(sorted(tickers.items())),
        sector=sector
    )

    raw_edgar = load_edgar(tickers)

    if "Revenue Growth" in raw_yf.columns or "CapEx Growth" in raw_yf.columns:
        print("\n=== RAW YFINANCE EVG CHECK ===")
        print(
            raw_yf[
                [
                    "Ticker",
                    "Revenue Growth",
                    "CapEx",
                    "CapEx Growth"
                ]
            ]
        )

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
    }