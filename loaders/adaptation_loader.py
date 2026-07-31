"""Census business AI-use observations for the Adaptation research view."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.debug_config import debug_print


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NATIONAL_HISTORY_PATH = PROJECT_ROOT / "data" / "adaptation_national_history.csv"
SECTOR_SNAPSHOT_PATH = PROJECT_ROOT / "data" / "adaptation_sector_snapshot.csv"
BTOS_NATIONAL_URL = "https://www.census.gov/hfp/btos/downloads/National.xlsx"
BTOS_SECTOR_URL = "https://www.census.gov/hfp/btos/downloads/Sector.xlsx"

NAICS_SECTORS = {
    "11": "Agriculture, Forestry, Fishing and Hunting",
    "21": "Mining, Quarrying, and Oil and Gas Extraction",
    "22": "Utilities",
    "23": "Construction",
    "31": "Manufacturing",
    "42": "Wholesale Trade",
    "44": "Retail Trade",
    "48": "Transportation and Warehousing",
    "51": "Information",
    "52": "Finance and Insurance",
    "53": "Real Estate and Rental and Leasing",
    "54": "Professional, Scientific, and Technical Services",
    "55": "Management of Companies and Enterprises",
    "56": "Administrative and Support and Waste Management",
    "61": "Educational Services",
    "62": "Health Care and Social Assistance",
    "71": "Arts, Entertainment, and Recreation",
    "72": "Accommodation and Food Services",
    "81": "Other Services",
    "XX": "Multi-unit Companies",
}


def _percent(value):
    text = str(value).strip()
    if not text.endswith("%"):
        return np.nan
    return pd.to_numeric(text[:-1], errors="coerce")


def _cycle_columns(frame: pd.DataFrame) -> list[str]:
    return [str(column) for column in frame.columns if str(column).isdigit() and len(str(column)) == 6]


def _cycle_dates(workbook: bytes) -> dict[str, pd.Timestamp]:
    dates = pd.read_excel(BytesIO(workbook), sheet_name="Collection and Reference Dates", engine="openpyxl")
    dates["Smpdt"] = pd.to_numeric(dates.get("Smpdt"), errors="coerce")
    dates["Publication Date"] = pd.to_datetime(dates.get("Publication Date"), errors="coerce")
    return {
        str(int(row["Smpdt"])): pd.Timestamp(row["Publication Date"])
        for _, row in dates.dropna(subset=["Smpdt", "Publication Date"]).iterrows()
    }


def parse_btos_national_workbook(content: bytes) -> pd.DataFrame:
    estimates = pd.read_excel(BytesIO(content), sheet_name="Response Estimates", engine="openpyxl")
    errors = pd.read_excel(BytesIO(content), sheet_name="Response Standard Errors", engine="openpyxl")
    cycle_dates = _cycle_dates(content)
    rows = []
    for question, metric in [(7, "Current AI Use"), (24, "Expected AI Use")]:
        selector = (pd.to_numeric(estimates["Question ID"], errors="coerce") == question) & estimates["Answer"].astype(str).str.strip().eq("Yes")
        error_selector = (pd.to_numeric(errors["Question ID"], errors="coerce") == question) & errors["Answer"].astype(str).str.strip().eq("Yes")
        if not selector.any() or not error_selector.any():
            raise ValueError(f"BTOS national workbook missing question {question} Yes response")
        row = estimates.loc[selector].iloc[0]
        error_row = errors.loc[error_selector].iloc[0]
        for cycle in _cycle_columns(estimates):
            value = _percent(row.get(cycle))
            if pd.isna(value) or cycle not in cycle_dates:
                continue
            rows.append({
                "Cycle": cycle,
                "Date": cycle_dates[cycle],
                "Metric": metric,
                "Value": float(value),
                "Standard Error": _percent(error_row.get(cycle)),
            })
    long = pd.DataFrame(rows)
    if long.empty:
        raise ValueError("BTOS national workbook produced no AI-use observations")
    values = long.pivot(index=["Cycle", "Date"], columns="Metric", values="Value").reset_index()
    standard_errors = long.pivot(index=["Cycle", "Date"], columns="Metric", values="Standard Error").reset_index().rename(columns={
        "Current AI Use": "Current AI Use SE",
        "Expected AI Use": "Expected AI Use SE",
    })
    output = values.merge(standard_errors, on=["Cycle", "Date"], how="left")
    output["Expected Adoption Gap"] = output["Expected AI Use"] - output["Current AI Use"]
    return output.sort_values("Date", kind="stable").drop_duplicates("Date", keep="last").reset_index(drop=True)


def parse_btos_sector_workbook(content: bytes) -> pd.DataFrame:
    estimates = pd.read_excel(BytesIO(content), sheet_name="Response Estimates", engine="openpyxl")
    errors = pd.read_excel(BytesIO(content), sheet_name="Response Standard Errors", engine="openpyxl")
    cycle_dates = _cycle_dates(content)
    cycles = _cycle_columns(estimates)
    if not cycles:
        raise ValueError("BTOS sector workbook contains no cycle columns")
    latest = max(cycles, key=int)
    rows = []
    for sector_code in estimates["Sector"].dropna().astype(str).unique():
        payload = {"Sector Code": sector_code, "Sector": NAICS_SECTORS.get(sector_code, sector_code)}
        for question, metric in [(7, "Current AI Use"), (24, "Expected AI Use")]:
            selector = (
                estimates["Sector"].astype(str).eq(sector_code)
                & (pd.to_numeric(estimates["Question ID"], errors="coerce") == question)
                & estimates["Answer"].astype(str).str.strip().eq("Yes")
            )
            error_selector = (
                errors["Sector"].astype(str).eq(sector_code)
                & (pd.to_numeric(errors["Question ID"], errors="coerce") == question)
                & errors["Answer"].astype(str).str.strip().eq("Yes")
            )
            payload[metric] = _percent(estimates.loc[selector].iloc[0].get(latest)) if selector.any() else np.nan
            payload[f"{metric} SE"] = _percent(errors.loc[error_selector].iloc[0].get(latest)) if error_selector.any() else np.nan
        payload["Expected Adoption Gap"] = payload["Expected AI Use"] - payload["Current AI Use"] if pd.notna(payload["Expected AI Use"]) and pd.notna(payload["Current AI Use"]) else np.nan
        payload["Observation Date"] = cycle_dates.get(latest)
        rows.append(payload)
    return pd.DataFrame(rows)


def _ensure_expected_adoption_gap(frame: pd.DataFrame) -> pd.DataFrame:
    """Recompute the descriptive gap whenever both component estimates exist."""
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    output = frame.copy()
    current = pd.to_numeric(output.get("Current AI Use"), errors="coerce")
    expected = pd.to_numeric(output.get("Expected AI Use"), errors="coerce")
    if isinstance(current, pd.Series) and isinstance(expected, pd.Series):
        output["Current AI Use"] = current
        output["Expected AI Use"] = expected
        output["Expected Adoption Gap"] = expected - current
    return output


def _persist(national: pd.DataFrame, sector: pd.DataFrame) -> None:
    national_out = _ensure_expected_adoption_gap(national)
    national_out["Date"] = pd.to_datetime(national_out["Date"], errors="coerce").dt.date.astype(str)
    sector_out = _ensure_expected_adoption_gap(sector)
    sector_out["Observation Date"] = pd.to_datetime(sector_out["Observation Date"], errors="coerce").dt.date.astype(str)
    national_temp = NATIONAL_HISTORY_PATH.with_suffix(".csv.tmp")
    sector_temp = SECTOR_SNAPSHOT_PATH.with_suffix(".csv.tmp")
    national_out.to_csv(national_temp, index=False)
    sector_out.to_csv(sector_temp, index=False)
    national_temp.replace(NATIONAL_HISTORY_PATH)
    sector_temp.replace(SECTOR_SNAPSHOT_PATH)


def _load_local() -> tuple[pd.DataFrame, pd.DataFrame]:
    national = pd.read_csv(NATIONAL_HISTORY_PATH) if NATIONAL_HISTORY_PATH.exists() else pd.DataFrame()
    sector = pd.read_csv(SECTOR_SNAPSHOT_PATH) if SECTOR_SNAPSHOT_PATH.exists() else pd.DataFrame()
    legacy_gap_column = "Adoption" + " Pipeline"
    if legacy_gap_column in national.columns and "Expected Adoption Gap" not in national.columns:
        national = national.rename(columns={legacy_gap_column: "Expected Adoption Gap"})
    if legacy_gap_column in sector.columns and "Expected Adoption Gap" not in sector.columns:
        sector = sector.rename(columns={legacy_gap_column: "Expected Adoption Gap"})
    if not national.empty:
        national["Date"] = pd.to_datetime(national["Date"], errors="coerce", format="mixed")
        for column in ["Current AI Use", "Expected AI Use", "Expected Adoption Gap", "Current AI Use SE", "Expected AI Use SE"]:
            if column in national.columns:
                national[column] = pd.to_numeric(national[column], errors="coerce")
        national = national.dropna(subset=["Date"]).sort_values("Date", kind="stable")
    if not sector.empty:
        sector["Observation Date"] = pd.to_datetime(sector["Observation Date"], errors="coerce", format="mixed")
        for column in ["Current AI Use", "Expected AI Use", "Expected Adoption Gap", "Current AI Use SE", "Expected AI Use SE"]:
            if column in sector.columns:
                sector[column] = pd.to_numeric(sector[column], errors="coerce")
    national = _ensure_expected_adoption_gap(national)
    sector = _ensure_expected_adoption_gap(sector)
    return national, sector


def _summarize(national: pd.DataFrame, sector: pd.DataFrame, *, source: str) -> dict:
    national = _ensure_expected_adoption_gap(national)
    sector = _ensure_expected_adoption_gap(sector)
    if national.empty:
        return {
            "source_mode": "unavailable",
            "source": source,
            "snapshot_date": None,
            "national_history": national,
            "sector_snapshot": sector,
            "current_use": np.nan,
            "expected_use": np.nan,
            "expected_adoption_gap": np.nan,
            "annual_change": np.nan,
        }
    latest = national.iloc[-1]
    latest_date = pd.Timestamp(latest["Date"])
    prior = national.loc[national["Date"] <= latest_date - pd.DateOffset(years=1)]
    annual_change = np.nan
    if not prior.empty:
        annual_change = float(latest["Current AI Use"]) - float(prior.iloc[-1]["Current AI Use"])
    return {
        "source_mode": "live" if source.endswith("Live") else "local_history",
        "source": source,
        "snapshot_date": latest_date.date().isoformat(),
        "national_history": national,
        "sector_snapshot": sector,
        "current_use": float(latest["Current AI Use"]),
        "expected_use": float(latest["Expected AI Use"]),
        "expected_adoption_gap": float(latest["Expected AI Use"] - latest["Current AI Use"]),
        "current_use_se": pd.to_numeric(latest.get("Current AI Use SE"), errors="coerce"),
        "expected_use_se": pd.to_numeric(latest.get("Expected AI Use SE"), errors="coerce"),
        "annual_change": annual_change,
    }


@st.cache_data(ttl=43200)
def load_adaptation_data(force_refresh: bool = False, refresh_token: int = 0) -> dict:
    """Return observed business AI use and expected near-term use.

    The first-pass Adaptation view is descriptive. It does not infer productivity,
    causality, labor displacement, or realized return from adoption alone.
    """
    del force_refresh, refresh_token
    try:
        national_response = requests.get(BTOS_NATIONAL_URL, timeout=45)
        national_response.raise_for_status()
        sector_response = requests.get(BTOS_SECTOR_URL, timeout=45)
        sector_response.raise_for_status()
        national = parse_btos_national_workbook(national_response.content)
        sector = parse_btos_sector_workbook(sector_response.content)
        _persist(national, sector)
        return _summarize(national, sector, source="Census BTOS Live")
    except Exception as exc:
        debug_print(f"BTOS adaptation refresh failed -> {exc}")
        national, sector = _load_local()
        return _summarize(national, sector, source="Census BTOS Local History")
