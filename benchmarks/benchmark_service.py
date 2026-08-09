import numpy as np
import pandas as pd
import streamlit as st

from archive.archive_reader import load_benchmark_history, rows_for_date
from benchmarks.benchmark_normalization import normalize_benchmark_dataframe
from config.benchmark_config import (
    ACTIVE_BENCHMARKS,
    BENCHMARK_VERSION,
    QQQ_WEIGHTS_EFFECTIVE_DATE,
)
from config.debug_config import debug_print
from config.market_clock import is_market_hours, market_cache_token
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

    if not is_market_hours():
        if latest_archive is not None:
            debug_print(f"Market closed; loading latest weighted benchmark archive: {benchmark}")
            latest_archive["source_mode"] = "archive_market_closed"
            return latest_archive
        raise RuntimeError(
            f"{benchmark} benchmark archive is unavailable outside regular market hours. "
            "Use Refresh YFinance to request a manual live pull."
        )

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

        normalized = normalize_benchmark_dataframe(frame)
        normalized["version"] = BENCHMARK_VERSION
        normalized["source_mode"] = "live"
        normalized["refresh_trigger"] = trigger
        return normalized
    except Exception as exc:
        if latest_archive is not None:
            debug_print(f"Benchmark live pull failed; using archive: {benchmark} -> {exc}")
            latest_archive["source_mode"] = "archive_fallback"
            latest_archive["live_error"] = str(exc)
            return latest_archive
        raise
