"""Market-data freshness shown in the platform masthead."""

from __future__ import annotations

import pandas as pd

from archive.archive_reader import latest_ticker_rows, load_yf_history
from config.sector_config import all_tickers


def _market_dates(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype="datetime64[ns]")
    for column in ("Market Data Date", "Date"):
        if column not in frame.columns:
            continue
        dates = pd.to_datetime(frame[column], errors="coerce", format="mixed")
        if dates.notna().any():
            return dates
    return pd.Series(dtype="datetime64[ns]")


def _retained_market_frame() -> pd.DataFrame | None:
    history = load_yf_history()
    latest = latest_ticker_rows(history, all_tickers())
    if latest is None or latest.empty:
        return None
    return latest


def _format_date(value: pd.Timestamp) -> str:
    return f"{value.month}.{value.day}.{value.year}"


def market_snapshot_label(frame: pd.DataFrame | None = None) -> str | None:
    """Describe the actual per-ticker freshness of the market universe."""
    active = frame if isinstance(frame, pd.DataFrame) and not frame.empty else _retained_market_frame()
    dates = _market_dates(active)
    valid = dates.dropna()
    if valid.empty:
        return None

    latest = pd.Timestamp(valid.max())
    current = int((dates.dt.date == latest.date()).sum())
    total = int(len(dates))
    retained = max(0, total - current)
    if retained == 0:
        return f"Market data {_format_date(latest)}"

    stale = dates.loc[dates.notna() & (dates.dt.date != latest.date())]
    stale_unique = sorted({pd.Timestamp(value) for value in stale})
    if len(stale_unique) == 1:
        retained_detail = f"{retained} retained from {_format_date(stale_unique[0])}"
    elif stale_unique:
        retained_detail = f"{retained} retained · oldest {_format_date(stale_unique[0])}"
    else:
        retained_detail = f"{retained} retained"

    return (
        f"Market data through {_format_date(latest)} · "
        f"{current}/{total} current · {retained_detail}"
    )
