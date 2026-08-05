from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CES_PATH = PROJECT_ROOT / "data" / "workforce_ces_history.csv"
JOLTS_PATH = PROJECT_ROOT / "data" / "workforce_job_openings_history.csv"


def _read_history(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    if "Date" in frame.columns:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    if "Value" in frame.columns:
        frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    return frame.dropna(subset=[column for column in ["Date", "Value"] if column in frame.columns]).reset_index(drop=True)


def _latest_summary(frame: pd.DataFrame, *, metric: str | None = None) -> pd.DataFrame:
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if clean.empty or not {"Date", "Series", "Value"}.issubset(clean.columns):
        return pd.DataFrame(columns=["Series", "Date", "Value", "YoY Change"])
    if metric is not None and "Metric" in clean.columns:
        clean = clean.loc[clean["Metric"].astype(str).eq(metric)]
    rows = []
    for series, group in clean.groupby("Series", sort=False):
        group = group.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
        if group.empty:
            continue
        latest = group.iloc[-1]
        target = pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)
        prior = group.loc[group["Date"] <= target]
        yoy = np.nan
        if not prior.empty:
            previous = pd.to_numeric(prior.iloc[-1]["Value"], errors="coerce")
            current = pd.to_numeric(latest["Value"], errors="coerce")
            if pd.notna(previous) and previous != 0 and pd.notna(current):
                yoy = float(current / previous - 1.0)
        rows.append({
            "Series": str(series),
            "Date": pd.Timestamp(latest["Date"]),
            "Value": float(latest["Value"]),
            "YoY Change": yoy,
            "Unit": str(latest.get("Unit", "")),
            "Series ID": str(latest.get("Series ID", "")),
        })
    return pd.DataFrame(rows).sort_values("Series", kind="stable").reset_index(drop=True)


@st.cache_data(ttl=21600)
def load_workforce_data() -> dict:
    ces = _read_history(CES_PATH)
    jolts = _read_history(JOLTS_PATH)
    employment = ces.loc[ces.get("Metric", pd.Series(index=ces.index, dtype=str)).astype(str).eq("Employment")].copy()
    earnings = ces.loc[ces.get("Metric", pd.Series(index=ces.index, dtype=str)).astype(str).eq("Hourly earnings")].copy()
    return {
        "source_mode": "retained_official",
        "employment_history": employment,
        "earnings_history": earnings,
        "job_openings_history": jolts,
        "employment_latest": _latest_summary(employment),
        "earnings_latest": _latest_summary(earnings),
        "job_openings_latest": _latest_summary(jolts),
        "snapshot_date": max(
            [date for date in [employment.get("Date", pd.Series(dtype="datetime64[ns]")).max(), earnings.get("Date", pd.Series(dtype="datetime64[ns]")).max(), jolts.get("Date", pd.Series(dtype="datetime64[ns]")).max()] if pd.notna(date)],
            default=pd.NaT,
        ),
        "source_manifest": pd.DataFrame([
            {"Dataset": "Employment and hourly earnings", "Source": "BLS Current Employment Statistics", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Directly relevant industries; not every job is attributed to AI."},
            {"Dataset": "Job openings", "Source": "BLS Job Openings and Labor Turnover Survey", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Broad labor-demand context; not AI-specific postings."},
        ]),
    }
