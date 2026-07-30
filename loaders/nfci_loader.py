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
ANFCI_SERIES_ID = "ANFCI"
NFCI_ARCHIVE_COLUMN = "Financial Conditions NFCI"
NFCI_ARCHIVE_DATE_COLUMN = "Financial Conditions NFCI Date"
ANFCI_ARCHIVE_COLUMN = "Adjusted Financial Conditions ANFCI"
ANFCI_ARCHIVE_DATE_COLUMN = "Adjusted Financial Conditions ANFCI Date"
NFCI_PUBLIC_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI,ANFCI"
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
    """Return a clean Date/Value/ANFCI financial-conditions history frame.

    ``Value`` remains the NFCI column used by the
    existing snapshot and chart helpers. ANFCI is retained as an optional
    comparator and never replaces the headline NFCI reading.
    """
    columns = ["Date", "Value", "ANFCI"]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)

    date_column = next(
        (
            column
            for column in ["Date", "DATE", "observation_date", "Observation Date", "date"]
            if column in frame.columns
        ),
        None,
    )
    nfci_column = next(
        (
            column
            for column in ["Value", "NFCI", NFCI_ARCHIVE_COLUMN, "VALUE"]
            if column in frame.columns
        ),
        None,
    )
    anfci_column = next(
        (
            column
            for column in ["ANFCI", ANFCI_ARCHIVE_COLUMN]
            if column in frame.columns
        ),
        None,
    )
    if date_column is None or nfci_column is None:
        return pd.DataFrame(columns=columns)

    selected = [date_column, nfci_column]
    if anfci_column is not None and anfci_column not in selected:
        selected.append(anfci_column)
    out = frame[selected].copy()
    rename = {date_column: "Date", nfci_column: "Value"}
    if anfci_column is not None:
        rename[anfci_column] = "ANFCI"
    out = out.rename(columns=rename)
    if "ANFCI" not in out.columns:
        out["ANFCI"] = np.nan

    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    for column in ["Value", "ANFCI"]:
        out[column] = pd.to_numeric(out[column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
    out = out.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    return out.drop_duplicates(subset=["Date"], keep="last")[columns].reset_index(drop=True)


def _load_archived_nfci_history() -> pd.DataFrame:
    """Read NFCI and optional ANFCI history from the retained FRED archive."""
    archive = load_fred_history()
    if archive is None or archive.empty or NFCI_ARCHIVE_COLUMN not in archive.columns:
        return pd.DataFrame(columns=["Date", "Value", "ANFCI"])

    date_column = (
        NFCI_ARCHIVE_DATE_COLUMN
        if NFCI_ARCHIVE_DATE_COLUMN in archive.columns
        else "Date"
    )
    if date_column not in archive.columns:
        return pd.DataFrame(columns=["Date", "Value", "ANFCI"])

    columns = [date_column, NFCI_ARCHIVE_COLUMN]
    if ANFCI_ARCHIVE_COLUMN in archive.columns:
        columns.append(ANFCI_ARCHIVE_COLUMN)
    frame = archive[columns].copy()
    frame = frame.rename(
        columns={
            date_column: "Date",
            NFCI_ARCHIVE_COLUMN: "Value",
            ANFCI_ARCHIVE_COLUMN: "ANFCI",
        }
    )
    return _normalize_nfci_history(frame)


@st.cache_data(ttl=86400)
def load_nfci_history() -> pd.DataFrame:
    """Load weekly NFCI and ANFCI history from live, public, or archived sources.

    The financial-conditions pair is isolated from the broader FRED loader so its chart history cannot
    interfere with the dashboard's primary macro-data load path.
    """
    fred = _get_fred_client()
    if fred is not None:
        try:
            nfci = fred.get_series(NFCI_SERIES_ID).rename("Value")
            anfci = fred.get_series(ANFCI_SERIES_ID).rename("ANFCI")
            frame = pd.concat([nfci, anfci], axis=1).reset_index()
            frame = frame.rename(columns={frame.columns[0]: "Date"})
            normalized = _normalize_nfci_history(frame)
            if not normalized.empty:
                normalized.attrs["source"] = "FRED Live"
                return normalized
        except Exception as exc:
            debug_print(f"FRED failed: NFCI/ANFCI history -> {exc}")

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
