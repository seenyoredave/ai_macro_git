import streamlit as st
import numpy as np
import pandas as pd

from datetime import date
from archive.archive_reader import load_benchmark_history 
from loaders.benchmark_loader import load_all_benchmarks
from benchmarks.benchmark_normalization import normalize_benchmark_dataframe
from config.debug_config import debug_print 


#################################################
# LOAD RAW BENCHMARKS (cached at service level)
#################################################

@st.cache_data(ttl=3600)
def _load_raw_benchmarks():
    return load_all_benchmarks()


#################################################
# BUILD NORMALIZED BENCHMARK PACKAGE
#################################################

@st.cache_data(ttl=3600)
def get_benchmark_package():

    package = {}

    for name in ["QQQ", "SPY", "DIA"]:

        archived = get_archived_benchmark_metrics(name)

        if archived is not None:
            debug_print(f"Loading today's benchmark package from benchmark_history.csv: {name}")

            package[name] = {
                "raw": pd.DataFrame(),
                "normalized": {
                    "forward_pe": archived["forward_pe"],
                    "avg_return": archived["avg_return"],
                    "beta": archived["beta"],
                    "member_count": archived["member_count"],
                },
                "metrics": archived,
            }

        else:
            raw = _load_raw_benchmarks()

            for raw_name, df in raw.items():
                norm = normalize_benchmark_dataframe(df)

                package[raw_name] = {
                    "raw": df,
                    "normalized": norm,
                    "metrics": {
                        "forward_pe": norm["forward_pe"],
                        "avg_return": norm["avg_return"],
                        "beta": norm["beta"],
                        "member_count": norm["member_count"],
                    },
                }

            break

    return package

#################################################
# CHECK BENCHMARK ARCHIVE
#################################################

def get_archived_benchmark_metrics(benchmark: str):
    try:
        df = load_benchmark_history()
    except Exception:
        return None

    if df is None or df.empty:
        return None

    required = [
        "Date",
        "Benchmark",
        "Forward P/E",
        "Avg Return",
        "Beta",
        "Member Count",
    ]

    if any(col not in df.columns for col in required):
        return None

    today = str(date.today())

    df = df.copy()
    df["Date"] = df["Date"].astype(str)
    df["Benchmark"] = df["Benchmark"].astype(str).str.upper().str.strip()

    row = df[
        (df["Date"] == today)
        &
        (df["Benchmark"] == benchmark.upper().strip())
    ]

    if row.empty:
        return None

    row = row.iloc[-1]

    return {
        "forward_pe": row.get("Forward P/E", np.nan),
        "avg_return": row.get("Avg Return", np.nan),
        "beta": row.get("Beta", np.nan),
        "member_count": row.get("Member Count", 0),
    }

#################################################
# PUBLIC API (THIS is what everything imports)
#################################################

@st.cache_data(ttl=3600)
def get_benchmark_metrics(benchmark: str):

    archived = get_archived_benchmark_metrics(benchmark)

    if archived is not None:
        debug_print(f"Loading today's benchmark metrics from benchmark_history.csv: {benchmark}")
        return archived

    package = get_benchmark_package()

    if benchmark not in package:
        return {
            "forward_pe": np.nan,
            "avg_return": np.nan,
            "beta": np.nan,
            "member_count": 0
        }

    return package[benchmark]["metrics"]