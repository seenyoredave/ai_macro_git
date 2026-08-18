"""Current county drought context from the U.S. Drought Monitor REST service."""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from helpers.atomic_io import atomic_write_csv

USDM_COUNTY_URL = (
    "https://usdmdataservices.unl.edu/api/CountyStatistics/"
    "GetDroughtSeverityStatisticsByAreaPercent"
)
SOURCE_LABEL = "U.S. Drought Monitor county statistics"
SOURCE_URL = "https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx"

OUTPUT_COLUMNS = [
    "FIPS",
    "County",
    "State",
    "Snapshot Date",
    "D0+ Area Percent",
    "D1+ Area Percent",
    "D2+ Area Percent",
    "D3+ Area Percent",
    "D4 Area Percent",
    "Source",
    "Source URL",
]


def _normalize_fips(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return ""
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(5) if digits else ""


def _find_column(frame: pd.DataFrame, *candidates: str) -> str | None:
    lookup = {str(column).strip().casefold(): column for column in frame.columns}
    for candidate in candidates:
        found = lookup.get(candidate.casefold())
        if found is not None:
            return str(found)
    return None


def _response_frame(response: requests.Response) -> pd.DataFrame:
    content_type = str(response.headers.get("content-type") or "").casefold()
    if "json" in content_type:
        payload = response.json()
        if isinstance(payload, dict):
            for key in ("data", "results", "features"):
                candidate = payload.get(key)
                if isinstance(candidate, list):
                    payload = candidate
                    break
        if isinstance(payload, list):
            return pd.DataFrame(payload)
    return pd.read_csv(StringIO(response.text))


def normalize_county_statistics(frame: pd.DataFrame | None, *, state: str = "") -> pd.DataFrame:
    """Normalize one USDM county-statistics response to cumulative D0-D4 shares."""

    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    source = frame.copy()
    fips_col = _find_column(source, "FIPS", "CountyFIPS", "County FIPS", "GEOID")
    county_col = _find_column(source, "County", "CountyName", "County Name", "Name")
    state_col = _find_column(source, "State", "StateAbbreviation", "State Abbreviation")
    date_col = _find_column(source, "MapDate", "ValidStart", "Date", "Snapshot Date")
    d0_col = _find_column(source, "D0", "D0-D4", "D0+", "D0 Area Percent")
    d1_col = _find_column(source, "D1", "D1-D4", "D1+", "D1 Area Percent")
    d2_col = _find_column(source, "D2", "D2-D4", "D2+", "D2 Area Percent")
    d3_col = _find_column(source, "D3", "D3-D4", "D3+", "D3 Area Percent")
    d4_col = _find_column(source, "D4", "D4 Area Percent")

    if fips_col is None or date_col is None or any(column is None for column in (d0_col, d1_col, d2_col, d3_col, d4_col)):
        raise ValueError(f"USDM county response schema changed; columns={list(source.columns)}")

    output = pd.DataFrame(index=source.index)
    output["FIPS"] = source[fips_col].map(_normalize_fips)
    output["County"] = source[county_col].fillna("").astype(str).str.strip() if county_col else ""
    output["State"] = (
        source[state_col].fillna("").astype(str).str.upper().str.strip()
        if state_col
        else str(state or "").upper().strip()
    )
    dates = pd.to_datetime(source[date_col], errors="coerce", format="mixed")
    output["Snapshot Date"] = dates.dt.date.astype("string")
    for target, column in (
        ("D0+ Area Percent", d0_col),
        ("D1+ Area Percent", d1_col),
        ("D2+ Area Percent", d2_col),
        ("D3+ Area Percent", d3_col),
        ("D4 Area Percent", d4_col),
    ):
        output[target] = pd.to_numeric(source[column], errors="coerce")
    output["Source"] = SOURCE_LABEL
    output["Source URL"] = SOURCE_URL
    output = output.loc[output["FIPS"].ne("") & dates.notna()].copy()
    if output.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    output["_date"] = dates.loc[output.index]
    output = (
        output.sort_values(["FIPS", "_date"], kind="stable")
        .drop_duplicates("FIPS", keep="last")
        .drop(columns="_date")
        .reset_index(drop=True)
    )
    return output[OUTPUT_COLUMNS]


def fetch_county_drought(
    states: Iterable[str],
    *,
    as_of: date | None = None,
    session: requests.Session | None = None,
    timeout: int = 30,
) -> tuple[pd.DataFrame, dict]:
    """Fetch the latest weekly county drought snapshot for the requested states."""

    target = as_of or date.today()
    start = target - timedelta(days=28)
    unique_states = sorted({str(value or "").upper().strip() for value in states if str(value or "").strip()})
    client = session or requests.Session()
    frames: list[pd.DataFrame] = []
    errors: dict[str, str] = {}

    for state in unique_states:
        try:
            response = client.get(
                USDM_COUNTY_URL,
                params={
                    "aoi": state,
                    "startdate": f"{start.month}/{start.day}/{start.year}",
                    "enddate": f"{target.month}/{target.day}/{target.year}",
                    "statisticsType": 1,
                },
                headers={"Accept": "application/json, text/csv;q=0.9"},
                timeout=timeout,
            )
            response.raise_for_status()
            normalized = normalize_county_statistics(_response_frame(response), state=state)
            if normalized.empty:
                errors[state] = "No county rows returned."
            else:
                frames.append(normalized)
        except Exception as exc:  # provider failure becomes an explicit partial-refresh report
            errors[state] = f"{type(exc).__name__}: {exc}"

    output = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    if not output.empty:
        output = output.sort_values(["State", "FIPS"], kind="stable").reset_index(drop=True)
    report = {
        "source": SOURCE_LABEL,
        "requested_states": len(unique_states),
        "refreshed_states": len(unique_states) - len(errors),
        "county_rows": int(len(output)),
        "errors": errors,
        "source_mode": (
            "live_refresh" if unique_states and not errors
            else "partial_refresh" if output is not None and not output.empty
            else "failed"
        ),
    }
    return output, report


def persist_county_drought(frame: pd.DataFrame, path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(frame[OUTPUT_COLUMNS], output, compression="gzip")
