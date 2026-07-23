"""U.S. Census private data-center construction loader."""

from __future__ import annotations

from io import BytesIO
from datetime import date
from pathlib import Path
import re

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.debug_config import debug_print


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION_HISTORY_PATH = PROJECT_ROOT / "data" / "data_center_construction_history.csv"
CONSTRUCTION_RELEASE_PATH = PROJECT_ROOT / "data" / "construction_release_calendar.csv"

CENSUS_PRIVATE_SA_URL = (
    "https://www.census.gov/construction/c30/xlsx/privsatime.xlsx"
)


def _clean_header(value) -> str:
    text = str(value).replace("\n_x000D_", " ").replace("\n", " ")
    return " ".join(text.split()).strip()


def _parse_census_month(value):
    if value is None or pd.isna(value):
        return pd.NaT

    text = re.sub(r"[pr]$", "", str(value).strip(), flags=re.IGNORECASE)
    return pd.to_datetime(text, format="%b-%y", errors="coerce")


def parse_private_construction_workbook(content: bytes) -> pd.DataFrame:
    """Parse the Census Private SA workbook into a stable three-column frame."""
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
    """Persist the parsed Census series for future derived-history rebuilds."""
    if df is None or df.empty:
        return

    out = df.copy()
    out["Observation Date"] = pd.to_datetime(
        out["Observation Date"], errors="coerce"
    ).dt.date.astype(str)

    CONSTRUCTION_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = CONSTRUCTION_HISTORY_PATH.with_suffix(".csv.tmp")
    out.to_csv(temp, index=False)
    temp.replace(CONSTRUCTION_HISTORY_PATH)


def _record_construction_availability(latest_observation_date) -> None:
    """Record when a Census observation first became available to this app."""
    observation = pd.to_datetime(latest_observation_date, errors="coerce")
    if pd.isna(observation):
        return

    row = pd.DataFrame([{
        "Release Date": date.today().isoformat(),
        "Observation Date": observation.date().isoformat(),
    }])

    if CONSTRUCTION_RELEASE_PATH.exists() and CONSTRUCTION_RELEASE_PATH.stat().st_size > 0:
        existing = pd.read_csv(CONSTRUCTION_RELEASE_PATH)
        combined = pd.concat([existing, row], ignore_index=True, sort=False)
    else:
        combined = row

    combined = combined.drop_duplicates(subset=["Release Date"], keep="last")
    combined = combined.sort_values("Release Date", kind="stable")
    temp = CONSTRUCTION_RELEASE_PATH.with_suffix(".csv.tmp")
    combined.to_csv(temp, index=False)
    temp.replace(CONSTRUCTION_RELEASE_PATH)


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
def load_data_center_construction() -> dict:
    """Return latest data-center construction value and YoY growth.

    Failure is represented as missing data. ADI's 3-of-4 coverage rule decides
    whether the wider index can still be constituted.
    """
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
        return {
            "value": np.nan,
            "date": None,
            "yoy_growth": np.nan,
            "share_private_nonresidential": np.nan,
            "source": "Census Live Failed",
        }
