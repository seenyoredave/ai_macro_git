"""Market-data date shown in the platform masthead."""

from __future__ import annotations

import pandas as pd

from archive.archive_reader import latest_complete_ticker_rows, load_yf_history
from config.sector_config import all_tickers


def _date_from_frame(frame: pd.DataFrame | None) -> pd.Timestamp | pd.NaT:
    """Return the dominant date for the market rows currently powering the app."""
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.NaT

    for column in ("Market Data Date", "Date"):
        if column not in frame.columns:
            continue
        dates = pd.to_datetime(frame[column], errors="coerce", format="mixed").dropna()
        if dates.empty:
            continue
        counts = dates.value_counts()
        return pd.Timestamp(counts.index[0])

    return pd.NaT


def _retained_market_date() -> pd.Timestamp | pd.NaT:
    """Fallback date when no loaded market frame is available."""
    history = load_yf_history()
    complete = latest_complete_ticker_rows(history, all_tickers())
    if complete is None or complete.empty or "Date" not in complete.columns:
        return pd.NaT
    dates = pd.to_datetime(complete["Date"], errors="coerce", format="mixed")
    return dates.max() if dates.notna().any() else pd.NaT


def market_snapshot_label(frame: pd.DataFrame | None = None) -> str | None:
    """Describe the market date actually loaded, falling back to retained history."""
    market_date = _date_from_frame(frame)
    if pd.isna(market_date):
        market_date = _retained_market_date()
    if pd.isna(market_date):
        return None
    return f"Market data {market_date.month}.{market_date.day}.{market_date.year}"
