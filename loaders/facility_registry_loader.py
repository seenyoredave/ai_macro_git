from __future__ import annotations

from hashlib import sha1
from pathlib import Path
import re

import numpy as np
import pandas as pd
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

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


def normalize_im3_locations(locations: pd.DataFrame | None) -> pd.DataFrame:
    if locations is None or not isinstance(locations, pd.DataFrame) or locations.empty:
        return _blank_registry()
    if not {"Latitude", "Longitude"}.issubset(locations.columns):
        return _blank_registry()
    output = pd.DataFrame(index=locations.index)
    output["Facility"] = locations.get("Facility", "")
    output["Operator"] = locations.get("Operator", "")
    output["State"] = locations.get("State", "")
    output["County"] = locations.get("County", "")
    output["Latitude"] = locations.get("Latitude")
    output["Longitude"] = locations.get("Longitude")
    output["Square Feet"] = locations.get("Square Feet", np.nan)
    output["Record Type"] = locations.get("Type", "point")
    output["Source Class"] = "Observed footprint"
    output["Location Precision"] = "Mapped centroid"
    output["Status"] = "Observed footprint"
    output["Evidence Grade"] = "C"
    output["Evidence Type"] = "Open geospatial inventory"
    output["Inventory Confidence"] = "observed footprint"
    output["Source"] = "IM3 Open Source Data Center Atlas / OpenStreetMap"
    output["Source URL"] = "https://doi.org/10.57931/3017294"
    output["Upstream Source URL"] = "https://www.openstreetmap.org"
    output["Notes"] = "Mapped footprint only; no project stage, capacity, power, water, or AI-use claim."
    output["Facility ID"] = output.apply(
        lambda row: _stable_id("im3", row.get("Facility"), row.get("Operator"), row.get("Latitude"), row.get("Longitude")),
        axis=1,
    )
    output["Source Record ID"] = output["Facility ID"]
    return _normalize_registry(output)


def load_curated_facility_records() -> pd.DataFrame:
    if not SEED_PATH.exists() or SEED_PATH.stat().st_size == 0:
        return _blank_registry()
    output = _normalize_registry(pd.read_csv(SEED_PATH))
    if output.empty:
        return output
    output["Source Class"] = "Primary project evidence"
    output["Record Type"] = output["Record Type"].replace("", "project")
    output["Source Record ID"] = output["Source Record ID"].where(output["Source Record ID"].ne(""), output["Facility ID"])
    return output


def load_gigawatt_facility_records(*, verified_only: bool = False) -> pd.DataFrame:
    source_path = GIGAWATT_VERIFIED_PATH if verified_only and GIGAWATT_VERIFIED_PATH.exists() else GIGAWATT_PATH
    if not source_path.exists() or source_path.stat().st_size == 0:
        return _blank_registry()
    raw = pd.read_csv(source_path)
    if raw.empty:
        return _blank_registry()
    raw["State"] = raw.get("region", "").map(normalize_us_state)
    country = raw.get("country", "").fillna("").astype(str).str.upper()
    raw = raw.loc[country.eq("US") | (country.eq("XX") & raw["State"].ne(""))].copy()
    confidence = raw.get("confidence", "").fillna("").astype(str).str.lower()
    if verified_only:
        raw = raw.loc[confidence.eq("verified")].copy()
        confidence = raw.get("confidence", "").fillna("").astype(str).str.lower()
    if raw.empty:
        return _blank_registry()
    verified = confidence.eq("verified")
    raw_status = raw.get("status", "").fillna("").astype(str).str.lower()
    status_map = {
        "operational": "Operational", "construction": "Under construction",
        "announced": "Announced", "blocked": "Blocked",
    }
    output = pd.DataFrame(index=raw.index)
    output["Facility ID"] = "gigawatt:" + raw["id"].fillna("").astype(str)
    output["Source Record ID"] = raw["id"].fillna("").astype(str)
    output["Record Type"] = np.where(verified, "project", "footprint")
    output["Source Class"] = np.where(verified, "Secondary project inventory", "Observed footprint")
    output["Facility"] = raw.get("name", "")
    output["Operator"] = raw.get("operator_id", "")
    output["Developer"] = raw.get("operator_id", "")
    output["Occupant"] = raw.get("tenant", "")
    output["State"] = raw["State"]
    output["Latitude"] = pd.to_numeric(raw.get("lat"), errors="coerce")
    output["Longitude"] = pd.to_numeric(raw.get("lon"), errors="coerce")
    output["Location Precision"] = "Published point"
    output["Status"] = np.where(verified, raw_status.map(status_map).fillna("Status unknown"), "Observed footprint")
    output["Status Date"] = pd.to_datetime(raw.get("announced_date"), errors="coerce", format="mixed").where(verified)
    output["Expected Service Date"] = pd.to_datetime(raw.get("rfs_date"), errors="coerce", format="mixed").where(verified)
    for target, source in [
        ("Published Capacity Estimate Low MW", "est_mw_low"),
        ("Published Capacity Estimate MW", "est_mw_mid"),
        ("Published Capacity Estimate High MW", "est_mw_high"),
    ]:
        output[target] = pd.to_numeric(raw.get(source), errors="coerce").where(verified)
    output["Capacity Estimate Basis"] = raw.get("mw_source", "").fillna("").astype(str).where(verified, "")
    output["Evidence Grade"] = np.where(verified, "C", "D")
    output["Evidence Type"] = np.where(verified, "Third-party project inventory", "Open geospatial inventory")
    output["Inventory Confidence"] = confidence
    output["Source"] = "Gigawatt Map retained export"
    output["Source URL"] = "https://gigawattmap.com/data"
    output["Upstream Source URL"] = raw.get("source_url", "").fillna("")
    output["Source Date"] = pd.to_datetime(raw.get("announced_date"), errors="coerce", format="mixed")
    output["Notes"] = [
        (
            "Secondary project record; published MW is an estimate, not contracted or energized capacity. "
            if is_verified else
            "Open-geospatial footprint retained for map coverage only; no project-stage or capacity claim. "
        ) + (str(note).strip() if str(note).strip() not in {"", "nan"} else "")
        for is_verified, note in zip(verified, raw.get("notes", "").fillna(""))
    ]
    return _normalize_registry(output.dropna(subset=["Latitude", "Longitude"]))



def _valid_url(value) -> bool:
    text = str(value or "").strip()
    return text.startswith("https://") or text.startswith("http://")


def _parse_capacity_text(value) -> tuple[float, float, float, str]:
    text = str(value or "").strip()
    if not text or text.casefold() in _UNKNOWN_TEXT:
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
        params={
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
        },
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
    if raw.empty:
        return raw
    if repository_writes_enabled():
        atomic_write_csv(raw, FRACTRACKER_PATH)
    return raw


def load_fractracker_facility_records(*, force_refresh: bool = False) -> pd.DataFrame:
    try:
        raw = _fractracker_raw_frame(force_refresh=force_refresh)
    except Exception:
        if not FRACTRACKER_PATH.exists() or not FRACTRACKER_PATH.stat().st_size:
            return _blank_registry()
        try:
            raw = pd.read_csv(FRACTRACKER_PATH)
        except Exception:
            return _blank_registry()
    if raw.empty:
        return _blank_registry()

    aliases = {
        "OBJECTID": ("OBJECTID", "objectid", "fid"),
        "name": ("name", "facility_name"),
        "operator": ("operator", "operator_name"),
        "tenant": ("tenant",),
        "address": ("address",),
        "city": ("city",),
        "state": ("state",),
        "county": ("county",),
        "zip": ("zip", "zip_code"),
        "lat": ("lat", "latitude"),
        "long": ("long", "lon", "longitude"),
        "location_confidence": ("location_confidence",),
        "purpose": ("purpose",),
        "status": ("status",),
        "status_detail": ("status_detail", "resistance_status"),
        "expected_date_online": ("expected_date_online",),
        "facility_size_sq_ft": ("facility_size_sq_ft", "facility_size_sqft"),
        "number_of_buildings": ("number_of_buildings",),
        "property_size_acres": ("property_size_acres",),
        "project_cost": ("project_cost",),
        "mw": ("mw",),
        "power_source": ("power_source",),
        "dedicated_power_plant": ("dedicated_power_plant",),
        "number_of_generators": ("number_of_generators",),
        "cooling_source": ("cooling_source",),
        "cooling_type": ("cooling_type",),
        "community_push_back": ("community_push_back", "community_pushback"),
        "other_info": ("other_info",),
        "information_source": ("information_source",),
        "date_created": ("date_created",),
        "date_updated": ("date_updated",),
    }

    def column(name: str, default="") -> pd.Series:
        for candidate in aliases.get(name, (name,)):
            if candidate in raw.columns:
                return raw[candidate]
        return pd.Series(default, index=raw.index)

    status_map = {
        "approved/permitted/under construction": "Approved / permitted / under construction",
        "cancelled": "Cancelled",
        "canceled": "Cancelled",
        "expanding": "Expanding",
        "operating": "Operational",
        "operational": "Operational",
        "proposed": "Proposed",
        "suspended": "Suspended",
        "unknown": "Status unknown",
    }
    output = pd.DataFrame(index=raw.index)
    fallback_ids = raw.apply(
        lambda row: _stable_id(
            "fractracker-source",
            row.get("facility_name", row.get("name", "")),
            row.get("address", ""),
            row.get("lat", row.get("_geometry_y", "")),
            row.get("long", row.get("_geometry_x", "")),
        ),
        axis=1,
    )
    object_values = column("OBJECTID", np.nan)
    object_ids = object_values.where(object_values.notna(), fallback_ids).astype(str)
    output["Facility ID"] = "fractracker:" + object_ids.str.replace("fractracker-source:", "", regex=False)
    output["Source Record ID"] = object_ids
    output["Record Type"] = "project"
    output["Source Class"] = "Open project tracker"
    output["Facility"] = column("name")
    output["Operator"] = column("operator")
    output["Developer"] = column("operator")
    output["Occupant"] = column("tenant")
    output["Address"] = column("address")
    output["City"] = column("city")
    output["State"] = column("state")
    output["County"] = column("county")
    output["ZIP Code"] = column("zip")
    output["Latitude"] = pd.to_numeric(column("lat", np.nan).combine_first(column("_geometry_y", np.nan)), errors="coerce")
    output["Longitude"] = pd.to_numeric(column("long", np.nan).combine_first(column("_geometry_x", np.nan)), errors="coerce")
    output["Location Precision"] = column("location_confidence")
    output["Purpose"] = column("purpose")
    raw_status = column("status").fillna("").astype(str).str.casefold().str.strip()
    output["Status"] = raw_status.map(status_map).fillna("Status unknown")
    output["Status Detail"] = column("status_detail").fillna("").astype(str)
    output.loc[output["Status Detail"].eq(""), "Status Detail"] = column("status").fillna("").astype(str)
    output["Expected Service Date"] = _parse_mixed_dates(column("expected_date_online"))
    output["Square Feet"] = pd.to_numeric(column("facility_size_sq_ft", np.nan), errors="coerce")
    output["Building Count"] = pd.to_numeric(column("number_of_buildings", np.nan), errors="coerce")
    output["Property Size Acres"] = pd.to_numeric(column("property_size_acres", np.nan), errors="coerce")
    output["Project Cost"] = column("project_cost")
    output["Raw Capacity Text"] = column("mw")
    parsed = output["Raw Capacity Text"].map(_parse_capacity_text)
    output["Published Capacity Estimate Low MW"] = parsed.map(lambda value: value[0])
    output["Published Capacity Estimate MW"] = parsed.map(lambda value: value[1])
    output["Published Capacity Estimate High MW"] = parsed.map(lambda value: value[2])
    output["Capacity Estimate Basis"] = parsed.map(lambda value: value[3])
    output["Power Source"] = column("power_source")
    output["Dedicated Power Plant"] = column("dedicated_power_plant")
    output["Generator Count"] = pd.to_numeric(column("number_of_generators", np.nan), errors="coerce")
    cooling = pd.DataFrame({"source": column("cooling_source"), "type": column("cooling_type")}).fillna("").astype(str)
    output["Cooling System"] = cooling.apply(
        lambda row: " / ".join(dict.fromkeys(item.strip() for item in row if item.strip())), axis=1
    )
    output["Water Source"] = column("cooling_source")
    output["Community Response"] = column("community_push_back")

    source_columns = [name for name in raw.columns if re.fullmatch(r"info_source_[1-8]", str(name))]
    source_lists = [
        list(dict.fromkeys(value.strip() for value in row if _valid_url(value)))
        for _, row in raw[source_columns].fillna("").astype(str).iterrows()
    ] if source_columns else [[] for _ in range(len(raw))]
    output["Source URL"] = [items[0] if items else "https://www.fractracker.org/data-centers/" for items in source_lists]
    output["Upstream Source URL"] = [" | ".join(items) for items in source_lists]
    source_counts = pd.Series([len(items) for items in source_lists], index=raw.index)
    output["Evidence Grade"] = np.where(source_counts.ge(2) & ~output["Status"].eq("Status unknown"), "B", "C")
    output["Evidence Type"] = "Cross-referenced open project tracker"
    output["Inventory Confidence"] = column("location_confidence")
    output["Source"] = "FracTracker Open U.S. Data Centers Tracker"
    output["Source Date"] = _parse_mixed_dates(column("date_created", np.nan))
    output["Source Updated Date"] = _parse_mixed_dates(column("date_updated", np.nan))
    output["Review Status"] = np.where(output["Status"].eq("Status unknown"), "Review status", "Source reviewed")
    other = column("other_info").fillna("").astype(str)
    information = column("information_source").fillna("").astype(str)
    output["Notes"] = [" ".join(item for item in [a.strip(), b.strip()] if item) for a, b in zip(other, information)]
    return _normalize_registry(output.dropna(subset=["Latitude", "Longitude"]))


def _identity_token(value) -> str:
    tokens = [
        token for token in _clean_token(value).split()
        if token not in {
            "data", "center", "centre", "datacenter", "campus", "facility", "project",
            "llc", "inc", "corp", "corporation", "company", "co", "the",
        }
    ]
    return " ".join(tokens)


def _token_similarity(left, right) -> float:
    left_tokens = set(_identity_token(left).split())
    right_tokens = set(_identity_token(right).split())
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


KNOWN_CAMPUS_ALIASES = {
    frozenset({"homer city energy", "homer city redevelopment"}),
}
KNOWN_WIDE_RADIUS_CAMPUS_NAMES = {
    "caprock lbb 01",
    "coreweave plano",
    "xai colossus 2",
}


def _known_campus_alias(left, right) -> bool:
    pair = frozenset(
        {
            _identity_token(left.get("Facility")),
            _identity_token(right.get("Facility")),
        }
    )
    return len(pair) == 2 and pair in KNOWN_CAMPUS_ALIASES


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    values = pd.to_numeric(pd.Series([lat1, lon1, lat2, lon2]), errors="coerce")
    if values.isna().any():
        return np.inf
    a1, o1, a2, o2 = np.radians(values.to_numpy(dtype=float))
    delta_lat = a2 - a1
    delta_lon = o2 - o1
    h = np.sin(delta_lat / 2.0) ** 2 + np.cos(a1) * np.cos(a2) * np.sin(delta_lon / 2.0) ** 2
    return float(6371.0088 * 2.0 * np.arcsin(np.sqrt(h)))


def _same_facility(left: pd.Series, right: pd.Series) -> bool:
    if str(left.get("Source") or "") == str(right.get("Source") or ""):
        return False
    if normalize_us_state(left.get("State")) != normalize_us_state(right.get("State")):
        return False
    distance = _haversine_km(left.get("Latitude"), left.get("Longitude"), right.get("Latitude"), right.get("Longitude"))
    if not np.isfinite(distance) or distance > 5.0:
        return False
    name_score = _token_similarity(left.get("Facility"), right.get("Facility"))
    operator_score = _token_similarity(left.get("Operator"), right.get("Operator"))
    address_score = _token_similarity(left.get("Address"), right.get("Address"))
    if distance <= 0.06:
        return True
    if distance <= 0.35 and max(name_score, operator_score, address_score) >= 0.34:
        return True
    if distance <= 1.5 and name_score >= 0.72:
        return True
    return distance <= 5.0 and name_score >= 0.85 and operator_score >= 0.5


def _canonical_priority(frame: pd.DataFrame) -> pd.Series:
    source_rank = frame["Source Class"].map({
        "Primary project evidence": 5,
        "Open project tracker": 4,
        "Secondary project inventory": 3,
        "Observed footprint": 1,
    }).fillna(0)
    grade_rank = frame["Evidence Grade"].map({"A": 5, "B": 4, "C": 3, "D": 2}).fillna(0)
    structured = frame[
        ["Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW"]
    ].notna().sum(axis=1)
    freshness = pd.to_datetime(frame["Source Updated Date"], errors="coerce").rank(method="dense", pct=True).fillna(0)
    return source_rank * 100 + grade_rank * 10 + structured + freshness


def _assign_canonical_ids(observations: pd.DataFrame) -> pd.DataFrame:
    if observations.empty:
        return observations
    clean = observations.reset_index(drop=True).copy()
    parent = list(range(len(clean)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    buckets: dict[tuple[str, int, int], list[int]] = {}
    bucket_degrees = 0.05
    bucket_span = 2
    for index, row in clean.iterrows():
        state = normalize_us_state(row.get("State"))
        lat = pd.to_numeric(row.get("Latitude"), errors="coerce")
        lon = pd.to_numeric(row.get("Longitude"), errors="coerce")
        if pd.isna(lat) or pd.isna(lon):
            continue
        lat_bucket = int(np.floor(float(lat) / bucket_degrees))
        lon_bucket = int(np.floor(float(lon) / bucket_degrees))
        candidates = []
        for lat_offset in range(-bucket_span, bucket_span + 1):
            for lon_offset in range(-bucket_span, bucket_span + 1):
                candidates.extend(buckets.get((state, lat_bucket + lat_offset, lon_bucket + lon_offset), []))
        for candidate in candidates:
            if _same_facility(row, clean.iloc[candidate]):
                union(index, candidate)
        buckets.setdefault((state, lat_bucket, lon_bucket), []).append(index)

    groups: dict[int, list[int]] = {}
    for index in range(len(clean)):
        groups.setdefault(find(index), []).append(index)
    for member_indexes in groups.values():
        member_ids = sorted(clean.loc[member_indexes, "Facility ID"].astype(str))
        canonical_id = _stable_id("facility", *member_ids)
        clean.loc[member_indexes, "Canonical Facility ID"] = canonical_id
        clean.loc[member_indexes, "Duplicate Group ID"] = canonical_id
        if len(member_indexes) > 1:
            clean.loc[member_indexes, "Review Status"] = f"Matched across {len(member_indexes)} source records"
    return _normalize_registry(clean)


def build_facility_observations(
    locations: pd.DataFrame | None,
    supplemental_records: pd.DataFrame | None = None,
) -> pd.DataFrame:
    frames = [normalize_im3_locations(locations), _normalize_registry(supplemental_records), load_curated_facility_records()]
    populated = [frame for frame in frames if not frame.empty]
    observations = pd.concat(populated, ignore_index=True, sort=False) if populated else _blank_registry()
    observations = _normalize_registry(observations)
    return _assign_canonical_ids(observations) if not observations.empty else observations


def _has_value(value, column: str) -> bool:
    if column in NUMERIC_COLUMNS:
        return pd.notna(pd.to_numeric(value, errors="coerce"))
    if column in DATE_COLUMNS:
        return pd.notna(pd.to_datetime(value, errors="coerce"))
    return _known_text(value)


def _merge_canonical_group(group: pd.DataFrame) -> pd.Series:
    ranked = group.copy()
    ranked["_priority"] = _canonical_priority(ranked)
    ranked = ranked.sort_values("_priority", ascending=False, kind="stable")
    result = ranked.iloc[0].copy()
    for column in FACILITY_COLUMNS:
        for value in ranked[column]:
            if _has_value(value, column):
                result[column] = value
                break
    canonical_id = str(group["Canonical Facility ID"].iloc[0])
    result["Facility ID"] = canonical_id
    result["Canonical Facility ID"] = canonical_id
    result["Duplicate Group ID"] = canonical_id
    result["Source Record ID"] = " | ".join(dict.fromkeys(group["Source Record ID"].replace("", np.nan).dropna().astype(str)))
    result["Source"] = " | ".join(dict.fromkeys(group["Source"].replace("", np.nan).dropna().astype(str)))
    urls = []
    for field in ["Source URL", "Upstream Source URL"]:
        for cell in group.loc[group[field].fillna("").astype(str).str.strip().ne(""), field].astype(str):
            urls.extend(item.strip() for item in cell.split("|") if _valid_url(item.strip()))
    result["Upstream Source URL"] = " | ".join(dict.fromkeys(urls))
    if len(group) > 1:
        result["Review Status"] = f"Canonical record from {len(group)} source records"
    return result.drop(labels=["_priority"], errors="ignore")


def canonicalize_facility_observations(observations: pd.DataFrame | None) -> pd.DataFrame:
    clean = _normalize_registry(observations)
    if clean.empty:
        return clean
    if clean["Canonical Facility ID"].fillna("").astype(str).str.strip().eq("").any():
        clean = _assign_canonical_ids(clean)
    rows = [
        _merge_canonical_group(group)
        for _, group in clean.groupby("Canonical Facility ID", sort=False, dropna=False)
    ]
    return _normalize_registry(pd.DataFrame(rows))


def build_facility_registry(
    locations: pd.DataFrame | None,
    supplemental_records: pd.DataFrame | None = None,
) -> pd.DataFrame:
    return canonicalize_facility_observations(
        build_facility_observations(locations, supplemental_records)
    )


def _normalized_address(value) -> str:
    text = _clean_token(value)
    if text in {"", "unknown", "n a", "na", "none", "not disclosed"}:
        return ""
    replacements = {
        " street ": " st ", " road ": " rd ", " avenue ": " ave ",
        " boulevard ": " blvd ", " drive ": " dr ", " highway ": " hwy ",
        " lane ": " ln ", " court ": " ct ", " parkway ": " pkwy ",
    }
    padded = f" {text} "
    for old, new in replacements.items():
        padded = padded.replace(old, new)
    return " ".join(padded.split())


def _same_campus(left: pd.Series, right: pd.Series) -> bool:
    if normalize_us_state(left.get("State")) != normalize_us_state(right.get("State")):
        return False
    distance = _haversine_km(left.get("Latitude"), left.get("Longitude"), right.get("Latitude"), right.get("Longitude"))
    if not np.isfinite(distance):
        return False

    # A small, explicit alias table handles materially important records whose
    # published coordinates refer to different points within the same project.
    if distance <= 50.0 and _known_campus_alias(left, right):
        return True

    left_address = _normalized_address(left.get("Address"))
    right_address = _normalized_address(right.get("Address"))
    if left_address and left_address == right_address and distance <= 1.0:
        return True
    if distance <= 0.075:
        return True

    name_score = _token_similarity(left.get("Facility"), right.get("Facility"))
    operator_score = _token_similarity(left.get("Operator"), right.get("Operator"))
    left_name = _identity_token(left.get("Facility"))
    right_name = _identity_token(right.get("Facility"))
    if distance <= 1.5 and left_name and left_name == right_name:
        return True
    if (
        distance <= 10.0
        and left_name
        and left_name == right_name
        and left_name in KNOWN_WIDE_RADIUS_CAMPUS_NAMES
    ):
        return True
    if distance > 5.0:
        return False
    if distance <= 0.25 and name_score >= 0.80:
        return True
    if distance <= 0.75 and operator_score >= 0.90 and name_score >= 0.25:
        return True
    return distance <= 1.5 and name_score >= 0.82 and operator_score >= 0.72


def _campus_status(values: pd.Series) -> str:
    statuses = {str(value).strip() for value in values if str(value).strip()}
    active = {
        "Approved / permitted / under construction", "Under construction",
        "Proposed", "Planned", "Announced",
    }
    if "Expanding" in statuses or ("Operational" in statuses and statuses.intersection(active)):
        return "Expanding"
    for status in [
        "Operational", "Under construction", "Approved / permitted / under construction",
        "Proposed", "Planned", "Announced", "Suspended", "Cancelled", "Blocked",
        "Observed footprint", "Status unknown",
    ]:
        if status in statuses:
            return status
    return "Status unknown"


def _merge_campus_group(group: pd.DataFrame) -> pd.Series:
    ranked = group.copy()
    ranked["_priority"] = _canonical_priority(ranked)
    ranked = ranked.sort_values("_priority", ascending=False, kind="stable")
    result = ranked.iloc[0].copy()
    result["Status"] = _campus_status(group["Status"])
    building_total = pd.to_numeric(group["Building Count"], errors="coerce").sum(min_count=1)
    result["Building Count"] = max(int(building_total) if pd.notna(building_total) else 0, len(group))
    for column in [
        "Square Feet", "Published Capacity Estimate Low MW",
        "Published Capacity Estimate MW", "Published Capacity Estimate High MW",
        "Planned Data Center Capacity MW", "Contracted Utility Capacity MW",
        "Energized Capacity MW", "Annual Electricity Consumption MWh",
        "Planned Onsite Generation MW", "Property Size Acres",
        "Water Withdrawal Gallons/Year", "Water Consumption Gallons/Year",
    ]:
        values = pd.to_numeric(group[column], errors="coerce").dropna()
        if not values.empty:
            result[column] = values.max()
    dates = pd.to_datetime(group["Expected Service Date"], errors="coerce").dropna()
    if not dates.empty:
        result["Expected Service Date"] = dates.min()
    campus_id = _stable_id("campus", *sorted(group["Canonical Facility ID"].astype(str)))
    result["Facility ID"] = campus_id
    result["Canonical Facility ID"] = campus_id
    result["Duplicate Group ID"] = campus_id
    source_ids = list(dict.fromkeys(group["Source Record ID"].replace("", np.nan).dropna().astype(str)))
    result["Source Record ID"] = " | ".join(source_ids)
    sources = list(dict.fromkeys(group["Source"].replace("", np.nan).dropna().astype(str)))
    result["Source"] = " | ".join(sources)
    result["Review Status"] = f"Campus record from {len(group)} canonical location record{'s' if len(group) != 1 else ''}"
    return result.drop(labels=["_priority"], errors="ignore")


def build_campus_registry(registry: pd.DataFrame | None) -> pd.DataFrame:
    clean = _normalize_registry(registry)
    if clean.empty:
        return clean
    clean = clean.reset_index(drop=True)
    parent = list(range(len(clean)))

    def find(value: int) -> int:
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    buckets: dict[tuple[str, int, int], list[int]] = {}
    # 0.25-degree cells plus a two-cell search expose the full comparison
    # radius, including coordinate-imprecise large campuses. The match rules
    # above remain conservative; this only fixes candidate generation.
    bucket_degrees = 0.25
    bucket_span = 2
    for index, row in clean.iterrows():
        state = normalize_us_state(row.get("State"))
        lat = pd.to_numeric(row.get("Latitude"), errors="coerce")
        lon = pd.to_numeric(row.get("Longitude"), errors="coerce")
        if pd.isna(lat) or pd.isna(lon):
            continue
        lat_bucket = int(np.floor(float(lat) / bucket_degrees))
        lon_bucket = int(np.floor(float(lon) / bucket_degrees))
        candidates = []
        for lat_offset in range(-bucket_span, bucket_span + 1):
            for lon_offset in range(-bucket_span, bucket_span + 1):
                candidates.extend(buckets.get((state, lat_bucket + lat_offset, lon_bucket + lon_offset), []))
        for candidate in candidates:
            if _same_campus(row, clean.iloc[candidate]):
                union(index, candidate)
        buckets.setdefault((state, lat_bucket, lon_bucket), []).append(index)

    groups: dict[int, list[int]] = {}
    for index in range(len(clean)):
        groups.setdefault(find(index), []).append(index)
    rows = [_merge_campus_group(clean.loc[indexes]) for indexes in groups.values()]
    return _normalize_registry(pd.DataFrame(rows))

def registry_coverage(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    total = int(len(clean))
    fields = {}
    for field in CAPACITY_FIELDS:
        valid = int(pd.to_numeric(clean[field], errors="coerce").notna().sum()) if total else 0
        fields[field] = {"records": valid, "total": total, "share": valid / total if total else np.nan}
    structured = ["Planned Data Center Capacity MW", "Contracted Utility Capacity MW", "Energized Capacity MW"]
    structured_count = int(clean[structured].notna().any(axis=1).sum()) if total else 0
    return {
        "records": total,
        "states": int(clean["State"].replace("", np.nan).nunique()) if total else 0,
        "mapped_footprints": int(clean["Record Type"].eq("footprint").sum()) if total else 0,
        "project_records": int(clean["Record Type"].eq("project").sum()) if total else 0,
        "primary_project_records": int(clean["Source Class"].eq("Primary project evidence").sum()) if total else 0,
        "open_tracker_records": int(clean["Source Class"].eq("Open project tracker").sum()) if total else 0,
        "records_with_structured_capacity": structured_count,
        "records_with_source_links": int((clean["Upstream Source URL"].map(_known_text) | clean["Source URL"].map(_known_text)).sum()) if total else 0,
        "evidence_grades": {str(k): int(v) for k, v in clean["Evidence Grade"].replace("", np.nan).value_counts().to_dict().items()},
        "evidence_types": {str(k): int(v) for k, v in clean["Evidence Type"].replace("", np.nan).value_counts().to_dict().items()},
        "inventory_confidence": {str(k): int(v) for k, v in clean["Inventory Confidence"].replace("", np.nan).value_counts().to_dict().items()},
        "fields": fields,
    }


def registry_stage_summary(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    specs = {
        "online": ("Operational", {"Operational"}),
        "expanding": ("Expanding", {"Expanding"}),
        "approved": ("Approved / permitted / construction", {"Approved / permitted / under construction"}),
        "planned": ("Proposed / announced", {"Proposed", "Planned", "Announced"}),
        "suspended": ("Suspended / cancelled / blocked", {"Suspended", "Cancelled", "Blocked"}),
        "footprint": ("Observed footprint", {"Observed footprint"}),
    }
    output = {}
    for key, (label, statuses) in specs.items():
        rows = clean.loc[clean["Status"].isin(statuses)].copy()
        published = pd.to_numeric(rows["Published Capacity Estimate MW"], errors="coerce")
        planned = pd.to_numeric(rows["Planned Data Center Capacity MW"], errors="coerce")
        capacity = planned.combine_first(published)
        output[key] = {
            "label": label,
            "records": int(len(rows)),
            "states": int(rows["State"].replace("", np.nan).nunique()) if not rows.empty else 0,
            "capacity_mw": float(capacity.sum(min_count=1)) if capacity.notna().any() else np.nan,
            "capacity_records": int(capacity.notna().sum()),
            "records_frame": rows,
        }
    pipeline_statuses = {"Approved / permitted / under construction", "Expanding", "Proposed", "Planned", "Announced"}
    pipeline_rows = clean.loc[clean["Status"].isin(pipeline_statuses)].copy()
    published = pd.to_numeric(pipeline_rows["Published Capacity Estimate MW"], errors="coerce")
    planned = pd.to_numeric(pipeline_rows["Planned Data Center Capacity MW"], errors="coerce")
    capacity = planned.combine_first(published)
    output["pipeline"] = {
        "label": "Active pipeline",
        "records": int(len(pipeline_rows)),
        "states": int(pipeline_rows["State"].replace("", np.nan).nunique()) if not pipeline_rows.empty else 0,
        "capacity_mw": float(capacity.sum(min_count=1)) if capacity.notna().any() else np.nan,
        "capacity_records": int(capacity.notna().sum()),
        "records_frame": pipeline_rows,
    }
    return output


WATER_EVIDENCE_FIELDS = {
    "Water source identified": "Water Source",
    "Cooling design disclosed": "Cooling System",
    "Withdrawal disclosed": "Water Withdrawal Gallons/Year",
    "Consumption disclosed": "Water Consumption Gallons/Year",
    "WUE disclosed": "Site WUE L/kWh",
    "Permit or utility record located": "Water Permit or Utility Record",
    "Reclaimed-water use documented": "Reclaimed Water Use",
}


def _known_text(value) -> bool:
    text = str(value or "").strip().lower()
    return text not in _UNKNOWN_TEXT and not any(token in text for token in ("not disclosed", "unknown", "unavailable"))


def water_evidence_mask(registry: pd.DataFrame | None) -> pd.Series:
    clean = _normalize_registry(registry)
    if clean.empty:
        return pd.Series(dtype=bool)
    masks = []
    for field in WATER_EVIDENCE_FIELDS.values():
        masks.append(pd.to_numeric(clean[field], errors="coerce").notna() if field in NUMERIC_COLUMNS else clean[field].map(_known_text))
    result = masks[0].copy()
    for mask in masks[1:]:
        result |= mask
    return result


def water_evidence_coverage(registry: pd.DataFrame | None) -> dict:
    clean = _normalize_registry(registry)
    total = int(len(clean))
    fields = {}
    for label, field in WATER_EVIDENCE_FIELDS.items():
        valid = 0 if total == 0 else int(
            pd.to_numeric(clean[field], errors="coerce").notna().sum()
            if field in NUMERIC_COLUMNS else clean[field].map(_known_text).sum()
        )
        fields[label] = {"field": field, "records": valid, "total": total, "share": valid / total if total else np.nan}
    return {
        "records": total,
        "records_with_any_water_evidence": int(water_evidence_mask(clean).sum()) if total else 0,
        "fields": fields,
    }
