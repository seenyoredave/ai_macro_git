import numpy as np
import pandas as pd

from analytics.valuation import aggregate_forward_ebit_yield
from config.factor_config import FACTOR_CONFIG
from config.debug_config import debug_print, DEBUG

def _weighted_mean(df, column, *, min_count=5):
    if df is None or df.empty or column not in df.columns:
        return np.nan
    values = pd.to_numeric(df[column], errors="coerce")
    valid = values.notna() & np.isfinite(values)
    return float(values.loc[valid].mean()) if int(valid.sum()) >= min_count else np.nan

def calc_relative_performance(df, benchmark_return):
    sector_return = _weighted_mean(df, "1Y Return", min_count=5)
    if pd.isna(sector_return) or pd.isna(benchmark_return):
        return np.nan
    return sector_return - float(benchmark_return)

def calc_forward_ebit_yield_discount(df, benchmark_ebit_yield):
    valuation = aggregate_forward_ebit_yield(
        df,
        min_count=5,
        min_coverage=0.60,
    )
    sector_yield = valuation["yield"]
    benchmark_ebit_yield = pd.to_numeric(benchmark_ebit_yield, errors="coerce")
    if (
        pd.isna(sector_yield)
        or pd.isna(benchmark_ebit_yield)
        or benchmark_ebit_yield <= 0
    ):
        return np.nan
    return float(benchmark_ebit_yield) - float(sector_yield)

def calc_market_breadth(df):
    if df is None or df.empty or "Price Extension 200D" not in df.columns:
        return np.nan
    extension = (
        pd.to_numeric(df["Price Extension 200D"], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(extension) < 5:
        return np.nan
    return float((extension > 0).mean())

FACTOR_FUNCTIONS = {
    "relative_performance": lambda df, benchmark_return, benchmark_yield: calc_relative_performance(
        df, benchmark_return
    ),
    "forward_ebit_yield_discount": lambda df, benchmark_return, benchmark_yield: calc_forward_ebit_yield_discount(
        df, benchmark_yield
    ),
    "market_breadth": lambda df, benchmark_return, benchmark_yield: calc_market_breadth(df),
}

def calc_sector_factors(sector, yf_df, benchmark_metrics=None):
    empty_out = pd.DataFrame(columns=["Sector", "Factor", "Value"])

    if yf_df is None or yf_df.empty:
        if DEBUG:
            debug_print(f"FACTOR ENGINE WARNING: empty yf_df for sector={sector}")
        return empty_out

    bm = benchmark_metrics or {}
    benchmark_return = bm.get("avg_return", np.nan)
    benchmark_ebit_yield = bm.get("forward_ebit_yield", np.nan)
    factors = FACTOR_CONFIG.get(sector)

    if not factors:
        if DEBUG:
            debug_print(f"FACTOR ENGINE WARNING: no FACTOR_CONFIG entry for sector={sector}")
        return empty_out

    rows = []

    for factor_name in factors:
        if factor_name not in FACTOR_FUNCTIONS:
            raise ValueError(f"Unknown factor: {factor_name}")

        rows.append({
            "Sector": sector,
            "Factor": factor_name,
            "Value": FACTOR_FUNCTIONS[factor_name](
                yf_df,
                benchmark_return,
                benchmark_ebit_yield,
            ),
        })

    out = pd.DataFrame(rows, columns=["Sector", "Factor", "Value"])
    out["Sector"] = out["Sector"].astype(str)
    out["Factor"] = out["Factor"].astype(str)
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    return out
