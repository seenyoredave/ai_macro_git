from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCTIVITY_PATH = PROJECT_ROOT / "data" / "economic_impact_productivity_history.csv"
INVESTMENT_PATH = PROJECT_ROOT / "data" / "info_processing_investment_history.csv"
CPI_PATH = PROJECT_ROOT / "data" / "economic_impact_cpi_history.csv"


def _read(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    for column in ["Date", "Observation Date"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    for column in ["Value", "Info Processing Investment Level", "CPI"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _latest_metric(frame: pd.DataFrame, sector: str, measure: str, metric: str = "Year-over-year change") -> dict:
    if frame.empty:
        return {"value": np.nan, "date": None, "series_id": ""}
    mask = (
        frame.get("sector_name", pd.Series("", index=frame.index)).astype(str).eq(sector)
        & frame.get("measure_text", pd.Series("", index=frame.index)).astype(str).eq(measure)
        & frame.get("Metric", pd.Series("", index=frame.index)).astype(str).eq(metric)
    )
    clean = frame.loc[mask].dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "series_id": ""}
    latest = clean.iloc[-1]
    return {"value": float(latest["Value"]), "date": pd.Timestamp(latest["Date"]), "series_id": str(latest.get("Series ID", ""))}


def _investment_summary(frame: pd.DataFrame) -> dict:
    if frame.empty or not {"Observation Date", "Info Processing Investment Level"}.issubset(frame.columns):
        return {"value": np.nan, "date": None, "yoy": np.nan}
    clean = frame.dropna(subset=["Observation Date", "Info Processing Investment Level"]).sort_values("Observation Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy": np.nan}
    latest = clean.iloc[-1]
    target = latest["Observation Date"] - pd.DateOffset(years=1)
    prior = clean.loc[clean["Observation Date"] <= target]
    yoy = np.nan
    if not prior.empty and float(prior.iloc[-1]["Info Processing Investment Level"]) > 0:
        yoy = float(latest["Info Processing Investment Level"] / prior.iloc[-1]["Info Processing Investment Level"] - 1.0) * 100.0
    return {"value": float(latest["Info Processing Investment Level"]), "date": pd.Timestamp(latest["Observation Date"]), "yoy": yoy}


def _inflation_summary(frame: pd.DataFrame) -> dict:
    if frame.empty or not {"Date", "CPI"}.issubset(frame.columns):
        return {"value": np.nan, "date": None, "yoy": np.nan}
    clean = frame.dropna(subset=["Date", "CPI"]).sort_values("Date", kind="stable")
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy": np.nan}
    latest = clean.iloc[-1]
    target = pd.Timestamp(latest["Date"]) - pd.DateOffset(years=1)
    prior = clean.loc[clean["Date"] <= target]
    yoy = np.nan
    if not prior.empty and float(prior.iloc[-1]["CPI"]) > 0:
        yoy = (float(latest["CPI"]) / float(prior.iloc[-1]["CPI"]) - 1.0) * 100.0
    return {"value": float(latest["CPI"]), "date": pd.Timestamp(latest["Date"]), "yoy": yoy}


@st.cache_data(ttl=21600)
def load_economic_impact_data() -> dict:
    productivity = _read(PRODUCTIVITY_PATH)
    investment = _read(INVESTMENT_PATH)
    cpi = _read(CPI_PATH)
    if not investment.empty and "Observation Date" in investment.columns:
        investment = investment.loc[investment["Observation Date"] >= pd.Timestamp("2020-01-01")].reset_index(drop=True)
    return {
        "source_mode": "retained_official",
        "productivity_history": productivity,
        "investment_history": investment,
        "cpi_history": cpi,
        "nonfarm_productivity": _latest_metric(productivity, "Nonfarm Business", "Labor productivity (output per hour)"),
        "nonfarm_output": _latest_metric(productivity, "Nonfarm Business", "Real value-added output"),
        "nonfarm_compensation": _latest_metric(productivity, "Nonfarm Business", "Hourly compensation"),
        "nonfarm_unit_labor_cost": _latest_metric(productivity, "Nonfarm Business", "Unit labor costs"),
        "manufacturing_productivity": _latest_metric(productivity, "Manufacturing", "Labor productivity (output per hour)"),
        "manufacturing_output": _latest_metric(productivity, "Manufacturing", "Real value-added output"),
        "information_investment": _investment_summary(investment),
        "inflation": _inflation_summary(cpi),
        "snapshot_date": productivity.get("Date", pd.Series(dtype="datetime64[ns]")).max() if not productivity.empty else pd.NaT,
        "source_manifest": pd.DataFrame([
            {"Dataset": "Productivity, output, compensation, and unit labor costs", "Source": "BLS Labor Productivity and Costs", "Frequency": "Quarterly", "Coverage": "2020-present", "Attribution boundary": "Realized macro outcomes; no causal attribution to AI."},
            {"Dataset": "Information-processing equipment and software investment", "Source": "BEA via FRED retained history", "Frequency": "Quarterly", "Coverage": "Chronology through latest retained release", "Attribution boundary": "Real chained-dollar investment in the broader information-processing asset class, not exclusively AI."},
            {"Dataset": "Consumer Price Index", "Source": "BLS via FRED retained history", "Frequency": "Monthly", "Coverage": "2020-present", "Attribution boundary": "Used only to express nominal compensation and unit-labor-cost growth in inflation-adjusted terms."},
        ]),
    }
