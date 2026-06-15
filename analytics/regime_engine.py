### These functions build the AI cycle strategy, cycle score, and CDI index functions. 


import pandas as pd
import numpy as np

from helpers.macro_normalization import normalize_series
from config.debug_config import debug_print  


def cycle_strategy(score):
    
    if pd.isna(score): 
            return {
                "regime": "No Data",
                "action": "Insufficient data",
                "risk": "Unable to assess",
                "positioning": "No signal"
            }
    if score < 30:
        return {
            "regime": "Early Cycle",
            "action": "🟢 Accumulate aggressively on dips",
            "risk": "Low valuation risk, demand accelerating",
            "positioning": "Overweight semicap (KLAC/ASML)"
        }
    elif score < 60:
        return {
            "regime": "Expansion Cycle",
            "action": "🟡 Hold core, add selectively",
            "risk": "Healthy growth, volatility normal",
            "positioning": "Neutral to overweight"
        }
    elif score < 80:
        return {
            "regime": "Late Cycle",
            "action": "🟠 Trim into strength, avoid chasing",
            "risk": "Valuation compression risk rising",
            "positioning": "Neutral / tactical only"
        }
    else:
        return {
            "regime": "Peak Cycle",
            "action": "🔴 Reduce exposure, raise cash buffer",
            "risk": "High drawdown probability",
            "positioning": "Underweight / defensive tilt"
        }

def cycle_score(df):
    """
    Compute a composite cycle score using normalized PE, return, beta, and price position.
    Returns 0-100 score.
    """
    pe = normalize_series(
        df.get(
            "P/E",
            pd.Series(dtype=float)
        )
    ).mean()

    ret = normalize_series(
        df.get(
            "1Y Return",
            pd.Series(dtype=float)
        )
    ).mean()

    beta = normalize_series(
        df.get(
            "Beta",
            pd.Series(dtype=float)
        )
    ).mean()

    pe = 0.5 if pd.isna(pe) else pe
    ret = 0.5 if pd.isna(ret) else ret
    beta = 0.5 if pd.isna(beta) else beta

    price_pos = df.apply(
        lambda row: (row["Price"] - row["52W Low"]) / (row["52W High"] - row["52W Low"])
        if pd.notna(row.get("Price")) and pd.notna(row.get("52W Low")) and pd.notna(row.get("52W High")) and row["52W High"] != row["52W Low"]
        else np.nan,
        axis=1
    )

    clean_price_pos = price_pos.dropna()
    price_pos_mean = (
        clean_price_pos.mean()
        if not clean_price_pos.empty
        else 0.5
    )
    
    score = (0.25 * pe + 0.2 * ret + 0.2 * beta + 0.35 * price_pos_mean) * 100
    
     
    debug_print("PE:", pe)
    debug_print("RET:", ret)
    debug_print("BETA:", beta)
    debug_print("PRICE_POS:", price_pos_mean)
    
    return score

def ai_cdi_index(macro_df):
    """
    AI Cognitive Dissonance Index

    Measures divergence between:
    - Cycle Maturity (market enthusiasm)
    - Heat (internal factor stress)

    Higher = more disconnected from fundamentals.
    """

    if macro_df.empty:
        return np.nan

    temp = macro_df["Cycle Score"].mean()
    heat = macro_df["Heat"].mean()

    return temp - heat

