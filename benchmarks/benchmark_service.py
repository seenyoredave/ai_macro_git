import numpy as np
import pandas as pd
import streamlit as st

from archive.archive_reader import load_benchmark_history, rows_for_date
from benchmarks.benchmark_normalization import normalize_benchmark_dataframe
from config.benchmark_config import (
    ACTIVE_BENCHMARKS,
    BENCHMARK_UNIVERSES,
    BENCHMARK_VERSION,
    BENCHMARK_WEIGHTS,
    QQQ_WEIGHTS_EFFECTIVE_DATE,
)
from config.debug_config import debug_print
from config.market_clock import market_cache_token
from loaders.benchmark_loader import load_benchmark

_REQUIRED_ARCHIVE_COLUMNS = {
    "Date",
    "Benchmark",
    "Forward EV/EBIT",
    "Forward EBIT Yield",
    "Avg Return",
    "Beta",
    "Member Count",
    "Benchmark Version",
}


def _metrics_from_archive_row(row):
    archive_date = pd.to_datetime(row.get("Date"), errors="coerce")
    market_data_date = pd.to_datetime(
        row.get("Market Data Date", row.get("Date")), errors="coerce"
    )
    return {
        "forward_ev_ebit": row.get("Forward EV/EBIT", np.nan),
        "forward_ebit_yield": row.get("Forward EBIT Yield", np.nan),
        "avg_return": row.get("Avg Return", np.nan),
        "beta": row.get("Beta", np.nan),
        "member_count": row.get("Member Count", 0),
        "version": BENCHMARK_VERSION,
        "weight_effective_date": row.get(
            "Weight Effective Date", QQQ_WEIGHTS_EFFECTIVE_DATE
        ),
        "source_mode": "archive",
        "archive_date": (
            archive_date.date().isoformat() if pd.notna(archive_date) else None
        ),
        "market_data_date": (
            market_data_date.date().isoformat()
            if pd.notna(market_data_date)
            else None
        ),
    }


def get_archived_benchmark_metrics(benchmark: str, *, current_only: bool = True):
    try:
        history = load_benchmark_history()
    except Exception:
        return None

    if history is None or history.empty or not _REQUIRED_ARCHIVE_COLUMNS.issubset(history.columns):
        return None

    eligible = history.copy()
    eligible["Benchmark"] = eligible["Benchmark"].astype(str).str.upper().str.strip()
    eligible["Benchmark Version"] = eligible["Benchmark Version"].astype(str).str.strip()
    eligible = eligible[
        (eligible["Benchmark"] == benchmark.upper().strip())
        & (eligible["Benchmark Version"] == BENCHMARK_VERSION)
    ].copy()
    if eligible.empty:
        return None

    if current_only:
        eligible = rows_for_date(eligible)
    else:
        eligible["_parsed_date"] = pd.to_datetime(
            eligible["Date"], errors="coerce", format="mixed"
        )
        eligible = eligible.loc[eligible["_parsed_date"].notna()].sort_values(
            "_parsed_date",
            kind="stable",
        )

    if eligible.empty:
        return None

    return _metrics_from_archive_row(eligible.iloc[-1])


def _single_market_data_date(frame: pd.DataFrame) -> str:
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Market Data Date" not in frame.columns:
        raise ValueError("Benchmark input has no Market Data Date")
    dates = pd.to_datetime(
        frame["Market Data Date"], errors="coerce", format="mixed"
    ).dt.date.dropna()
    unique = sorted(set(dates))
    if len(unique) != 1:
        raise ValueError(f"Benchmark members do not share one market date: {unique}")
    return unique[0].isoformat()


def get_benchmark_metrics_from_market_frame(benchmark: str, market_frame: pd.DataFrame) -> dict:
    """Build the fixed benchmark directly from the resolved market universe.

    This keeps the sector reference on the exact same provider observation date
    as the 204-name YFinance universe.  The retained market universe contains
    GOOG but not GOOGL, so the documented fixed-reference contract uses the
    retained GOOG Class C return for the GOOGL Class A weight as well.  That
    makes every benchmark observation reproducible from ``yf_history.csv``.
    """
    if benchmark not in ACTIVE_BENCHMARKS:
        raise ValueError(f"Benchmark {benchmark} is configured but not active")
    if not isinstance(market_frame, pd.DataFrame) or market_frame.empty:
        raise ValueError("Resolved market frame is unavailable for benchmark construction")
    if "Ticker" not in market_frame.columns:
        raise ValueError("Resolved market frame has no Ticker column")

    members = BENCHMARK_UNIVERSES[benchmark]
    weights = BENCHMARK_WEIGHTS.get(benchmark)
    if not weights:
        raise ValueError(f"Active benchmark {benchmark} has no configured weights")

    frame = market_frame.copy()
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame = frame.drop_duplicates(subset=["Ticker"], keep="last").set_index("Ticker")

    rows = []
    aliases = {}
    for ticker in members:
        source_ticker = ticker
        if source_ticker not in frame.index and ticker == "GOOGL" and "GOOG" in frame.index:
            source_ticker = "GOOG"
            aliases[ticker] = source_ticker
        if source_ticker not in frame.index:
            raise ValueError(f"Fixed benchmark member unavailable in market universe: {ticker}")
        row = frame.loc[source_ticker].copy()
        row["Ticker"] = ticker
        row["Benchmark Weight"] = float(weights[ticker])
        rows.append(row)

    benchmark_frame = pd.DataFrame(rows).reset_index(drop=True)
    market_data_date = _single_market_data_date(benchmark_frame)
    normalized = normalize_benchmark_dataframe(benchmark_frame)
    normalized.update(
        {
            "version": BENCHMARK_VERSION,
            "weight_effective_date": QQQ_WEIGHTS_EFFECTIVE_DATE,
            "market_data_date": market_data_date,
            "member_count": int(len(benchmark_frame)),
            "member_aliases": aliases,
        }
    )

    load_report = dict(getattr(market_frame, "attrs", {}).get("load_report", {}) or {})
    raw_mode = str(load_report.get("source_mode") or "").strip().casefold()
    live_complete = (
        raw_mode.startswith("live")
        and int(load_report.get("archive_fallback_tickers") or 0) == 0
        and not (load_report.get("missing_tickers") or [])
    )
    normalized["source_mode"] = (
        "live_market_universe" if live_complete else "retained_market_universe"
    )
    normalized["live_tickers"] = len(benchmark_frame) if live_complete else 0
    normalized["expected_tickers"] = len(members)
    normalized["archive_fallback_tickers"] = 0 if live_complete else len(benchmark_frame)
    normalized["missing_tickers"] = []
    normalized["archive_field_backfills"] = int(load_report.get("archive_field_backfills") or 0)
    return normalized


def get_benchmark_metrics(
    benchmark: str,
    *,
    force_refresh: bool = False,
    refresh_token: int = 0,
    clock_token: str | None = None,
    allow_live: bool = False,
):
    if benchmark not in ACTIVE_BENCHMARKS:
        raise ValueError(f"Benchmark {benchmark} is configured but not active")

    live_enabled = bool(allow_live and force_refresh)
    return _get_benchmark_metrics_cached(
        benchmark,
        force_refresh=bool(force_refresh),
        refresh_token=int(refresh_token),
        clock_token=(clock_token or market_cache_token()) if live_enabled else "retained-snapshot",
        allow_live=live_enabled,
    )


@st.cache_data(ttl=900)
def _get_benchmark_metrics_cached(
    benchmark: str,
    *,
    force_refresh: bool = False,
    refresh_token: int = 0,
    clock_token: str | None = None,
    allow_live: bool = False,
):
    current_archive = get_archived_benchmark_metrics(benchmark, current_only=True)
    latest_archive = get_archived_benchmark_metrics(benchmark, current_only=False)

    if not (force_refresh and allow_live) and current_archive is not None:
        debug_print(f"Loading current-date weighted benchmark from archive: {benchmark}")
        current_archive["source_mode"] = "archive_current"
        return current_archive

    if not (force_refresh and allow_live):
        if latest_archive is not None:
            latest_archive["source_mode"] = "archive_read_mode"
            return latest_archive
        raise RuntimeError(
            f"{benchmark} benchmark archive is unavailable. Use Refresh YFinance "
            "in Developer Tools to create a snapshot."
        )

    # Explicit developer refreshes are real refreshes even outside regular
    # trading hours.  This path remains for bounded tooling/tests; the main app
    # now constructs QQQ from the same resolved 204-name YFinance frame so the
    # reference and sector universe cannot land on different market dates.
    try:
        trigger = "manual" if force_refresh else "automatic_daily"
        debug_print(f"Pulling current weighted benchmark ({trigger}): {benchmark}")
        frame = load_benchmark(
            benchmark,
            force_refresh=force_refresh,
            refresh_token=refresh_token,
            clock_token=clock_token,
            allow_live=True,
        )
        if frame is None or frame.empty:
            raise ValueError(f"{benchmark} benchmark pull returned an empty DataFrame")

        market_data_date = _single_market_data_date(frame)
        normalized = normalize_benchmark_dataframe(frame)
        normalized["version"] = BENCHMARK_VERSION
        normalized["source_mode"] = "live"
        normalized["refresh_trigger"] = trigger
        normalized["market_data_date"] = market_data_date
        return normalized
    except Exception as exc:
        if latest_archive is not None:
            debug_print(f"Benchmark live pull failed; using archive: {benchmark} -> {exc}")
            latest_archive["source_mode"] = "archive_fallback"
            latest_archive["live_error"] = str(exc)
            return latest_archive
        raise
