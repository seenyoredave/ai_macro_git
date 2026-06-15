import streamlit as st
import numpy as np
import pandas as pd

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

    raw = _load_raw_benchmarks()
    package = {}

    for name, df in raw.items():

    
        debug_print("=== BENCHMARK DF DEBUG (PRE-NORMALIZATION) ===")
        debug_print(df.columns)
        debug_print(df.head())

        debug_print("Forward P/E null count:", df.get("Forward P/E", pd.Series()).isna().sum())
        debug_print("Beta null count:", df.get("Beta", pd.Series()).isna().sum())
        debug_print("1Y Return null count:", df.get("1Y Return", pd.Series()).isna().sum())

        debug_print("Forward P/E sample:", df.get("Forward P/E", pd.Series()).head(10))
        debug_print("Beta sample:", df.get("Beta", pd.Series()).head(10))
        debug_print("1Y Return sample:", df.get("1Y Return", pd.Series()).head(10))

        norm = normalize_benchmark_dataframe(df)

        package[name] = {
            "raw": df,
            "normalized": norm,
            "metrics": {
                "forward_pe": norm["forward_pe"],
                "avg_return": norm["avg_return"],
                "beta": norm["beta"],
                "member_count": norm["member_count"]
            }
        }

    return package


#################################################
# PUBLIC API (THIS is what everything imports)
#################################################

@st.cache_data(ttl=3600)
def get_benchmark_metrics(benchmark: str):

    package = get_benchmark_package()

    if benchmark not in package:
        return {
            "forward_pe": np.nan,
            "avg_return": np.nan,
            "beta": np.nan,
            "member_count": 0
        }

    return package[benchmark]["metrics"]