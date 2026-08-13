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
from loaders.market_prices import (
    PRESSURE_COLUMNS,
    calc_trading_pressure_fields,
    one_year_return,
    year_to_date_snapshot,
)

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

YFINANCE_PULL_MAX_ATTEMPTS = 3
YFINANCE_PULL_INITIAL_WORKERS = 2
YFINANCE_PULL_BATCH_SIZE = 24
YFINANCE_PULL_BATCH_PAUSE_SECONDS = 0.35
YFINANCE_PULL_RETRY_DELAY_SECONDS = 2.0
YFINANCE_PULL_RATE_LIMIT_DELAY_SECONDS = 6.0


def _is_yfinance_rate_limit_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".casefold()
    tokens = (
        "429",
        "too many requests",
        "rate limit",
        "ratelimit",
        "rate-limit",
        "yf rate limit",
    )
    return any(token in text for token in tokens)


def _chunked(items, size):
    size = max(1, int(size))
    for start in range(0, len(items), size):
        yield items[start:start + size]

YF_REQUIRED_COLUMNS = [
    "Date",
    "Market Data Date",
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
    "YTD Return",
    "YTD Start Market Cap",
    "YTD Year",
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
        "latest_data_date": None,
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
        if "Market Data Date" in latest.columns:
            market_dates = pd.to_datetime(
                latest["Market Data Date"], errors="coerce", format="mixed"
            ).dropna()
            if not market_dates.empty:
                status["latest_data_date"] = market_dates.max().date().isoformat()

    return status

def describe_edgar_archive_status(tickers):
    return describe_edgar_freshness_status(tickers)

def _has_ytd_coverage(frame, tickers, threshold=0.90):
    if frame is None or frame.empty or "Ticker" not in frame.columns:
        return False
    required = {"YTD Return", "YTD Start Market Cap"}
    if not required.issubset(frame.columns):
        return False
    expected = _expected_ticker_set(tickers)
    if not expected:
        return False
    current = frame.copy()
    current["Ticker"] = current["Ticker"].astype(str).str.upper().str.strip()
    valid = current.loc[
        current["Ticker"].isin(expected)
        & pd.to_numeric(current["YTD Return"], errors="coerce").notna()
        & pd.to_numeric(current["YTD Start Market Cap"], errors="coerce").gt(0)
    ]
    return valid["Ticker"].nunique() >= int(np.ceil(len(expected) * float(threshold)))


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


def _market_data_dates(frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Market Data Date" not in frame.columns:
        return []
    parsed = pd.to_datetime(
        frame["Market Data Date"], errors="coerce", format="mixed"
    ).dt.date
    if parsed.isna().any() or len(parsed) != len(frame):
        return []
    return sorted({value.isoformat() for value in parsed})


def resolve_yfinance_market_date_mismatch(merged, fallback, tickers):
    """Use one complete retained snapshot when live rows span market dates.

    YFinance occasionally returns a stale close for one otherwise successful
    ticker.  Mixing that row with current-date rows is valid for neither the
    fixed QQQ reference nor retained history.  The analytical transaction may
    continue from the prior complete retained snapshot, but the live refresh
    remains unsuccessful and must not advance YFinance-owned history.
    """
    live_dates = _market_data_dates(merged)
    if len(live_dates) == 1:
        return merged

    raw_tickers = tickers.keys() if isinstance(tickers, dict) else tickers
    expected_order = [str(ticker).upper().strip() for ticker in raw_tickers]
    expected = set(expected_order)
    retained = ensure_yf_schema(fallback) if isinstance(fallback, pd.DataFrame) else pd.DataFrame()
    if retained.empty or "Ticker" not in retained.columns:
        return merged

    retained = retained.copy()
    retained["Ticker"] = retained["Ticker"].astype(str).str.upper().str.strip()
    retained = retained.loc[retained["Ticker"].isin(expected)].drop_duplicates(
        subset=["Ticker"], keep="last"
    )
    retained_dates = _market_data_dates(retained)
    returned = set(retained["Ticker"]) if not retained.empty else set()
    if returned != expected or len(retained_dates) != 1:
        return merged

    row_order = {ticker: index for index, ticker in enumerate(expected_order)}
    retained["_ticker_order"] = retained["Ticker"].map(row_order)
    retained = (
        retained.sort_values("_ticker_order", kind="stable")
        .drop(columns="_ticker_order")
        .reset_index(drop=True)
    )

    prior_report = dict(getattr(merged, "attrs", {}).get("load_report", {}) or {})
    provider_live_tickers = int(prior_report.get("live_tickers") or 0)
    retained.attrs["load_report"] = {
        **prior_report,
        "source_mode": "archive_fallback_market_date_mismatch",
        "live_tickers": 0,
        "provider_live_tickers": provider_live_tickers,
        "archive_fallback_tickers": len(expected),
        "archive_fallback_symbols": sorted(expected),
        "archive_field_backfills": 0,
        "archive_field_backfill_details": [],
        "archive_field_backfill_columns": {},
        "missing_tickers": [],
        "returned_tickers": len(returned),
        "live_market_data_dates": live_dates,
        "retained_market_data_date": retained_dates[0],
        "live_error": (
            "YFinance live rows did not share one Market Data Date; "
            "the complete retained market snapshot was used without advancing history."
        ),
    }
    return retained

def _safe_market_number(fast_info, info, *keys):
    for key in keys:
        value = (fast_info or {}).get(key)
        if value is None:
            value = (info or {}).get(key)
        value = safe_float(value)
        if pd.notna(value):
            return value
    return np.nan

def _fetch_company_attempt(ticker, company):
    """Fetch one YFinance company and preserve transport/rate-limit diagnostics."""
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
            raise ValueError("price history was empty")
        history = history.dropna(subset=["Close"])
        if history.empty:
            raise ValueError("price history contained no valid close")

        market_data_date = pd.to_datetime(
            history.index[-1], errors="coerce", utc=True
        )

        result = {
            "Ticker": ticker,
            "Company": company,
            "Market Data Date": (
                market_data_date.date().isoformat()
                if pd.notna(market_data_date)
                else None
            ),
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
            **year_to_date_snapshot(history, market_cap),
            **calc_trading_pressure_fields(history),
        }
        return {
            "ticker": str(ticker).upper().strip(),
            "result": result,
            "error": "",
            "rate_limited": False,
        }
    except Exception as exc:
        return {
            "ticker": str(ticker).upper().strip(),
            "result": None,
            "error": f"{type(exc).__name__}: {exc}",
            "rate_limited": _is_yfinance_rate_limit_error(exc),
        }


def pull_yfinance(ticker_tuple, attempts=YFINANCE_PULL_MAX_ATTEMPTS):
    """Pull the configured universe with provider-friendly adaptive pacing.

    The retained archive still advances only on complete live row coverage.
    Pacing changes therefore improve resilience without relaxing the 204/204
    publication contract or silently treating archive fallback rows as live.
    """
    started = time.perf_counter()
    tickers = {str(key).upper().strip(): value for key, value in dict(ticker_tuple).items()}
    pending = dict(tickers)
    collected = {}
    attempt_counts = {ticker: 0 for ticker in tickers}
    last_errors = {}
    rate_limit_events = 0
    market_date_mismatch_events = 0
    market_date_retry_tickers = set()
    retry_delays = []
    rounds_run = 0
    max_attempts = max(1, int(attempts))

    for attempt in range(max_attempts):
        if not pending:
            break
        rounds_run += 1
        workers = YFINANCE_PULL_INITIAL_WORKERS if attempt == 0 else 1
        batch_size = YFINANCE_PULL_BATCH_SIZE if attempt == 0 else min(12, YFINANCE_PULL_BATCH_SIZE)
        items = list(pending.items())
        round_rate_limited = False

        batches = list(_chunked(items, batch_size))
        for batch_index, batch in enumerate(batches):
            with ThreadPoolExecutor(max_workers=workers) as executor:
                outcomes = list(executor.map(lambda item: _fetch_company_attempt(*item), batch))

            for outcome in outcomes:
                ticker = str(outcome.get("ticker") or "").upper().strip()
                if not ticker:
                    continue
                attempt_counts[ticker] = int(attempt_counts.get(ticker, 0)) + 1
                result = outcome.get("result")
                if result:
                    collected[ticker] = result
                    pending.pop(ticker, None)
                    last_errors.pop(ticker, None)
                    continue
                error = str(outcome.get("error") or "unknown provider failure")
                last_errors[ticker] = error
                if bool(outcome.get("rate_limited")):
                    rate_limit_events += 1
                    round_rate_limited = True

            # A tiny inter-batch pause reduces burstiness without materially
            # extending a successful 204-company refresh.
            if batch_index + 1 < len(batches):
                time.sleep(YFINANCE_PULL_BATCH_PAUSE_SECONDS)

        # Successful transport does not guarantee a coherent market
        # observation. Yahoo can briefly return the prior close for one ticker
        # while the rest of the universe has advanced. Retry only those
        # outliers inside the existing bounded attempt budget.
        dated = {}
        for ticker, row in collected.items():
            parsed = pd.to_datetime(
                row.get("Market Data Date"), errors="coerce", format="mixed"
            )
            dated[ticker] = parsed.date() if pd.notna(parsed) else None
        valid_dates = [value for value in dated.values() if value is not None]
        if valid_dates:
            counts = pd.Series(valid_dates).value_counts()
            dominant_date = max(counts.index, key=lambda value: (int(counts[value]), value))
            outliers = sorted(
                ticker for ticker, value in dated.items() if value != dominant_date
            )
            if outliers:
                market_date_mismatch_events += 1
                market_date_retry_tickers.update(outliers)
                for ticker in outliers:
                    collected.pop(ticker, None)
                    pending[ticker] = tickers[ticker]
                    last_errors[ticker] = (
                        "Market Data Date did not match the dominant live observation "
                        f"date {dominant_date.isoformat()}"
                    )

        if pending and attempt + 1 < max_attempts:
            base = (
                YFINANCE_PULL_RATE_LIMIT_DELAY_SECONDS
                if round_rate_limited
                else YFINANCE_PULL_RETRY_DELAY_SECONDS
            )
            delay = min(20.0, float(base) * (1.0 + attempt))
            retry_delays.append(delay)
            time.sleep(delay)

    ordered = [
        collected[ticker]
        for ticker in tickers
        if ticker in collected
    ]
    frame = pd.DataFrame(ordered)
    frame.attrs["provider_report"] = {
        "requested_tickers": len(tickers),
        "succeeded_tickers": len(collected),
        "failed_tickers": sorted(pending),
        "failed_errors": {ticker: last_errors.get(ticker, "") for ticker in sorted(pending)},
        "attempt_rounds": int(rounds_run),
        "retry_rounds": max(0, int(rounds_run) - 1),
        "total_fetch_attempts": int(sum(attempt_counts.values())),
        "rate_limit_events": int(rate_limit_events),
        "market_date_mismatch_events": int(market_date_mismatch_events),
        "market_date_retry_tickers": sorted(market_date_retry_tickers),
        "retry_delays_sec": retry_delays,
        "initial_workers": int(YFINANCE_PULL_INITIAL_WORKERS),
        "retry_workers": 1,
        "batch_size": int(YFINANCE_PULL_BATCH_SIZE),
        "elapsed_sec": time.perf_counter() - started,
    }
    return frame

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
    allow_live=False,
):
    # Both an explicit refresh request and developer-policy authorization are
    # required. Neither flag is sufficient on its own.
    live_enabled = bool(allow_live and force_refresh)
    return _load_yfinance_cached(
        ticker_tuple,
        sector=sector,
        force_refresh=bool(force_refresh),
        refresh_token=int(refresh_token),
        clock_token=(clock_token or market_cache_token()) if live_enabled else "retained-snapshot",
        allow_live=live_enabled,
    )

@st.cache_data(ttl=900)
def _load_yfinance_cached(
    ticker_tuple,
    sector=None,
    *,
    force_refresh=False,
    refresh_token=0,
    clock_token=None,
    allow_live=False,
):

    del refresh_token, clock_token

    tickers = dict(ticker_tuple)
    archived_today = read_yf_history_for_date(tickers, sector=sector)
    latest_archive = read_latest_yf_history(tickers, sector=sector)

    # Reader startup is intentionally freshness-agnostic. A stale retained
    # snapshot may warrant a warning, but it must never authorize a provider
    # call. Live access is reserved for an explicit developer refresh.
    if not (force_refresh and allow_live):
        retained = (
            archived_today
            if archived_today is not None and not archived_today.empty
            else latest_archive
        )
        if retained is None or retained.empty:
            raise RuntimeError(
                "YFinance retained history is unavailable. Use Refresh YFinance "
                "in Developer Tools to create a snapshot."
            )
        return _archive_yfinance_result(
            retained,
            tickers,
            source_mode="archive_read_mode",
            decision="retained_snapshot",
        )
    decision = yfinance_load_decision(
        force_refresh=bool(force_refresh),
        market_open=is_market_hours(),
        has_current_archive=archived_today is not None and not archived_today.empty,
        has_latest_archive=latest_archive is not None and not latest_archive.empty,
    )

    ytd_archive = (
        archived_today
        if archived_today is not None and not archived_today.empty
        else latest_archive
    )
    if (
        decision in {"archive_current", "archive_closed"}
        and not _has_ytd_coverage(ytd_archive, tickers)
    ):
        decision = "live_ytd_bootstrap"

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
        trigger = (
            "manual"
            if force_refresh
            else "ytd_bootstrap"
            if decision == "live_ytd_bootstrap"
            else "automatic_daily"
        )
        debug_print(f"Pulling current YFinance data ({trigger}): {sector}")
        fresh = pull_yfinance(ticker_tuple)
        provider_report = dict(getattr(fresh, "attrs", {}).get("provider_report", {}))
        if fresh is None or fresh.empty:
            failures = provider_report.get("failed_tickers") or []
            detail = f"; failed tickers={','.join(failures[:12])}" if failures else ""
            raise ValueError(f"yfinance returned an empty DataFrame{detail}")

        merged = merge_live_yfinance_with_archive(fresh, fallback, tickers)
        merged = resolve_yfinance_market_date_mismatch(merged, fallback, tickers)
        report = dict(getattr(merged, "attrs", {}).get("load_report", {}))
        report.update({
            "decision": decision,
            "refresh_trigger": trigger,
            "provider_attempt_rounds": int(provider_report.get("attempt_rounds") or 0),
            "provider_retry_rounds": int(provider_report.get("retry_rounds") or 0),
            "provider_fetch_attempts": int(provider_report.get("total_fetch_attempts") or 0),
            "provider_rate_limit_events": int(provider_report.get("rate_limit_events") or 0),
            "provider_market_date_mismatch_events": int(
                provider_report.get("market_date_mismatch_events") or 0
            ),
            "provider_market_date_retry_tickers": (
                provider_report.get("market_date_retry_tickers") or []
            ),
            "provider_failed_tickers": provider_report.get("failed_tickers") or [],
            "provider_failed_errors": provider_report.get("failed_errors") or {},
            "provider_retry_delays_sec": provider_report.get("retry_delays_sec") or [],
            "provider_initial_workers": int(provider_report.get("initial_workers") or YFINANCE_PULL_INITIAL_WORKERS),
            "provider_batch_size": int(provider_report.get("batch_size") or YFINANCE_PULL_BATCH_SIZE),
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
        "yfinance": load_yfinance(
            tuple(sorted(tickers.items())), sector=sector, allow_live=False
        ),
        "edgar": load_edgar(tickers, allow_live=False),
    }

def load_market_universe(
    tickers,
    *,
    force_yfinance_refresh=False,
    yfinance_refresh_token=0,
    force_edgar_refresh=False,
    edgar_refresh_token=0,
    clock_token=None,
    allow_yfinance_live=False,
    allow_edgar_live=False,
):
    yfinance_live_enabled = bool(
        allow_yfinance_live and force_yfinance_refresh
    )
    edgar_live_enabled = bool(allow_edgar_live and force_edgar_refresh)
    return _load_market_universe_cached(
        tickers,
        force_yfinance_refresh=bool(force_yfinance_refresh),
        yfinance_refresh_token=int(yfinance_refresh_token),
        force_edgar_refresh=bool(force_edgar_refresh),
        edgar_refresh_token=int(edgar_refresh_token),
        clock_token=(
            clock_token or market_cache_token()
            if yfinance_live_enabled
            else "retained-snapshot"
        ),
        allow_yfinance_live=yfinance_live_enabled,
        allow_edgar_live=edgar_live_enabled,
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
    allow_yfinance_live=False,
    allow_edgar_live=False,
):

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
        allow_live=allow_yfinance_live,
    )
    yf_elapsed = time.perf_counter() - yf_started

    edgar_started = time.perf_counter()
    raw_edgar, edgar_runtime_report = load_edgar_with_report(
        tickers,
        force_refresh=force_edgar_refresh,
        allow_live=allow_edgar_live,
        refresh_token=edgar_refresh_token,
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
