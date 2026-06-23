
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

AI_EXPOSURE_WEIGHTS = {
    1: 0.60,
    2: 0.80,
    3: 1.00,
    4: 1.20,
    5: 1.40,
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


def add_basket_tiers(df, ai_exposure_score=None):
    """
    Adds basket tiering and AI exposure weighting.

    Basket Score / Basket Tier / Basket Weight:
        Economic significance inside the basket.

    AI Exposure Score:
        Manual 1-5 score for how directly the company expresses
        the assigned sector's AI thesis.

    Effective Basket Weight:
        Basket Weight adjusted by AI Exposure Multiplier.
    """

    df = df.copy()

    ai_exposure_score = ai_exposure_score or {}

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

    # Existing economic-significance score.
    df["Basket Score"] = (
        0.70 * market_cap_score
        + 0.20 * revenue_score
        + 0.10 * return_score
    )

    df["Basket Tier"] = assign_tiers(df["Basket Score"])

    df["Basket Weight"] = df["Basket Tier"].map(TIER_WEIGHTS)

    ai_exposure_score = ai_exposure_score or {}

    df["AI Exposure Score"] = (
        df["Ticker"]
        .map(ai_exposure_score)
        .fillna(3)
        .astype(float)
        .clip(1, 5)
    )

    df["AI Weight"] = (
        df["AI Exposure Score"]
        .round()
        .astype(int)
        .map(AI_EXPOSURE_WEIGHTS)
        .fillna(1.00)
    )

    df["Effective Basket Weight"] = (
        df["Basket Weight"] * df["AI Weight"]
    )

    if DEBUG:
        debug_print(
            df[
                [
                    "Ticker",
                    "AI Exposure Score",
                    "AI Exposure Multiplier",
                    "Market Cap",
                    "Revenue",
                    "1Y Return",
                    "Basket Score",
                    "Basket Tier",
                    "Basket Weight",
                    "Effective Basket Weight",
                ]
            ]
        )

        debug_df = df[
            [
                "Ticker",
                "AI Exposure Score",
                "AI Exposure Multiplier",
                "Market Cap",
                "Revenue",
                "1Y Return",
                "Basket Score",
                "Basket Tier",
                "Basket Weight",
                "Effective Basket Weight",
            ]
        ].copy()

        debug_df["MC Score"] = market_cap_score
        debug_df["Rev Score"] = revenue_score
        debug_df["Ret Score"] = return_score

        debug_print(
            debug_df.sort_values(
                "Effective Basket Weight",
                ascending=False
            )
        )

    return df