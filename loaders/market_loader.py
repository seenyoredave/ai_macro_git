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
from config.market_clock import (
    is_market_hours,
    market_cache_token,
    utc_now,
    yfinance_load_decision,
)
from loaders.company_fundamentals import extract_fundamental_fields, safe_float
from loaders.edgar_loader import (
    describe_edgar_freshness_status,
    load_edgar,
    load_edgar_with_report,
)
from loaders.market_freshness import merge_live_with_archive
from loaders.market_prices import PRESSURE_COLUMNS, calc_trading_pressure_fields, one_year_return

EVG_REQUIRED_COLUMNS = ["Revenue Growth", "CapEx", "CapEx Growth"]
FORWARD_VALUATION_COLUMNS = [
    "Forward Revenue",
    "Operating Income",
    "Operating Margin",
    "Forward EBIT",
    "Enterprise Value",
    "Forward EV/EBIT",
]
FINANCIAL_CONDITION_COLUMNS = [
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
YF_REQUIRED_COLUMNS = [
    "Date",
    "Sector",
    "Ticker",
    "Company",
    "Price",
    "P/E",
    "Forward EV/EBIT",
    "Market Cap",
    "Enterprise Value",
    "Revenue",
    "Forward Revenue",
    "Operating Income",
    "Operating Margin",
    "Forward EBIT",
    *EVG_REQUIRED_COLUMNS,
    *FINANCIAL_CONDITION_COLUMNS,
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

    if sector is None and "Ticker" in filtered.columns:
        filtered = filtered.drop_duplicates(subset=["Ticker"], keep="last")

    return ensure_yf_schema(filtered)

def read_latest_yf_history(tickers, sector=None):
    history = load_yf_history()
    if history is None or history.empty or not {"Date", "Ticker"}.issubset(history.columns):
        return None

    latest = latest_complete_ticker_rows(history, tickers, sector=sector)
    if latest is None or latest.empty:
        return None
    if sector is None and "Ticker" in latest.columns:
        latest = latest.drop_duplicates(subset=["Ticker"], keep="last")
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

def merge_live_yfinance_with_archive(fresh, fallback, tickers):
    return merge_live_with_archive(
        fresh,
        fallback,
        tickers,
        required_columns=YF_REQUIRED_COLUMNS,
        metadata_columns=(
            "Date",
            "Sector",
            "Ticker",
            "Company",
            "Basket Score",
            "Basket Tier",
            "Basket Weight",
        ),
    )

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
        market_cap = _safe_market_number(fast_info, info, "market_cap", "marketCap")
        net_debt = pd.to_numeric(fundamentals.get("Net Debt", np.nan), errors="coerce")
        forward_ebit = pd.to_numeric(
            fundamentals.get("Forward EBIT", np.nan), errors="coerce"
        )
        enterprise_value = (
            float(market_cap) + float(net_debt)
            if pd.notna(market_cap) and pd.notna(net_debt)
            else _safe_market_number(fast_info, info, "enterprise_value", "enterpriseValue")
        )
        forward_ev_ebit = (
            float(enterprise_value) / float(forward_ebit)
            if pd.notna(enterprise_value)
            and pd.notna(forward_ebit)
            and enterprise_value > 0
            and abs(float(forward_ebit)) > 1e-9
            else np.nan
        )

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
            "Forward EV/EBIT": forward_ev_ebit,
            "Market Cap": market_cap,
            "Enterprise Value": enterprise_value,
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

def pull_yfinance(ticker_tuple, attempts=2):
    tickers = dict(ticker_tuple)
    pending = dict(tickers)
    collected = {}

    for attempt in range(max(1, int(attempts))):
        if not pending:
            break
        workers = 3 if attempt == 0 else 1
        items = list(pending.items())
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(lambda item: _fetch_company(*item), items))

        for result in results:
            if result and result.get("Ticker"):
                ticker = str(result["Ticker"]).upper().strip()
                collected[ticker] = result
                pending.pop(ticker, None)

        if pending and attempt + 1 < max(1, int(attempts)):
            time.sleep(1.0)

    ordered = [
        collected[ticker]
        for ticker in (str(value).upper().strip() for value in tickers)
        if ticker in collected
    ]
    return pd.DataFrame(ordered)

def _archive_yfinance_result(frame, tickers, *, source_mode, decision):
    archived = ensure_yf_schema(frame).copy()
    expected = _expected_ticker_set(tickers)
    returned = (
        set(archived["Ticker"].dropna().astype(str).str.upper().str.strip())
        if "Ticker" in archived.columns
        else set()
    )
    archived.attrs["load_report"] = {
        "source_mode": source_mode,
        "decision": decision,
        "requested_at_utc": utc_now().isoformat(timespec="seconds"),
        "archive_tickers": len(returned),
        "missing_tickers": sorted(expected - returned),
    }
    return archived

def load_yfinance(
    ticker_tuple,
    sector=None,
    *,
    force_refresh=False,
    refresh_token=0,
    clock_token=None,
):
    return _load_yfinance_cached(
        ticker_tuple,
        sector=sector,
        force_refresh=bool(force_refresh),
        refresh_token=int(refresh_token),
        clock_token=clock_token or market_cache_token(),
    )

@st.cache_data(ttl=900)
def _load_yfinance_cached(
    ticker_tuple,
    sector=None,
    *,
    force_refresh=False,
    refresh_token=0,
    clock_token=None,
):

    del refresh_token, clock_token

    tickers = dict(ticker_tuple)
    archived_today = read_yf_history_for_date(tickers, sector=sector)
    latest_archive = read_latest_yf_history(tickers, sector=sector)
    decision = yfinance_load_decision(
        force_refresh=bool(force_refresh),
        market_open=is_market_hours(),
        has_current_archive=archived_today is not None and not archived_today.empty,
        has_latest_archive=latest_archive is not None and not latest_archive.empty,
    )

    if decision == "archive_current":
        debug_print(f"Using current-date YFinance archive: {sector}")
        return _archive_yfinance_result(
            archived_today,
            tickers,
            source_mode="archive_current",
            decision=decision,
        )

    if decision == "archive_closed":
        debug_print(f"Market closed; using latest complete YFinance archive: {sector}")
        return _archive_yfinance_result(
            latest_archive,
            tickers,
            source_mode="archive_market_closed",
            decision=decision,
        )

    if decision == "unavailable":
        raise RuntimeError(
            "YFinance archive is unavailable outside regular market hours. "
            "Use Refresh YFinance to request a manual live pull."
        )

    fallback = archived_today if archived_today is not None and not archived_today.empty else latest_archive

    try:
        trigger = "manual" if force_refresh else "automatic_daily"
        debug_print(f"Pulling current YFinance data ({trigger}): {sector}")
        fresh = pull_yfinance(ticker_tuple)
        if fresh is None or fresh.empty:
            raise ValueError("yfinance returned an empty DataFrame")

        merged = merge_live_yfinance_with_archive(fresh, fallback, tickers)
        report = dict(getattr(merged, "attrs", {}).get("load_report", {}))
        report.update({
            "decision": decision,
            "refresh_trigger": trigger,
        })
        merged.attrs["load_report"] = report
        return ensure_yf_schema(merged)

    except Exception as exc:
        debug_print(f"Current YFinance pull failed -> {exc}")
        if fallback is not None and not fallback.empty:
            result = _archive_yfinance_result(
                fallback,
                tickers,
                source_mode="archive_fallback",
                decision=decision,
            )
            result.attrs["load_report"]["live_error"] = str(exc)
            return result

        raise RuntimeError(
            "YFinance failed and no usable yf_history fallback exists."
        ) from exc

@st.cache_data(ttl=900)
def load_sector_data(tickers, sector=None):
    return {
        "yfinance": load_yfinance(tuple(sorted(tickers.items())), sector=sector),
        "edgar": load_edgar(tickers),
    }

def load_market_universe(
    tickers,
    *,
    force_yfinance_refresh=False,
    yfinance_refresh_token=0,
    force_edgar_refresh=False,
    edgar_refresh_token=0,
    clock_token=None,
):
    return _load_market_universe_cached(
        tickers,
        force_yfinance_refresh=bool(force_yfinance_refresh),
        yfinance_refresh_token=int(yfinance_refresh_token),
        force_edgar_refresh=bool(force_edgar_refresh),
        edgar_refresh_token=int(edgar_refresh_token),
        clock_token=clock_token or market_cache_token(),
    )

@st.cache_data(ttl=900)
def _load_market_universe_cached(
    tickers,
    *,
    force_yfinance_refresh=False,
    yfinance_refresh_token=0,
    force_edgar_refresh=False,
    edgar_refresh_token=0,
    clock_token=None,
):

    del edgar_refresh_token

    load_started = time.perf_counter()
    expected_count = len(tickers)
    yf_archive_status = describe_yf_archive_status(tickers, sector=None)
    edgar_archive_status = describe_edgar_archive_status(tickers)

    yf_started = time.perf_counter()
    raw_yf = load_yfinance(
        tuple(sorted(tickers.items())),
        sector=None,
        force_refresh=force_yfinance_refresh,
        refresh_token=yfinance_refresh_token,
        clock_token=clock_token,
    )
    yf_elapsed = time.perf_counter() - yf_started

    edgar_started = time.perf_counter()
    raw_edgar, edgar_runtime_report = load_edgar_with_report(
        tickers,
        force_refresh=force_edgar_refresh,
    )
    edgar_elapsed = time.perf_counter() - edgar_started

    yf_runtime_report = dict(getattr(raw_yf, "attrs", {}).get("load_report", {}))

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
        "_load_report": {
            "loader": "load_market_universe",
            "expected_tickers": expected_count,
            "total_elapsed_sec": time.perf_counter() - load_started,
            "yfinance": {
                **yf_archive_status,
                **yf_runtime_report,
                "elapsed_sec": yf_elapsed,
                "returned_tickers": _count_returned_tickers(raw_yf),
            },
            "edgar": {
                **edgar_archive_status,
                **edgar_runtime_report,
                "elapsed_sec": edgar_elapsed,
                "returned_tickers": _count_returned_tickers(raw_edgar),
            },
        },
    }
