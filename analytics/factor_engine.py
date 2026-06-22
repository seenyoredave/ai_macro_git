import numpy as np
import pandas as pd

from config.factor_config import FACTOR_CONFIG
from benchmarks.benchmark_service import get_benchmark_metrics
from config.debug_config import debug_print, DEBUG



#################################################
# FACTOR CALCULATIONS (PURE FUNCTIONS)
#################################################

def calc_relative_performance(df, benchmark_return):
    returns = pd.to_numeric(df["1Y Return"], errors="coerce").dropna()

    if len(returns) < 5 or pd.isna(benchmark_return):
        return np.nan

    return returns.mean() - benchmark_return


def calc_valuation_premium(df, benchmark_pe):
    pe = pd.to_numeric(df["Forward P/E"], errors="coerce").dropna()

    if len(pe) < 5 or pd.isna(benchmark_pe) or benchmark_pe <= 0:
        return np.nan

    return pe.mean() / benchmark_pe


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


#################################################
# FACTOR DISPATCH TABLE
#################################################

FACTOR_FUNCTIONS = {
    "relative_performance": lambda df, r, pe: calc_relative_performance(df, r),
    "valuation_premium": lambda df, r, pe: calc_valuation_premium(df, pe),
    "momentum_breadth": lambda df, r, pe: calc_momentum_breadth(df),
    "dispersion": lambda df, r, pe: calc_dispersion(df),
}


#################################################
# MAIN ENGINE
#################################################

def calc_sector_factors(sector, yf_df, benchmark="QQQ"):

    # Always return a predictable schema
    empty_out = pd.DataFrame(
        columns=[
            "Sector",
            "Factor",
            "Value"
        ]
    )

    if yf_df is None or yf_df.empty:
        if DEBUG:
            debug_print(f"FACTOR ENGINE WARNING: empty yf_df for sector={sector}")
        return empty_out

    # Pull clean benchmark metrics only
    bm = get_benchmark_metrics(benchmark)

    benchmark_return = bm.get("avg_return", np.nan)
    benchmark_pe = bm.get("forward_pe", np.nan)

    factors = FACTOR_CONFIG.get(sector)

    if not factors:
        if DEBUG:
            debug_print(f"FACTOR ENGINE WARNING: no FACTOR_CONFIG entry for sector={sector}")
            debug_print("Available FACTOR_CONFIG sectors:", list(FACTOR_CONFIG.keys()))
            debug_print("yf_df columns:", yf_df.columns.tolist())
            debug_print("yf_df shape:", yf_df.shape)

        return empty_out

    rows = []

    for factor_name in factors:

        if factor_name not in FACTOR_FUNCTIONS:
            raise ValueError(f"Unknown factor: {factor_name}")

        value = FACTOR_FUNCTIONS[factor_name](
            yf_df,
            benchmark_return,
            benchmark_pe
        )

        if DEBUG:
            debug_print("RUNNING FACTOR:", factor_name)
            debug_print("SECTOR:", sector)
            debug_print("FACTORS:", factors)
            debug_print("YF DF SHAPE:", yf_df.shape)
            debug_print("YF COLS:", yf_df.columns.tolist())

        rows.append({
            "Sector": sector,
            "Factor": factor_name,
            "Value": value
        })

    out = pd.DataFrame(
        rows,
        columns=[
            "Sector",
            "Factor",
            "Value"
        ]
    )

    out["Sector"] = out["Sector"].astype(str)
    out["Factor"] = out["Factor"].astype(str)
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")

    return out