from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from archive.archive_reader import (
    filter_expected_tickers,
    load_edgar_history,
    parse_archive_dates,
)
from config.market_clock import market_date

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

    return True


def is_archive_eligible_edgar_payload(payload) -> bool:
    return (
        isinstance(payload, dict)
        and str(payload.get("EDGAR Source", "")).strip() == "SEC Live"
        and _is_usable_edgar_row(payload)
    )


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
        cutoff = market_date() - timedelta(days=int(max_age_days))
        filtered = filtered[filtered["_parsed_date"] >= cutoff].copy()

        if filtered.empty:
            return pd.DataFrame(columns=df.columns)

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
