import numpy as np
import pandas as pd

from config.factor_config import FACTOR_CONFIG
from config.debug_config import debug_print, DEBUG


def calc_relative_performance(df, benchmark_return):
    returns = pd.to_numeric(df["1Y Return"], errors="coerce").dropna()
    if len(returns) < 5 or pd.isna(benchmark_return):
        return np.nan
    return returns.mean() - float(benchmark_return)


def calc_earnings_yield_discount(df, benchmark_pe):
    pe = pd.to_numeric(df["Forward P/E"], errors="coerce")
    pe = pe[(pe > 0) & np.isfinite(pe)]

    if len(pe) < 5 or pd.isna(benchmark_pe) or float(benchmark_pe) <= 0:
        return np.nan

    sector_earnings_yield = (1.0 / pe).mean()
    benchmark_earnings_yield = 1.0 / float(benchmark_pe)
    return benchmark_earnings_yield - sector_earnings_yield



def calc_momentum_breadth(df):
    returns = pd.to_numeric(df["1Y Return"], errors="coerce").dropna()
    if len(returns) < 5:
        return np.nan
    return (returns > 0).mean()


def calc_dispersion(df):
    returns = pd.to_numeric(df["1Y Return"], errors="coerce").dropna()
    if len(returns) < 5:
        return np.nan
    return returns.std()


FACTOR_FUNCTIONS = {
    "relative_performance": lambda df, r, pe: calc_relative_performance(df, r),
    "earnings_yield_discount": lambda df, r, pe: calc_earnings_yield_discount(df, pe),
    "momentum_breadth": lambda df, r, pe: calc_momentum_breadth(df),
    "dispersion": lambda df, r, pe: calc_dispersion(df),
}


def calc_sector_factors(sector, yf_df, benchmark_metrics=None):
    empty_out = pd.DataFrame(columns=["Sector", "Factor", "Value"])

    if yf_df is None or yf_df.empty:
        if DEBUG:
            debug_print(f"FACTOR ENGINE WARNING: empty yf_df for sector={sector}")
        return empty_out

    bm = benchmark_metrics or {}
    benchmark_return = bm.get("avg_return", np.nan)
    benchmark_pe = bm.get("forward_pe", np.nan)
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
                benchmark_pe,
            ),
        })

    out = pd.DataFrame(rows, columns=["Sector", "Factor", "Value"])
    out["Sector"] = out["Sector"].astype(str)
    out["Factor"] = out["Factor"].astype(str)
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    return out
