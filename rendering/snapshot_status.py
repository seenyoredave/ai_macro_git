"""Retained-market date for the platform release line."""

from __future__ import annotations

import pandas as pd

from archive.archive_reader import latest_complete_ticker_rows, load_yf_history
from config.sector_config import all_tickers


def _retained_market_date() -> pd.Timestamp | pd.NaT:
    history = load_yf_history()
    complete = latest_complete_ticker_rows(history, all_tickers())
    if complete is None or complete.empty or "Date" not in complete.columns:
        return pd.NaT
    dates = pd.to_datetime(complete["Date"], errors="coerce", format="mixed")
    return dates.max() if dates.notna().any() else pd.NaT


def retained_market_snapshot_label() -> str | None:
    market_date = _retained_market_date()
    if pd.isna(market_date):
        return None
    return (
        "Retained market snapshot through "
        f"{market_date.month}.{market_date.day}.{market_date.year}"
    )
