from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.debug_config import debug_print
from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv, synchronized_path
from loaders.census import clean_header as _clean_header, parse_census_month as _parse_census_month
from config.market_clock import market_date

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION_HISTORY_PATH = PROJECT_ROOT / "data" / "data_center_construction_history.csv"
CONSTRUCTION_RELEASE_PATH = PROJECT_ROOT / "data" / "construction_release_calendar.csv"

CENSUS_PRIVATE_SA_URL = (
    "https://www.census.gov/construction/c30/xlsx/privsatime.xlsx"
)

def parse_private_construction_workbook(content: bytes) -> pd.DataFrame:
    raw = pd.read_excel(
        BytesIO(content),
        sheet_name="Private SA",
        header=3,
        engine="openpyxl",
    )

    raw.columns = [_clean_header(col) for col in raw.columns]

    required = ["Date", "Data center", "Nonresidential"]
    missing = [col for col in required if col not in raw.columns]

    if missing:
        raise ValueError(
            "Census construction workbook contract changed; "
            f"missing columns: {missing}"
        )

    out = raw[required].copy()
    out["Observation Date"] = out["Date"].map(_parse_census_month)
    out["Data Center Construction"] = pd.to_numeric(
        out["Data center"], errors="coerce"
    )
    out["Private Nonresidential Construction"] = pd.to_numeric(
        out["Nonresidential"], errors="coerce"
    )

    out = out.dropna(
        subset=["Observation Date", "Data Center Construction"]
    ).sort_values("Observation Date")

    out = out.drop_duplicates(subset=["Observation Date"], keep="last")

    return out[
        [
            "Observation Date",
            "Data Center Construction",
            "Private Nonresidential Construction",
        ]
    ].reset_index(drop=True)

def _persist_construction_history(df: pd.DataFrame) -> None:
    if not repository_writes_enabled() or df is None or df.empty:
        return

    out = df.copy()
    out["Observation Date"] = pd.to_datetime(
        out["Observation Date"], errors="coerce"
    ).dt.date.astype(str)
    atomic_write_csv(out, CONSTRUCTION_HISTORY_PATH)

def _load_local_construction_history() -> pd.DataFrame | None:
    if (
        not CONSTRUCTION_HISTORY_PATH.exists()
        or CONSTRUCTION_HISTORY_PATH.stat().st_size == 0
    ):
        return None

    try:
        frame = pd.read_csv(CONSTRUCTION_HISTORY_PATH)
    except Exception as exc:
        debug_print(f"Local data-center construction history load failed -> {exc}")
        return None

    required = {
        "Observation Date",
        "Data Center Construction",
        "Private Nonresidential Construction",
    }
    if not required.issubset(frame.columns):
        return None

    frame = frame[list(required)].copy()
    frame["Observation Date"] = pd.to_datetime(
        frame["Observation Date"], errors="coerce"
    )
    frame["Data Center Construction"] = pd.to_numeric(
        frame["Data Center Construction"], errors="coerce"
    )
    frame["Private Nonresidential Construction"] = pd.to_numeric(
        frame["Private Nonresidential Construction"], errors="coerce"
    )
    frame = frame.dropna(
        subset=["Observation Date", "Data Center Construction"]
    ).sort_values("Observation Date")
    frame = frame.drop_duplicates(subset=["Observation Date"], keep="last")
    return frame if not frame.empty else None

def _record_construction_availability(latest_observation_date) -> None:
    if not repository_writes_enabled():
        return
    observation = pd.to_datetime(latest_observation_date, errors="coerce")
    if pd.isna(observation):
        return

    row = pd.DataFrame([{
        "Release Date": market_date().isoformat(),
        "Observation Date": observation.date().isoformat(),
    }])

    with synchronized_path(CONSTRUCTION_RELEASE_PATH):
        if CONSTRUCTION_RELEASE_PATH.exists() and CONSTRUCTION_RELEASE_PATH.stat().st_size > 0:
            existing = pd.read_csv(CONSTRUCTION_RELEASE_PATH)
            combined = pd.concat([existing, row], ignore_index=True, sort=False)
        else:
            combined = row
        combined = combined.drop_duplicates(subset=["Release Date"], keep="last")
        combined = combined.sort_values("Release Date", kind="stable")
        atomic_write_csv(combined, CONSTRUCTION_RELEASE_PATH, lock=False)

def summarize_data_center_construction(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {
            "value": np.nan,
            "date": None,
            "yoy_growth": np.nan,
            "share_private_nonresidential": np.nan,
            "source": "Census Unavailable",
        }

    working = df.copy().sort_values("Observation Date")
    latest = working.iloc[-1]
    latest_date = pd.Timestamp(latest["Observation Date"])
    target = latest_date - pd.DateOffset(years=1)

    prior_rows = working[working["Observation Date"] <= target]
    prior = prior_rows.iloc[-1] if not prior_rows.empty else None

    current_value = float(latest["Data Center Construction"])
    yoy_growth = np.nan

    if prior is not None:
        prior_value = float(prior["Data Center Construction"])
        day_gap = (latest_date - pd.Timestamp(prior["Observation Date"])).days

        if prior_value > 0 and 330 <= day_gap <= 400:
            yoy_growth = (current_value / prior_value) - 1

    nonres = pd.to_numeric(
        pd.Series([latest["Private Nonresidential Construction"]]),
        errors="coerce",
    ).iloc[0]

    share = (
        current_value / float(nonres)
        if pd.notna(nonres) and float(nonres) > 0
        else np.nan
    )

    return {
        "value": current_value,
        "date": latest_date.date().isoformat(),
        "yoy_growth": yoy_growth,
        "share_private_nonresidential": share,
        "source": "Census Live",
    }

@st.cache_data(ttl=86400)
def load_data_center_construction(
    force_refresh: bool = False,
    refresh_token: int = 0,
    allow_live: bool = False,
) -> dict:
    del refresh_token
    local = _load_local_construction_history()
    if not force_refresh and local is not None and not local.empty:
        result = summarize_data_center_construction(local)
        result["source"] = "Census Local History"
        return result
    if not force_refresh and not allow_live:
        return {
            "value": np.nan,
            "date": None,
            "yoy_growth": np.nan,
            "share_private_nonresidential": np.nan,
            "source": "Census Retained History Unavailable",
        }
    try:
        response = requests.get(CENSUS_PRIVATE_SA_URL, timeout=30)
        response.raise_for_status()
        parsed = parse_private_construction_workbook(response.content)
        _persist_construction_history(parsed)
        if not parsed.empty:
            _record_construction_availability(parsed.iloc[-1]["Observation Date"])
        return summarize_data_center_construction(parsed)
    except Exception as exc:
        debug_print(f"Census data-center construction load failed -> {exc}")
        if local is not None and not local.empty:
            result = summarize_data_center_construction(local)
            result["source"] = "Census Local History"
            return result
        return {
            "value": np.nan,
            "date": None,
            "yoy_growth": np.nan,
            "share_private_nonresidential": np.nan,
            "source": "Census Unavailable",
        }
