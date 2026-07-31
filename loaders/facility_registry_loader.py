"""Evidence-graded facility registry for observed and verified data-center records.

The registry merges the IM3/OpenStreetMap observed footprint with a small,
explicitly curated project ledger. It is not a census of US data centers.
Unknown capacity, power, and water fields remain null and are never inferred
from square footage or project language.
"""

from __future__ import annotations

from hashlib import sha1
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_ROOT / "data" / "facility_registry_seed.csv"

FACILITY_COLUMNS = [
    "Facility ID",
    "Facility",
    "Operator",
    "Owner",
    "Occupant",
    "State",
    "County",
    "Latitude",
    "Longitude",
    "Location Precision",
    "Status",
    "Status Date",
    "Square Feet",
    "Planned Data Center Capacity MW",
    "Contracted Utility Capacity MW",
    "Energized Capacity MW",
    "Annual Electricity Consumption MWh",
    "Planned Onsite Generation MW",
    "Water Withdrawal Gallons/Year",
    "Water Consumption Gallons/Year",
    "Site WUE L/kWh",
    "Cooling System",
    "Water Source",
    "Evidence Grade",
    "Evidence Type",
    "Source",
    "Source URL",
    "Source Date",
    "Notes",
]

NUMERIC_COLUMNS = [
    "Latitude",
    "Longitude",
    "Square Feet",
    "Planned Data Center Capacity MW",
    "Contracted Utility Capacity MW",
    "Energized Capacity MW",
    "Annual Electricity Consumption MWh",
    "Planned Onsite Generation MW",
    "Water Withdrawal Gallons/Year",
    "Water Consumption Gallons/Year",
    "Site WUE L/kWh",
]

CAPACITY_FIELDS = [
    "Square Feet",
    "Planned Data Center Capacity MW",
    "Contracted Utility Capacity MW",
    "Energized Capacity MW",
    "Annual Electricity Consumption MWh",
    "Planned Onsite Generation MW",
    "Water Withdrawal Gallons/Year",
    "Water Consumption Gallons/Year",
    "Site WUE L/kWh",
]


def _blank_registry() -> pd.DataFrame:
    return pd.DataFrame(columns=FACILITY_COLUMNS)


def _stable_im3_id(row: pd.Series) -> str:
    key = "|".join(
        [
            str(row.get("Facility") or ""),
            str(row.get("Operator") or ""),
            str(row.get("Latitude") or ""),
            str(row.get("Longitude") or ""),
        ]
    )
    return f"im3:{sha1(key.encode('utf-8')).hexdigest()[:16]}"


def _normalize_registry(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _blank_registry()
    output = frame.copy()
    for column in FACILITY_COLUMNS:
        if column not in output.columns:
            output[column] = np.nan if column in NUMERIC_COLUMNS else ""
    for column in NUMERIC_COLUMNS:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    for column in ["Status Date", "Source Date"]:
        output[column] = pd.to_datetime(output[column], errors="coerce", format="mixed")
    for column in set(FACILITY_COLUMNS) - set(NUMERIC_COLUMNS) - {"Status Date", "Source Date"}:
        output[column] = output[column].fillna("").astype(str).str.strip()
    return (
        output[FACILITY_COLUMNS]
        .drop_duplicates(subset=["Facility ID"], keep="last")
        .reset_index(drop=True)
    )


def normalize_im3_locations(locations: pd.DataFrame | None) -> pd.DataFrame:
    """Translate IM3 map rows into the evidence-graded registry contract."""
    if locations is None or not isinstance(locations, pd.DataFrame) or locations.empty:
        return _blank_registry()
    required = {"Latitude", "Longitude"}
    if not required.issubset(locations.columns):
        return _blank_registry()

    output = pd.DataFrame(index=locations.index)
    output["Facility"] = locations.get("Facility", "")
    output["Operator"] = locations.get("Operator", "")
    output["Owner"] = ""
    output["Occupant"] = ""
    output["State"] = locations.get("State", "")
    output["County"] = locations.get("County", "")
    output["Latitude"] = locations.get("Latitude")
    output["Longitude"] = locations.get("Longitude")
    output["Location Precision"] = "Mapped centroid"
    output["Status"] = "Observed footprint"
    output["Status Date"] = pd.NaT
    output["Square Feet"] = locations.get("Square Feet", np.nan)
    output["Planned Data Center Capacity MW"] = np.nan
    output["Contracted Utility Capacity MW"] = np.nan
    output["Energized Capacity MW"] = np.nan
    output["Annual Electricity Consumption MWh"] = np.nan
    output["Planned Onsite Generation MW"] = np.nan
    output["Water Withdrawal Gallons/Year"] = np.nan
    output["Water Consumption Gallons/Year"] = np.nan
    output["Site WUE L/kWh"] = np.nan
    output["Cooling System"] = ""
    output["Water Source"] = ""
    output["Evidence Grade"] = "C"
    output["Evidence Type"] = "Open geospatial inventory"
    output["Source"] = "IM3 Data Center Atlas / OpenStreetMap"
    output["Source URL"] = "https://github.com/IMMM-SFA/datacenter-atlas"
    output["Source Date"] = pd.NaT
    output["Notes"] = (
        "Observed mapped footprint. Record does not establish construction stage, "
        "compute capacity, power demand, water demand, or AI-specific use."
    )
    output["Facility ID"] = output.apply(_stable_im3_id, axis=1)
    return _normalize_registry(output)


def load_curated_facility_records() -> pd.DataFrame:
    if not SEED_PATH.exists() or SEED_PATH.stat().st_size == 0:
        return _blank_registry()
    return _normalize_registry(pd.read_csv(SEED_PATH))


def build_facility_registry(locations: pd.DataFrame | None) -> pd.DataFrame:
    """Merge mapped and curated records without replacing unknown values."""
    observed = normalize_im3_locations(locations)
    curated = load_curated_facility_records()
    frames = [frame for frame in (observed, curated) if isinstance(frame, pd.DataFrame) and not frame.empty]
    combined = pd.concat(frames, ignore_index=True, sort=False) if frames else _blank_registry()
    return _normalize_registry(combined)


def registry_coverage(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    total = int(len(clean))
    coverage = {}
    for field in CAPACITY_FIELDS:
        valid = int(pd.to_numeric(clean[field], errors="coerce").notna().sum()) if total else 0
        coverage[field] = {
            "records": valid,
            "total": total,
            "share": (valid / total) if total else np.nan,
        }
    verified = int(clean["Facility ID"].str.startswith("verified:", na=False).sum()) if total else 0
    return {
        "records": total,
        "states": int(clean["State"].replace("", np.nan).nunique()) if total else 0,
        "verified_project_records": verified,
        "fields": coverage,
    }
