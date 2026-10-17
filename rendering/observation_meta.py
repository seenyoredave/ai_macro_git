"""Compact source and observation date for public readings."""

from __future__ import annotations

import pandas as pd


def source_through(source: str, observed: object) -> str:
    source = str(source or "").strip()
    if not source:
        raise ValueError("An observation label requires a source")
    date = pd.to_datetime(observed, errors="coerce", format="mixed")
    if pd.isna(date):
        return source
    return f"{source} · through {date.strftime('%Y-%m-%d')}"


def latest_observation(frame: object, date_column: str = "Date"):
    """Use observation dates only; retrieval timestamps are not observations."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or date_column not in frame:
        return None
    dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed")
    return dates.max() if dates.notna().any() else None
