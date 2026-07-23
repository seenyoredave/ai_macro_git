import numpy as np
import pandas as pd
import streamlit as st

from archive.archive_reader import load_benchmark_history, rows_for_date
from benchmarks.benchmark_normalization import normalize_benchmark_dataframe
from config.benchmark_config import ACTIVE_BENCHMARKS, BENCHMARK_VERSION
from config.debug_config import debug_print
from loaders.benchmark_loader import load_all_benchmarks


@st.cache_data(ttl=3600)
def _load_raw_benchmarks():
    return load_all_benchmarks()


def get_archived_benchmark_metrics(benchmark: str):
    try:
        history = load_benchmark_history()
    except Exception:
        return None

    required = {
        "Date",
        "Benchmark",
        "Forward P/E",
        "Avg Return",
        "Beta",
        "Member Count",
        "Benchmark Version",
    }
    if history is None or history.empty or not required.issubset(history.columns):
        return None

    current = rows_for_date(history)
    if current.empty:
        return None

    current = current.copy()
    current["Benchmark"] = current["Benchmark"].astype(str).str.upper().str.strip()
    current["Benchmark Version"] = current["Benchmark Version"].astype(str).str.strip()
    row = current[
        (current["Benchmark"] == benchmark.upper().strip())
        & (current["Benchmark Version"] == BENCHMARK_VERSION)
    ]
    if row.empty:
        return None

    row = row.iloc[-1]
    return {
        "forward_pe": row.get("Forward P/E", np.nan),
        "avg_return": row.get("Avg Return", np.nan),
        "beta": row.get("Beta", np.nan),
        "member_count": row.get("Member Count", 0),
        "version": BENCHMARK_VERSION,
    }


@st.cache_data(ttl=3600)
def get_benchmark_package():
    package = {}
    raw_package = None

    for name in ACTIVE_BENCHMARKS:
        archived = get_archived_benchmark_metrics(name)
        if archived is not None:
            debug_print(f"Loading today's weighted benchmark from archive: {name}")
            package[name] = {"raw": pd.DataFrame(), "normalized": archived, "metrics": archived}
            continue

        if raw_package is None:
            raw_package = _load_raw_benchmarks()
        frame = raw_package.get(name, pd.DataFrame())
        normalized = normalize_benchmark_dataframe(frame)
        normalized["version"] = BENCHMARK_VERSION
        package[name] = {"raw": frame, "normalized": normalized, "metrics": normalized}

    return package


@st.cache_data(ttl=3600)
def get_benchmark_metrics(benchmark: str):
    if benchmark not in ACTIVE_BENCHMARKS:
        raise ValueError(f"Benchmark {benchmark} is configured but not active")

    archived = get_archived_benchmark_metrics(benchmark)
    if archived is not None:
        return archived

    package = get_benchmark_package()
    return package.get(
        benchmark,
        {
            "forward_pe": np.nan,
            "avg_return": np.nan,
            "beta": np.nan,
            "member_count": 0,
            "version": BENCHMARK_VERSION,
        },
    )["metrics"] if benchmark in package else {
        "forward_pe": np.nan,
        "avg_return": np.nan,
        "beta": np.nan,
        "member_count": 0,
        "version": BENCHMARK_VERSION,
    }
