import time

import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from loaders.edgar_loader import (
    describe_edgar_freshness_status,
    load_edgar,
    load_edgar_with_report,
)
from archive.archive_reader import (
    filter_expected_tickers,
    has_expected_tickers,
    latest_complete_ticker_rows,
    load_yf_history,
    rows_for_date,
)

from config.debug_config import debug_print 


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

FINANCIAL_STRAIN_COLUMNS = [
    "Operating Cash Flow",
    "Free Cash Flow",
    "Net Income",
    "EBITDA",
    "Total Debt",
    "Cash",
    "Net Debt",
]

YF_REFRESH_REQUIRED_COLUMNS = EVG_REQUIRED_COLUMNS + FINANCIAL_STRAIN_COLUMNS

def ensure_yf_schema(df):
    """
    Ensures archived yfinance data has all currently expected columns.
    Missing newer columns are added as NaN so old archives remain usable.
    """
    required_columns = [
        "Date",
        "Sector",
        "Ticker",
        "Company",
        "Price",
        "P/E",
        "Forward P/E",
        "Market Cap",
        "Revenue",
        "Revenue Growth",
        "CapEx",
        "CapEx Growth",
        "Operating Cash Flow",
        "Free Cash Flow",
        "Net Income",
        "EBITDA",
        "Total Debt",
        "Cash",
        "Net Debt",
        "Beta",
        "52W High",
        "52W Low",
        "1Y Return",
        "Basket Score",
        "Basket Tier",
        "Basket Weight",
    ]

    df = df.copy()

    for col in required_columns:
        if col not in df.columns:
            df[col] = np.nan

    return df

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


def _safe_info_number(info, *keys):
    for key in keys:
        value = safe_float(info.get(key))

        if not pd.isna(value):
            return value

    return np.nan


def _latest_statement_value(ticker_obj, statement_attrs, row_names, *, ttm=False):
    """Return a latest statement value from yfinance financial statements.

    For flow variables where quarterly data exists, ttm=True sums the latest
    four quarters. Otherwise this returns the latest annual value found.
    """
    for attr in statement_attrs:
        try:
            statement = getattr(ticker_obj, attr)
        except Exception:
            statement = pd.DataFrame()

        row = get_cashflow_row(statement, row_names)

        if row is None:
            continue

        values = pd.to_numeric(row, errors="coerce").dropna()

        if values.empty:
            continue

        if ttm and str(attr).startswith("quarterly") and len(values) >= 4:
            return float(values.iloc[:4].sum())

        return float(values.iloc[0])

    return np.nan


def calc_financial_strain_fields(ticker_obj, info, capex_value=np.nan):
    """Collect cash-flow and debt fields used by hidden risk selection.

    These are raw company-level financial fields. Ratios are calculated later
    at the sector-assessment layer so the public dashboard does not gain new
    visible score columns.
    """
    operating_cash_flow = _safe_info_number(
        info,
        "operatingCashflow",
        "operating_cashflow",
    )

    if pd.isna(operating_cash_flow):
        operating_cash_flow = _latest_statement_value(
            ticker_obj,
            ["quarterly_cashflow", "cashflow"],
            [
                "Operating Cash Flow",
                "Total Cash From Operating Activities",
                "Net Cash Provided By Operating Activities",
                "Cash Flow From Continuing Operating Activities",
            ],
            ttm=True,
        )

    free_cash_flow = _safe_info_number(
        info,
        "freeCashflow",
        "free_cashflow",
    )

    if pd.isna(free_cash_flow):
        free_cash_flow = _latest_statement_value(
            ticker_obj,
            ["quarterly_cashflow", "cashflow"],
            ["Free Cash Flow", "FreeCashFlow"],
            ttm=True,
        )

    # If yfinance does not expose FCF directly, derive it from OCF - CapEx.
    # capex_value is stored as an absolute positive investment outflow.
    if pd.isna(free_cash_flow) and not pd.isna(operating_cash_flow) and not pd.isna(capex_value):
        free_cash_flow = operating_cash_flow - abs(float(capex_value))

    net_income = _safe_info_number(
        info,
        "netIncomeToCommon",
        "netIncome",
    )

    if pd.isna(net_income):
        net_income = _latest_statement_value(
            ticker_obj,
            ["quarterly_income_stmt", "income_stmt"],
            ["Net Income", "Net Income Common Stockholders"],
            ttm=True,
        )

    ebitda = _safe_info_number(info, "ebitda")

    if pd.isna(ebitda):
        ebitda = _latest_statement_value(
            ticker_obj,
            ["quarterly_income_stmt", "income_stmt"],
            ["EBITDA", "Normalized EBITDA"],
            ttm=True,
        )

    total_debt = _safe_info_number(info, "totalDebt")

    if pd.isna(total_debt):
        total_debt = _latest_statement_value(
            ticker_obj,
            ["balance_sheet", "quarterly_balance_sheet"],
            [
                "Total Debt",
                "TotalDebt",
                "Long Term Debt And Capital Lease Obligation",
                "Long Term Debt",
            ],
            ttm=False,
        )

    cash = _safe_info_number(info, "totalCash")

    if pd.isna(cash):
        cash = _latest_statement_value(
            ticker_obj,
            ["balance_sheet", "quarterly_balance_sheet"],
            [
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                "Cash Equivalents",
            ],
            ttm=False,
        )

    net_debt = np.nan

    if not pd.isna(total_debt) and not pd.isna(cash):
        net_debt = total_debt - cash

    return {
        "Operating Cash Flow": operating_cash_flow,
        "Free Cash Flow": free_cash_flow,
        "Net Income": net_income,
        "EBITDA": ebitda,
        "Total Debt": total_debt,
        "Cash": cash,
        "Net Debt": net_debt,
    }

#################################################
# YF HISTORY SETTINGS
#################################################

YF_HISTORY_PATH = Path("archive/yf_history.csv")

def read_yf_history_for_date(tickers, sector=None, target_date=None):
    df = load_yf_history()

    if df is None or df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    dated = rows_for_date(df, target_date=target_date)

    if dated.empty:
        return None

    filtered = filter_expected_tickers(dated, tickers, sector=sector)

    if not has_expected_tickers(filtered, tickers):
        return None

    return ensure_yf_schema(filtered)

def read_latest_yf_history(tickers, sector=None):
    df = load_yf_history()

    if df is None or df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    latest = latest_complete_ticker_rows(
        df,
        tickers,
        sector=sector,
    )

    if latest is None or latest.empty:
        return None

    return ensure_yf_schema(latest)


def _expected_ticker_set(tickers):
    if isinstance(tickers, dict):
        raw = tickers.keys()
    else:
        raw = tickers

    return {str(t).upper().strip() for t in raw}


def describe_yf_archive_status(tickers, sector=None):
    expected = _expected_ticker_set(tickers)
    df = load_yf_history()

    out = {
        "expected_tickers": len(expected),
        "today_archive_rows": 0,
        "today_archive_tickers": 0,
        "today_missing_tickers": sorted(expected),
        "today_complete": False,
        "latest_complete_date": None,
    }

    if df is None or df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return out

    today_rows = rows_for_date(df)
    today_filtered = filter_expected_tickers(today_rows, expected, sector=sector)

    if today_filtered is None or today_filtered.empty or "Ticker" not in today_filtered.columns:
        found = set()
    else:
        found = set(today_filtered["Ticker"].dropna().astype(str).str.upper().str.strip())

    out["today_archive_rows"] = int(0 if today_filtered is None else len(today_filtered))
    out["today_archive_tickers"] = int(len(found))
    out["today_missing_tickers"] = sorted(expected - found)
    out["today_complete"] = expected.issubset(found)

    latest = latest_complete_ticker_rows(df, expected, sector=sector)

    if latest is not None and not latest.empty and "Date" in latest.columns:
        dates = pd.to_datetime(latest["Date"], errors="coerce", format="mixed").dropna()

        if not dates.empty:
            out["latest_complete_date"] = dates.max().date().isoformat()

    return out


def describe_edgar_archive_status(tickers):
    return describe_edgar_freshness_status(tickers)


def _count_returned_tickers(payload):
    if isinstance(payload, pd.DataFrame):
        if payload.empty or "Ticker" not in payload.columns:
            return 0

        return int(payload["Ticker"].dropna().astype(str).str.upper().str.strip().nunique())

    if isinstance(payload, dict):
        return int(len([k for k, v in payload.items() if v is not None]))

    return 0


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
            financial_strain_fields = calc_financial_strain_fields(
                t,
                info,
                capex_value=capex,
            )

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
                **financial_strain_fields,
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

    if archived_today is not None:
        archived_today = archived_today.copy()

        # Ensure columns required by current downstream calculations exist.
        # Older archives remain readable, but if these fields are entirely
        # absent/empty for today's snapshot we refresh YF once to backfill.
        for col in YF_REFRESH_REQUIRED_COLUMNS:
            if col not in archived_today.columns:
                archived_today[col] = np.nan

        missing_or_empty = [
            col for col in YF_REFRESH_REQUIRED_COLUMNS
            if pd.to_numeric(archived_today[col], errors="coerce").dropna().empty
        ]

        if not missing_or_empty:
            debug_print(f"Loading today's yfinance rows from yf_history.csv: {sector}")
            return archived_today

        debug_print(
            f"Today's yf_history found, but required current-model columns are missing/empty "
            f"{missing_or_empty}. Pulling yfinance to backfill: {sector}"
        )

        fresh = pull_yfinance(ticker_tuple)

        if fresh is None or fresh.empty:
            debug_print("Fresh yfinance backfill returned empty. Using archive as-is.")
            return archived_today

        fresh = fresh.copy()
        fresh["Ticker"] = fresh["Ticker"].astype(str).str.upper().str.strip()
        archived_today["Ticker"] = archived_today["Ticker"].astype(str).str.upper().str.strip()

        fresh_lookup = fresh.set_index("Ticker")

        for col in missing_or_empty:
            if col in fresh_lookup.columns:
                archived_today[col] = archived_today["Ticker"].map(fresh_lookup[col])
            else:
                archived_today[col] = np.nan

        return archived_today

    try:
        debug_print(f"No yf_history rows found for today. Pulling yfinance: {sector}")

        df = pull_yfinance(ticker_tuple)

        if df.empty:
            raise ValueError("yfinance returned an empty DataFrame")

        return df

    except Exception as e:
        debug_print(f"yfinance pull failed -> {e}")

        fallback = read_latest_yf_history(
            tickers,
            sector=sector
        )

        if fallback is not None:
            debug_print(f"Using latest yf_history.csv fallback: {sector}")
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

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
    }
    
@st.cache_data(ttl=3600)
def load_market_universe(tickers):
    """
    Load YFinance and EDGAR once for the full ticker universe.

    tickers:
        dict like {"MSFT": "MSFT", "NVDA": "NVDA"}
    """

    load_started = time.perf_counter()
    expected_count = len(tickers)

    yf_archive_status = describe_yf_archive_status(tickers, sector=None)
    edgar_archive_status = describe_edgar_archive_status(tickers)

    yf_started = time.perf_counter()
    raw_yf = load_yfinance(
        tuple(sorted(tickers.items())),
        sector=None
    )
    yf_elapsed = time.perf_counter() - yf_started

    edgar_started = time.perf_counter()
    raw_edgar, edgar_runtime_report = load_edgar_with_report(tickers)
    edgar_elapsed = time.perf_counter() - edgar_started

    total_elapsed = time.perf_counter() - load_started

    load_report = {
        "loader": "load_market_universe",
        "expected_tickers": expected_count,
        "total_elapsed_sec": total_elapsed,
        "yfinance": {
            **yf_archive_status,
            "elapsed_sec": yf_elapsed,
            "returned_tickers": _count_returned_tickers(raw_yf),
            "source_mode": (
                "archive_today"
                if yf_archive_status.get("today_complete")
                else "live_or_fallback"
            ),
        },
        "edgar": {
            **edgar_archive_status,
            **edgar_runtime_report,
            "elapsed_sec": edgar_elapsed,
            "returned_tickers": _count_returned_tickers(raw_edgar),
        },
    }

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
        "_load_report": load_report,
    }