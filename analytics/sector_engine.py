from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.regime_engine import cycle_strategy
from analytics.hhi_engine import sector_basket_concentration
from analytics.valuation import (
    SECTOR_VALUATION_VERSION,
    aggregate_forward_ebit_yield,
    aggregate_profitable_forward_ev_ebit,
)
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
    raw = {
        "Valuation Stretch": _factor_raw(
            factor_df, "forward_ebit_yield_discount"
        ),
        "Price Extension": _median_numeric(yf_df, "Price Extension 200D"),
        "Momentum Acceleration": _median_numeric(yf_df, "Momentum Acceleration"),
        "Volatility Expansion": _median_numeric(yf_df, "Volatility Expansion"),
        "Volume Activity": _median_numeric(yf_df, "Volume Activity"),
    }

    scores = {
        "Valuation Stretch": tanh_score(raw["Valuation Stretch"], center=0.0, scale=0.04),
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
    if factor_df is None or factor_df.empty:
        return {
            "Sector Score": np.nan,
            "Sector Pressure": np.nan,
            "Cycle Strategy": cycle_strategy(np.nan),
            "Avg Return": np.nan,
            "Forward EV/EBIT": np.nan,
            "Forward EV/EBIT Status": "Unavailable",
            "Sector Valuation Version": SECTOR_VALUATION_VERSION,
            "Forward EBIT Yield": np.nan,
            "Forward EBIT Company Count": 0,
            "Forward EBIT Coverage": 0.0,
            "Forward EV/EBIT Company Count": 0,
            "Forward EV/EBIT Coverage": 0.0,
            "Forward EV/EBIT Data Coverage": 0.0,
            "Loss-Making EV Share": np.nan,
            "Loss-Making Company Count": 0,
            "Beta": np.nan,
            "Sector Basket Concentration": np.nan,
            "Sector Raw HHI": np.nan,
            "Sector Effective Firms": np.nan,
            "Sector Concentration Company Count": 0,
            "Sector Concentration Coverage": 0.0,
            "Sector Concentration Version": "",
            "Scored Factors": pd.DataFrame(),
            "Pressure Components": pd.DataFrame(),
        }

    normalized_df = normalize_factor_table(factor_df)
    sector_score = calc_sector_scores(normalized_df)
    pressure_score, pressure_components = calc_trading_pressure(yf_df, factor_df)
    concentration = sector_basket_concentration(yf_df)
    valuation_discount = _factor_raw(factor_df, "forward_ebit_yield_discount")

    valuation = aggregate_forward_ebit_yield(
        yf_df,
        min_count=5,
        min_coverage=0.60,
    )
    sector_forward_ebit_yield = valuation["yield"]

    cohort_valuation = aggregate_profitable_forward_ev_ebit(
        yf_df,
        min_valid_count=5,
        min_profitable_count=3,
        min_coverage=0.60,
    )
    forward_multiple = cohort_valuation.get("multiple", np.nan)
    profitable_count = int(cohort_valuation.get("profitable_company_count", 0) or 0)
    valid_count = int(cohort_valuation.get("valid_company_count", 0) or 0)
    profitable_ev_share = pd.to_numeric(
        cohort_valuation.get("profitable_ev_share", np.nan), errors="coerce"
    )
    data_coverage = pd.to_numeric(
        cohort_valuation.get("data_coverage", 0.0), errors="coerce"
    )
    loss_making_ev_share = pd.to_numeric(
        cohort_valuation.get("loss_making_ev_share", np.nan), errors="coerce"
    )
    if pd.notna(forward_multiple):
        valuation_status = (
            f"Available — profitable-cohort ratio of sums; {profitable_count} profitable "
            f"companies, {profitable_ev_share * 100:.0f}% of valid EV; "
            f"{data_coverage * 100:.0f}% forward-EBIT data coverage"
        )
    elif valid_count < 5 or data_coverage < 0.60:
        valuation_status = "Unavailable — insufficient forward-EBIT data coverage"
    else:
        valuation_status = "Unavailable — fewer than three profitable companies"

    return {
        "Sector Score": sector_score,
        "Sector Pressure": pressure_score,
        "Cycle Strategy": cycle_strategy(sector_score),
        "Avg Return": _mean_column(yf_df, "1Y Return"),
        "Forward EV/EBIT": forward_multiple,
        "Forward EV/EBIT Status": valuation_status,
        "Sector Valuation Version": SECTOR_VALUATION_VERSION,
        "Forward EBIT Yield": sector_forward_ebit_yield,
        "Forward EBIT Company Count": valuation.get("company_count", 0),
        "Forward EBIT Coverage": valuation.get("coverage", 0.0),
        "Forward EV/EBIT Company Count": cohort_valuation.get("profitable_company_count", 0),
        "Forward EV/EBIT Coverage": cohort_valuation.get("profitable_ev_share", np.nan),
        "Forward EV/EBIT Data Coverage": cohort_valuation.get("data_coverage", 0.0),
        "Loss-Making EV Share": cohort_valuation.get("loss_making_ev_share", np.nan),
        "Loss-Making Company Count": cohort_valuation.get("loss_making_company_count", 0),
        "Valuation Discount": valuation_discount,
        "Beta": _mean_column(yf_df, "Beta"),
        "Sector Basket Concentration": concentration.get("adjusted_hhi", np.nan),
        "Sector Raw HHI": concentration.get("raw_hhi", np.nan),
        "Sector Effective Firms": concentration.get("effective_firms", np.nan),
        "Sector Concentration Company Count": concentration.get("valid_company_count", 0),
        "Sector Concentration Coverage": concentration.get("coverage", 0.0),
        "Sector Concentration Version": concentration.get("version", ""),
        "Scored Factors": normalized_df,
        "Pressure Components": pressure_components,
    }
