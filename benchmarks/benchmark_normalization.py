"""Weighted benchmark proxy normalization."""

import numpy as np
import pandas as pd

from analytics.valuation import aggregate_forward_ebit_yield


def _weighted_mean(df, value_col, weight_col="Benchmark Weight"):
    if value_col not in df.columns or weight_col not in df.columns:
        return np.nan

    values = pd.to_numeric(df[value_col], errors="coerce")
    weights = pd.to_numeric(df[weight_col], errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return np.nan
    return float(np.average(values[valid], weights=weights[valid]))


def _aggregate_forward_ebit_yield(df):
    """Return ratio-of-sums forward EBIT yield for the benchmark proxy."""
    return aggregate_forward_ebit_yield(
        df,
        min_count=2,
        min_coverage=0.60,
        coverage_weight_column="Benchmark Weight",
    )


def normalize_benchmark_dataframe(df: pd.DataFrame) -> dict:
    frame = df.copy()
    valuation = _aggregate_forward_ebit_yield(frame)
    forward_ebit_yield = valuation["yield"]
    return {
        "forward_ebit_yield": forward_ebit_yield,
        "forward_ev_ebit": (
            1.0 / forward_ebit_yield
            if pd.notna(forward_ebit_yield) and forward_ebit_yield > 0
            else np.nan
        ),
        "avg_return": _weighted_mean(frame, "1Y Return"),
        "beta": _weighted_mean(frame, "Beta"),
        "member_count": int(frame["Ticker"].nunique(dropna=True)) if "Ticker" in frame else 0,
    }
