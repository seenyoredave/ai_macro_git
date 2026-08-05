from __future__ import annotations

from hashlib import sha1
from pathlib import Path
import re

import numpy as np
import pandas as pd

from loaders.data_center_inventory_loader import STATE_ABBREVIATIONS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


SEED_PATH = PROJECT_ROOT / "data" / "facility_registry_seed.csv"


GIGAWATT_PATH = PROJECT_ROOT / "data" / "infrastructure" / "raw" / "gigawattmap" / "datacenters.csv"


GIGAWATT_VERIFIED_PATH = PROJECT_ROOT / "data" / "infrastructure" / "derived" / "gigawatt_verified_us_projects.csv"


FRACTRACKER_PATH = PROJECT_ROOT / "data" / "infrastructure" / "raw" / "fractracker" / "data_center_facilities_latest.csv"


FRACTRACKER_FEATURE_URL = (
    "https://services1.arcgis.com/AbQpv9doWn5so44u/ArcGIS/rest/services/"
    "Data_Centers_by_Congressional_District_WFL1/FeatureServer/7/query"
)


FACILITY_COLUMNS = [
    "Facility ID", "Canonical Facility ID", "Source Record ID", "Duplicate Group ID", "Review Status",
    "Record Type", "Source Class", "Facility", "Operator", "Owner", "Developer", "Occupant",
    "Address", "City", "State", "County", "ZIP Code", "Latitude", "Longitude", "Location Precision",
    "Purpose", "Status", "Status Detail", "Status Date", "Expected Service Date", "Square Feet",
    "Building Count", "Property Size Acres", "Project Cost", "Raw Capacity Text",
    "Published Capacity Estimate Low MW", "Published Capacity Estimate MW",
    "Published Capacity Estimate High MW", "Capacity Estimate Basis", "Planned Data Center Capacity MW",
    "Contracted Utility Capacity MW", "Energized Capacity MW", "Annual Electricity Consumption MWh",
    "Planned Onsite Generation MW", "Power Source", "Dedicated Power Plant", "Generator Count",
    "Utility", "Balancing Authority", "Watershed", "Water Withdrawal Gallons/Year",
    "Water Consumption Gallons/Year", "Site WUE L/kWh", "Cooling System", "Water Source",
    "Water Permit or Utility Record", "Reclaimed Water Use", "Water Evidence Scope",
    "Water Evidence Grade", "Water Evidence Type", "Water Evidence Source", "Water Evidence URL",
    "Water Evidence Date", "Community Response", "Evidence Grade", "Evidence Type",
    "Inventory Confidence", "Source", "Source URL", "Upstream Source URL", "Source Date",
    "Source Updated Date", "Notes",
]


NUMERIC_COLUMNS = [
    "Latitude", "Longitude", "Square Feet", "Published Capacity Estimate Low MW",
    "Published Capacity Estimate MW", "Published Capacity Estimate High MW",
    "Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW",
    "Annual Electricity Consumption MWh", "Planned Onsite Generation MW",
    "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year", "Site WUE L/kWh",
    "Building Count", "Property Size Acres",
]


DATE_COLUMNS = ["Status Date", "Expected Service Date", "Source Date", "Source Updated Date", "Water Evidence Date"]


CAPACITY_FIELDS = [
    "Square Feet", "Published Capacity Estimate MW", "Planned Data Center Capacity MW",
    "Contracted Utility Capacity MW", "Energized Capacity MW", "Annual Electricity Consumption MWh",
    "Planned Onsite Generation MW", "Building Count", "Property Size Acres", "Water Withdrawal Gallons/Year",
    "Water Consumption Gallons/Year", "Site WUE L/kWh",
]


US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR", "VI", "GU", "AS", "MP",
}


_UNKNOWN_TEXT = {
    "", "n/a", "na", "none", "unknown", "unavailable", "not available", "not disclosed",
    "undisclosed",
}


def _blank_registry() -> pd.DataFrame:
    return pd.DataFrame(columns=FACILITY_COLUMNS)


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


def _stable_id(prefix: str, *values) -> str:
    key = "|".join(str(value or "") for value in values)
    return f"{prefix}:{sha1(key.encode('utf-8')).hexdigest()[:16]}"


def _normalize_registry(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _blank_registry()
    output = frame.copy()
    for column in FACILITY_COLUMNS:
        if column not in output.columns:
            output[column] = np.nan if column in NUMERIC_COLUMNS else ""
    for column in NUMERIC_COLUMNS:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    for column in DATE_COLUMNS:
        output[column] = pd.to_datetime(output[column], errors="coerce", format="mixed")
    text_columns = set(FACILITY_COLUMNS) - set(NUMERIC_COLUMNS) - set(DATE_COLUMNS)
    for column in text_columns:
        output[column] = output[column].fillna("").astype(str).str.strip()
    output["State"] = output["State"].map(normalize_us_state)
    return output[FACILITY_COLUMNS].drop_duplicates(subset=["Facility ID"], keep="last").reset_index(drop=True)


def _valid_url(value) -> bool:
    text = str(value or "").strip()
    return text.startswith("https://") or text.startswith("http://")


def _known_text(value) -> bool:
    text = str(value or "").strip().lower()
    return text not in _UNKNOWN_TEXT and not any(token in text for token in ("not disclosed", "unknown", "unavailable"))
