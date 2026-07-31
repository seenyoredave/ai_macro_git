"""State-selectable USGS surface-water availability context.

The first water layer uses the USGS National Water Availability Assessment
surface-water supply and use index (SUI). It intentionally does not represent
or infer groundwater availability, water rights, utility service, permits,
withdrawals, consumption, or facility causation.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.debug_config import debug_print


_CACHE_DATA = getattr(st, "cache_data", lambda *args, **kwargs: (lambda function: function))


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = PROJECT_ROOT / "data" / "water_context"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

NWDC_DATA_URL = "https://api.water.usgs.gov/nwaa-data/data"
WBD_HUC8_QUERY_URL = (
    "https://hydro.nationalmap.gov/arcgis/rest/services/wbd/FeatureServer/4/query"
)
MODEL_ID = "iwa-assessment-outputs-conus-2025"
VARIABLE_ID = "sui"
OBSERVATION_YEAR = 2020

STATE_NAMES = {
    "AL": "Alabama", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida",
    "GA": "Georgia", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana",
    "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin",
    "WY": "Wyoming",
}


def _metric_path(state_code: str) -> Path:
    return CACHE_DIR / f"sui_huc8_{state_code.lower()}_{OBSERVATION_YEAR}.csv"


def _geometry_path(state_code: str) -> Path:
    return CACHE_DIR / f"wbd_huc8_{state_code.lower()}.geojson"


def _sui_band(value) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric):
        return "Unknown"
    if numeric < 0.25:
        return "Lower"
    if numeric < 0.50:
        return "Moderate"
    if numeric < 0.75:
        return "High"
    return "Very high"


def _parse_nwdc_payload(payload: dict) -> pd.DataFrame:
    """Normalize the documented NWDC location-keyed JSON response."""
    rows = []
    data = (payload or {}).get("data", {}) or {}
    huc_payload = data.get("huc12_id", {}) or {}
    if not isinstance(huc_payload, dict):
        return pd.DataFrame(columns=["HUC12", "Observation Year", "SUI"])

    for huc12, observations in huc_payload.items():
        if isinstance(observations, dict):
            observations = [observations]
        for observation in observations or []:
            if not isinstance(observation, dict):
                continue
            value = observation.get(VARIABLE_ID)
            if value is None:
                value = observation.get("sui_frac")
            if value is None:
                value = next(
                    (candidate for key, candidate in observation.items() if str(key).startswith("sui_")),
                    None,
                )
            date_token = (
                observation.get("water_year")
                or observation.get("year")
                or str(observation.get("year_month") or "")[:4]
                or OBSERVATION_YEAR
            )
            rows.append(
                {
                    "HUC12": str(huc12).zfill(12),
                    "Observation Year": pd.to_numeric(date_token, errors="coerce"),
                    "SUI": pd.to_numeric(value, errors="coerce"),
                }
            )
    return pd.DataFrame(rows, columns=["HUC12", "Observation Year", "SUI"])


def _fetch_state_sui(state_code: str) -> pd.DataFrame:
    chunks = []
    skip = 0
    limit = 600
    while True:
        response = requests.get(
            NWDC_DATA_URL,
            params={
                "model": MODEL_ID,
                "variable": VARIABLE_ID,
                "location": f"stateCd:{state_code}",
                "startdate": str(OBSERVATION_YEAR),
                "enddate": str(OBSERVATION_YEAR),
                "timeres": "annualwy",
                "intersection": "overlap",
                "format": "json",
                "limit": limit,
                "skip": skip,
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        chunk = _parse_nwdc_payload(payload)
        if chunk.empty:
            break
        chunks.append(chunk)
        returned_hucs = int(chunk["HUC12"].nunique())
        if returned_hucs < limit:
            break
        skip += limit
        if skip > 100000:
            raise RuntimeError("NWDC pagination exceeded safety limit")

    if not chunks:
        return pd.DataFrame(columns=["HUC8", "Median SUI", "P75 SUI", "HUC12 Count", "Observation Year"])
    huc12 = pd.concat(chunks, ignore_index=True)
    huc12 = huc12.dropna(subset=["HUC12", "SUI"])
    huc12["HUC8"] = huc12["HUC12"].astype(str).str[:8]
    grouped = (
        huc12.groupby("HUC8", as_index=False)
        .agg(
            **{
                "Median SUI": ("SUI", "median"),
                "P75 SUI": ("SUI", lambda values: values.quantile(0.75)),
                "HUC12 Count": ("HUC12", "nunique"),
            }
        )
    )
    grouped["Observation Year"] = OBSERVATION_YEAR
    grouped["SUI Band"] = grouped["Median SUI"].map(_sui_band)
    return grouped


def _fetch_state_huc8_geojson(state_code: str) -> dict:
    response = requests.get(
        WBD_HUC8_QUERY_URL,
        params={
            "where": f"states LIKE '%{state_code}%'",
            "outFields": "huc8,name,states,areasqkm",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
            "resultRecordCount": "2000",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("type") != "FeatureCollection":
        raise ValueError("USGS WBD service did not return a GeoJSON FeatureCollection")
    for feature in payload.get("features", []):
        properties = (feature or {}).setdefault("properties", {})
        huc8 = str(properties.get("huc8") or properties.get("HUC8") or "").zfill(8)
        if huc8:
            properties["huc8"] = huc8
        if "name" not in properties and properties.get("NAME") is not None:
            properties["name"] = properties.get("NAME")
        if "states" not in properties and properties.get("STATES") is not None:
            properties["states"] = properties.get("STATES")
        if "areasqkm" not in properties and properties.get("AREASQKM") is not None:
            properties["areasqkm"] = properties.get("AREASQKM")
    return payload


def _load_local_metric(state_code: str) -> pd.DataFrame:
    path = _metric_path(state_code)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["HUC8", "Median SUI", "P75 SUI", "HUC12 Count", "Observation Year", "SUI Band"])
    frame = pd.read_csv(path, dtype={"HUC8": str})
    frame["HUC8"] = frame["HUC8"].astype(str).str.zfill(8)
    for column in ["Median SUI", "P75 SUI", "HUC12 Count", "Observation Year"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "SUI Band" not in frame.columns:
        frame["SUI Band"] = frame.get("Median SUI", np.nan).map(_sui_band)
    return frame


def _load_local_geometry(state_code: str) -> dict:
    path = _geometry_path(state_code)
    if not path.exists() or path.stat().st_size == 0:
        return {"type": "FeatureCollection", "features": []}
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        debug_print(f"Water geometry cache read failed -> {exc}")
        return {"type": "FeatureCollection", "features": []}


def _persist_metric(state_code: str, frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    path = _metric_path(state_code)
    temp = path.with_suffix(".csv.tmp")
    frame.to_csv(temp, index=False)
    temp.replace(path)


def _persist_geometry(state_code: str, payload: dict) -> None:
    if not payload.get("features"):
        return
    path = _geometry_path(state_code)
    temp = path.with_suffix(".geojson.tmp")
    temp.write_text(json.dumps(payload, separators=(",", ":")))
    temp.replace(path)


def _geometry_names(payload: dict) -> pd.DataFrame:
    rows = []
    for feature in (payload or {}).get("features", []):
        properties = (feature or {}).get("properties", {}) or {}
        huc8 = str(properties.get("huc8") or properties.get("HUC8") or "").zfill(8)
        if not huc8:
            continue
        rows.append(
            {
                "HUC8": huc8,
                "Watershed": str(properties.get("name") or properties.get("NAME") or ""),
                "States": str(properties.get("states") or properties.get("STATES") or ""),
                "Area Sq Km": pd.to_numeric(
                    properties.get("areasqkm") or properties.get("AREASQKM"), errors="coerce"
                ),
            }
        )
    return pd.DataFrame(rows).drop_duplicates("HUC8", keep="last") if rows else pd.DataFrame(columns=["HUC8", "Watershed", "States", "Area Sq Km"])


@_CACHE_DATA(ttl=604800)
def load_water_context(state_code: str = "TX", force_refresh: bool = False) -> dict:
    """Load one state's HUC8 display layer from consistent national USGS inputs."""
    state_code = str(state_code or "TX").upper()
    if state_code not in STATE_NAMES:
        raise ValueError(f"Unsupported CONUS state code: {state_code}")

    metric_source = "Unavailable"
    geometry_source = "Unavailable"
    metric = pd.DataFrame()
    geometry = {"type": "FeatureCollection", "features": []}

    if force_refresh or not _metric_path(state_code).exists():
        try:
            metric = _fetch_state_sui(state_code)
            _persist_metric(state_code, metric)
            metric_source = "USGS NWDC Live"
        except Exception as exc:
            debug_print(f"USGS water context refresh failed -> {exc}")
    if metric.empty:
        metric = _load_local_metric(state_code)
        if not metric.empty:
            metric_source = "USGS NWDC Local Cache"

    if force_refresh or not _geometry_path(state_code).exists():
        try:
            geometry = _fetch_state_huc8_geojson(state_code)
            _persist_geometry(state_code, geometry)
            geometry_source = "USGS WBD Live"
        except Exception as exc:
            debug_print(f"USGS HUC8 geometry refresh failed -> {exc}")
    if not geometry.get("features"):
        geometry = _load_local_geometry(state_code)
        if geometry.get("features"):
            geometry_source = "USGS WBD Local Cache"

    names = _geometry_names(geometry)
    water = metric.merge(names, on="HUC8", how="left") if not metric.empty else metric
    complete = bool(not water.empty and geometry.get("features"))
    source_mode = (
        "live"
        if complete and (metric_source.endswith("Live") or geometry_source.endswith("Live"))
        else "local_history"
        if complete
        else "unavailable"
    )
    return {
        "state_code": state_code,
        "state_name": STATE_NAMES[state_code],
        "source_mode": source_mode,
        "metric_source": metric_source,
        "geometry_source": geometry_source,
        "model": "USGS National Water Availability Assessment Outputs (CONUS 2025)",
        "variable": "Surface water supply and use index",
        "observation_year": OBSERVATION_YEAR,
        "aggregation": "Median HUC12 annual-water-year SUI within each HUC8",
        "metric_url": NWDC_DATA_URL,
        "geometry_url": WBD_HUC8_QUERY_URL,
        "limitations": [
            "Surface-water context only; groundwater availability and depletion are not included.",
            "The index does not establish water rights, permits, utility delivery, or facility demand.",
            "HUC8 values are display aggregates of HUC12 model outputs and are not regulatory thresholds.",
        ],
        "water": water,
        "geojson": geometry,
        "watershed_count": int(water["HUC8"].nunique()) if isinstance(water, pd.DataFrame) and not water.empty else 0,
    }
