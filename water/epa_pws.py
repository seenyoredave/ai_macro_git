"""Facility-point overlap cache for EPA public-water service-area boundaries.

A polygon intersection is geographic context only.  It is never promoted to a
claim that the facility is an actual customer of the intersecting water system.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

import pandas as pd
import requests

from helpers.atomic_io import atomic_write_csv

SERVICE_VERSION = "3.1"
QUERY_URL = (
    "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/"
    "Water_System_Boundaries/FeatureServer/0/query"
)
SOURCE_URL = "https://www.epa.gov/ground-water-and-drinking-water/public-water-system-service-areas"
OUT_FIELDS = ",".join(
    [
        "PWSID",
        "PWS_Name",
        "Primacy_Agency",
        "Population_Served_Count",
        "Service_Connections_Count",
        "Model_Method",
        "Service_Area_Type",
        "Symbology_Field",
        "Original_Data_Provider",
        "Data_Provider_Type",
        "Verification_Status",
        "Confirmed",
        "Feature_Type",
    ]
)

CACHE_COLUMNS = [
    "Query Key",
    "Facility ID",
    "Latitude",
    "Longitude",
    "PWSID",
    "PWS Name",
    "Primacy Agency",
    "Population Served",
    "Service Connections",
    "Boundary Basis",
    "Model Method",
    "Service Area Type",
    "Original Data Provider",
    "Data Provider Type",
    "Verification Status",
    "Boundary Confirmed Field",
    "Feature Type",
    "Query Status",
    "Service Version",
    "Retrieved At UTC",
    "Source URL",
]


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def _facility_id(row: pd.Series, index: Any) -> str:
    for field in ("Facility ID", "Campus ID", "Canonical Facility ID", "site_id"):
        value = _text(row.get(field))
        if value:
            return value
    parts = [
        _text(row.get("State")),
        _text(row.get("County")),
        _text(row.get("Operator")),
        _text(row.get("Facility")),
    ]
    joined = "|".join(part for part in parts if part)
    return joined or f"row-{index}"


def query_key(facility_id: str, latitude: float, longitude: float) -> str:
    return f"{facility_id}|{latitude:.5f}|{longitude:.5f}|epa-pws-{SERVICE_VERSION}"


CWS_MODEL_METHODS = {"CENSUS PLACE", "DECISION TREE", "OSM", "PARCEL", "RANDOM FOREST"}


def _boundary_basis(attributes: dict[str, Any]) -> str:
    """Classify EPA CWS boundary provenance using both v2 and v3 metadata.

    EPA documents ``Symbology_Field`` as MODELED/STATE and also documents the
    community-system ``Model_Method`` field, where State denotes a sourced
    boundary and the named modeling methods denote EPA-derived boundaries.
    Version 3 rows do not populate every added metadata field consistently, so
    either signal may be required.
    """

    symbology = _text(attributes.get("Symbology_Field")).upper()
    if symbology == "STATE":
        return "authoritative"
    if symbology == "MODELED":
        return "modeled"

    model_method = _text(attributes.get("Model_Method")).upper()
    if model_method == "STATE":
        return "authoritative"
    if model_method in CWS_MODEL_METHODS:
        return "modeled"
    return "unclassified"


def _is_community_system(attributes: dict[str, Any]) -> bool:
    """Keep the analytical layer bounded to community water systems.

    EPA Version 3 combines community and non-community service areas in one
    feature service. ``Feature_Type`` is therefore the preferred discriminator.
    Older/community rows can have a blank feature type, so the original
    STATE/MODELED symbology remains a conservative compatibility fallback.
    """

    feature_type = _text(attributes.get("Feature_Type")).casefold()
    if feature_type:
        compact = feature_type.replace("-", " ").replace("_", " ")
        if any(token in compact for token in ("non community", "transient", "ntnc", "tncws", "tnc")):
            return False
        if "community" in compact or compact.strip() == "cws":
            return True

    symbology = _text(attributes.get("Symbology_Field")).upper()
    if symbology in {"STATE", "MODELED"}:
        return True

    # ``Model_Method`` belongs to the community-system schema.  Use it only as
    # a compatibility fallback when Feature_Type and Symbology_Field are blank.
    model_method = _text(attributes.get("Model_Method")).upper()
    return model_method == "STATE" or model_method in CWS_MODEL_METHODS


def _request_one(
    *,
    facility_id: str,
    latitude: float,
    longitude: float,
    timeout: int,
    attempts: int,
) -> list[dict[str, Any]]:
    key = query_key(facility_id, latitude, longitude)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    last_error = ""

    for attempt in range(max(int(attempts), 1)):
        try:
            response = requests.get(
                QUERY_URL,
                params={
                    "f": "json",
                    "where": "1=1",
                    "geometry": f"{longitude:.7f},{latitude:.7f}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": OUT_FIELDS,
                    "returnGeometry": "false",
                },
                timeout=timeout,
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(str(payload["error"]))
            features = list(payload.get("features") or [])

            rows: list[dict[str, Any]] = []
            for feature in features:
                attributes = dict((feature or {}).get("attributes") or {})
                # EPA Version 3 combines community and non-community systems.
                # Keep this analytical layer to community systems only.
                if not _is_community_system(attributes):
                    continue
                rows.append(
                    {
                        "Query Key": key,
                        "Facility ID": facility_id,
                        "Latitude": latitude,
                        "Longitude": longitude,
                        "PWSID": _text(attributes.get("PWSID")),
                        "PWS Name": _text(attributes.get("PWS_Name")),
                        "Primacy Agency": _text(attributes.get("Primacy_Agency")),
                        "Population Served": pd.to_numeric(attributes.get("Population_Served_Count"), errors="coerce"),
                        "Service Connections": pd.to_numeric(attributes.get("Service_Connections_Count"), errors="coerce"),
                        "Boundary Basis": _boundary_basis(attributes),
                        "Model Method": _text(attributes.get("Model_Method")),
                        "Service Area Type": _text(attributes.get("Service_Area_Type")),
                        "Original Data Provider": _text(attributes.get("Original_Data_Provider")),
                        "Data Provider Type": _text(attributes.get("Data_Provider_Type")),
                        "Verification Status": _text(attributes.get("Verification_Status")),
                        "Boundary Confirmed Field": _text(attributes.get("Confirmed")),
                        "Feature Type": _text(attributes.get("Feature_Type")),
                        "Query Status": "matched",
                        "Service Version": SERVICE_VERSION,
                        "Retrieved At UTC": retrieved,
                        "Source URL": SOURCE_URL,
                    }
                )
            if rows:
                return rows
            return [
                {
                    "Query Key": key,
                    "Facility ID": facility_id,
                    "Latitude": latitude,
                    "Longitude": longitude,
                    "PWSID": "",
                    "PWS Name": "",
                    "Primacy Agency": "",
                    "Population Served": float("nan"),
                    "Service Connections": float("nan"),
                    "Boundary Basis": "",
                    "Model Method": "",
                    "Service Area Type": "",
                    "Original Data Provider": "",
                    "Data Provider Type": "",
                    "Verification Status": "",
                    "Boundary Confirmed Field": "",
                    "Feature Type": "",
                    "Query Status": "no_match",
                    "Service Version": SERVICE_VERSION,
                    "Retrieved At UTC": retrieved,
                    "Source URL": SOURCE_URL,
                }
            ]
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 < max(int(attempts), 1):
                time.sleep(min(4.0, 0.6 * (2**attempt)))

    return [
        {
            "Query Key": key,
            "Facility ID": facility_id,
            "Latitude": latitude,
            "Longitude": longitude,
            "PWSID": "",
            "PWS Name": "",
            "Primacy Agency": "",
            "Population Served": float("nan"),
            "Service Connections": float("nan"),
            "Boundary Basis": "",
            "Model Method": "",
            "Service Area Type": "",
            "Original Data Provider": "",
            "Data Provider Type": "",
            "Verification Status": "",
            "Boundary Confirmed Field": "",
            "Feature Type": "",
            "Query Status": f"error: {last_error}",
            "Service Version": SERVICE_VERSION,
            "Retrieved At UTC": retrieved,
            "Source URL": SOURCE_URL,
        }
    ]


def normalize_cache(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=CACHE_COLUMNS)
    output = frame.copy()
    for column in CACHE_COLUMNS:
        if column not in output.columns:
            output[column] = ""
    for column in ("Latitude", "Longitude", "Population Served", "Service Connections"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output[CACHE_COLUMNS]


def load_cache(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.exists() or source.stat().st_size == 0:
        return pd.DataFrame(columns=CACHE_COLUMNS)
    try:
        return normalize_cache(pd.read_csv(source, dtype={"PWSID": str, "Facility ID": str, "Query Key": str}))
    except Exception:
        return pd.DataFrame(columns=CACHE_COLUMNS)


def refresh_facility_matches(
    facilities: pd.DataFrame | None,
    *,
    cache_path: str | Path,
    max_workers: int = 6,
    timeout: int = 25,
    attempts: int = 3,
    persist: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Resolve uncached facility points against EPA CWS service-area polygons."""

    cache_path = Path(cache_path)
    cache = load_cache(cache_path)
    frame = facilities.copy() if isinstance(facilities, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        return cache, {"source_mode": "retained", "requested_points": 0, "queried_points": 0, "errors": {}}

    requests_by_key: dict[str, tuple[str, float, float]] = {}
    for index, row in frame.iterrows():
        latitude = pd.to_numeric(row.get("Latitude"), errors="coerce")
        longitude = pd.to_numeric(row.get("Longitude"), errors="coerce")
        if pd.isna(latitude) or pd.isna(longitude):
            continue
        facility_id = _facility_id(row, index)
        key = query_key(facility_id, float(latitude), float(longitude))
        requests_by_key[key] = (facility_id, float(latitude), float(longitude))

    resolved_status = cache.get("Query Status", pd.Series(dtype=str)).fillna("").astype(str).isin({"matched", "no_match"})
    resolved_keys = set(cache.loc[resolved_status, "Query Key"].astype(str)) if not cache.empty else set()
    pending = {key: value for key, value in requests_by_key.items() if key not in resolved_keys}

    new_rows: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=max(1, min(int(max_workers), 12))) as executor:
            futures = {
                executor.submit(
                    _request_one,
                    facility_id=facility_id,
                    latitude=latitude,
                    longitude=longitude,
                    timeout=timeout,
                    attempts=attempts,
                ): key
                for key, (facility_id, latitude, longitude) in pending.items()
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    rows = future.result()
                except Exception as exc:  # defensive; _request_one normally contains provider errors
                    rows = []
                    errors[key] = f"{type(exc).__name__}: {exc}"
                new_rows.extend(rows)
                for row in rows:
                    status = str(row.get("Query Status") or "")
                    if status.startswith("error:"):
                        errors[key] = status.removeprefix("error:").strip()

    if pending and not cache.empty:
        cache = cache.loc[~cache["Query Key"].astype(str).isin(pending)].copy()
    additions = normalize_cache(pd.DataFrame(new_rows)) if new_rows else pd.DataFrame(columns=CACHE_COLUMNS)
    output = pd.concat([cache, additions], ignore_index=True) if not cache.empty or not additions.empty else pd.DataFrame(columns=CACHE_COLUMNS)
    output = normalize_cache(output)
    if not output.empty:
        output = output.sort_values(["Facility ID", "Query Key", "PWSID"], kind="stable").reset_index(drop=True)

    if persist:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_csv(output, cache_path, compression="gzip")

    report = {
        "source_mode": "live_refresh" if pending and not errors else "partial_refresh" if pending else "retained_cache",
        "requested_points": len(requests_by_key),
        "queried_points": len(pending),
        "cached_points": len(requests_by_key) - len(pending),
        "resolved_points": int(
            output.loc[output["Query Status"].isin(["matched", "no_match"]), "Query Key"].nunique()
        ) if not output.empty else 0,
        "matched_points": int(
            output.loc[output["Query Status"].eq("matched") & output["PWSID"].fillna("").astype(str).ne(""), "Query Key"].nunique()
        ) if not output.empty else 0,
        "errors": errors,
    }
    return output, report
