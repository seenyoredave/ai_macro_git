from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

from config.debug_config import debug_print
from loaders.census import clean_header as _clean_header, parse_census_month as _parse_census_month
from analytics.spatial_context import infrastructure_attribution
from loaders.compute_manufacturing_loader import load_compute_manufacturing_data
from loaders.data_center_inventory_loader import load_data_center_inventory
from loaders.facility_registry_loader import (
    build_campus_registry,
    build_facility_observations,
    canonicalize_facility_observations,
    load_fractracker_facility_records,
    load_gigawatt_facility_records,
    registry_coverage,
    registry_stage_summary,
    water_evidence_coverage,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONSTRUCTION_HISTORY_PATH = PROJECT_ROOT / "data" / "infrastructure_construction_history.csv"
DATA_CENTER_LOCATIONS_PATH = PROJECT_ROOT / "data" / "data_center_locations.csv"

CENSUS_PRIVATE_SA_URL = "https://www.census.gov/construction/c30/xlsx/privsatime.xlsx"
CENSUS_PUBLIC_SA_URL = "https://www.census.gov/construction/c30/xlsx/pubsatime.xlsx"
DATA_CENTER_MAP_URL = (
    "https://raw.githubusercontent.com/IMMM-SFA/datacenter-atlas/refs/heads/main/"
    "static/im3_datacenter_centroids.geojson"
)

PRIVATE_SERIES = {
    "Data center": "Data Center Construction",
    "Nonresidential": "Private Nonresidential Construction",
    "Computer/ electronic/ electrical": "Computer, Electronic & Electrical Manufacturing Construction",
    "Manufacturing": "Private Manufacturing Construction",
    "Electric": "Electric Power Construction",
    "Communication": "Communication Construction",
}
PUBLIC_SERIES = {
    "Public Highway and street": "Public Highway and Street Construction",
    "Public Transportation": "Public Transportation Construction",
    "Public Water supply": "Public Water Supply Construction",
    "Public Sewage and waste disposal": "Public Sewage and Waste Disposal Construction",
}

def _parse_construction_workbook(content: bytes, *, sheet: str, series: dict[str, str]) -> pd.DataFrame:
    raw = pd.read_excel(BytesIO(content), sheet_name=sheet, header=3, engine="openpyxl")
    raw.columns = [_clean_header(column) for column in raw.columns]
    required = ["Date", *series]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError(f"Census construction contract changed; missing columns: {missing}")

    output = raw[required].copy().rename(columns=series)
    output["Observation Date"] = output.pop("Date").map(_parse_census_month)
    for column in series.values():
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return (
        output.dropna(subset=["Observation Date"])
        .sort_values("Observation Date", kind="stable")
        .drop_duplicates("Observation Date", keep="last")
        .reset_index(drop=True)
    )

def parse_private_infrastructure_workbook(content: bytes) -> pd.DataFrame:
    return _parse_construction_workbook(content, sheet="Private SA", series=PRIVATE_SERIES)

def parse_public_infrastructure_workbook(content: bytes) -> pd.DataFrame:
    return _parse_construction_workbook(content, sheet="Public SA", series=PUBLIC_SERIES)

def _normalize_construction_history(frame: pd.DataFrame | None) -> pd.DataFrame:
    expected = ["Observation Date", *PRIVATE_SERIES.values(), *PUBLIC_SERIES.values()]
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=expected)
    output = frame.copy()
    legacy_column = "Semiconductor Manufacturing Construction"
    current_column = "Computer, Electronic & Electrical Manufacturing Construction"
    if current_column not in output.columns and legacy_column in output.columns:
        output[current_column] = output[legacy_column]
    if "Observation Date" not in output.columns:
        return pd.DataFrame(columns=expected)
    output["Observation Date"] = pd.to_datetime(output["Observation Date"], errors="coerce", format="mixed")
    for column in expected[1:]:
        if column not in output.columns:
            output[column] = np.nan
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output = (
        output[expected]
        .dropna(subset=["Observation Date"])
        .sort_values("Observation Date", kind="stable")
        .drop_duplicates("Observation Date", keep="last")
        .reset_index(drop=True)
    )
    for column in PUBLIC_SERIES.values():
        first_valid = output.loc[pd.to_numeric(output[column], errors="coerce").gt(0), "Observation Date"]
        if not first_valid.empty:
            output.loc[output["Observation Date"] < first_valid.min(), column] = np.nan
    return output

def _persist_construction_history(frame: pd.DataFrame) -> None:
    if not repository_writes_enabled():
        return
    clean = _normalize_construction_history(frame)
    if clean.empty:
        return
    output = clean.copy()
    output["Observation Date"] = output["Observation Date"].dt.date.astype(str)
    atomic_write_csv(output, CONSTRUCTION_HISTORY_PATH)

def _load_local_construction_history() -> pd.DataFrame:
    if not CONSTRUCTION_HISTORY_PATH.exists() or CONSTRUCTION_HISTORY_PATH.stat().st_size == 0:
        return _normalize_construction_history(None)
    try:
        return _normalize_construction_history(pd.read_csv(CONSTRUCTION_HISTORY_PATH))
    except Exception as exc:
        debug_print(f"Infrastructure construction history load failed -> {exc}")
        return _normalize_construction_history(None)

def _series_summary(history: pd.DataFrame, column: str, *, denominator: str | None = None) -> dict:
    if history.empty or column not in history.columns:
        return {"value": np.nan, "date": None, "yoy_growth": np.nan, "share": np.nan, "history": pd.DataFrame(columns=["Date", "Value"])}
    clean = history[["Observation Date", column] + ([denominator] if denominator and denominator in history.columns else [])].copy()
    clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna(subset=["Observation Date", column]).sort_values("Observation Date")
    if clean.empty:
        return {"value": np.nan, "date": None, "yoy_growth": np.nan, "share": np.nan, "history": pd.DataFrame(columns=["Date", "Value"])}
    latest = clean.iloc[-1]
    latest_date = pd.Timestamp(latest["Observation Date"])
    target = latest_date - pd.DateOffset(years=1)
    prior = clean.loc[clean["Observation Date"] <= target]
    yoy = np.nan
    if not prior.empty:
        prior_row = prior.iloc[-1]
        prior_value = pd.to_numeric(prior_row[column], errors="coerce")
        day_gap = (latest_date - pd.Timestamp(prior_row["Observation Date"])).days
        if pd.notna(prior_value) and prior_value > 0 and 330 <= day_gap <= 400:
            yoy = float(latest[column]) / float(prior_value) - 1.0
    share = np.nan
    if denominator and denominator in clean.columns:
        denominator_value = pd.to_numeric(latest.get(denominator), errors="coerce")
        if pd.notna(denominator_value) and denominator_value > 0:
            share = float(latest[column]) / float(denominator_value)
    return {
        "value": float(latest[column]),
        "date": latest_date.date().isoformat(),
        "yoy_growth": yoy,
        "share": share,
        "history": clean[["Observation Date", column]].rename(columns={"Observation Date": "Date", column: "Value"}).reset_index(drop=True),
    }

def parse_data_center_geojson(payload: dict) -> pd.DataFrame:
    rows = []
    for feature in (payload or {}).get("features", []):
        geometry = (feature or {}).get("geometry") or {}
        coordinates = geometry.get("coordinates") or []
        if geometry.get("type") != "Point" or len(coordinates) < 2:
            continue
        properties = (feature or {}).get("properties") or {}
        lon = pd.to_numeric(coordinates[0], errors="coerce")
        lat = pd.to_numeric(coordinates[1], errors="coerce")
        if pd.isna(lat) or pd.isna(lon):
            continue
        rows.append({
            "State": str(properties.get("state_abb") or "").strip(),
            "County": str(properties.get("county") or "").strip(),
            "Operator": str(properties.get("operator") or "").strip(),
            "Facility": str(properties.get("name") or "").strip(),
            "Square Feet": pd.to_numeric(properties.get("sqft"), errors="coerce"),
            "Latitude": float(lat),
            "Longitude": float(lon),
            "Type": str(properties.get("type") or "point").strip(),
        })
    output = pd.DataFrame(rows)
    if output.empty:
        return pd.DataFrame(columns=["State", "County", "Operator", "Facility", "Square Feet", "Latitude", "Longitude", "Type"])
    return output.drop_duplicates(subset=["Latitude", "Longitude", "Facility"], keep="last").reset_index(drop=True)

def _persist_locations(frame: pd.DataFrame) -> None:
    if not repository_writes_enabled() or frame is None or frame.empty:
        return
    atomic_write_csv(frame, DATA_CENTER_LOCATIONS_PATH)

def _load_local_locations() -> pd.DataFrame:
    if not DATA_CENTER_LOCATIONS_PATH.exists() or DATA_CENTER_LOCATIONS_PATH.stat().st_size == 0:
        return parse_data_center_geojson({})
    try:
        frame = pd.read_csv(DATA_CENTER_LOCATIONS_PATH)
    except Exception as exc:
        debug_print(f"Data-center map history load failed -> {exc}")
        return parse_data_center_geojson({})
    required = {"State", "County", "Operator", "Facility", "Latitude", "Longitude"}
    if not required.issubset(frame.columns):
        return parse_data_center_geojson({})
    for column in ["Latitude", "Longitude", "Square Feet"]:
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "Type" not in frame.columns:
        frame["Type"] = "point"
    return frame.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)

def _load_live_construction() -> pd.DataFrame:
    private_response = requests.get(CENSUS_PRIVATE_SA_URL, timeout=30)
    private_response.raise_for_status()
    public_response = requests.get(CENSUS_PUBLIC_SA_URL, timeout=30)
    public_response.raise_for_status()
    private = parse_private_infrastructure_workbook(private_response.content)
    public = parse_public_infrastructure_workbook(public_response.content)
    return _normalize_construction_history(private.merge(public, on="Observation Date", how="outer"))

def _load_live_locations() -> pd.DataFrame:
    response = requests.get(DATA_CENTER_MAP_URL, timeout=45)
    response.raise_for_status()
    try:
        payload = response.json()
    except Exception:
        payload = json.loads(response.text)
    return parse_data_center_geojson(payload)

@st.cache_data(ttl=86400)
def load_infrastructure_data(
    force_refresh: bool = False,
    refresh_token: int = 0,
    force_fred_refresh: bool = False,
    fred_refresh_token: int = 0,
) -> dict:
    del refresh_token

    construction = _load_local_construction_history()
    construction_source = "Census Retained History"
    if force_refresh:
        try:
            refreshed = _load_live_construction()
            if not refreshed.empty:
                construction = refreshed
                _persist_construction_history(construction)
                construction_source = "Census Live Refresh"
        except Exception as exc:
            debug_print(f"Infrastructure construction refresh failed -> {exc}")

    locations = _load_local_locations()
    map_source = "Shared facility registry: FracTracker project tracker, Gigawatt Map footprint records, and curated primary evidence"
    map_refreshed = False
    if force_refresh:
        try:
            refreshed_locations = _load_live_locations()
            if not refreshed_locations.empty:
                locations = refreshed_locations
                _persist_locations(locations)
                map_source = "IM3 live footprint + FracTracker project tracker + Gigawatt Map footprint records + curated primary evidence"
                map_refreshed = True
        except Exception as exc:
            debug_print(f"Data-center map refresh failed -> {exc}")

    fractracker_records = load_fractracker_facility_records(force_refresh=force_refresh)
    gigawatt_all = load_gigawatt_facility_records(verified_only=False)
    gigawatt_verified = load_gigawatt_facility_records(verified_only=True)
    supplemental = pd.concat(
        [frame for frame in [fractracker_records, gigawatt_all] if isinstance(frame, pd.DataFrame) and not frame.empty],
        ignore_index=True,
        sort=False,
    ) if not fractracker_records.empty or not gigawatt_all.empty else pd.DataFrame()
    facility_observations = build_facility_observations(locations, supplemental_records=supplemental)
    registry = canonicalize_facility_observations(facility_observations)
    campus_registry = build_campus_registry(registry)
    coverage = registry_coverage(registry)
    stage_summary = registry_stage_summary(registry)
    water_coverage = water_evidence_coverage(registry)
    compute_manufacturing = load_compute_manufacturing_data(
        force_refresh=force_fred_refresh,
        refresh_token=fred_refresh_token,
    )
    data_center_inventory = load_data_center_inventory()

    series = {
        "Data Center Construction": _series_summary(construction, "Data Center Construction", denominator="Private Nonresidential Construction"),
        "Computer, Electronic & Electrical Manufacturing Construction": _series_summary(
            construction,
            "Computer, Electronic & Electrical Manufacturing Construction",
            denominator="Private Manufacturing Construction",
        ),
        "Electric Power Construction": _series_summary(
            construction,
            "Electric Power Construction",
            denominator="Private Nonresidential Construction",
        ),
        "Communication Construction": _series_summary(construction, "Communication Construction", denominator="Private Nonresidential Construction"),
        "Public Highway and Street Construction": _series_summary(construction, "Public Highway and Street Construction"),
        "Public Transportation Construction": _series_summary(construction, "Public Transportation Construction"),
        "Public Water Supply Construction": _series_summary(construction, "Public Water Supply Construction"),
        "Public Sewage and Waste Disposal Construction": _series_summary(construction, "Public Sewage and Waste Disposal Construction"),
    }
    for payload in series.values():
        payload["source"] = construction_source

    attribution = infrastructure_attribution(construction)

    return {
        "source_mode": "live_refresh" if "Live Refresh" in construction_source or map_refreshed else "retained",
        "construction_source": construction_source,
        "map_source": map_source,
        "construction_history": construction,
        "locations": locations,
        "facility_registry": registry,
        "campus_registry": campus_registry,
        "facility_observations": facility_observations,
        "facility_coverage": coverage,
        "facility_stage_summary": stage_summary,
        "water_evidence_coverage": water_coverage,
        "compute_manufacturing": compute_manufacturing,
        "data_center_inventory": data_center_inventory,
        "infrastructure_attribution": attribution,
        "infrastructure_source_manifest": compute_manufacturing.get("source_manifest"),
        "infrastructure_field_dictionary": compute_manufacturing.get("field_dictionary"),
        "location_count": int(len(registry)),
        "observed_location_count": int(len(locations)),
        "fractracker_facility_count": int(len(fractracker_records)),
        "retained_gigawatt_count": int(len(gigawatt_all)),
        "footprint_only_gigawatt_count": int(max(len(gigawatt_all) - len(gigawatt_verified), 0)),
        "gigawatt_verified_count": int(len(gigawatt_verified)),
        "primary_project_count": int(coverage.get("primary_project_records", 0) or 0),
        "state_count": int(registry["State"].replace("", np.nan).nunique()) if not registry.empty else 0,
        "series": series,
    }
