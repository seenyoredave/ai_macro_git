from __future__ import annotations

from io import StringIO
import os

import numpy as np
import pandas as pd
import requests
import streamlit as st
from fredapi import Fred

from archive.archive_reader import load_fred_history
from config.debug_config import debug_print


NFCI_SERIES_ID = "NFCI"
NFCI_ARCHIVE_COLUMN = "Financial Conditions NFCI"
NFCI_ARCHIVE_DATE_COLUMN = "Financial Conditions NFCI Date"
NFCI_PUBLIC_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI"
)


def _optional_streamlit_secret(name: str, default=None):
    """Read an optional Streamlit secret without requiring secrets.toml."""
    try:
        return st.secrets.get(name, default)
    except Exception as exc:
        debug_print(f"Optional Streamlit secret unavailable: {name} -> {exc}")
        return default


def _get_fred_client():
    """Create an authenticated FRED client when a key is available."""
    key = os.getenv("FRED_API_KEY") or _optional_streamlit_secret("FRED_API_KEY")
    return Fred(api_key=key) if key else None


def _normalize_nfci_history(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Return a clean Date/Value NFCI history frame."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    date_column = next(
        (
            column
            for column in ["Date", "DATE", "Observation Date", "date"]
            if column in frame.columns
        ),
        None,
    )
    value_column = next(
        (
            column
            for column in ["Value", "NFCI", NFCI_ARCHIVE_COLUMN, "VALUE"]
            if column in frame.columns
        ),
        None,
    )
    if date_column is None or value_column is None:
        return pd.DataFrame(columns=["Date", "Value"])

    out = frame[[date_column, value_column]].copy()
    out.columns = ["Date", "Value"]
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    out = out.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    return out.drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)


def _load_archived_nfci_history() -> pd.DataFrame:
    """Read NFCI history from the retained FRED archive."""
    archive = load_fred_history()
    if archive is None or archive.empty or NFCI_ARCHIVE_COLUMN not in archive.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    date_column = (
        NFCI_ARCHIVE_DATE_COLUMN
        if NFCI_ARCHIVE_DATE_COLUMN in archive.columns
        else "Date"
    )
    if date_column not in archive.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    frame = archive[[date_column, NFCI_ARCHIVE_COLUMN]].copy()
    frame.columns = ["Date", "Value"]
    return _normalize_nfci_history(frame)


@st.cache_data(ttl=86400)
def load_nfci_history() -> pd.DataFrame:
    """Load weekly NFCI history from live, public, or archived sources.

    NFCI is isolated from the broader FRED loader so its chart history cannot
    interfere with the dashboard's primary macro-data load path.
    """
    fred = _get_fred_client()
    if fred is not None:
        try:
            series = fred.get_series(NFCI_SERIES_ID)
            frame = pd.DataFrame({"Date": series.index, "Value": series.to_numpy()})
            normalized = _normalize_nfci_history(frame)
            if not normalized.empty:
                normalized.attrs["source"] = "FRED Live"
                return normalized
        except Exception as exc:
            debug_print(f"FRED failed: NFCI history -> {exc}")

    try:
        response = requests.get(NFCI_PUBLIC_CSV_URL, timeout=20)
        response.raise_for_status()
        normalized = _normalize_nfci_history(pd.read_csv(StringIO(response.text)))
        if not normalized.empty:
            normalized.attrs["source"] = "FRED Public CSV"
            return normalized
    except Exception as exc:
        debug_print(f"Public NFCI history load failed -> {exc}")

    archived = _load_archived_nfci_history()
    archived.attrs["source"] = "FRED Archive" if not archived.empty else "Unavailable"
    return archived
