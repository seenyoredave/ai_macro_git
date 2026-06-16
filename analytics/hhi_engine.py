# analytics/market_structure.py

import numpy as np
import pandas as pd


def calc_hhi_from_sector_data(sector_data):

    if sector_data is None:
        return np.nan

    market_caps = []

    for sector, df in sector_data.items():

        if df is None or df.empty:
            continue

        if "Market Cap" not in df.columns:
            continue

        caps = pd.to_numeric(
            df["Market Cap"],
            errors="coerce"
        ).dropna()

        caps = caps[caps > 0]

        market_caps.extend(caps.tolist())

    if not market_caps:
        return np.nan

    market_caps = np.array(market_caps, dtype=float)
    shares = market_caps / market_caps.sum()

    return np.sum(shares ** 2)