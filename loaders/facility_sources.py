from __future__ import annotations

import re

import numpy as np
import pandas as pd
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv
from loaders.facility_registry_common import (
    FRACTRACKER_FEATURE_URL,
    FRACTRACKER_PATH,
    GIGAWATT_PATH,
    GIGAWATT_VERIFIED_PATH,
    SEED_PATH,
    _UNKNOWN_TEXT,
    _blank_registry,
    _normalize_registry,
    _stable_id,
    _valid_url,
    normalize_us_state,
)

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


def load_fractracker_facility_records(
    *,
    force_refresh: bool = False,
    return_report: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict]:
    source_mode = "retained"
    error = None

    def finish(frame: pd.DataFrame):
        report = {
            "source_mode": source_mode,
            "requested": bool(force_refresh),
            "returned_rows": int(len(frame)),
            "error": error,
        }
        return (frame, report) if return_report else frame

    try:
        raw = _fractracker_raw_frame(force_refresh=force_refresh)
        if force_refresh:
            source_mode = "live_refresh"
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        source_mode = "retained_fallback"
        if not FRACTRACKER_PATH.exists() or not FRACTRACKER_PATH.stat().st_size:
            return finish(_blank_registry())
        try:
            raw = pd.read_csv(FRACTRACKER_PATH)
        except Exception as fallback_exc:
            error = f"{error}; fallback {type(fallback_exc).__name__}: {fallback_exc}"
            return finish(_blank_registry())
    if raw.empty and force_refresh and FRACTRACKER_PATH.exists() and FRACTRACKER_PATH.stat().st_size:
        error = "ValueError: live source returned no records"
        source_mode = "retained_fallback"
        try:
            raw = pd.read_csv(FRACTRACKER_PATH)
        except Exception as fallback_exc:
            error = f"{error}; fallback {type(fallback_exc).__name__}: {fallback_exc}"
    if raw.empty:
        return finish(_blank_registry())

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
    return finish(_normalize_registry(output.dropna(subset=["Latitude", "Longitude"])))
