"""Weighted benchmark proxy normalization."""

import numpy as np
import pandas as pd


def _weighted_mean(df, value_col, weight_col="Benchmark Weight"):
    if value_col not in df.columns or weight_col not in df.columns:
        return np.nan

    values = pd.to_numeric(df[value_col], errors="coerce")
    weights = pd.to_numeric(df[weight_col], errors="coerce")
    valid = values.notna() & weights.notna() & (weights > 0)
    if not valid.any():
        return np.nan
    return float(np.average(values[valid], weights=weights[valid]))


def _weighted_forward_pe(df):
    """Return the reciprocal of weighted earnings yield.

    This preserves the existing ``forward_pe`` public field while ensuring the
    valuation comparison uses weighted earnings yield rather than arithmetic P/E.
    """
    pe = pd.to_numeric(df.get("Forward P/E"), errors="coerce")
    weights = pd.to_numeric(df.get("Benchmark Weight"), errors="coerce")
    valid = pe.notna() & weights.notna() & (pe > 0) & (weights > 0)
    if not valid.any():
        return np.nan

    earnings_yield = np.average(1.0 / pe[valid], weights=weights[valid])
    return float(1.0 / earnings_yield) if earnings_yield > 0 else np.nan


def normalize_benchmark_dataframe(df: pd.DataFrame) -> dict:
    frame = df.copy()
    return {
        "forward_pe": _weighted_forward_pe(frame),
        "avg_return": _weighted_mean(frame, "1Y Return"),
        "beta": _weighted_mean(frame, "Beta"),
        "member_count": int(frame["Ticker"].nunique(dropna=True)) if "Ticker" in frame else 0,
    }
