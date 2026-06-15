

import numpy as np
import pandas as pd
import streamlit as st 

from config.debug_config import debug_print 
from config.debug_config import DEBUG

if DEBUG:
    st.caption("Using cached market data")

TIER_WEIGHTS = {
    1: 4.0,
    2: 3.0,
    3: 2.0,
    4: 1.0,
}

def percentile_score(series, higher_is_better=True):
    values = pd.to_numeric(series, errors="coerce")

    if values.notna().sum() < 2:
        return pd.Series(50.0, index=series.index)

    ranks = values.rank(pct=True) * 100

    if not higher_is_better:
        ranks = 100 - ranks

    return ranks.fillna(50.0)


def assign_tiers(score_series):
    scores = pd.to_numeric(score_series, errors="coerce")

    if scores.notna().sum() < 4:
        return pd.Series(2, index=score_series.index)

    return pd.qcut(
        scores.rank(method="first"),
        q=4,
        labels=[4, 3, 2, 1]
    ).astype(int)


def add_basket_tiers(df):
    df = df.copy()

    market_cap_score = percentile_score(
        df.get("Market Cap", pd.Series(index=df.index)),
        higher_is_better=True
    )

    revenue_score = percentile_score(
        df.get("Revenue", pd.Series(index=df.index)),
        higher_is_better=True
    )

    return_score = percentile_score(
        df.get("1Y Return", pd.Series(index=df.index)),
        higher_is_better=True
    )

    df["Basket Score"] = (
        0.70 * market_cap_score
        + 0.20 * revenue_score
        + 0.10 * return_score
    )

    df["Basket Tier"] = assign_tiers(df["Basket Score"])

    df["Basket Weight"] = df["Basket Tier"].map(TIER_WEIGHTS)
    """
    if DEBUG:
        debug_cols = ["Ticker", "Market Cap", "Revenue", "1Y Return"]
        existing_debug_cols = [col for col in debug_cols if col in df.columns]

        debug_print(df[existing_debug_cols])
    """
    compute_df = df[
        [
            "Ticker",
            "Market Cap",
            "Revenue",
            "1Y Return"
        ]
    ].copy()
    import streamlit as st

    required_cols = ["Ticker", "Market Cap", "Revenue", "1Y Return"]
    missing_cols = [col for col in required_cols if col not in df.columns]

    if missing_cols:
        st.error("Basket tiering received an unexpected dataframe.")
        st.write("Missing columns:", missing_cols)
        st.write("Actual columns:", list(df.columns))
        st.write("Shape:", df.shape)
        st.write("Preview:", df.head())
        st.stop()
        
    compute_df["MC Score"] = market_cap_score
    compute_df["Rev Score"] = revenue_score
    compute_df["Ret Score"] = return_score
    compute_df["Basket Score"] = df["Basket Score"]

    """debug_print(compute_df.sort_values(
        "Basket Score",
        ascending=False
    ))"""
    return df
       
