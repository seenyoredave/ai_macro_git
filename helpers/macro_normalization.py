### These functions pull data from loader functions and normalize for computation. 


import pandas as pd
import numpy as np



def normalize_series(series):
    """
    Scales a pandas series between 0-1 robustly.
    Returns 0.5 for constant or empty series.
    """
    clean = series.dropna()
    if clean.empty or clean.max() == clean.min():
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - clean.min()) / (clean.max() - clean.min() + 1e-6)

def normalize_put_call(pcr):

    # P/C ratio works backwards - low = bullish/ high = bearish
    # 0.55 = extremely bullish --> 100 --> capital extreme optimism 
    # 0.7 = normal --> 71
    # 1.0 = cautious --> 29
    # 1.1+ = fearful --> 0 --> capital defensive 
    

    if pd.isna(pcr):
        return np.nan

    low = 0.55
    high = 1.10

    normalized = (
        (high - pcr)
        /
        (high - low)
    ) * 100

    return np.clip(
        normalized,
        0,
        100
    )
    
def normalize_consumer_sentiment(value):

    if pd.isna(value):
        return np.nan

    low = 50
    high = 115

    normalized = (
        (value - low)
        /
        (high - low)
    ) * 100

    return np.clip(
        normalized,
        0,
        100
    )

def normalize_fed_funds(rate):
    """
    Convert Fed Funds Rate into a 0-100 liquidity score.

    0% Fed Funds  -> 100 (maximum liquidity)
    6% Fed Funds  -> 0   (tight liquidity)

    Values outside range are clipped.
    """

    if pd.isna(rate):
        return np.nan

    low = 0.0
    high = 6.0

    normalized = (
        (high - rate)
        /
        (high - low)
    ) * 100

    return np.clip(
        normalized,
        0,
        100
    )

def normalize_pmi(pmi):
    """
    PMI normalization.

    40 = recessionary
    50 = neutral
    60 = very strong expansion

    Returns 0-100.
    """

    if pd.isna(pmi):
        return np.nan

    low = 40
    high = 60

    normalized = (
        (pmi - low)
        /
        (high - low)
    ) * 100

    return np.clip(
        normalized,
        0,
        100
    )

def normalize_industrial_production(value):

    if pd.isna(value):
        return np.nan

    low = 90
    high = 110

    normalized = (
        (value - low)
        /
        (high - low)
    ) * 100

    return np.clip(
        normalized,
        0,
        100
    )
  