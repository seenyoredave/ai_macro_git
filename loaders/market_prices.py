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

def year_to_date_snapshot(history, market_cap=np.nan):
    """Return the standard YTD price return and implied opening market cap.

    The return begins at the final available close before January 1.  The
    opening market cap uses the current share count implied by the supplied
    market cap, which keeps the contribution calculation internally coherent
    without introducing a second shares-outstanding data request.
    """
    out = {
        "YTD Return": np.nan,
        "YTD Start Market Cap": np.nan,
        "YTD Year": np.nan,
    }
    if history is None or history.empty or "Close" not in history.columns:
        return out

    close = pd.to_numeric(history["Close"], errors="coerce").dropna()
    if close.empty:
        return out

    dates = pd.to_datetime(close.index, errors="coerce", utc=True)
    valid = dates.notna()
    close = close.loc[valid]
    dates = dates[valid].tz_convert(None)
    if close.empty:
        return out

    year = int(dates[-1].year)
    year_start = pd.Timestamp(year=year, month=1, day=1)
    prior_mask = dates < year_start
    current_mask = dates >= year_start
    if not current_mask.any():
        return out

    if prior_mask.any():
        start_close = float(close.iloc[np.flatnonzero(prior_mask)[-1]])
    else:
        start_close = float(close.iloc[np.flatnonzero(current_mask)[0]])
    end_close = float(close.iloc[-1])
    if not np.isfinite(start_close) or not np.isfinite(end_close) or start_close <= 0:
        return out

    ytd_return = (end_close / start_close) - 1.0
    cap = pd.to_numeric(market_cap, errors="coerce")
    start_cap = (
        float(cap) / (1.0 + ytd_return)
        if pd.notna(cap) and float(cap) > 0 and (1.0 + ytd_return) > 0
        else np.nan
    )
    return {
        "YTD Return": float(ytd_return),
        "YTD Start Market Cap": start_cap,
        "YTD Year": year,
    }

