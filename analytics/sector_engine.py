"""Sector-level AI Equity Index and trading-pressure calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.regime_engine import cycle_strategy
from analytics.scoring import tanh_score, weighted_available_score
from config.debug_config import DEBUG, debug_print
from factors.factor_normalization import normalize_factor
from factors.factor_weights import FACTOR_WEIGHTS


PRESSURE_WEIGHTS = {
    "Valuation Stretch": 0.25,
    "Price Extension": 0.25,
    "Momentum Acceleration": 0.20,
    "Volatility Expansion": 0.15,
    "Volume Activity": 0.15,
}


def normalize_factor_table(factor_df):
    rows = []

    for _, row in factor_df.iterrows():
        raw_score = normalize_factor(row["Factor"], row["Value"])
        score_100 = ((raw_score + 1) / 2) * 100 if pd.notna(raw_score) else np.nan
        rows.append({
            "Sector": row["Sector"],
            "Factor": row["Factor"],
            "Raw Value": row["Value"],
            "Raw Score": raw_score,
            "Score": score_100,
        })

    return pd.DataFrame(rows)


def calc_sector_scores(normalized_df):
    """Combine AEI factors using the fixed 3-of-4 data contract."""
    if normalized_df is None or normalized_df.empty:
        return np.nan

    scores = {
        str(row["Factor"]): row["Score"]
        for _, row in normalized_df.iterrows()
    }
    combined = weighted_available_score(
        scores,
        FACTOR_WEIGHTS,
        min_components=3,
    )

    if DEBUG:
        debug_print("\n--- AEI SECTOR SCORING ---")
        debug_print("Valid components:", combined["valid_components"])
        debug_print("Final score:", combined["score"])

    return combined["score"]


def _median_numeric(df, column, min_count=3):
    """Robust sector aggregate for ticker-level pressure inputs."""
    if df is None or df.empty or column not in df.columns:
        return np.nan

    values = (
        pd.to_numeric(df[column], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    return float(values.median()) if len(values) >= min_count else np.nan


def _factor_raw(factor_df, factor_name):
    if factor_df is None or factor_df.empty:
        return np.nan

    rows = factor_df[factor_df["Factor"] == factor_name]
    if rows.empty:
        return np.nan

    return pd.to_numeric(rows.iloc[-1]["Value"], errors="coerce")


def calc_trading_pressure(yf_df, factor_df=None):
    """Calculate sector trading pressure from extension and instability.

    Pressure is intentionally distinct from AEI. It uses valuation stretch,
    price extension, momentum acceleration, volatility expansion, and abnormal
    volume. At least three of five components must be valid. Fixed weights are
    renormalized over valid components; missing values are never zero-filled.
    """
    raw = {
        "Valuation Stretch": _factor_raw(factor_df, "earnings_yield_discount"),
        "Price Extension": _median_numeric(yf_df, "Price Extension 200D"),
        "Momentum Acceleration": _median_numeric(yf_df, "Momentum Acceleration"),
        "Volatility Expansion": _median_numeric(yf_df, "Volatility Expansion"),
        "Volume Activity": _median_numeric(yf_df, "Volume Activity"),
    }

    scores = {
        "Valuation Stretch": tanh_score(raw["Valuation Stretch"], center=0.0, scale=0.03),
        "Price Extension": tanh_score(raw["Price Extension"], center=0.0, scale=0.20),
        "Momentum Acceleration": tanh_score(raw["Momentum Acceleration"], center=0.0, scale=0.15),
        "Volatility Expansion": tanh_score(raw["Volatility Expansion"], center=0.0, scale=0.60),
        "Volume Activity": tanh_score(raw["Volume Activity"], center=0.0, scale=0.75),
    }

    combined = weighted_available_score(
        scores,
        PRESSURE_WEIGHTS,
        min_components=3,
    )

    rows = []
    for name in PRESSURE_WEIGHTS:
        rows.append({
            "Component": name,
            "Raw Value": raw[name],
            "Score": scores[name],
            "Weight": PRESSURE_WEIGHTS[name],
            "Active Weight": combined["normalized_weights"].get(name, np.nan),
        })

    return combined["score"], pd.DataFrame(rows)



def _mean_column(yf_df, column):
    if yf_df is None or yf_df.empty or column not in yf_df.columns:
        return np.nan
    values = pd.to_numeric(yf_df[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return float(values.mean()) if values.notna().any() else np.nan


def build_sector_metrics(factor_df, yf_df):
    """Return the existing public sector-metrics schema with AEI semantics."""
    if factor_df is None or factor_df.empty:
        return {
            "Sector Score": np.nan,
            "Sector Pressure": np.nan,
            "Cycle Strategy": cycle_strategy(np.nan),
            "Avg Return": np.nan,
            "Forward P/E": np.nan,
            "Beta": np.nan,
            "Scored Factors": pd.DataFrame(),
            "Pressure Components": pd.DataFrame(),
        }

    normalized_df = normalize_factor_table(factor_df)
    sector_score = calc_sector_scores(normalized_df)
    pressure_score, pressure_components = calc_trading_pressure(yf_df, factor_df)

    return {
        "Sector Score": sector_score,
        "Sector Pressure": pressure_score,
        "Cycle Strategy": cycle_strategy(sector_score),
        "Avg Return": _mean_column(yf_df, "1Y Return"),
        "Forward P/E": _mean_column(yf_df, "Forward P/E"),
        "Beta": _mean_column(yf_df, "Beta"),
        "Scored Factors": normalized_df,
        "Pressure Components": pressure_components,
    }
