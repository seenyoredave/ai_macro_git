from __future__ import annotations

from hashlib import sha1, sha256
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_bundle, atomic_write_csv
from loaders.data_center_inventory_loader import STATE_ABBREVIATIONS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CURATED_SOURCE_PATH = PROJECT_ROOT / "data" / "infrastructure" / "curated" / "data_center_primary_evidence.csv"
IDENTITY_DECISIONS_PATH = PROJECT_ROOT / "data" / "infrastructure" / "curated" / "data_center_identity_decisions.csv"
GIGAWATT_PATH = PROJECT_ROOT / "data" / "infrastructure" / "raw" / "gigawattmap" / "datacenters.csv"
GIGAWATT_VERIFIED_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "gigawatt_verified_us_projects.csv"
FRACTRACKER_PATH = PROJECT_ROOT / "data" / "infrastructure" / "raw" / "fractracker" / "data_center_facilities_latest.csv"
FRACTRACKER_FEATURE_URL = (
    "https://services1.arcgis.com/AbQpv9doWn5so44u/ArcGIS/rest/services/"
    "Data_Centers_by_Congressional_District_WFL1/FeatureServer/7/query"
)
IM3_RETAINED_PATH = PROJECT_ROOT / "data" / "data_center_locations.csv"
REGISTRY_DERIVED_DIR = PROJECT_ROOT / "data" / "infrastructure" / "derived"
REGISTRY_ENTITIES_PATH = REGISTRY_DERIVED_DIR / "universal_data_center_entities.csv"
REGISTRY_OBSERVATIONS_PATH = REGISTRY_DERIVED_DIR / "universal_data_center_observations.csv"
REGISTRY_MEMBERSHIP_PATH = REGISTRY_DERIVED_DIR / "universal_data_center_membership.csv"
REGISTRY_UNRESOLVED_PATH = REGISTRY_DERIVED_DIR / "universal_data_center_unresolved.csv"
REGISTRY_METADATA_PATH = REGISTRY_DERIVED_DIR / "universal_data_center_registry.json"

REGISTRY_VERSION = "9.6.2"

OBSERVATION_COLUMNS = [
    "Observation ID", "Source Record ID", "Source", "Source Class", "Observation Level",
    "Name", "Operator", "Owner", "Developer", "Occupant", "Address", "City", "State",
    "County", "ZIP Code", "Latitude", "Longitude", "Location Precision", "Purpose", "Status",
    "Status Detail", "Status Date", "Expected Service Date", "Square Feet", "Facility Count", "Building Count",
    "Property Size Acres", "Project Cost", "Raw Capacity Text", "Published Capacity Estimate Low MW",
    "Published Capacity Estimate MW", "Published Capacity Estimate High MW", "Capacity Estimate Basis",
    "Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW",
    "Annual Electricity Consumption MWh", "Planned Onsite Generation MW", "Power Source",
    "Dedicated Power Plant", "Generator Count", "Utility", "Balancing Authority", "Watershed",
    "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
    "Cooling System", "Water Source", "Water Permit or Utility Record", "Reclaimed Water Use",
    "Water Evidence Scope", "Water Evidence Grade", "Water Evidence Type", "Water Evidence Source",
    "Water Evidence URL", "Water Evidence Date", "Community Response", "Evidence Grade",
    "Evidence Type", "Inventory Confidence", "Source URL", "Upstream Source URL", "Source Date",
    "Source Updated Date", "Notes",
]

NUMERIC_COLUMNS = {
    "Latitude", "Longitude", "Square Feet", "Facility Count", "Building Count", "Property Size Acres",
    "Published Capacity Estimate Low MW", "Published Capacity Estimate MW",
    "Published Capacity Estimate High MW", "Planned Data Center Capacity MW",
    "Contracted Utility Capacity MW", "Energized Capacity MW", "Annual Electricity Consumption MWh",
    "Planned Onsite Generation MW", "Generator Count", "Water Withdrawal Gallons/Year",
    "Water Consumption Gallons/Year", "Site WUE L/kWh",
}
DATE_COLUMNS = {"Status Date", "Expected Service Date", "Water Evidence Date", "Source Date", "Source Updated Date"}

CAMPUS_COLUMNS = [
    "Campus ID", "Campus Name", "Campus Label", "Identity Basis", "Identity Confidence", "Anchor Observation ID", "Resolution Method", "Operator", "Owner", "Developer", "Occupant", "Address", "City",
    "State", "County", "ZIP Code", "Latitude", "Longitude", "Location Precision", "Purpose", "Status",
    "Status Detail", "Status Date", "Expected Service Date", "Square Feet", "Facility Count", "Building Count",
    "Property Size Acres", "Project Cost", "Published Capacity Estimate Low MW",
    "Published Capacity Estimate MW", "Published Capacity Estimate High MW", "Capacity Estimate Basis",
    "Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW",
    "Annual Electricity Consumption MWh", "Planned Onsite Generation MW", "Power Source",
    "Dedicated Power Plant", "Generator Count", "Utility", "Balancing Authority", "Watershed",
    "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
    "Cooling System", "Water Source", "Water Permit or Utility Record", "Reclaimed Water Use",
    "Water Evidence Scope", "Water Evidence Grade", "Water Evidence Type", "Water Evidence Source",
    "Water Evidence URL", "Water Evidence Date", "Community Response", "Evidence Grade", "Evidence Type",
    "Inventory Confidence", "Source", "Source URL", "Upstream Source URL", "Source Date",
    "Source Updated Date", "Source Record IDs", "Member Observation IDs", "Member Entity IDs",
    "Registry Version",
]

ENTITY_COLUMNS = [
    "Entity ID", "Entity Level", "Parent Entity ID", "Entity Name", "Entity Label",
    *[column for column in CAMPUS_COLUMNS if column not in {"Campus Name", "Campus Label"}],
]
MEMBERSHIP_COLUMNS = [
    "Member Entity ID", "Parent Entity ID", "Campus ID", "Relationship", "Source Record ID",
    "Observation ID", "Relationship Basis", "Registry Version",
]

US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA",
    "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT",
    "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}
UNKNOWN_TEXT = {"", "n/a", "na", "none", "unknown", "unavailable", "not available", "not disclosed", "undisclosed"}
GENERIC_NAMES = {
    "", "data center", "datacenter", "data centre", "facility", "campus", "project",
}

COUNTY_SUFFIXES = (
    " county", " parish", " borough", " census area", " municipality", " city and borough",
)



def normalize_us_state(value) -> str:
    raw = str(value or "").strip()
    if raw in STATE_ABBREVIATIONS:
        return STATE_ABBREVIATIONS[raw]
    title = raw.title()
    if title in STATE_ABBREVIATIONS:
        return STATE_ABBREVIATIONS[title]
    text = raw.upper()
    if text.startswith("US-") and len(text) == 5:
        text = text[-2:]
    return text if text in US_STATE_CODES else ""


def _clean_token(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _identity_token(value) -> str:
    tokens = [
        token for token in _clean_token(value).split()
        if token not in {"data", "center", "centre", "datacenter", "campus", "facility", "project", "llc", "inc", "corp", "corporation", "company", "co", "the"}
    ]
    return " ".join(tokens)


def _stable_id(prefix: str, *values) -> str:
    key = "|".join(str(value or "") for value in values)
    return f"{prefix}:{sha1(key.encode('utf-8')).hexdigest()[:16]}"


def _known_text(value) -> bool:
    text = str(value or "").strip().casefold()
    return text not in UNKNOWN_TEXT and not any(token in text for token in ("not disclosed", "unknown", "unavailable"))


def _valid_url(value) -> bool:
    return str(value or "").strip().startswith(("https://", "http://"))


def _normalize_observations(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=OBSERVATION_COLUMNS)
    output = frame.copy()
    for column in OBSERVATION_COLUMNS:
        if column not in output.columns:
            output[column] = np.nan if column in NUMERIC_COLUMNS else pd.NaT if column in DATE_COLUMNS else ""
    for column in NUMERIC_COLUMNS:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    for column in DATE_COLUMNS:
        output[column] = pd.to_datetime(output[column], errors="coerce", format="mixed")
    for column in set(OBSERVATION_COLUMNS) - NUMERIC_COLUMNS - DATE_COLUMNS:
        output[column] = output[column].fillna("").astype(str).str.strip()
    output["State"] = output["State"].map(normalize_us_state)
    output["Observation Level"] = output["Observation Level"].str.casefold().replace({"project": "campus", "footprint": "building", "point": "site_point"})
    output.loc[~output["Observation Level"].isin({"campus", "facility", "building", "site_point"}), "Observation Level"] = "site_point"
    missing = output["Observation ID"].eq("")
    output.loc[missing, "Observation ID"] = [
        _stable_id("observation", source, source_id, name, lat, lon)
        for source, source_id, name, lat, lon in zip(
            output.loc[missing, "Source"], output.loc[missing, "Source Record ID"], output.loc[missing, "Name"],
            output.loc[missing, "Latitude"], output.loc[missing, "Longitude"],
        )
    ]
    return output[OBSERVATION_COLUMNS].drop_duplicates("Observation ID", keep="last").reset_index(drop=True)


def normalize_im3_observations(locations: pd.DataFrame | None) -> pd.DataFrame:
    if locations is None or not isinstance(locations, pd.DataFrame) or locations.empty:
        return _normalize_observations(None)
    if not {"Latitude", "Longitude"}.issubset(locations.columns):
        return _normalize_observations(None)
    out = pd.DataFrame(index=locations.index)
    out["Name"] = locations.get("Facility", locations.get("Name", ""))
    out["Operator"] = locations.get("Operator", "")
    out["State"] = locations.get("State", "")
    out["County"] = locations.get("County", "")
    out["Latitude"] = locations.get("Latitude")
    out["Longitude"] = locations.get("Longitude")
    out["Square Feet"] = locations.get("Square Feet", np.nan)
    raw_level = locations.get("Type", pd.Series("point", index=locations.index)).fillna("point").astype(str).str.casefold()
    out["Observation Level"] = raw_level.map({"campus": "campus", "building": "building", "point": "site_point"}).fillna("site_point")
    out["Source Class"] = np.where(out["Observation Level"].eq("campus"), "Campus geometry", "Observed footprint")
    out["Location Precision"] = "Mapped centroid"
    out["Status"] = "Observed footprint"
    out["Evidence Grade"] = np.where(out["Observation Level"].eq("campus"), "B", "C")
    out["Evidence Type"] = "Open geospatial inventory"
    out["Inventory Confidence"] = out["Observation Level"].map({"campus": "mapped campus", "building": "mapped building", "site_point": "mapped point"})
    out["Source"] = "IM3 Open Source Data Center Atlas / OpenStreetMap"
    out["Source URL"] = "https://doi.org/10.57931/3017294"
    out["Upstream Source URL"] = "https://www.openstreetmap.org"
    out["Notes"] = "IM3 geospatial observation. Identity grain is preserved by Observation Level."
    out["Source Record ID"] = [
        _stable_id("im3-source", name, operator, lat, lon, level)
        for name, operator, lat, lon, level in zip(out["Name"], out["Operator"], out["Latitude"], out["Longitude"], out["Observation Level"])
    ]
    out["Observation ID"] = "im3:" + out["Source Record ID"].str.split(":").str[-1]
    return _normalize_observations(out)


def load_curated_data_center_observations() -> pd.DataFrame:
    if not CURATED_SOURCE_PATH.exists() or not CURATED_SOURCE_PATH.stat().st_size:
        return _normalize_observations(None)
    raw = pd.read_csv(CURATED_SOURCE_PATH)
    if raw.empty:
        return _normalize_observations(None)
    out = pd.DataFrame(index=raw.index)
    mapping = {
        "Name": "Facility", "Operator": "Operator", "Owner": "Owner", "Developer": "Developer", "Occupant": "Occupant",
        "Address": "Address", "City": "City", "State": "State", "County": "County", "ZIP Code": "ZIP Code",
        "Latitude": "Latitude", "Longitude": "Longitude", "Location Precision": "Location Precision", "Purpose": "Purpose",
        "Status": "Status", "Status Detail": "Status Detail", "Status Date": "Status Date", "Expected Service Date": "Expected Service Date",
        "Square Feet": "Square Feet", "Building Count": "Building Count", "Property Size Acres": "Property Size Acres", "Project Cost": "Project Cost",
        "Raw Capacity Text": "Raw Capacity Text", "Published Capacity Estimate Low MW": "Published Capacity Estimate Low MW",
        "Published Capacity Estimate MW": "Published Capacity Estimate MW", "Published Capacity Estimate High MW": "Published Capacity Estimate High MW",
        "Capacity Estimate Basis": "Capacity Estimate Basis", "Planned Data Center Capacity MW": "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW": "Contracted Utility Capacity MW", "Energized Capacity MW": "Energized Capacity MW",
        "Annual Electricity Consumption MWh": "Annual Electricity Consumption MWh", "Planned Onsite Generation MW": "Planned Onsite Generation MW",
        "Power Source": "Power Source", "Dedicated Power Plant": "Dedicated Power Plant", "Generator Count": "Generator Count", "Utility": "Utility",
        "Balancing Authority": "Balancing Authority", "Watershed": "Watershed", "Water Withdrawal Gallons/Year": "Water Withdrawal Gallons/Year",
        "Water Consumption Gallons/Year": "Water Consumption Gallons/Year", "Site WUE L/kWh": "Site WUE L/kWh", "Cooling System": "Cooling System",
        "Water Source": "Water Source", "Water Permit or Utility Record": "Water Permit or Utility Record", "Reclaimed Water Use": "Reclaimed Water Use",
        "Water Evidence Scope": "Water Evidence Scope", "Water Evidence Grade": "Water Evidence Grade", "Water Evidence Type": "Water Evidence Type",
        "Water Evidence Source": "Water Evidence Source", "Water Evidence URL": "Water Evidence URL", "Water Evidence Date": "Water Evidence Date",
        "Community Response": "Community Response", "Evidence Grade": "Evidence Grade", "Evidence Type": "Evidence Type", "Inventory Confidence": "Inventory Confidence",
        "Source URL": "Source URL", "Upstream Source URL": "Upstream Source URL", "Source Date": "Source Date", "Source Updated Date": "Source Updated Date", "Notes": "Notes",
    }
    for target, source in mapping.items():
        out[target] = raw[source] if source in raw.columns else np.nan if target in NUMERIC_COLUMNS else ""
    out["Source"] = raw.get("Source", "Curated primary evidence")
    out["Source Class"] = "Primary project evidence"
    raw_level = raw.get("Record Type", pd.Series("project", index=raw.index)).fillna("project").astype(str).str.casefold()
    out["Observation Level"] = raw_level.map({"building": "building", "facility": "facility", "campus": "campus", "project": "campus", "point": "site_point", "footprint": "building"}).fillna("campus")
    source_ids = raw.get("Source Record ID", raw.get("Facility ID", pd.Series("", index=raw.index))).fillna("").astype(str)
    out["Source Record ID"] = source_ids
    out["Observation ID"] = [
        _stable_id("curated", source_id, name, lat, lon)
        for source_id, name, lat, lon in zip(source_ids, out["Name"], out["Latitude"], out["Longitude"])
    ]
    return _normalize_observations(out)


def load_gigawatt_data_center_observations(*, verified_only: bool = False) -> pd.DataFrame:
    source_path = GIGAWATT_VERIFIED_PATH if verified_only and GIGAWATT_VERIFIED_PATH.exists() else GIGAWATT_PATH
    if not source_path.exists() or not source_path.stat().st_size:
        return _normalize_observations(None)
    raw = pd.read_csv(source_path)
    if raw.empty:
        return _normalize_observations(None)
    region = raw.get("region", pd.Series("", index=raw.index)).fillna("").astype(str)
    raw["State"] = region.map(normalize_us_state)
    country = raw.get("country", pd.Series("", index=raw.index)).fillna("").astype(str).str.upper()
    confidence = raw.get("confidence", pd.Series("", index=raw.index)).fillna("").astype(str).str.casefold()
    source_ids = raw.get("id", pd.Series("", index=raw.index)).fillna("").astype(str)
    osm_like = source_ids.str.startswith(("osm-way-", "osm-node-", "osm-relation-")) | confidence.eq("osm_only")
    # Gigawatt's OSM-derived rows sometimes use country=XX and omit region even
    # when the geometry is in the United States. Keep those source observations
    # long enough to reconcile them against the retained IM3 U.S. geometry; the
    # registry build drops any row whose U.S. jurisdiction cannot be established.
    raw = raw.loc[country.eq("US") | raw["State"].ne("") | (country.eq("XX") & osm_like)].copy()
    confidence = raw.get("confidence", pd.Series("", index=raw.index)).fillna("").astype(str).str.casefold()
    source_ids = raw.get("id", pd.Series("", index=raw.index)).fillna("").astype(str)
    osm_like = source_ids.str.startswith(("osm-way-", "osm-node-", "osm-relation-")) | confidence.eq("osm_only")
    if verified_only:
        raw = raw.loc[confidence.eq("verified")].copy()
        confidence = raw.get("confidence", pd.Series("", index=raw.index)).fillna("").astype(str).str.casefold()
        source_ids = raw.get("id", pd.Series("", index=raw.index)).fillna("").astype(str)
        osm_like = source_ids.str.startswith(("osm-way-", "osm-node-", "osm-relation-")) | confidence.eq("osm_only")
    if raw.empty:
        return _normalize_observations(None)
    verified = confidence.eq("verified")
    out = pd.DataFrame(index=raw.index)
    out["Observation ID"] = "gigawatt:" + source_ids
    out["Source Record ID"] = source_ids
    out["Observation Level"] = np.where(verified, "campus", np.where(osm_like, "building", "site_point"))
    out["Source Class"] = np.where(verified, "Secondary project inventory", "Observed footprint")
    out["Name"] = raw.get("name", "")
    out["Operator"] = raw.get("operator_id", "")
    out["Developer"] = raw.get("operator_id", "")
    out["Occupant"] = raw.get("tenant", "")
    out["State"] = raw["State"]
    out["Latitude"] = pd.to_numeric(raw.get("lat"), errors="coerce")
    out["Longitude"] = pd.to_numeric(raw.get("lon"), errors="coerce")
    out["Location Precision"] = "Published point"
    status_map = {"operational": "Operational", "construction": "Under construction", "announced": "Announced", "blocked": "Blocked"}
    raw_status = raw.get("status", pd.Series("", index=raw.index)).fillna("").astype(str).str.casefold()
    out["Status"] = np.where(verified, raw_status.map(status_map).fillna("Status unknown"), "Observed footprint")
    out["Status Date"] = pd.to_datetime(raw.get("announced_date"), errors="coerce", format="mixed").where(verified)
    out["Expected Service Date"] = pd.to_datetime(raw.get("rfs_date"), errors="coerce", format="mixed").where(verified)
    for target, source in [("Published Capacity Estimate Low MW", "est_mw_low"), ("Published Capacity Estimate MW", "est_mw_mid"), ("Published Capacity Estimate High MW", "est_mw_high")]:
        values = pd.to_numeric(raw.get(source), errors="coerce")
        out[target] = values.where(verified | osm_like)
    out["Capacity Estimate Basis"] = raw.get("mw_source", pd.Series("", index=raw.index)).fillna("").astype(str)
    out["Evidence Grade"] = np.where(verified, "C", "D")
    out["Evidence Type"] = np.where(verified, "Third-party project inventory", "Open geospatial inventory")
    out["Inventory Confidence"] = confidence
    out["Source"] = "Gigawatt Map retained export"
    out["Source URL"] = "https://gigawattmap.com/data"
    out["Upstream Source URL"] = raw.get("source_url", pd.Series("", index=raw.index)).fillna("")
    out["Source Date"] = pd.to_datetime(raw.get("announced_date"), errors="coerce", format="mixed")
    out["Notes"] = raw.get("notes", pd.Series("", index=raw.index)).fillna("").astype(str)
    return _normalize_observations(out.dropna(subset=["Latitude", "Longitude"]))


def _parse_capacity_text(value) -> tuple[float, float, float, str]:
    text = str(value or "").strip()
    if not text or text.casefold() in UNKNOWN_TEXT:
        return np.nan, np.nan, np.nan, ""
    lowered = text.casefold().replace(",", "")
    numbers = [float(item) for item in re.findall(r"(?<![a-z])([0-9]+(?:\.[0-9]+)?)", lowered)]
    if not numbers:
        return np.nan, np.nan, np.nan, text
    multiplier = 1000.0 if re.search(r"\bgw\b|gigawatt", lowered) else 1.0
    if len(numbers) == 1:
        value_mw = numbers[0] * multiplier
        return value_mw, value_mw, value_mw, text
    if len(numbers) == 2 and bool(re.search(r"\bto\b|[-–—]", lowered)):
        low, high = sorted(number * multiplier for number in numbers)
        return low, (low + high) / 2.0, high, text
    return np.nan, np.nan, np.nan, text


def _parse_mixed_dates(values: pd.Series) -> pd.Series:
    series = values.copy()
    numeric = pd.to_numeric(series, errors="coerce")
    parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    epoch_mask = numeric.notna() & numeric.abs().gt(10_000_000_000)
    if epoch_mask.any():
        parsed.loc[epoch_mask] = pd.to_datetime(numeric.loc[epoch_mask], unit="ms", errors="coerce")
    return parsed


def _fractracker_raw_frame(*, force_refresh: bool = False, timeout: int = 30) -> pd.DataFrame:
    if not force_refresh and FRACTRACKER_PATH.exists() and FRACTRACKER_PATH.stat().st_size:
        try:
            return pd.read_csv(FRACTRACKER_PATH)
        except Exception:
            pass
    response = requests.get(
        FRACTRACKER_FEATURE_URL,
        params={"where": "1=1", "outFields": "*", "returnGeometry": "true", "outSR": "4326", "f": "json"},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(f"FracTracker feature service error: {payload['error']}")
    rows = []
    for feature in payload.get("features", []):
        attributes = dict(feature.get("attributes") or {})
        geometry = feature.get("geometry") or {}
        attributes["_geometry_x"] = geometry.get("x")
        attributes["_geometry_y"] = geometry.get("y")
        rows.append(attributes)
    raw = pd.DataFrame(rows)
    if not raw.empty and repository_writes_enabled():
        atomic_write_csv(raw, FRACTRACKER_PATH)
    return raw


def load_fractracker_data_center_observations(*, force_refresh: bool = False, allow_live: bool = False, return_report: bool = False):
    live_refresh = bool(force_refresh and allow_live)
    source_mode = "retained"
    error = None

    def finish(frame: pd.DataFrame):
        report = {"source_mode": source_mode, "requested": bool(force_refresh), "authorized": bool(allow_live), "executed": live_refresh, "returned_rows": int(len(frame)), "error": error}
        return (frame, report) if return_report else frame

    try:
        raw = _fractracker_raw_frame(force_refresh=live_refresh)
        if live_refresh:
            source_mode = "live_refresh"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        source_mode = "retained_fallback"
        if not FRACTRACKER_PATH.exists() or not FRACTRACKER_PATH.stat().st_size:
            return finish(_normalize_observations(None))
        try:
            raw = pd.read_csv(FRACTRACKER_PATH)
        except Exception as fallback_exc:
            error = f"{error}; fallback {type(fallback_exc).__name__}: {fallback_exc}"
            return finish(_normalize_observations(None))
    if raw.empty:
        return finish(_normalize_observations(None))

    aliases = {
        "OBJECTID": ("OBJECTID", "objectid", "fid"), "name": ("name", "facility_name"), "operator": ("operator", "operator_name"),
        "tenant": ("tenant",), "address": ("address",), "city": ("city",), "state": ("state",), "county": ("county",), "zip": ("zip", "zip_code"),
        "lat": ("lat", "latitude"), "long": ("long", "lon", "longitude"), "location_confidence": ("location_confidence",), "purpose": ("purpose",),
        "status": ("status",), "status_detail": ("status_detail", "resistance_status"), "expected_date_online": ("expected_date_online",),
        "facility_size_sq_ft": ("facility_size_sq_ft", "facility_size_sqft"), "number_of_buildings": ("number_of_buildings",),
        "property_size_acres": ("property_size_acres",), "project_cost": ("project_cost",), "mw": ("mw",), "power_source": ("power_source",),
        "dedicated_power_plant": ("dedicated_power_plant",), "number_of_generators": ("number_of_generators",), "cooling_source": ("cooling_source",),
        "cooling_type": ("cooling_type",), "community_push_back": ("community_push_back", "community_pushback"), "other_info": ("other_info",),
        "information_source": ("information_source",), "date_created": ("date_created",), "date_updated": ("date_updated",),
    }

    def column(name: str, default="") -> pd.Series:
        for candidate in aliases.get(name, (name,)):
            if candidate in raw.columns:
                return raw[candidate]
        return pd.Series(default, index=raw.index)

    status_map = {"approved/permitted/under construction": "Approved / permitted / under construction", "cancelled": "Cancelled", "canceled": "Cancelled", "expanding": "Expanding", "operating": "Operational", "operational": "Operational", "proposed": "Proposed", "suspended": "Suspended", "unknown": "Status unknown"}
    out = pd.DataFrame(index=raw.index)
    fallback_ids = raw.apply(lambda row: _stable_id("fractracker-source", row.get("facility_name", row.get("name", "")), row.get("address", ""), row.get("lat", row.get("_geometry_y", "")), row.get("long", row.get("_geometry_x", ""))), axis=1)
    object_values = column("OBJECTID", np.nan)
    object_ids = object_values.where(object_values.notna(), fallback_ids).astype(str)
    out["Observation ID"] = "fractracker:" + object_ids.str.replace("fractracker-source:", "", regex=False)
    out["Source Record ID"] = object_ids
    out["Observation Level"] = "campus"
    out["Source Class"] = "Open project tracker"
    out["Name"] = column("name")
    out["Operator"] = column("operator")
    out["Developer"] = column("operator")
    out["Occupant"] = column("tenant")
    out["Address"] = column("address")
    out["City"] = column("city")
    out["State"] = column("state")
    out["County"] = column("county")
    out["ZIP Code"] = column("zip")
    out["Latitude"] = pd.to_numeric(column("lat", np.nan).combine_first(column("_geometry_y", np.nan)), errors="coerce")
    out["Longitude"] = pd.to_numeric(column("long", np.nan).combine_first(column("_geometry_x", np.nan)), errors="coerce")
    out["Location Precision"] = column("location_confidence")
    out["Purpose"] = column("purpose")
    raw_status = column("status").fillna("").astype(str).str.casefold().str.strip()
    out["Status"] = raw_status.map(status_map).fillna("Status unknown")
    out["Status Detail"] = column("status_detail").fillna("").astype(str)
    out.loc[out["Status Detail"].eq(""), "Status Detail"] = column("status").fillna("").astype(str)
    out["Expected Service Date"] = _parse_mixed_dates(column("expected_date_online"))
    out["Square Feet"] = pd.to_numeric(column("facility_size_sq_ft", np.nan), errors="coerce")
    out["Building Count"] = pd.to_numeric(column("number_of_buildings", np.nan), errors="coerce")
    out["Property Size Acres"] = pd.to_numeric(column("property_size_acres", np.nan), errors="coerce")
    out["Project Cost"] = column("project_cost")
    out["Raw Capacity Text"] = column("mw")
    parsed = out["Raw Capacity Text"].map(_parse_capacity_text)
    out["Published Capacity Estimate Low MW"] = parsed.map(lambda value: value[0])
    out["Published Capacity Estimate MW"] = parsed.map(lambda value: value[1])
    out["Published Capacity Estimate High MW"] = parsed.map(lambda value: value[2])
    out["Capacity Estimate Basis"] = parsed.map(lambda value: value[3])
    out["Power Source"] = column("power_source")
    out["Dedicated Power Plant"] = column("dedicated_power_plant")
    out["Generator Count"] = pd.to_numeric(column("number_of_generators", np.nan), errors="coerce")
    cooling = pd.DataFrame({"source": column("cooling_source"), "type": column("cooling_type")}).fillna("").astype(str)
    out["Cooling System"] = cooling.apply(lambda row: " / ".join(dict.fromkeys(item.strip() for item in row if item.strip())), axis=1)
    out["Water Source"] = column("cooling_source")
    out["Community Response"] = column("community_push_back")
    source_columns = [name for name in raw.columns if re.fullmatch(r"info_source_[1-8]", str(name))]
    source_lists = [list(dict.fromkeys(value.strip() for value in row if _valid_url(value))) for _, row in raw[source_columns].fillna("").astype(str).iterrows()] if source_columns else [[] for _ in range(len(raw))]
    out["Source URL"] = [items[0] if items else "https://www.fractracker.org/data-centers/" for items in source_lists]
    out["Upstream Source URL"] = [" | ".join(items) for items in source_lists]
    source_counts = pd.Series([len(items) for items in source_lists], index=raw.index)
    out["Evidence Grade"] = np.where(source_counts.ge(2) & ~out["Status"].eq("Status unknown"), "B", "C")
    out["Evidence Type"] = "Cross-referenced open project tracker"
    out["Inventory Confidence"] = column("location_confidence")
    out["Source"] = "FracTracker Open U.S. Data Centers Tracker"
    out["Source Date"] = _parse_mixed_dates(column("date_created", np.nan))
    out["Source Updated Date"] = _parse_mixed_dates(column("date_updated", np.nan))
    other = column("other_info").fillna("").astype(str)
    information = column("information_source").fillna("").astype(str)
    out["Notes"] = [" ".join(item for item in [a.strip(), b.strip()] if item) for a, b in zip(other, information)]
    return finish(_normalize_observations(out.dropna(subset=["Latitude", "Longitude"])))


def load_data_center_identity_decisions() -> pd.DataFrame:
    columns = ["Source Record ID", "Decision Group", "Decision", "Evidence URL", "Decision Note"]
    if not IDENTITY_DECISIONS_PATH.exists() or not IDENTITY_DECISIONS_PATH.stat().st_size:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(IDENTITY_DECISIONS_PATH, dtype=str).fillna("")
    required = {"Source Record ID", "Decision Group", "Decision"}
    if not required.issubset(frame.columns):
        raise ValueError("Data-center identity decision ledger schema changed")
    return frame



# ---------------------------------------------------------------------------
# Universal Data Center Registry identity engine
# ---------------------------------------------------------------------------
# Identity is resolved once, here.  Domain modules consume Campus IDs and never
# merge, split, deduplicate, or manufacture data-center entities.


def _decision_index() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    decisions = load_data_center_identity_decisions()
    merge: dict[str, set[str]] = {}
    separate: dict[str, set[str]] = {}
    if decisions.empty:
        return merge, separate
    for _, row in decisions.iterrows():
        source_id = str(row.get("Source Record ID") or "").strip()
        group = str(row.get("Decision Group") or "").strip()
        decision = str(row.get("Decision") or "").strip().casefold()
        if not source_id or not group:
            continue
        target = merge if decision == "merge" else separate if decision == "separate" else None
        if target is not None:
            target.setdefault(source_id, set()).add(group)
    return merge, separate


def _decision_groups(source_id, index: dict[str, set[str]]) -> set[str]:
    groups: set[str] = set()
    for item in str(source_id or "").split("|"):
        groups.update(index.get(item.strip(), ()))
    return groups


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    try:
        values = tuple(float(value) for value in (lat1, lon1, lat2, lon2))
    except (TypeError, ValueError):
        return np.inf
    if not all(math.isfinite(value) for value in values):
        return np.inf
    a1, o1, a2, o2 = map(math.radians, values)
    dlat = a2 - a1
    dlon = o2 - o1
    h = math.sin(dlat / 2.0) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(dlon / 2.0) ** 2
    return 6371.0088 * 2.0 * math.asin(math.sqrt(h))


def _county_token(value) -> str:
    text = _clean_token(value)
    for suffix in COUNTY_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
            break
    return text


def _normalized_address(value) -> str:
    text = _clean_token(value)
    if not text or text in UNKNOWN_TEXT:
        return ""
    padded = f" {text} "
    replacements = {
        " street ": " st ", " road ": " rd ", " avenue ": " ave ", " boulevard ": " blvd ",
        " drive ": " dr ", " highway ": " hwy ", " lane ": " ln ", " court ": " ct ",
        " parkway ": " pkwy ", " route ": " rte ",
    }
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return " ".join(padded.split())


def _operator_identity(row) -> str:
    for column in ("Operator", "Owner", "Developer", "Occupant"):
        token = _identity_token(row.get(column))
        if token:
            return token
    return ""


def _name_identity(value) -> str:
    return _identity_token(value)


def _token_similarity(left, right) -> float:
    a = set(_identity_token(left).split())
    b = set(_identity_token(right).split())
    return len(a & b) / len(a | b) if a and b else 0.0


def _operator_match(left, right) -> bool:
    """Compare operator identities without encoding site-specific exceptions.

    Corporate source feeds commonly alternate between a parent brand and a
    longer operating name (for example a one-token brand versus that brand plus
    service descriptors).  Exact token containment therefore counts as the same
    operator when the shorter identity is a substantive brand token.
    """
    left_token = _identity_token(left)
    right_token = _identity_token(right)
    if not left_token or not right_token:
        return False
    if left_token == right_token:
        return True
    left_parts = set(left_token.split())
    right_parts = set(right_token.split())
    smaller, larger = (left_parts, right_parts) if len(left_parts) <= len(right_parts) else (right_parts, left_parts)
    if smaller.issubset(larger) and len(smaller) == 1 and len(next(iter(smaller))) >= 4:
        return True
    return _token_similarity(left_token, right_token) >= 0.82


def _is_county_name(name, county) -> bool:
    name_token = _county_token(name)
    county_token = _county_token(county)
    return bool(name_token and county_token and name_token == county_token)


def _is_generic_name(name, *, operator="", county="") -> bool:
    token = _clean_token(name)
    if token in GENERIC_NAMES:
        return True
    if _is_county_name(name, county):
        return True
    operator_token = _clean_token(operator)
    return bool(token and operator_token and token == operator_token)


def _meaningful_name(row) -> str:
    name = str(row.get("Name") or "").strip()
    if not _known_text(name):
        return ""
    if _is_generic_name(name, operator=row.get("Operator"), county=row.get("County")):
        return ""
    return name


def _source_priority_value(row) -> int:
    source_class = str(row.get("Source Class") or "")
    level = str(row.get("Observation Level") or "")
    grade = str(row.get("Evidence Grade") or "").upper()
    source_rank = {
        "Primary project evidence": 700,
        "Campus geometry": 650,
        "Open project tracker": 600,
        "Secondary project inventory": 500,
        "Observed footprint": 200,
    }.get(source_class, 100)
    level_rank = {"campus": 80, "facility": 60, "site_point": 40, "building": 20}.get(level, 0)
    grade_rank = {"A": 8, "B": 6, "C": 4, "D": 2}.get(grade, 0)
    return source_rank + level_rank + grade_rank


def _same_jurisdiction(left, right) -> bool:
    if normalize_us_state(left.get("State")) != normalize_us_state(right.get("State")):
        return False
    left_county = _county_token(left.get("County"))
    right_county = _county_token(right.get("County"))
    return not (left_county and right_county and left_county != right_county)


def _same_jurisdiction_values(left: dict, right: dict) -> bool:
    if left["state"] != right["state"]:
        return False
    return not (left["county"] and right["county"] and left["county"] != right["county"])


def _prepare_identity_records(observations: pd.DataFrame, merge_index, separate_index) -> list[dict]:
    records: list[dict] = []
    for index, row in observations.iterrows():
        operator = _operator_identity(row)
        name = str(row.get("Name") or "").strip()
        meaningful = _meaningful_name(row)
        lat = pd.to_numeric(row.get("Latitude"), errors="coerce")
        lon = pd.to_numeric(row.get("Longitude"), errors="coerce")
        source_id = str(row.get("Source Record ID") or "").strip()
        records.append({
            "index": int(index),
            "state": normalize_us_state(row.get("State")),
            "county": _county_token(row.get("County")),
            "lat": float(lat) if pd.notna(lat) else math.nan,
            "lon": float(lon) if pd.notna(lon) else math.nan,
            "source_id": source_id,
            "source": str(row.get("Source") or ""),
            "source_class": str(row.get("Source Class") or ""),
            "level": str(row.get("Observation Level") or ""),
            "name": name,
            "name_id": _name_identity(name),
            "meaningful_name": meaningful,
            "operator": operator,
            "address": _normalized_address(row.get("Address")),
            "priority": _source_priority_value(row),
            "merge_groups": frozenset(_decision_groups(source_id, merge_index)),
            "separate_groups": frozenset(_decision_groups(source_id, separate_index)),
        })
    return records


def _reviewed_separate_prepared(left: dict, right: dict) -> bool:
    return bool(left["separate_groups"] & right["separate_groups"])


def _reviewed_merge_prepared(left: dict, right: dict) -> bool:
    return bool(left["merge_groups"] & right["merge_groups"])


def _distance_prepared(left: dict, right: dict) -> float:
    return _haversine_km(left["lat"], left["lon"], right["lat"], right["lon"])


def _anchor_strength(row) -> tuple[bool, str, str]:
    """Return whether a source observation can establish campus identity."""
    level = str(row.get("Observation Level") or "")
    source_class = str(row.get("Source Class") or "")
    if level != "campus":
        return False, "", ""
    if source_class == "Campus geometry":
        return True, "source campus geometry", "high"
    if source_class == "Primary project evidence":
        return True, "curated project identity", "high"
    name = _meaningful_name(row)
    operator = _operator_identity(row)
    address = _normalized_address(row.get("Address"))
    if name and (operator or address):
        return True, "named project identity", "high"
    if name:
        return True, "named project identity", "medium"
    if operator and address:
        return True, "operator + address", "medium"
    if address:
        return True, "addressed project identity", "medium"
    return False, "insufficient campus identity", ""


def _anchor_pair_match(left: dict, right: dict) -> tuple[bool, str]:
    if _reviewed_separate_prepared(left, right):
        return False, ""
    if _reviewed_merge_prepared(left, right):
        return True, "reviewed identity decision"
    if not _same_jurisdiction_values(left, right):
        return False, ""
    distance = _distance_prepared(left, right)
    if not math.isfinite(distance):
        return False, ""
    if left["address"] and right["address"]:
        if left["address"] == right["address"] and distance <= 2.0:
            return True, "same published address"
        left_number = re.match(r"^\d+", left["address"])
        right_number = re.match(r"^\d+", right["address"])
        if left_number and right_number and left_number.group() != right_number.group():
            return False, ""
    operator_match = _operator_match(left["operator"], right["operator"])
    name_similarity = _token_similarity(left["meaningful_name"], right["meaningful_name"]) if left["meaningful_name"] and right["meaningful_name"] else 0.0
    if distance <= 0.075 and (operator_match or name_similarity >= 0.65 or not left["operator"] or not right["operator"]):
        return True, "coincident cross-source campus observation"
    if operator_match and left["meaningful_name"] and right["meaningful_name"] and name_similarity >= 0.72 and distance <= 1.5:
        return True, "same operator + campus name"
    if operator_match and distance <= 0.30 and (not left["meaningful_name"] or not right["meaningful_name"] or name_similarity >= 0.35):
        return True, "same operator + local campus observation"
    return False, ""


_SPATIAL_CELL_DEGREES = 0.025


def _spatial_cell(record: dict) -> tuple[str, int, int] | None:
    if not record["state"] or not math.isfinite(record["lat"]) or not math.isfinite(record["lon"]):
        return None
    return (
        record["state"],
        math.floor(record["lat"] / _SPATIAL_CELL_DEGREES),
        math.floor(record["lon"] / _SPATIAL_CELL_DEGREES),
    )


def _neighbor_cells(record: dict, radius_km: float):
    cell = _spatial_cell(record)
    if cell is None:
        return ()
    state, y, x = cell
    lat_km = 111.2 * _SPATIAL_CELL_DEGREES
    lon_km = max(0.35, 111.2 * math.cos(math.radians(record["lat"])) * _SPATIAL_CELL_DEGREES)
    sy = max(1, math.ceil(radius_km / lat_km))
    sx = max(1, math.ceil(radius_km / lon_km))
    return (
        (state, y + dy, x + dx)
        for dy in range(-sy, sy + 1)
        for dx in range(-sx, sx + 1)
    )


def _register_cluster(index: dict, decision_index: dict, cluster_id: int, record: dict) -> None:
    cell = _spatial_cell(record)
    if cell is not None:
        index.setdefault(cell, set()).add(cluster_id)
    for group in record["merge_groups"]:
        decision_index.setdefault(group, set()).add(cluster_id)


def _candidate_clusters(record: dict, spatial_index: dict, decision_index: dict, radius_km: float) -> set[int]:
    candidates: set[int] = set()
    for cell in _neighbor_cells(record, radius_km):
        candidates.update(spatial_index.get(cell, ()))
    for group in record["merge_groups"]:
        candidates.update(decision_index.get(group, ()))
    return candidates


def _cluster_anchors(records: list[dict], anchor_indexes: list[int]) -> list[dict]:
    clusters: list[dict] = []
    spatial_index: dict[tuple[str, int, int], set[int]] = {}
    decision_index: dict[str, set[int]] = {}
    for index in sorted(anchor_indexes, key=lambda idx: (-records[idx]["priority"], idx)):
        row = records[index]
        matches: list[tuple[float, int, str]] = []
        for cidx in sorted(_candidate_clusters(row, spatial_index, decision_index, 2.0)):
            cluster = clusters[cidx]
            reasons: list[str] = []
            compatible = True
            for member_index in cluster["indexes"]:
                matched, reason = _anchor_pair_match(row, records[member_index])
                if not matched:
                    compatible = False
                    break
                reasons.append(reason)
            if compatible:
                distances = [_distance_prepared(row, records[member]) for member in cluster["indexes"]]
                finite = [value for value in distances if math.isfinite(value)]
                matches.append((min(finite) if finite else math.inf, cidx, reasons[0] if reasons else "campus anchor match"))
        if matches:
            _, chosen, reason = min(matches, key=lambda item: (item[0], item[1]))
            clusters[chosen]["indexes"].append(index)
            clusters[chosen]["reasons"].add(reason)
            _register_cluster(spatial_index, decision_index, chosen, row)
        else:
            chosen = len(clusters)
            clusters.append({"indexes": [index], "reasons": set()})
            _register_cluster(spatial_index, decision_index, chosen, row)
    return clusters


def _member_anchor_score(member: dict, anchor: dict) -> tuple[float, str] | None:
    if _reviewed_separate_prepared(member, anchor):
        return None
    if _reviewed_merge_prepared(member, anchor):
        return 10000.0, "reviewed identity decision"
    if not _same_jurisdiction_values(member, anchor):
        return None
    distance = _distance_prepared(member, anchor)
    if not math.isfinite(distance):
        return None
    level = member["level"]
    max_distance = 1.75 if level in {"building", "facility"} else 0.65
    if distance > max_distance:
        return None
    operator_ok = _operator_match(member["operator"], anchor["operator"])
    name_similarity = _token_similarity(member["meaningful_name"], anchor["meaningful_name"]) if member["meaningful_name"] and anchor["meaningful_name"] else 0.0
    address_match = bool(member["address"] and member["address"] == anchor["address"])
    if level == "building":
        if address_match:
            return 9000.0 - distance, "building at campus address"
        if operator_ok:
            return 8000.0 - distance, "building + operator within campus envelope"
        if anchor["operator"] and _clean_token(member["name"]) == _clean_token(anchor["operator"]):
            return 7600.0 - distance, "operator-labeled building within campus envelope"
        if name_similarity >= 0.72 and distance <= 0.75:
            return 7200.0 - distance, "building + campus name"
        return None
    if level == "facility":
        if address_match or operator_ok or name_similarity >= 0.72:
            return 7000.0 - distance, "facility linked to campus"
        return None
    if address_match:
        return 6500.0 - distance, "site point at campus address"
    if operator_ok and distance <= 0.45:
        return 6000.0 - distance, "site point + operator"
    if name_similarity >= 0.78 and distance <= 0.45:
        return 5800.0 - distance, "site point + campus name"
    if not member["meaningful_name"] and not member["operator"] and distance <= 0.10:
        return 5000.0 - distance, "coincident unlabeled site observation"
    return None


def _anchor_lookup(records: list[dict], clusters: list[dict]):
    spatial: dict[tuple[str, int, int], set[int]] = {}
    decisions: dict[str, set[int]] = {}
    anchor_to_cluster: dict[int, int] = {}
    for cidx, cluster in enumerate(clusters):
        for anchor_idx in cluster.get("anchor_indexes", ()):
            anchor_to_cluster[anchor_idx] = cidx
            record = records[anchor_idx]
            cell = _spatial_cell(record)
            if cell is not None:
                spatial.setdefault(cell, set()).add(anchor_idx)
            for group in record["merge_groups"]:
                decisions.setdefault(group, set()).add(anchor_idx)
    return spatial, decisions, anchor_to_cluster


def _candidate_anchors(record: dict, spatial: dict, decisions: dict, radius_km: float) -> set[int]:
    result: set[int] = set()
    for cell in _neighbor_cells(record, radius_km):
        result.update(spatial.get(cell, ()))
    for group in record["merge_groups"]:
        result.update(decisions.get(group, ()))
    return result


def _attach_to_anchor_clusters(records: list[dict], clusters: list[dict], remaining: set[int]) -> set[int]:
    if not clusters or not remaining:
        return set()
    spatial, decisions, anchor_to_cluster = _anchor_lookup(records, clusters)
    attached: set[int] = set()
    for index in sorted(remaining):
        member = records[index]
        choices: list[tuple[float, int, str]] = []
        for anchor_idx in _candidate_anchors(member, spatial, decisions, 1.75):
            score = _member_anchor_score(member, records[anchor_idx])
            if score is None:
                continue
            score_value, reason = score
            choices.append((score_value, anchor_to_cluster[anchor_idx], reason))
        if choices:
            _, chosen, reason = max(choices, key=lambda item: (item[0], -item[1]))
            clusters[chosen]["indexes"].append(index)
            clusters[chosen]["reasons"].add(reason)
            attached.add(index)
    return attached


def _building_pair_match(left: dict, right: dict) -> bool:
    if _reviewed_separate_prepared(left, right):
        return False
    if _reviewed_merge_prepared(left, right):
        return True
    if not _same_jurisdiction_values(left, right):
        return False
    distance = _distance_prepared(left, right)
    if not math.isfinite(distance):
        return False
    operator_ok = _operator_match(left["operator"], right["operator"])
    exact_name = bool(left["name_id"] and right["name_id"] and left["name_id"] == right["name_id"])
    generic_operator_name = bool(
        operator_ok
        and (
            _is_generic_name(left["name"], operator=left["operator"], county=left["county"])
            or _is_generic_name(right["name"], operator=right["operator"], county=right["county"])
        )
    )
    if operator_ok and (exact_name or generic_operator_name):
        return distance <= 0.80
    if exact_name and distance <= 0.50:
        return True
    if operator_ok and _token_similarity(left["name"], right["name"]) >= 0.55:
        return distance <= 0.45
    return False


def _facility_pair_match(left: dict, right: dict) -> bool:
    if _reviewed_separate_prepared(left, right):
        return False
    if _reviewed_merge_prepared(left, right):
        return True
    if not _same_jurisdiction_values(left, right):
        return False
    distance = _distance_prepared(left, right)
    if not math.isfinite(distance) or distance > 1.0:
        return False
    if left["address"] and right["address"] and left["address"] == right["address"]:
        return True
    operator_ok = _operator_match(left["operator"], right["operator"])
    name_similarity = _token_similarity(left["meaningful_name"], right["meaningful_name"]) if left["meaningful_name"] and right["meaningful_name"] else 0.0
    return bool(operator_ok and (name_similarity >= 0.55 or distance <= 0.35))


def _point_pair_match(left: dict, right: dict) -> bool:
    if _reviewed_separate_prepared(left, right):
        return False
    if _reviewed_merge_prepared(left, right):
        return True
    if not _same_jurisdiction_values(left, right):
        return False
    distance = _distance_prepared(left, right)
    if not math.isfinite(distance) or distance > 0.20:
        return False
    if _operator_match(left["operator"], right["operator"]):
        return True
    return bool(left["meaningful_name"] and right["meaningful_name"] and _token_similarity(left["meaningful_name"], right["meaningful_name"]) >= 0.80)


def _cluster_complete_link(records: list[dict], indexes: list[int], *, radius_km: float, matcher, reason: str) -> list[dict]:
    clusters: list[dict] = []
    spatial_index: dict[tuple[str, int, int], set[int]] = {}
    decision_index: dict[str, set[int]] = {}
    for index in sorted(indexes, key=lambda idx: (records[idx]["state"], records[idx]["county"], records[idx]["lat"], records[idx]["lon"], idx)):
        row = records[index]
        candidates: list[tuple[float, int]] = []
        for cidx in sorted(_candidate_clusters(row, spatial_index, decision_index, radius_km)):
            cluster = clusters[cidx]
            if all(matcher(row, records[member]) for member in cluster["indexes"]):
                finite = [distance for distance in (_distance_prepared(row, records[member]) for member in cluster["indexes"]) if math.isfinite(distance)]
                candidates.append((min(finite) if finite else math.inf, cidx))
        if candidates:
            _, chosen = min(candidates, key=lambda item: (item[0], item[1]))
            clusters[chosen]["indexes"].append(index)
            _register_cluster(spatial_index, decision_index, chosen, row)
        else:
            chosen = len(clusters)
            clusters.append({"indexes": [index], "anchor_indexes": [], "reasons": {reason}})
            _register_cluster(spatial_index, decision_index, chosen, row)
    return clusters




def _distinct_physical_building_count(records: list[dict], indexes: list[int]) -> int:
    """Count physical buildings after collapsing co-located source observations."""
    representatives: list[int] = []
    for index in sorted(indexes):
        record = records[index]
        matched = False
        for representative in representatives:
            other = records[representative]
            if not _same_jurisdiction_values(record, other):
                continue
            operator_ok = (
                not record["operator"]
                or not other["operator"]
                or _operator_match(record["operator"], other["operator"])
            )
            if not operator_ok:
                continue
            distance = _distance_prepared(record, other)
            if math.isfinite(distance) and distance <= 0.03:
                matched = True
                break
        if not matched:
            representatives.append(index)
    return len(representatives)

def _proximity_components(records: list[dict], indexes: list[int], *, radius_km: float, matcher) -> list[list[int]]:
    """Return local connected components using the shared spatial index.

    This is only a candidate-partitioning step. The stricter complete-link
    identity rule is still applied inside each component, so row order cannot
    create long geographic chains. Partitioning first prevents a dense county
    from repeatedly scanning every previously formed cluster.
    """
    ordered = sorted(indexes, key=lambda idx: (records[idx]["state"], records[idx]["county"], records[idx]["lat"], records[idx]["lon"], idx))
    parent = {idx: idx for idx in ordered}
    rank = {idx: 0 for idx in ordered}

    def find(value: int) -> int:
        root = value
        while parent[root] != root:
            root = parent[root]
        while parent[value] != value:
            nxt = parent[value]
            parent[value] = root
            value = nxt
        return root

    def union(left: int, right: int) -> None:
        a, b = find(left), find(right)
        if a == b:
            return
        if rank[a] < rank[b]:
            a, b = b, a
        parent[b] = a
        if rank[a] == rank[b]:
            rank[a] += 1

    spatial: dict[tuple[str, int, int], list[int]] = {}
    decisions: dict[str, list[int]] = {}
    for idx in ordered:
        row = records[idx]
        candidates: set[int] = set()
        for cell in _neighbor_cells(row, radius_km):
            candidates.update(spatial.get(cell, ()))
        for group in row["merge_groups"]:
            candidates.update(decisions.get(group, ()))
        for other in candidates:
            if matcher(row, records[other]):
                union(idx, other)
        cell = _spatial_cell(row)
        if cell is not None:
            spatial.setdefault(cell, []).append(idx)
        for group in row["merge_groups"]:
            decisions.setdefault(group, []).append(idx)

    groups: dict[int, list[int]] = {}
    for idx in ordered:
        groups.setdefault(find(idx), []).append(idx)
    return list(groups.values())


def _cluster_unassigned_buildings(records: list[dict], indexes: list[int]) -> list[dict]:
    clusters: list[dict] = []
    for component in _proximity_components(records, indexes, radius_km=0.80, matcher=_building_pair_match):
        # Preserve the existing complete-link campus boundary inside each local
        # connected component. Most national components are tiny; this keeps
        # the exact anti-chain rule while eliminating national quadratic scans.
        clusters.extend(
            _cluster_complete_link(
                records, component, radius_km=0.80, matcher=_building_pair_match,
                reason="inferred from co-located building records",
            )
        )
    return clusters


def _cluster_unassigned_facilities(records: list[dict], indexes: list[int]) -> list[dict]:
    return _cluster_complete_link(records, indexes, radius_km=1.0, matcher=_facility_pair_match, reason="inferred from source-native facility records")


def _cluster_remaining_points(records: list[dict], indexes: list[int]) -> tuple[list[dict], list[int]]:
    """Keep uncorroborated point observations below campus grain.

    A source point is location evidence, not a campus boundary or facility
    identity. Points may attach to a campus established by stronger source
    evidence in ``_attach_to_anchor_clusters``. A point that remains unassigned
    stays unresolved rather than manufacturing another campus.
    """
    return [], list(indexes)




def _source_ranked(group: pd.DataFrame) -> pd.DataFrame:
    if group.empty:
        return group.copy()
    if "_priority" in group.columns:
        return group
    output = group.copy()
    source_rank = output.get("Source Class", pd.Series("", index=output.index)).fillna("").astype(str).map({
        "Primary project evidence": 700,
        "Campus geometry": 650,
        "Open project tracker": 600,
        "Secondary project inventory": 500,
        "Observed footprint": 200,
    }).fillna(100)
    level_rank = output.get("Observation Level", pd.Series("", index=output.index)).fillna("").astype(str).map({
        "campus": 80, "facility": 60, "site_point": 40, "building": 20,
    }).fillna(0)
    grade_rank = output.get("Evidence Grade", pd.Series("", index=output.index)).fillna("").astype(str).str.upper().map({
        "A": 8, "B": 6, "C": 4, "D": 2,
    }).fillna(0)
    output["_priority"] = source_rank + level_rank + grade_rank
    return output.sort_values(["_priority", "Source Updated Date", "Observation ID"], ascending=[False, False, True], kind="stable")


def _best_text(group: pd.DataFrame, column: str, *, meaningful_name: bool = False) -> str:
    ranked = group if "_priority" in group.columns else _source_ranked(group)
    if column not in ranked.columns:
        return ""
    for index in ranked.index:
        value = ranked.at[index, column]
        if not _known_text(value):
            continue
        if meaningful_name and not _meaningful_name(ranked.loc[index]):
            continue
        return str(value).strip()
    return ""


def _campus_base_name(group: pd.DataFrame) -> str:
    ranked = _source_ranked(group)
    for _, row in ranked.iterrows():
        name = _meaningful_name(row)
        if name:
            return name
    operator = _best_text(group, "Operator") or _best_text(group, "Owner") or _best_text(group, "Developer")
    if operator:
        return operator
    city = _best_text(group, "City")
    if city:
        return f"Data center — {city}"
    address = _best_text(group, "Address")
    if address:
        return f"Data center — {address}"
    return "Data-center campus"


def _campus_label_base(name: str, city: str, county: str, state: str) -> str:
    """Return a globally meaningful campus label with explicit jurisdiction.

    Campus identity is carried by ``Campus ID``.  The display label must still
    expose a concrete geographic distinction so two real campuses with the same
    operator/name and same county name in different states never collapse into
    an ambiguous UI label.  City is preferred when it adds information; county
    is the fallback; the state code is always present for U.S. campuses.
    """
    name_text = str(name or "Data-center campus").strip() or "Data-center campus"
    city_text = str(city or "").strip()
    county_text = str(county or "").strip()
    state_code = normalize_us_state(state)
    name_token = _clean_token(name_text)
    city_token = _clean_token(city_text)
    county_token = _county_token(county_text)

    qualifier = ""
    if city_text and city_token and city_token not in name_token:
        qualifier = f"{city_text}, {state_code}" if state_code else city_text
    elif county_text and county_token and county_token not in name_token:
        qualifier = f"{county_text}, {state_code}" if state_code else county_text
    elif state_code:
        qualifier = state_code
    elif county_text:
        qualifier = county_text
    elif city_text:
        qualifier = city_text

    return f"{name_text} — {qualifier}" if qualifier else name_text


def _aggregate_numeric(group: pd.DataFrame, column: str, *, component_aggregation: str = "sum") -> float:
    """Roll one numeric field to campus grain using the entity hierarchy.

    A direct campus measurement is authoritative for the campus total. When no
    campus measurement exists, source-native facilities are aggregated. Building
    values are used when the evidence exists only at building grain. Duplicate
    source observations within a facility or building entity are resolved before aggregation.
    """
    if column not in group.columns:
        return np.nan
    values = pd.to_numeric(group[column], errors="coerce")

    campus_rows = group.loc[group["Observation Level"].eq("campus") & values.notna()].copy()
    if not campus_rows.empty:
        if "_priority" not in campus_rows.columns:
            campus_rows = _source_ranked(campus_rows)
        return float(pd.to_numeric(campus_rows.iloc[0][column], errors="coerce"))

    def aggregate_selected(selected: list[float]) -> float:
        if not selected:
            return np.nan
        series = pd.Series(selected, dtype=float)
        if component_aggregation == "max":
            return float(series.max())
        if component_aggregation == "mean":
            return float(series.mean())
        return float(series.sum())

    facility_values: list[float] = []
    for subset in _facility_groups(group):
        local = pd.to_numeric(subset.get(column), errors="coerce").dropna()
        if local.empty:
            continue
        ranked = subset.loc[local.index]
        if "_priority" not in ranked.columns:
            ranked = _source_ranked(ranked)
        facility_values.append(float(pd.to_numeric(ranked.iloc[0][column], errors="coerce")))
    if facility_values:
        return aggregate_selected(facility_values)

    building_values: list[float] = []
    for subset in _dedupe_building_groups(group):
        local = pd.to_numeric(subset.get(column), errors="coerce").dropna()
        if local.empty:
            continue
        ranked = subset.loc[local.index]
        if "_priority" not in ranked.columns:
            ranked = _source_ranked(ranked)
        building_values.append(float(pd.to_numeric(ranked.iloc[0][column], errors="coerce")))
    if building_values:
        return aggregate_selected(building_values)

    remaining = values.dropna()
    return aggregate_selected(remaining.astype(float).tolist())


def _combined_status(group: pd.DataFrame) -> str:
    statuses = {str(value).strip() for value in group.get("Status", pd.Series(dtype=str)) if _known_text(value)}
    active = {"Approved / permitted / under construction", "Under construction", "Proposed", "Planned", "Announced"}
    if "Expanding" in statuses or ("Operational" in statuses and statuses & active):
        return "Expanding"
    order = [
        "Operational", "Under construction", "Approved / permitted / under construction", "Proposed",
        "Planned", "Announced", "Suspended", "Cancelled", "Blocked", "Observed footprint", "Status unknown",
    ]
    return next((status for status in order if status in statuses), "Status unknown")


def _dedupe_building_groups(group: pd.DataFrame) -> list[pd.DataFrame]:
    buildings = group.loc[group["Observation Level"].eq("building")].copy()
    if buildings.empty:
        return []
    output: list[pd.DataFrame] = []
    used: set[int] = set()
    for index, row in buildings.iterrows():
        if index in used:
            continue
        members = [index]
        used.add(index)
        for other_index, other in buildings.loc[~buildings.index.isin(used)].iterrows():
            if not _same_jurisdiction(row, other):
                continue
            operator_match = (
                not _operator_identity(row)
                or not _operator_identity(other)
                or _operator_match(_operator_identity(row), _operator_identity(other))
            )
            if not operator_match:
                continue
            if _haversine_km(row.get("Latitude"), row.get("Longitude"), other.get("Latitude"), other.get("Longitude")) <= 0.03:
                members.append(other_index)
                used.add(other_index)
        output.append(buildings.loc[members].copy())
    return output


def _facility_groups(group: pd.DataFrame) -> list[pd.DataFrame]:
    facilities = group.loc[group["Observation Level"].eq("facility")].copy()
    if facilities.empty:
        return []
    facilities["_key"] = (
        facilities["Name"].map(_identity_token)
        + "|" + facilities.apply(_operator_identity, axis=1)
        + "|" + facilities["Address"].map(_normalized_address)
    )
    groups: list[pd.DataFrame] = []
    for _, subset in facilities.groupby("_key", sort=False, dropna=False):
        groups.append(subset.drop(columns="_key").copy())
    return groups


def _entity_row(entity_id: str, level: str, parent_id: str, campus_id: str, group: pd.DataFrame, name: str) -> dict:
    """Aggregate one registry entity at its native grain.

    The entity table is the single persisted data-center registry. Campus rows,
    facility rows, and building rows therefore carry the same metric vocabulary;
    domains can roll up or drill down without returning to source observations.
    """
    ranked = _source_ranked(group)
    latitude = pd.to_numeric(ranked.get("Latitude"), errors="coerce")
    longitude = pd.to_numeric(ranked.get("Longitude"), errors="coerce")
    row = {column: "" for column in ENTITY_COLUMNS}
    for column in NUMERIC_COLUMNS.intersection(ENTITY_COLUMNS):
        row[column] = np.nan
    for column in DATE_COLUMNS.intersection(ENTITY_COLUMNS):
        row[column] = pd.NaT
    row.update({
        "Entity ID": entity_id,
        "Entity Level": level,
        "Parent Entity ID": parent_id,
        "Entity Name": name,
        "Entity Label": name,
        "Campus ID": campus_id,
        "Operator": _best_text(ranked, "Operator"),
        "Owner": _best_text(ranked, "Owner"),
        "Developer": _best_text(ranked, "Developer"),
        "Occupant": _best_text(ranked, "Occupant"),
        "Address": _best_text(ranked, "Address"),
        "City": _best_text(ranked, "City"),
        "State": _best_text(ranked, "State"),
        "County": _best_text(ranked, "County"),
        "ZIP Code": _best_text(ranked, "ZIP Code"),
        "Latitude": float(latitude.mean()) if latitude.notna().any() else np.nan,
        "Longitude": float(longitude.mean()) if longitude.notna().any() else np.nan,
        "Location Precision": _best_text(ranked, "Location Precision"),
        "Purpose": _best_text(ranked, "Purpose"),
        "Status": _combined_status(ranked),
        "Status Detail": _best_text(ranked, "Status Detail"),
        "Status Date": pd.to_datetime(ranked.get("Status Date"), errors="coerce").max(),
        "Expected Service Date": pd.to_datetime(ranked.get("Expected Service Date"), errors="coerce").min(),
        "Project Cost": _best_text(ranked, "Project Cost"),
        "Capacity Estimate Basis": _best_text(ranked, "Capacity Estimate Basis"),
        "Power Source": _best_text(ranked, "Power Source"),
        "Dedicated Power Plant": _best_text(ranked, "Dedicated Power Plant"),
        "Utility": _best_text(ranked, "Utility"),
        "Balancing Authority": _best_text(ranked, "Balancing Authority"),
        "Watershed": _best_text(ranked, "Watershed"),
        "Cooling System": _best_text(ranked, "Cooling System"),
        "Water Source": _best_text(ranked, "Water Source"),
        "Water Permit or Utility Record": _best_text(ranked, "Water Permit or Utility Record"),
        "Reclaimed Water Use": _best_text(ranked, "Reclaimed Water Use"),
        "Water Evidence Scope": _best_text(ranked, "Water Evidence Scope"),
        "Water Evidence Grade": _best_text(ranked, "Water Evidence Grade"),
        "Water Evidence Type": _best_text(ranked, "Water Evidence Type"),
        "Water Evidence Source": _best_text(ranked, "Water Evidence Source"),
        "Water Evidence URL": _best_text(ranked, "Water Evidence URL"),
        "Water Evidence Date": pd.to_datetime(ranked.get("Water Evidence Date"), errors="coerce").max(),
        "Community Response": _best_text(ranked, "Community Response"),
        "Evidence Grade": _best_text(ranked, "Evidence Grade"),
        "Evidence Type": _best_text(ranked, "Evidence Type"),
        "Inventory Confidence": _best_text(ranked, "Inventory Confidence"),
        "Source": " | ".join(dict.fromkeys(value for value in ranked["Source"].astype(str) if value)),
        "Source URL": _best_text(ranked, "Source URL"),
        "Upstream Source URL": _best_text(ranked, "Upstream Source URL"),
        "Source Date": pd.to_datetime(ranked.get("Source Date"), errors="coerce").max(),
        "Source Updated Date": pd.to_datetime(ranked.get("Source Updated Date"), errors="coerce").max(),
        "Source Record IDs": " | ".join(dict.fromkeys(ranked["Source Record ID"].astype(str))),
        "Member Observation IDs": " | ".join(ranked["Observation ID"].astype(str)),
        "Registry Version": REGISTRY_VERSION,
    })
    for column in NUMERIC_COLUMNS.intersection(ENTITY_COLUMNS):
        aggregation = "mean" if column == "Site WUE L/kWh" else "max" if column == "Property Size Acres" else "sum"
        row[column] = _aggregate_numeric(ranked, column, component_aggregation=aggregation)
    return row

def _build_entities(group: pd.DataFrame, campus_id: str, campus_name: str) -> tuple[list[dict], list[dict]]:
    entities: list[dict] = []
    membership: list[dict] = []
    campus_entity = _entity_row(campus_id, "campus", "", campus_id, group, campus_name)
    entities.append(campus_entity)

    facility_anchors: list[tuple[str, pd.DataFrame]] = []
    for subset in _facility_groups(group):
        entity_id = _stable_id("facility", *sorted(subset["Observation ID"].astype(str)))
        name = _best_text(subset, "Name") or "Data-center facility"
        entities.append(_entity_row(entity_id, "facility", campus_id, campus_id, subset, name))
        facility_anchors.append((entity_id, subset))
        for _, observation in subset.iterrows():
            membership.append({
                "Member Entity ID": entity_id,
                "Parent Entity ID": campus_id,
                "Campus ID": campus_id,
                "Relationship": "facility_in_campus",
                "Source Record ID": observation.get("Source Record ID", ""),
                "Observation ID": observation.get("Observation ID", ""),
                "Relationship Basis": "source-native facility observation",
                "Registry Version": REGISTRY_VERSION,
            })

    for subset in _dedupe_building_groups(group):
        entity_id = _stable_id("building", *sorted(subset["Observation ID"].astype(str)))
        name = _best_text(subset, "Name") or "Data-center building"
        parent_id = campus_id
        if facility_anchors:
            candidates: list[tuple[float, str]] = []
            building = subset.iloc[0]
            for facility_id, facility_group in facility_anchors:
                facility = facility_group.iloc[0]
                distance = _haversine_km(building.get("Latitude"), building.get("Longitude"), facility.get("Latitude"), facility.get("Longitude"))
                if math.isfinite(distance) and distance <= 0.75:
                    candidates.append((distance, facility_id))
            if candidates:
                parent_id = min(candidates)[1]
        entities.append(_entity_row(entity_id, "building", parent_id, campus_id, subset, name))
        for _, observation in subset.iterrows():
            membership.append({
                "Member Entity ID": entity_id,
                "Parent Entity ID": parent_id,
                "Campus ID": campus_id,
                "Relationship": "building_in_facility" if parent_id != campus_id else "building_in_campus",
                "Source Record ID": observation.get("Source Record ID", ""),
                "Observation ID": observation.get("Observation ID", ""),
                "Relationship Basis": "source-native building observation",
                "Registry Version": REGISTRY_VERSION,
            })

    represented = {row["Observation ID"] for row in membership}
    for _, observation in group.iterrows():
        observation_id = str(observation.get("Observation ID") or "")
        if observation_id in represented:
            continue
        membership.append({
            "Member Entity ID": campus_id,
            "Parent Entity ID": campus_id,
            "Campus ID": campus_id,
            "Relationship": "observation_supports_campus",
            "Source Record ID": observation.get("Source Record ID", ""),
            "Observation ID": observation_id,
            "Relationship Basis": "campus identity evidence",
            "Registry Version": REGISTRY_VERSION,
        })
    return entities, membership


def _single_text(row, column: str) -> str:
    value = row.get(column)
    return str(value).strip() if _known_text(value) else ""


def _single_number(row, column: str) -> float:
    value = pd.to_numeric(row.get(column), errors="coerce")
    return float(value) if pd.notna(value) else np.nan


def _single_date(row, column: str):
    return pd.to_datetime(row.get(column), errors="coerce")


def _single_campus_name(row) -> str:
    name = _meaningful_name(row)
    if name:
        return name
    for column in ("Operator", "Owner", "Developer"):
        value = _single_text(row, column)
        if value:
            return value
    city = _single_text(row, "City")
    if city:
        return f"Data center — {city}"
    address = _single_text(row, "Address")
    if address:
        return f"Data center — {address}"
    return "Data-center campus"


def _build_singleton_campus_row(observations: pd.DataFrame, cluster: dict) -> tuple[dict, list[dict], list[dict]]:
    index = int(cluster["indexes"][0])
    row = observations.iloc[index]
    level = str(row.get("Observation Level") or "")
    anchor_indexes = [idx for idx in cluster.get("anchor_indexes", []) if idx == index]
    if anchor_indexes:
        campus_id = _stable_id("campus", row.get("Source"), row.get("Source Record ID"))
        anchor_observation_id = str(row.get("Observation ID") or "")
        identity_basis = cluster.get("identity_basis") or "explicit campus identity"
        confidence = cluster.get("identity_confidence") or "high"
    else:
        campus_id = _stable_id("campus-inferred", row.get("Observation ID"))
        anchor_observation_id = ""
        identity_basis = cluster.get("identity_basis") or "inferred from source observation"
        confidence = cluster.get("identity_confidence") or "low"
    campus_name = _single_campus_name(row)
    campus = {column: "" for column in CAMPUS_COLUMNS}
    for column in NUMERIC_COLUMNS.intersection(CAMPUS_COLUMNS):
        campus[column] = np.nan
    for column in DATE_COLUMNS.intersection(CAMPUS_COLUMNS):
        campus[column] = pd.NaT
    campus.update({
        "Campus ID": campus_id,
        "Campus Name": campus_name,
        "Campus Label": "",
        "Identity Basis": identity_basis,
        "Identity Confidence": confidence,
        "Anchor Observation ID": anchor_observation_id,
        "Resolution Method": "; ".join(sorted(set(cluster.get("reasons", ())))) or identity_basis,
        "Operator": _single_text(row, "Operator"),
        "Owner": _single_text(row, "Owner"),
        "Developer": _single_text(row, "Developer"),
        "Occupant": _single_text(row, "Occupant"),
        "Address": _single_text(row, "Address"),
        "City": _single_text(row, "City"),
        "State": _single_text(row, "State"),
        "County": _single_text(row, "County"),
        "ZIP Code": _single_text(row, "ZIP Code"),
        "Latitude": _single_number(row, "Latitude"),
        "Longitude": _single_number(row, "Longitude"),
        "Location Precision": _single_text(row, "Location Precision"),
        "Purpose": _single_text(row, "Purpose"),
        "Status": _single_text(row, "Status") or "Status unknown",
        "Status Detail": _single_text(row, "Status Detail"),
        "Status Date": _single_date(row, "Status Date"),
        "Expected Service Date": _single_date(row, "Expected Service Date"),
        "Facility Count": 1.0 if level == "facility" else np.nan,
        "Building Count": 1.0 if level == "building" else np.nan,
        "Project Cost": _single_text(row, "Project Cost"),
        "Capacity Estimate Basis": _single_text(row, "Capacity Estimate Basis"),
        "Power Source": _single_text(row, "Power Source"),
        "Dedicated Power Plant": _single_text(row, "Dedicated Power Plant"),
        "Utility": _single_text(row, "Utility"),
        "Balancing Authority": _single_text(row, "Balancing Authority"),
        "Watershed": _single_text(row, "Watershed"),
        "Cooling System": _single_text(row, "Cooling System"),
        "Water Source": _single_text(row, "Water Source"),
        "Water Permit or Utility Record": _single_text(row, "Water Permit or Utility Record"),
        "Reclaimed Water Use": _single_text(row, "Reclaimed Water Use"),
        "Water Evidence Scope": _single_text(row, "Water Evidence Scope"),
        "Water Evidence Grade": _single_text(row, "Water Evidence Grade"),
        "Water Evidence Type": _single_text(row, "Water Evidence Type"),
        "Water Evidence Source": _single_text(row, "Water Evidence Source"),
        "Water Evidence URL": _single_text(row, "Water Evidence URL"),
        "Water Evidence Date": _single_date(row, "Water Evidence Date"),
        "Community Response": _single_text(row, "Community Response"),
        "Evidence Grade": _single_text(row, "Evidence Grade"),
        "Evidence Type": _single_text(row, "Evidence Type"),
        "Inventory Confidence": _single_text(row, "Inventory Confidence"),
        "Source": _single_text(row, "Source"),
        "Source URL": _single_text(row, "Source URL"),
        "Upstream Source URL": _single_text(row, "Upstream Source URL"),
        "Source Date": _single_date(row, "Source Date"),
        "Source Updated Date": _single_date(row, "Source Updated Date"),
        "Source Record IDs": str(row.get("Source Record ID") or ""),
        "Member Observation IDs": str(row.get("Observation ID") or ""),
        "Registry Version": REGISTRY_VERSION,
    })
    for column in NUMERIC_COLUMNS.intersection(CAMPUS_COLUMNS):
        if column not in {"Facility Count", "Building Count"}:
            campus[column] = _single_number(row, column)

    # Campus entities are materialized once from the campus table in
    # _materialize_entity_registry. Do not construct a throwaway campus entity
    # here: on a national registry with thousands of one-record campus anchors,
    # the per-row DataFrame work dominates rebuild time.
    entities: list[dict] = []
    observation_id = str(row.get("Observation ID") or "")
    source_record_id = str(row.get("Source Record ID") or "")
    if level in {"building", "facility"}:
        singleton_group = observations.iloc[[index]].copy()
        entity_id = _stable_id(level, observation_id)
        entity_name = _single_text(row, "Name") or f"Data-center {level}"
        entities.append(_entity_row(entity_id, level, campus_id, campus_id, singleton_group, entity_name))
        membership = [{
            "Member Entity ID": entity_id, "Parent Entity ID": campus_id, "Campus ID": campus_id,
            "Relationship": f"{level}_in_campus", "Source Record ID": source_record_id,
            "Observation ID": observation_id, "Relationship Basis": f"source-native {level} observation",
            "Registry Version": REGISTRY_VERSION,
        }]
        campus["Member Entity IDs"] = entity_id
    else:
        membership = [{
            "Member Entity ID": campus_id, "Parent Entity ID": campus_id, "Campus ID": campus_id,
            "Relationship": "observation_supports_campus", "Source Record ID": source_record_id,
            "Observation ID": observation_id, "Relationship Basis": "campus identity evidence",
            "Registry Version": REGISTRY_VERSION,
        }]
        campus["Member Entity IDs"] = ""
    return campus, entities, membership


def _build_campus_row(observations: pd.DataFrame, cluster: dict) -> tuple[dict, list[dict], list[dict]]:
    indexes = sorted(set(cluster["indexes"]))
    group = _source_ranked(observations.iloc[indexes].copy())
    anchor_indexes = [idx for idx in cluster.get("anchor_indexes", []) if idx in indexes]
    if anchor_indexes:
        anchor = max(anchor_indexes, key=lambda idx: (_source_priority_value(observations.iloc[idx]), -idx))
        campus_id = _stable_id("campus", observations.iloc[anchor].get("Source"), observations.iloc[anchor].get("Source Record ID"))
        anchor_observation_id = str(observations.iloc[anchor].get("Observation ID") or "")
        identity_basis = cluster.get("identity_basis") or "explicit campus identity"
        confidence = cluster.get("identity_confidence") or "high"
    else:
        building_ids = sorted(group.loc[group["Observation Level"].eq("building"), "Observation ID"].astype(str))
        seed_ids = building_ids or sorted(group["Observation ID"].astype(str))
        campus_id = _stable_id("campus-inferred", *seed_ids)
        anchor_observation_id = ""
        identity_basis = cluster.get("identity_basis") or "inferred from source observations"
        confidence = cluster.get("identity_confidence") or ("medium" if len(building_ids) >= 2 else "low")

    campus_name = _campus_base_name(group)
    latitude = pd.to_numeric(group.get("Latitude"), errors="coerce")
    longitude = pd.to_numeric(group.get("Longitude"), errors="coerce")
    levels = group["Observation Level"].astype(str)
    building_count = len(_dedupe_building_groups(group))
    facility_count = len(_facility_groups(group))

    row = {column: "" for column in CAMPUS_COLUMNS}
    row.update({
        "Campus ID": campus_id,
        "Campus Name": campus_name,
        "Campus Label": "",
        "Identity Basis": identity_basis,
        "Identity Confidence": confidence,
        "Anchor Observation ID": anchor_observation_id,
        "Resolution Method": "; ".join(sorted(set(cluster.get("reasons", ())))) or identity_basis,
        "Operator": _best_text(group, "Operator"),
        "Owner": _best_text(group, "Owner"),
        "Developer": _best_text(group, "Developer"),
        "Occupant": _best_text(group, "Occupant"),
        "Address": _best_text(group, "Address"),
        "City": _best_text(group, "City"),
        "State": _best_text(group, "State"),
        "County": _best_text(group, "County"),
        "ZIP Code": _best_text(group, "ZIP Code"),
        "Latitude": float(latitude.mean()) if latitude.notna().any() else np.nan,
        "Longitude": float(longitude.mean()) if longitude.notna().any() else np.nan,
        "Location Precision": _best_text(group, "Location Precision"),
        "Purpose": _best_text(group, "Purpose"),
        "Status": _combined_status(group),
        "Status Detail": _best_text(group, "Status Detail"),
        "Status Date": pd.to_datetime(group.get("Status Date"), errors="coerce").max(),
        "Expected Service Date": pd.to_datetime(group.get("Expected Service Date"), errors="coerce").min(),
        "Square Feet": _aggregate_numeric(group, "Square Feet"),
        "Facility Count": float(facility_count) if facility_count else np.nan,
        "Building Count": float(building_count) if building_count else np.nan,
        "Property Size Acres": _aggregate_numeric(group, "Property Size Acres", component_aggregation="max"),
        "Project Cost": _best_text(group, "Project Cost"),
        "Published Capacity Estimate Low MW": _aggregate_numeric(group, "Published Capacity Estimate Low MW"),
        "Published Capacity Estimate MW": _aggregate_numeric(group, "Published Capacity Estimate MW"),
        "Published Capacity Estimate High MW": _aggregate_numeric(group, "Published Capacity Estimate High MW"),
        "Capacity Estimate Basis": _best_text(group, "Capacity Estimate Basis"),
        "Planned Data Center Capacity MW": _aggregate_numeric(group, "Planned Data Center Capacity MW"),
        "Contracted Utility Capacity MW": _aggregate_numeric(group, "Contracted Utility Capacity MW"),
        "Energized Capacity MW": _aggregate_numeric(group, "Energized Capacity MW"),
        "Annual Electricity Consumption MWh": _aggregate_numeric(group, "Annual Electricity Consumption MWh"),
        "Planned Onsite Generation MW": _aggregate_numeric(group, "Planned Onsite Generation MW"),
        "Power Source": _best_text(group, "Power Source"),
        "Dedicated Power Plant": _best_text(group, "Dedicated Power Plant"),
        "Generator Count": _aggregate_numeric(group, "Generator Count"),
        "Utility": _best_text(group, "Utility"),
        "Balancing Authority": _best_text(group, "Balancing Authority"),
        "Watershed": _best_text(group, "Watershed"),
        "Water Withdrawal Gallons/Year": _aggregate_numeric(group, "Water Withdrawal Gallons/Year"),
        "Water Consumption Gallons/Year": _aggregate_numeric(group, "Water Consumption Gallons/Year"),
        "Site WUE L/kWh": _aggregate_numeric(group, "Site WUE L/kWh", component_aggregation="mean"),
        "Cooling System": _best_text(group, "Cooling System"),
        "Water Source": _best_text(group, "Water Source"),
        "Water Permit or Utility Record": _best_text(group, "Water Permit or Utility Record"),
        "Reclaimed Water Use": _best_text(group, "Reclaimed Water Use"),
        "Water Evidence Scope": _best_text(group, "Water Evidence Scope"),
        "Water Evidence Grade": _best_text(group, "Water Evidence Grade"),
        "Water Evidence Type": _best_text(group, "Water Evidence Type"),
        "Water Evidence Source": _best_text(group, "Water Evidence Source"),
        "Water Evidence URL": _best_text(group, "Water Evidence URL"),
        "Water Evidence Date": pd.to_datetime(group.get("Water Evidence Date"), errors="coerce").max(),
        "Community Response": _best_text(group, "Community Response"),
        "Evidence Grade": _best_text(group, "Evidence Grade"),
        "Evidence Type": _best_text(group, "Evidence Type"),
        "Inventory Confidence": _best_text(group, "Inventory Confidence"),
        "Source": " | ".join(dict.fromkeys(value for value in group["Source"].astype(str) if value)),
        "Source URL": _best_text(group, "Source URL"),
        "Upstream Source URL": _best_text(group, "Upstream Source URL"),
        "Source Date": pd.to_datetime(group.get("Source Date"), errors="coerce").max(),
        "Source Updated Date": pd.to_datetime(group.get("Source Updated Date"), errors="coerce").max(),
        "Source Record IDs": " | ".join(dict.fromkeys(group["Source Record ID"].astype(str))),
        "Member Observation IDs": " | ".join(group["Observation ID"].astype(str)),
        "Registry Version": REGISTRY_VERSION,
    })
    entities, membership = _build_entities(group, campus_id, campus_name)
    row["Member Entity IDs"] = " | ".join(entity["Entity ID"] for entity in entities if entity["Entity ID"] != campus_id)
    return row, entities, membership


def _assign_campus_labels(campuses: pd.DataFrame) -> pd.DataFrame:
    output = campuses.copy()
    if output.empty:
        return output
    output["_base_label"] = [
        _campus_label_base(name, city, county, state)
        for name, city, county, state in zip(
            output["Campus Name"], output["City"], output["County"], output["State"]
        )
    ]
    output["_identity_group"] = (
        output["_base_label"].map(_clean_token)
        + "|" + output["State"].map(normalize_us_state)
    )
    output["Campus Label"] = output["_base_label"]
    for _, indexes in output.groupby("_identity_group", sort=False).groups.items():
        indexes = list(indexes)
        if len(indexes) <= 1:
            continue
        ordered = sorted(
            indexes,
            key=lambda idx: (
                float(output.at[idx, "Latitude"]) if pd.notna(output.at[idx, "Latitude"]) else 999.0,
                float(output.at[idx, "Longitude"]) if pd.notna(output.at[idx, "Longitude"]) else 999.0,
                str(output.at[idx, "Campus ID"]),
            ),
        )
        for number, idx in enumerate(ordered, start=1):
            output.at[idx, "Campus Label"] = f"{output.at[idx, '_base_label']} — Campus {number}"
    if output["Campus Label"].duplicated().any():
        duplicates = output.loc[output["Campus Label"].duplicated(False), ["Campus ID", "Campus Label"]]
        raise ValueError(f"Universal Data Center Registry produced duplicate display labels: {duplicates.to_dict('records')[:5]}")
    return output.drop(columns=["_base_label", "_identity_group"])



def _normalize_entity_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=ENTITY_COLUMNS)
    output = frame.copy()
    for column in ENTITY_COLUMNS:
        if column not in output.columns:
            output[column] = np.nan if column in NUMERIC_COLUMNS else pd.NaT if column in DATE_COLUMNS else ""
    for column in NUMERIC_COLUMNS.intersection(output.columns):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    for column in DATE_COLUMNS.intersection(output.columns):
        output[column] = pd.to_datetime(output[column], errors="coerce", format="mixed")
    text_columns = set(ENTITY_COLUMNS) - NUMERIC_COLUMNS - DATE_COLUMNS
    for column in text_columns:
        output[column] = output[column].fillna("").astype(str).str.strip()
    return output[ENTITY_COLUMNS].reset_index(drop=True)


def _materialize_entity_registry(campuses: pd.DataFrame, entity_rows: list[dict]) -> pd.DataFrame:
    """Build the one persisted data-center entity table.

    Campus rows are materialized from the campus calculation after
    display labels are assigned. Earlier lightweight campus entity rows are
    discarded, so there is one authoritative row per Entity ID.
    """
    members = pd.DataFrame(entity_rows)
    if not members.empty and "Entity Level" in members.columns:
        members = members.loc[~members["Entity Level"].astype(str).eq("campus")].copy()
    members = _normalize_entity_frame(members)

    campus_entities: list[dict] = []
    for _, campus in campuses.iterrows():
        row = {column: "" for column in ENTITY_COLUMNS}
        for column in NUMERIC_COLUMNS.intersection(ENTITY_COLUMNS):
            row[column] = np.nan
        for column in DATE_COLUMNS.intersection(ENTITY_COLUMNS):
            row[column] = pd.NaT
        row.update({
            "Entity ID": str(campus.get("Campus ID") or ""),
            "Entity Level": "campus",
            "Parent Entity ID": "",
            "Entity Name": str(campus.get("Campus Name") or ""),
            "Entity Label": str(campus.get("Campus Label") or ""),
        })
        for column in CAMPUS_COLUMNS:
            if column in {"Campus Name", "Campus Label"}:
                continue
            if column in row:
                row[column] = campus.get(column)
        campus_entities.append(row)
    campus_frame = _normalize_entity_frame(pd.DataFrame(campus_entities))

    entities = pd.concat([campus_frame, members], ignore_index=True, sort=False)
    entities = _normalize_entity_frame(entities)
    if entities["Entity ID"].eq("").any() or entities["Entity ID"].duplicated().any():
        bad = entities.loc[entities["Entity ID"].eq("") | entities["Entity ID"].duplicated(False), ["Entity ID", "Entity Level", "Campus ID"]]
        raise ValueError(f"Universal Data Center Registry produced invalid Entity IDs: {bad.head(10).to_dict('records')}")

    # Member cardinalities are structural properties of the hierarchy, not
    # source observations. Populate them from the parent links.
    building_rows = entities.loc[entities["Entity Level"].eq("building")]
    if not building_rows.empty:
        counts = building_rows.groupby("Parent Entity ID")["Entity ID"].nunique()
        facility_mask = entities["Entity Level"].eq("facility")
        entities.loc[facility_mask, "Building Count"] = entities.loc[facility_mask, "Entity ID"].map(counts).fillna(0).astype(float)

    level_order = entities["Entity Level"].map({"campus": 0, "facility": 1, "building": 2}).fillna(9)
    entities = entities.assign(_level_order=level_order).sort_values(
        ["State", "County", "Campus ID", "_level_order", "Entity Label", "Entity ID"],
        kind="stable",
    ).drop(columns="_level_order").reset_index(drop=True)
    return entities


def campus_view(entities: pd.DataFrame | None) -> pd.DataFrame:
    """Return the campus-grain view derived from the entity table."""
    frame = _normalize_entity_frame(entities)
    if frame.empty:
        return pd.DataFrame(columns=CAMPUS_COLUMNS)
    campuses = frame.loc[frame["Entity Level"].eq("campus")].copy()
    if campuses.empty:
        return pd.DataFrame(columns=CAMPUS_COLUMNS)
    output = pd.DataFrame(index=campuses.index)
    output["Campus ID"] = campuses["Campus ID"]
    output["Campus Name"] = campuses["Entity Name"]
    output["Campus Label"] = campuses["Entity Label"]
    for column in CAMPUS_COLUMNS:
        if column in {"Campus ID", "Campus Name", "Campus Label"}:
            continue
        output[column] = campuses[column] if column in campuses.columns else ""
    output = output[CAMPUS_COLUMNS].reset_index(drop=True)
    if output["Campus ID"].eq("").any() or output["Campus ID"].duplicated().any():
        raise ValueError("Entity table contains invalid campus rows")
    if output["Campus Label"].eq("").any() or output["Campus Label"].duplicated().any():
        raise ValueError("Entity table contains invalid campus labels")
    return output

def _resolve_clusters(observations: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    merge_index, separate_index = _decision_index()
    records = _prepare_identity_records(observations, merge_index, separate_index)
    strong_anchors: list[int] = []
    anchor_meta: dict[int, tuple[str, str]] = {}
    for index, row in observations.iterrows():
        is_anchor, basis, confidence = _anchor_strength(row)
        if is_anchor:
            strong_anchors.append(index)
            anchor_meta[index] = (basis, confidence)

    anchor_clusters = _cluster_anchors(records, strong_anchors)
    clusters: list[dict] = []
    assigned: set[int] = set()
    for cluster in anchor_clusters:
        indexes = list(cluster["indexes"])
        anchor = max(indexes, key=lambda idx: (records[idx]["priority"], -idx))
        basis, confidence = anchor_meta[anchor]
        clusters.append({
            "indexes": indexes,
            "anchor_indexes": indexes.copy(),
            "reasons": set(cluster.get("reasons", ())),
            "identity_basis": basis,
            "identity_confidence": confidence,
        })
        assigned.update(indexes)

    remaining = set(range(len(observations))) - assigned
    assigned.update(_attach_to_anchor_clusters(records, clusters, remaining))

    building_indexes = [idx for idx, record in enumerate(records) if idx not in assigned and record["level"] == "building"]
    for cluster in _cluster_unassigned_buildings(records, building_indexes):
        # Building grain is subordinate to campus grain. A lone building
        # observation cannot manufacture a campus. Inference begins
        # only when the source evidence establishes a co-located multi-building
        # site; explicit campus/facility evidence is handled above.
        physical_buildings = _distinct_physical_building_count(records, cluster["indexes"])
        if physical_buildings < 2:
            continue
        cluster["identity_basis"] = "inferred campus from co-located building records"
        cluster["identity_confidence"] = "medium"
        clusters.append(cluster)
        assigned.update(cluster["indexes"])

    facility_indexes = [idx for idx, record in enumerate(records) if idx not in assigned and record["level"] == "facility"]
    for cluster in _cluster_unassigned_facilities(records, facility_indexes):
        cluster["identity_basis"] = "facility evidence establishes local campus"
        cluster["identity_confidence"] = "medium"
        clusters.append(cluster)
        assigned.update(cluster["indexes"])

    remaining = set(range(len(observations))) - assigned
    assigned.update(_attach_to_anchor_clusters(records, clusters, remaining))

    point_indexes = [
        idx for idx, record in enumerate(records)
        if idx not in assigned and record["level"] in {"site_point", "campus"}
    ]
    point_clusters, unresolved_indexes = _cluster_remaining_points(records, point_indexes)
    for cluster in point_clusters:
        cluster["identity_basis"] = "standalone mapped site observation"
        cluster["identity_confidence"] = "low"
        clusters.append(cluster)
        assigned.update(cluster["indexes"])

    unresolved_set = set(unresolved_indexes)
    unresolved_set.update(idx for idx in range(len(observations)) if idx not in assigned)
    unresolved = observations.iloc[sorted(unresolved_set)].copy() if unresolved_set else observations.iloc[0:0].copy()
    unresolved["Resolution Reason"] = (
        "Insufficient evidence to establish or attach a distinct campus" if not unresolved.empty else pd.Series(dtype=str)
    )
    return clusters, unresolved.reset_index(drop=True)


def _inherit_us_jurisdiction(observations: pd.DataFrame) -> pd.DataFrame:
    """Resolve missing U.S. state/county from co-located IM3 geometry.

    This is source reconciliation, not campus identity resolution.  It exists
    because some OSM-derived Gigawatt rows retain the OSM geometry and name but
    omit country/region metadata.  Only rows corroborated by a retained U.S. IM3
    observation are admitted to the U.S. registry.
    """
    if observations.empty:
        return observations
    output = observations.copy()
    im3_rows = output.loc[
        output["State"].ne("")
        & output["Source"].astype(str).str.contains("IM3", case=False, na=False)
        & pd.to_numeric(output["Latitude"], errors="coerce").notna()
        & pd.to_numeric(output["Longitude"], errors="coerce").notna()
    ].copy()
    if im3_rows.empty:
        return output.loc[output["State"].ne("")].reset_index(drop=True)

    # Coarse cells keep the reconciliation linear on the national retained set.
    cells: dict[tuple[int, int], list[int]] = {}
    for idx, row in im3_rows.iterrows():
        lat = float(row["Latitude"]); lon = float(row["Longitude"])
        cells.setdefault((round(lat * 20), round(lon * 20)), []).append(idx)

    missing_indexes = output.index[output["State"].eq("")].tolist()
    for idx in missing_indexes:
        row = output.loc[idx]
        lat = pd.to_numeric(row.get("Latitude"), errors="coerce")
        lon = pd.to_numeric(row.get("Longitude"), errors="coerce")
        if pd.isna(lat) or pd.isna(lon):
            continue
        cell = (round(float(lat) * 20), round(float(lon) * 20))
        candidates: list[tuple[float, int]] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for ref_idx in cells.get((cell[0] + dy, cell[1] + dx), []):
                    ref = im3_rows.loc[ref_idx]
                    distance = _haversine_km(lat, lon, ref.get("Latitude"), ref.get("Longitude"))
                    if not math.isfinite(distance) or distance > 0.50:
                        continue
                    operator_ok = _operator_match(_operator_identity(row), _operator_identity(ref))
                    row_name = _meaningful_name(row)
                    ref_name = _meaningful_name(ref)
                    name_ok = bool(row_name and ref_name and _token_similarity(row_name, ref_name) >= 0.60)
                    if operator_ok or name_ok:
                        candidates.append((distance, ref_idx))
        if not candidates:
            continue
        _, chosen = min(candidates, key=lambda item: (item[0], item[1]))
        ref = im3_rows.loc[chosen]
        output.at[idx, "State"] = ref.get("State", "")
        output.at[idx, "County"] = ref.get("County", "")
        note = str(output.at[idx, "Notes"] or "").strip()
        inherited = "U.S. jurisdiction reconciled from co-located IM3 geometry."
        output.at[idx, "Notes"] = f"{note} {inherited}".strip()

    # The product registry is U.S.-scoped.  Foreign/unresolved XX observations
    # remain source data and never become ghost U.S. campuses.
    return output.loc[output["State"].ne("")].reset_index(drop=True)


def _normalize_registry_input(frames: list[pd.DataFrame]) -> pd.DataFrame:
    usable = [frame for frame in frames if isinstance(frame, pd.DataFrame) and not frame.empty]
    observations = _normalize_observations(pd.concat(usable, ignore_index=True, sort=False) if usable else None)
    if observations.empty:
        return observations
    observations = _inherit_us_jurisdiction(observations)
    if observations.empty:
        return observations
    # One source record represents one observation.  Duplicate retained copies
    # are collapsed before entity resolution; cross-source corroboration remains.
    observations = (
        observations.sort_values(["Source", "Source Record ID", "Observation ID"], kind="stable")
        .drop_duplicates(["Source", "Source Record ID"], keep="last")
        .reset_index(drop=True)
    )
    return observations


def build_universal_data_center_registry(
    im3_locations: pd.DataFrame | None,
    *,
    fractracker_observations: pd.DataFrame | None = None,
    gigawatt_observations: pd.DataFrame | None = None,
    curated_observations: pd.DataFrame | None = None,
) -> dict:
    observations = _normalize_registry_input([
        normalize_im3_observations(im3_locations),
        _normalize_observations(fractracker_observations),
        _normalize_observations(gigawatt_observations),
        _normalize_observations(curated_observations) if curated_observations is not None else load_curated_data_center_observations(),
    ])
    clusters, unresolved = _resolve_clusters(observations)

    campus_rows: list[dict] = []
    entity_rows: list[dict] = []
    membership_rows: list[dict] = []
    for cluster in clusters:
        if len(cluster.get("indexes", ())) == 1:
            campus, entities, membership = _build_singleton_campus_row(observations, cluster)
        else:
            campus, entities, membership = _build_campus_row(observations, cluster)
        campus_rows.append(campus)
        entity_rows.extend(entities)
        membership_rows.extend(membership)

    campus_calculation = pd.DataFrame(campus_rows, columns=CAMPUS_COLUMNS)
    if not campus_calculation.empty:
        campus_calculation = _assign_campus_labels(campus_calculation)
        if campus_calculation["Campus ID"].duplicated().any():
            raise ValueError("Universal Data Center Registry produced duplicate Campus IDs")
        numeric_columns = NUMERIC_COLUMNS.intersection(campus_calculation.columns)
        for column in numeric_columns:
            campus_calculation[column] = pd.to_numeric(campus_calculation[column], errors="coerce")
        campus_calculation = campus_calculation.sort_values(["State", "County", "Campus Label", "Campus ID"], kind="stable").reset_index(drop=True)

    entities = _materialize_entity_registry(campus_calculation, entity_rows)
    campuses = campus_view(entities)
    membership = pd.DataFrame(membership_rows, columns=MEMBERSHIP_COLUMNS)
    if not membership.empty and membership["Observation ID"].duplicated().any():
        duplicate_ids = membership.loc[membership["Observation ID"].duplicated(False), "Observation ID"].astype(str).unique().tolist()
        raise ValueError(f"A source observation was assigned to multiple registry entities: {duplicate_ids[:5]}")

    summary = data_center_registry_summary(campuses, entities, observations, unresolved)
    return {
        "version": REGISTRY_VERSION,
        "campuses": campuses,
        "entities": entities,
        "observations": observations,
        "membership": membership,
        "unresolved_observations": unresolved,
        "summary": summary,
    }


def data_center_registry_summary(
    campuses: pd.DataFrame | None,
    entities: pd.DataFrame | None = None,
    observations: pd.DataFrame | None = None,
    unresolved: pd.DataFrame | None = None,
) -> dict:
    campus_frame = campuses if isinstance(campuses, pd.DataFrame) else pd.DataFrame()
    entity_frame = entities if isinstance(entities, pd.DataFrame) else pd.DataFrame()
    observation_frame = observations if isinstance(observations, pd.DataFrame) else pd.DataFrame()
    unresolved_frame = unresolved if isinstance(unresolved, pd.DataFrame) else pd.DataFrame()
    status = campus_frame.get("Status", pd.Series("", index=campus_frame.index)).fillna("").astype(str)
    active = {"Operational", "Expanding", "Under construction", "Approved / permitted / under construction", "Proposed", "Planned", "Announced"}
    confidence = campus_frame.get("Identity Confidence", pd.Series("", index=campus_frame.index)).fillna("").astype(str)
    return {
        "registry_version": REGISTRY_VERSION,
        "campuses": int(len(campus_frame)),
        "states": int(campus_frame.get("State", pd.Series(dtype=object)).replace("", np.nan).nunique()) if not campus_frame.empty else 0,
        "operational_campuses": int(status.eq("Operational").sum()),
        "active_campuses": int(status.isin(active).sum()),
        "high_confidence_campuses": int(confidence.eq("high").sum()),
        "medium_confidence_campuses": int(confidence.eq("medium").sum()),
        "low_confidence_campuses": int(confidence.eq("low").sum()),
        "facility_entities": int(entity_frame.get("Entity Level", pd.Series(dtype=object)).eq("facility").sum()) if not entity_frame.empty else 0,
        "building_entities": int(entity_frame.get("Entity Level", pd.Series(dtype=object)).eq("building").sum()) if not entity_frame.empty else 0,
        "source_observations": int(len(observation_frame)),
        "unresolved_observations": int(len(unresolved_frame)),
        "mapped_campuses": int(pd.to_numeric(campus_frame.get("Latitude"), errors="coerce").notna().sum()) if not campus_frame.empty else 0,
    }


def assert_campus_foreign_keys(
    campuses: pd.DataFrame,
    domain_frame: pd.DataFrame | None,
    *,
    domain: str,
    allow_subset: bool = True,
) -> dict:
    if not isinstance(campuses, pd.DataFrame) or "Campus ID" not in campuses.columns:
        raise ValueError("Campus table is unavailable")
    if campuses["Campus ID"].duplicated().any():
        raise ValueError("Campus table contains duplicate Campus IDs")
    registry_ids = set(campuses["Campus ID"].dropna().astype(str)) - {""}
    frame = domain_frame.copy() if isinstance(domain_frame, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        return {"domain": domain, "campuses": len(registry_ids), "referenced_campuses": 0, "coverage_share": 0.0}
    if "Campus ID" not in frame.columns:
        raise ValueError(f"{domain} data-center evidence is missing Campus ID")
    refs = set(frame["Campus ID"].dropna().astype(str)) - {""}
    unknown = refs - registry_ids
    if unknown:
        raise ValueError(f"{domain} references {len(unknown)} Campus IDs outside the Universal Data Center Registry")
    if not allow_subset and refs != registry_ids:
        raise ValueError(f"{domain} campus universe does not equal the Universal Data Center Registry")
    return {
        "domain": domain,
        "campuses": len(registry_ids),
        "referenced_campuses": len(refs),
        "coverage_share": len(refs) / len(registry_ids) if registry_ids else np.nan,
    }


def campus_display_names(campuses: pd.DataFrame | None) -> pd.Series:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.Series(dtype=str)
    if "Campus Label" in campuses.columns:
        labels = campuses["Campus Label"].fillna("").astype(str).str.strip()
        if labels.ne("").all():
            return labels
    names = campuses.get("Campus Name", pd.Series("", index=campuses.index)).fillna("").astype(str).str.strip()
    county = campuses.get("County", pd.Series("", index=campuses.index)).fillna("").astype(str).str.strip()
    state = campuses.get("State", pd.Series("", index=campuses.index)).fillna("").astype(str).str.strip()
    return pd.Series([_campus_label_base(name, cty, st) for name, cty, st in zip(names, county, state)], index=campuses.index, dtype=str)


def campus_display_labels(campuses: pd.DataFrame | None) -> pd.Series:
    return campus_display_names(campuses)


def _sha256_path(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def registry_source_hashes() -> dict[str, str]:
    return {
        "data/data_center_locations.csv": _sha256_path(IM3_RETAINED_PATH),
        "data/infrastructure/curated/data_center_primary_evidence.csv": _sha256_path(CURATED_SOURCE_PATH),
        "data/infrastructure/curated/data_center_identity_decisions.csv": _sha256_path(IDENTITY_DECISIONS_PATH),
        "data/infrastructure/raw/gigawattmap/datacenters.csv": _sha256_path(GIGAWATT_PATH),
        "data/infrastructure/raw/fractracker/data_center_facilities_latest.csv": _sha256_path(FRACTRACKER_PATH),
    }


def registry_source_fingerprint() -> str:
    hashes = registry_source_hashes()
    material = "\n".join(f"{key}:{hashes[key]}" for key in sorted(hashes))
    return sha256(material.encode("utf-8")).hexdigest()[:24]


def _payload_valid(payload: dict) -> None:
    entities = payload.get("entities")
    membership = payload.get("membership")
    if not isinstance(entities, pd.DataFrame) or "Entity ID" not in entities.columns:
        raise ValueError("Universal Data Center Registry entity table is unavailable")
    if entities["Entity ID"].astype(str).duplicated().any():
        raise ValueError("Universal Data Center Registry contains duplicate Entity IDs")
    campuses = campus_view(entities)
    registry_ids = set(campuses["Campus ID"].dropna().astype(str)) - {""}
    if isinstance(entities, pd.DataFrame) and not entities.empty:
        unknown = set(entities.get("Campus ID", pd.Series(dtype=str)).dropna().astype(str)) - {""} - registry_ids
        if unknown:
            raise ValueError("Universal Data Center Registry entities contain unknown Campus IDs")
    if isinstance(membership, pd.DataFrame) and not membership.empty:
        unknown = set(membership.get("Campus ID", pd.Series(dtype=str)).dropna().astype(str)) - {""} - registry_ids
        if unknown:
            raise ValueError("Universal Data Center Registry membership contains unknown Campus IDs")
        if membership.get("Observation ID", pd.Series(dtype=str)).astype(str).duplicated().any():
            raise ValueError("A source observation is assigned to multiple registry entities")


def persist_universal_data_center_registry(payload: dict, *, force: bool = False) -> None:
    if not force and not repository_writes_enabled():
        return
    _payload_valid(payload)
    REGISTRY_DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    frames = {
        REGISTRY_ENTITIES_PATH: payload.get("entities", pd.DataFrame()),
        REGISTRY_OBSERVATIONS_PATH: payload.get("observations", pd.DataFrame()),
        REGISTRY_MEMBERSHIP_PATH: payload.get("membership", pd.DataFrame()),
        REGISTRY_UNRESOLVED_PATH: payload.get("unresolved_observations", pd.DataFrame()),
    }
    payloads = {path: frame.to_csv(index=False).encode("utf-8") for path, frame in frames.items()}
    metadata = {
        "registry_version": REGISTRY_VERSION,
        "source_fingerprint": registry_source_fingerprint(),
        "source_sha256": registry_source_hashes(),
        "summary": dict(payload.get("summary") or {}),
        "tables": {str(path.relative_to(PROJECT_ROOT)): int(len(frame)) for path, frame in frames.items()},
        "table_sha256": {
            str(path.relative_to(PROJECT_ROOT)): sha256(payloads[path]).hexdigest()
            for path in frames
        },
    }
    payloads[REGISTRY_METADATA_PATH] = (json.dumps(metadata, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write_bundle(payloads, transaction_key=REGISTRY_METADATA_PATH)


def load_retained_universal_data_center_registry(*, require_current: bool = True) -> dict | None:
    required = [
        REGISTRY_METADATA_PATH, REGISTRY_ENTITIES_PATH,
        REGISTRY_OBSERVATIONS_PATH, REGISTRY_MEMBERSHIP_PATH, REGISTRY_UNRESOLVED_PATH,
    ]
    if any(not path.exists() for path in required):
        return None
    try:
        metadata = json.loads(REGISTRY_METADATA_PATH.read_text(encoding="utf-8"))
        if str(metadata.get("registry_version")) != REGISTRY_VERSION:
            return None
        if require_current and str(metadata.get("source_fingerprint")) != registry_source_fingerprint():
            return None
        expected_table_hashes = dict(metadata.get("table_sha256") or {})
        if expected_table_hashes:
            for path in (REGISTRY_ENTITIES_PATH, REGISTRY_OBSERVATIONS_PATH, REGISTRY_MEMBERSHIP_PATH, REGISTRY_UNRESOLVED_PATH):
                relative = str(path.relative_to(PROJECT_ROOT))
                expected = str(expected_table_hashes.get(relative) or "")
                if not expected or _sha256_path(path) != expected:
                    return None
        entities = pd.read_csv(REGISTRY_ENTITIES_PATH)
        campuses = campus_view(entities)
        observations = pd.read_csv(REGISTRY_OBSERVATIONS_PATH)
        membership = pd.read_csv(REGISTRY_MEMBERSHIP_PATH)
        unresolved = pd.read_csv(REGISTRY_UNRESOLVED_PATH)
        for frame in (entities, campuses, observations, unresolved):
            for column in DATE_COLUMNS.intersection(frame.columns):
                frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
        payload = {
            "version": REGISTRY_VERSION,
            "campuses": campuses,
            "entities": entities,
            "observations": observations,
            "membership": membership,
            "unresolved_observations": unresolved,
            "summary": dict(metadata.get("summary") or data_center_registry_summary(campuses, entities, observations, unresolved)),
            "source_fingerprint": str(metadata.get("source_fingerprint") or ""),
            "retained": True,
        }
        _payload_valid(payload)
        return payload
    except Exception:
        return None


def build_registry_from_retained_sources() -> dict:
    locations = pd.read_csv(IM3_RETAINED_PATH) if IM3_RETAINED_PATH.exists() else pd.DataFrame()
    fractracker = load_fractracker_data_center_observations(force_refresh=False, allow_live=False)
    gigawatt = load_gigawatt_data_center_observations(verified_only=False)
    payload = build_universal_data_center_registry(
        locations,
        fractracker_observations=fractracker,
        gigawatt_observations=gigawatt,
    )
    payload["source_fingerprint"] = registry_source_fingerprint()
    payload["retained"] = False
    return payload


__all__ = [
    "REGISTRY_VERSION", "OBSERVATION_COLUMNS", "CAMPUS_COLUMNS", "ENTITY_COLUMNS", "MEMBERSHIP_COLUMNS",
    "normalize_us_state", "normalize_im3_observations", "load_curated_data_center_observations",
    "load_gigawatt_data_center_observations", "load_fractracker_data_center_observations",
    "load_data_center_identity_decisions", "build_universal_data_center_registry",
    "data_center_registry_summary", "assert_campus_foreign_keys", "campus_display_names", "campus_display_labels", "campus_view",
    "registry_source_hashes", "registry_source_fingerprint", "persist_universal_data_center_registry",
    "load_retained_universal_data_center_registry", "build_registry_from_retained_sources",
]
