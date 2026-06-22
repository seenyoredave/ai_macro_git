import numpy as np
import pandas as pd

from factors.factor_weights import FACTOR_WEIGHTS
from factors.factor_normalization import normalize_factor
from config.debug_config import debug_print 
from config.debug_config import DEBUG 

#################################################
# SPECULATION PRESSURE 
#################################################

SPECULATION_WEIGHTS = {
    "valuation_premium": 0.40,
    "relative_performance": 0.30,
    "dispersion": 0.20,
    "momentum_breadth": 0.10,
}


def calc_speculation_pressure(normalized_df):

    pressure = 0.0
    total_weight = 0.0

    for _, row in normalized_df.iterrows():

        factor = row["Factor"]
        weight = SPECULATION_WEIGHTS.get(factor, 0)

        if weight == 0 or pd.isna(row["Score"]):
            continue

        score = row["Score"]

        if factor == "dispersion":
            score = 100 - score

        pressure += score * weight
        total_weight += weight

    return pressure / total_weight if total_weight > 0 else np.nan


#################################################
# NORMALIZATION (FACTORS ONLY)
#################################################

def normalize_factor_table(factor_df):

    rows = []

    for _, row in factor_df.iterrows():

        raw_score = normalize_factor(
            row["Factor"],
            row["Value"]
        )

        score_100 = (
            ((raw_score + 1) / 2) * 100
            if pd.notna(raw_score)
            else np.nan
        )

        rows.append({
            "Sector": row["Sector"],
            "Factor": row["Factor"],
            "Raw Value": row["Value"],
            "Raw Score": raw_score,
            "Score": score_100
        })

    return pd.DataFrame(rows)


#################################################
# SECTOR SCORE
#################################################

def calc_sector_scores(normalized_df):

    score = 0.0
    total_weight = 0.0

    for _, row in normalized_df.iterrows():

        factor = row["Factor"]
        weight = FACTOR_WEIGHTS.get(factor, 0)

        if pd.notna(row["Score"]):
            score += row["Score"] * weight
            total_weight += weight
    
    if DEBUG:          
        debug_print("\n--- SECTOR SCORING ---")

        for _, row in normalized_df.iterrows():
            
            debug_print(
                row["Factor"],
                "Score:",
                row["Score"],
                "Weight:",
                FACTOR_WEIGHTS.get(row["Factor"], 0)
            )
            
        debug_print("Final Score:", score / total_weight)

    return score / total_weight if total_weight > 0 else np.nan


#################################################
# SECTOR METRICS (PURE AGGREGATION ONLY)
#################################################

def build_sector_metrics(factor_df, yf_df):

    if factor_df is None or factor_df.empty:
        return {
            "Sector Score": np.nan,
            "Sector Pressure": np.nan,
            "Avg Return": np.nan,
            "Forward P/E": np.nan,
            "Beta": np.nan,
            "Scored Factors": pd.DataFrame()
        }

    normalized_df = normalize_factor_table(factor_df)
    sector_score = calc_sector_scores(normalized_df)
    speculation_pressure = calc_speculation_pressure(normalized_df)
    
    return {
        "Sector Score": sector_score,
        "Sector Pressure": speculation_pressure,

        "Avg Return": yf_df["1Y Return"].mean() if "1Y Return" in yf_df else np.nan,
        "Forward P/E": yf_df["Forward P/E"].mean() if "Forward P/E" in yf_df else np.nan,
        "Beta": yf_df["Beta"].mean() if "Beta" in yf_df else np.nan,

        "Scored Factors": normalized_df
    }