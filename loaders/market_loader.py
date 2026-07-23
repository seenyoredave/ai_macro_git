"""Market-data orchestration.

This module owns archive-first loading and coordinates YFinance plus EDGAR.
Statement parsing lives in ``company_fundamentals``; price-history calculations
live in ``market_prices``.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

from archive.archive_reader import (
    filter_expected_tickers,
    has_expected_tickers,
    latest_complete_ticker_rows,
    load_yf_history,
    rows_for_date,
)
from config.debug_config import debug_print
from loaders.company_fundamentals import extract_fundamental_fields, safe_float
from loaders.edgar_loader import (
    describe_edgar_freshness_status,
    load_edgar,
    load_edgar_with_report,
)
from loaders.market_prices import PRESSURE_COLUMNS, calc_trading_pressure_fields, one_year_return


EVG_REQUIRED_COLUMNS = ["Revenue Growth", "CapEx", "CapEx Growth"]
FINANCIAL_STRAIN_COLUMNS = [
    "Operating Cash Flow",
    "Free Cash Flow",
    "Net Income",
    "EBITDA",
    "Total Debt",
    "Cash",
    "Net Debt",
    "FCF Margin YoY Change",
    "Net Debt / EBITDA YoY Change",
    "CapEx / OCF YoY Change",
]
YF_REFRESH_REQUIRED_COLUMNS = EVG_REQUIRED_COLUMNS + FINANCIAL_STRAIN_COLUMNS + PRESSURE_COLUMNS

YF_REQUIRED_COLUMNS = [
    "Date",
    "Sector",
    "Ticker",
    "Company",
    "Price",
    "P/E",
    "Forward P/E",
    "Market Cap",
    "Revenue",
    *EVG_REQUIRED_COLUMNS,
    *FINANCIAL_STRAIN_COLUMNS,
    "Beta",
    "52W High",
    "52W Low",
    "1Y Return",
    *PRESSURE_COLUMNS,
    "Basket Score",
    "Basket Tier",
    "Basket Weight",
]


def ensure_yf_schema(df):
    df = df.copy()
    for column in YF_REQUIRED_COLUMNS:
        if column not in df.columns:
            df[column] = np.nan
    return df


def _expected_ticker_set(tickers):
    raw = tickers.keys() if isinstance(tickers, dict) else tickers
    return {str(ticker).upper().strip() for ticker in raw}


def read_yf_history_for_date(tickers, sector=None, target_date=None):
    history = load_yf_history()
    if history is None or history.empty or not {"Date", "Ticker"}.issubset(history.columns):
        return None

    dated = rows_for_date(history, target_date=target_date)
    if dated.empty:
        return None

    filtered = filter_expected_tickers(dated, tickers, sector=sector)
    if not has_expected_tickers(filtered, tickers):
        return None

    return ensure_yf_schema(filtered)


def read_latest_yf_history(tickers, sector=None):
    history = load_yf_history()
    if history is None or history.empty or not {"Date", "Ticker"}.issubset(history.columns):
        return None

    latest = latest_complete_ticker_rows(history, tickers, sector=sector)
    if latest is None or latest.empty:
        return None
    return ensure_yf_schema(latest)


def describe_yf_archive_status(tickers, sector=None):
    expected = _expected_ticker_set(tickers)
    history = load_yf_history()
    status = {
        "expected_tickers": len(expected),
        "today_archive_rows": 0,
        "today_archive_tickers": 0,
        "today_missing_tickers": sorted(expected),
        "today_complete": False,
        "latest_complete_date": None,
    }

    if history is None or history.empty or not {"Date", "Ticker"}.issubset(history.columns):
        return status

    today = filter_expected_tickers(rows_for_date(history), expected, sector=sector)
    found = (
        set(today["Ticker"].dropna().astype(str).str.upper().str.strip())
        if today is not None and not today.empty and "Ticker" in today.columns
        else set()
    )

    status.update({
        "today_archive_rows": int(0 if today is None else len(today)),
        "today_archive_tickers": len(found),
        "today_missing_tickers": sorted(expected - found),
        "today_complete": expected.issubset(found),
    })

    latest = latest_complete_ticker_rows(history, expected, sector=sector)
    if latest is not None and not latest.empty and "Date" in latest.columns:
        dates = pd.to_datetime(latest["Date"], errors="coerce", format="mixed").dropna()
        if not dates.empty:
            status["latest_complete_date"] = dates.max().date().isoformat()

    return status


def describe_edgar_archive_status(tickers):
    return describe_edgar_freshness_status(tickers)


def _count_returned_tickers(payload):
    if isinstance(payload, pd.DataFrame):
        if payload.empty or "Ticker" not in payload.columns:
            return 0
        return int(payload["Ticker"].dropna().astype(str).str.upper().str.strip().nunique())
    if isinstance(payload, dict):
        return int(sum(value is not None for value in payload.values()))
    return 0


def _safe_market_number(fast_info, info, *keys):
    for key in keys:
        value = (fast_info or {}).get(key)
        if value is None:
            value = (info or {}).get(key)
        value = safe_float(value)
        if pd.notna(value):
            return value
    return np.nan


def _fetch_company(ticker, company):
    try:
        ticker_obj = yf.Ticker(ticker)
        fast_info = getattr(ticker_obj, "fast_info", {}) or {}
        info = getattr(ticker_obj, "info", {}) or {}
        fundamentals = extract_fundamental_fields(ticker_obj, info)

        history = ticker_obj.history(period="2y", auto_adjust=True)
        if history is None or history.empty:
            return None
        history = history.dropna(subset=["Close"])
        if history.empty:
            return None

        return {
            "Ticker": ticker,
            "Company": company,
            "Price": _safe_market_number(fast_info, info, "last_price", "regularMarketPrice"),
            "Beta": _safe_market_number(fast_info, info, "beta"),
            "P/E": _safe_market_number(fast_info, info, "trailing_pe", "trailingPE"),
            "Forward P/E": _safe_market_number(fast_info, info, "forward_pe", "forwardPE"),
            "Market Cap": _safe_market_number(fast_info, info, "market_cap", "marketCap"),
            "Revenue": _safe_market_number(fast_info, info, "total_revenue", "totalRevenue"),
            **fundamentals,
            "52W High": _safe_market_number(fast_info, info, "year_high", "fiftyTwoWeekHigh"),
            "52W Low": _safe_market_number(fast_info, info, "year_low", "fiftyTwoWeekLow"),
            "1Y Return": one_year_return(history),
            **calc_trading_pressure_fields(history),
        }
    except Exception as exc:
        print(f"{ticker} failed -> {exc}")
        return None


def pull_yfinance(ticker_tuple):
    tickers = dict(ticker_tuple)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda item: _fetch_company(*item), tickers.items()))
    return pd.DataFrame([result for result in results if result])


@st.cache_data(ttl=3600)
def load_yfinance(ticker_tuple, sector=None):
    tickers = dict(ticker_tuple)
    archived_today = read_yf_history_for_date(tickers, sector=sector)

    if archived_today is not None:
        archived_today = ensure_yf_schema(archived_today)
        missing = [
            column
            for column in YF_REFRESH_REQUIRED_COLUMNS
            if pd.to_numeric(archived_today[column], errors="coerce").dropna().empty
        ]
        if not missing:
            debug_print(f"Loading today's yfinance rows from yf_history.csv: {sector}")
            return archived_today

        debug_print(
            "Today's yf_history is missing current-model fields "
            f"{missing}. Pulling yfinance once to backfill: {sector}"
        )
        fresh = pull_yfinance(ticker_tuple)
        if fresh is None or fresh.empty:
            return archived_today

        archived_today = archived_today.copy()
        archived_today["Ticker"] = archived_today["Ticker"].astype(str).str.upper().str.strip()
        fresh = fresh.copy()
        fresh["Ticker"] = fresh["Ticker"].astype(str).str.upper().str.strip()
        lookup = fresh.set_index("Ticker")

        for column in missing:
            archived_today[column] = (
                archived_today["Ticker"].map(lookup[column])
                if column in lookup.columns
                else np.nan
            )
        return archived_today

    try:
        debug_print(f"No yf_history rows found for today. Pulling yfinance: {sector}")
        fresh = pull_yfinance(ticker_tuple)
        if fresh is None or fresh.empty:
            raise ValueError("yfinance returned an empty DataFrame")
        return fresh
    except Exception as exc:
        debug_print(f"yfinance pull failed -> {exc}")
        fallback = read_latest_yf_history(tickers, sector=sector)
        if fallback is not None:
            debug_print(f"Using latest yf_history.csv fallback: {sector}")
            return fallback
        raise RuntimeError("yfinance failed and no usable yf_history fallback exists.") from exc


@st.cache_data(ttl=3600)
def load_sector_data(tickers, sector=None):
    return {
        "yfinance": load_yfinance(tuple(sorted(tickers.items())), sector=sector),
        "edgar": load_edgar(tickers),
    }


@st.cache_data(ttl=3600)
def load_market_universe(tickers):
    load_started = time.perf_counter()
    expected_count = len(tickers)
    yf_archive_status = describe_yf_archive_status(tickers, sector=None)
    edgar_archive_status = describe_edgar_archive_status(tickers)

    yf_started = time.perf_counter()
    raw_yf = load_yfinance(tuple(sorted(tickers.items())), sector=None)
    yf_elapsed = time.perf_counter() - yf_started

    edgar_started = time.perf_counter()
    raw_edgar, edgar_runtime_report = load_edgar_with_report(tickers)
    edgar_elapsed = time.perf_counter() - edgar_started

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
        "_load_report": {
            "loader": "load_market_universe",
            "expected_tickers": expected_count,
            "total_elapsed_sec": time.perf_counter() - load_started,
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
        },
    }
