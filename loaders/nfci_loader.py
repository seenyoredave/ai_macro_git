from __future__ import annotations

from io import StringIO
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
from fredapi import Fred

from archive.archive_reader import load_fred_history
from config.debug_config import debug_print
from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

NFCI_SERIES_ID = "NFCI"
ANFCI_SERIES_ID = "ANFCI"
NFCI_ARCHIVE_COLUMN = "Financial Conditions NFCI"
NFCI_ARCHIVE_DATE_COLUMN = "Financial Conditions NFCI Date"
ANFCI_ARCHIVE_COLUMN = "Adjusted Financial Conditions ANFCI"
ANFCI_ARCHIVE_DATE_COLUMN = "Adjusted Financial Conditions ANFCI Date"
NFCI_PUBLIC_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI,ANFCI"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
NFCI_HISTORY_PATH = PROJECT_ROOT / "data" / "finance" / "nfci_anfci_history.csv"

def _optional_streamlit_secret(name: str, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception as exc:
        debug_print(f"Optional Streamlit secret unavailable: {name} -> {exc}")
        return default

def _get_fred_client():
    key = os.getenv("FRED_API_KEY") or _optional_streamlit_secret("FRED_API_KEY")
    return Fred(api_key=key) if key else None

def _normalize_nfci_history(frame: pd.DataFrame | None) -> pd.DataFrame:
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
    if NFCI_HISTORY_PATH.exists() and NFCI_HISTORY_PATH.stat().st_size:
        try:
            retained = _normalize_nfci_history(pd.read_csv(NFCI_HISTORY_PATH))
            if not retained.empty:
                return retained
        except Exception as exc:
            debug_print(f"Retained NFCI/ANFCI history load failed -> {exc}")

    # Backward-compatible fallback for builds that predate the dedicated
    # historical-series contract. This archive may contain only snapshots and
    # must never be overwritten as though it were the complete history.
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


def _persist_nfci_history(frame: pd.DataFrame) -> None:
    if not repository_writes_enabled():
        return
    normalized = _normalize_nfci_history(frame)
    if normalized.empty:
        return
    out = normalized.copy()
    out["Date"] = out["Date"].dt.date.astype(str)
    atomic_write_csv(out, NFCI_HISTORY_PATH)

@st.cache_data(ttl=86400)
def load_nfci_history(
    force_refresh: bool = False,
    refresh_token: int = 0,
    allow_live: bool = False,
) -> pd.DataFrame:
    del refresh_token
    if not force_refresh and not allow_live:
        archived = _load_archived_nfci_history()
        archived.attrs["source"] = "FRED Archive" if not archived.empty else "Unavailable"
        return archived

    fred = _get_fred_client()
    if fred is not None:
        try:
            nfci = fred.get_series(NFCI_SERIES_ID).rename("Value")
            anfci = fred.get_series(ANFCI_SERIES_ID).rename("ANFCI")
            frame = pd.concat([nfci, anfci], axis=1).reset_index()
            frame = frame.rename(columns={frame.columns[0]: "Date"})
            normalized = _normalize_nfci_history(frame)
            if not normalized.empty:
                _persist_nfci_history(normalized)
                normalized.attrs["source"] = "FRED Live"
                return normalized
        except Exception as exc:
            debug_print(f"FRED failed: NFCI/ANFCI history -> {exc}")

    try:
        response = requests.get(NFCI_PUBLIC_CSV_URL, timeout=20)
        response.raise_for_status()
        normalized = _normalize_nfci_history(pd.read_csv(StringIO(response.text)))
        if not normalized.empty:
            _persist_nfci_history(normalized)
            normalized.attrs["source"] = "FRED Public CSV"
            return normalized
    except Exception as exc:
        debug_print(f"Public NFCI history load failed -> {exc}")

    archived = _load_archived_nfci_history()
    archived.attrs["source"] = "FRED Archive" if not archived.empty else "Unavailable"
    return archived
