"""Price-history calculations for the market data pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd


PRESSURE_COLUMNS = [
    "Price Extension 200D",
    "Momentum Acceleration",
    "Volatility Expansion",
    "Volume Activity",
]


def calc_trading_pressure_fields(history):
    out = {column: np.nan for column in PRESSURE_COLUMNS}

    if history is None or history.empty or "Close" not in history.columns:
        return out

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()

    if len(close) >= 200:
        ma_200 = close.tail(200).mean()
        if ma_200 > 0:
            out["Price Extension 200D"] = (close.iloc[-1] / ma_200) - 1

    if len(close) >= 253:
        return_63 = (close.iloc[-1] / close.iloc[-64]) - 1
        return_252 = (close.iloc[-1] / close.iloc[-253]) - 1
        out["Momentum Acceleration"] = return_63 - (return_252 / 4.0)

        log_returns = np.log(close / close.shift(1)).dropna()
        vol_63 = log_returns.tail(63).std() * np.sqrt(252)
        vol_252 = log_returns.tail(252).std() * np.sqrt(252)
        if pd.notna(vol_252) and vol_252 > 0:
            out["Volatility Expansion"] = (vol_63 / vol_252) - 1

    if "Volume" in history.columns:
        volume = pd.to_numeric(history["Volume"], errors="coerce").dropna()
        if len(volume) >= 252:
            long_volume = volume.tail(252).mean()
            if long_volume > 0:
                out["Volume Activity"] = (volume.tail(20).mean() / long_volume) - 1

    return out


def one_year_return(history):
    if history is None or history.empty or "Close" not in history.columns:
        return np.nan

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if len(close) < 252:
        return np.nan
    return (close.iloc[-1] / close.iloc[-252]) - 1
