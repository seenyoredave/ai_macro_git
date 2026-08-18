"""Campus-point overlap cache for EPA public-water service-area boundaries."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any

import pandas as pd
import requests

from helpers.atomic_io import atomic_write_csv

SERVICE_VERSION = "3.2"
QUERY_URL = "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/Water_System_Boundaries/FeatureServer/0/query"
SOURCE_URL = "https://www.epa.gov/ground-water-and-drinking-water/public-water-system-service-areas"
OUT_FIELDS = ",".join([
    "PWSID", "PWS_Name", "Primacy_Agency", "Population_Served_Count", "Service_Connections_Count",
    "Model_Method", "Service_Area_Type", "Symbology_Field", "Original_Data_Provider", "Data_Provider_Type",
    "Verification_Status", "Confirmed", "Feature_Type",
])
CACHE_COLUMNS = [
    "Query Key", "Campus ID", "Latitude", "Longitude", "PWSID", "PWS Name", "Primacy Agency",
    "Population Served", "Service Connections", "Boundary Basis", "Model Method", "Service Area Type",
    "Original Data Provider", "Data Provider Type", "Verification Status", "Boundary Confirmed Field",
    "Feature Type", "Query Status", "Service Version", "Retrieved At UTC", "Source URL",
]


def _text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.casefold() == "nan" else text


def query_key(campus_id: str, latitude: float, longitude: float) -> str:
    return f"{campus_id}|{latitude:.5f}|{longitude:.5f}|epa-pws-{SERVICE_VERSION}"


CWS_MODEL_METHODS = {"CENSUS PLACE", "DECISION TREE", "OSM", "PARCEL", "RANDOM FOREST"}


def _boundary_basis(attributes: dict[str, Any]) -> str:
    symbology = _text(attributes.get("Symbology_Field")).upper()
    if symbology == "STATE": return "authoritative"
    if symbology == "MODELED": return "modeled"
    method = _text(attributes.get("Model_Method")).upper()
    if method == "STATE": return "authoritative"
    if method in CWS_MODEL_METHODS: return "modeled"
    return "unclassified"


def _is_community_system(attributes: dict[str, Any]) -> bool:
    feature_type = _text(attributes.get("Feature_Type")).casefold()
    if feature_type:
        compact = feature_type.replace("-", " ").replace("_", " ")
        if any(token in compact for token in ("non community", "transient", "ntnc", "tncws", "tnc")): return False
        if "community" in compact or compact.strip() == "cws": return True
    if _text(attributes.get("Symbology_Field")).upper() in {"STATE", "MODELED"}: return True
    method = _text(attributes.get("Model_Method")).upper()
    return method == "STATE" or method in CWS_MODEL_METHODS


def _row(*, key: str, campus_id: str, latitude: float, longitude: float, status: str, retrieved: str, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    a = attributes or {}
    return {
        "Query Key": key, "Campus ID": campus_id, "Latitude": latitude, "Longitude": longitude,
        "PWSID": _text(a.get("PWSID")), "PWS Name": _text(a.get("PWS_Name")), "Primacy Agency": _text(a.get("Primacy_Agency")),
        "Population Served": pd.to_numeric(a.get("Population_Served_Count"), errors="coerce"),
        "Service Connections": pd.to_numeric(a.get("Service_Connections_Count"), errors="coerce"),
        "Boundary Basis": _boundary_basis(a) if a else "", "Model Method": _text(a.get("Model_Method")),
        "Service Area Type": _text(a.get("Service_Area_Type")), "Original Data Provider": _text(a.get("Original_Data_Provider")),
        "Data Provider Type": _text(a.get("Data_Provider_Type")), "Verification Status": _text(a.get("Verification_Status")),
        "Boundary Confirmed Field": _text(a.get("Confirmed")), "Feature Type": _text(a.get("Feature_Type")),
        "Query Status": status, "Service Version": SERVICE_VERSION, "Retrieved At UTC": retrieved, "Source URL": SOURCE_URL,
    }


def _request_one(*, campus_id: str, latitude: float, longitude: float, timeout: int, attempts: int) -> list[dict[str, Any]]:
    key = query_key(campus_id, latitude, longitude)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    last_error = ""
    for attempt in range(max(int(attempts), 1)):
        try:
            response = requests.get(QUERY_URL, params={
                "f":"json", "where":"1=1", "geometry":f"{longitude:.7f},{latitude:.7f}", "geometryType":"esriGeometryPoint",
                "inSR":4326, "spatialRel":"esriSpatialRelIntersects", "outFields":OUT_FIELDS, "returnGeometry":"false",
            }, timeout=timeout)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
            response.raise_for_status(); payload=response.json()
            if payload.get("error"): raise RuntimeError(str(payload["error"]))
            rows=[]
            for feature in list(payload.get("features") or []):
                attributes=dict((feature or {}).get("attributes") or {})
                if _is_community_system(attributes): rows.append(_row(key=key,campus_id=campus_id,latitude=latitude,longitude=longitude,status="matched",retrieved=retrieved,attributes=attributes))
            return rows or [_row(key=key,campus_id=campus_id,latitude=latitude,longitude=longitude,status="no_match",retrieved=retrieved)]
        except Exception as exc:
            last_error=f"{type(exc).__name__}: {exc}"
            if attempt + 1 < max(int(attempts),1): time.sleep(min(4.0,0.6*(2**attempt)))
    return [_row(key=key,campus_id=campus_id,latitude=latitude,longitude=longitude,status=f"error: {last_error}",retrieved=retrieved)]


def normalize_cache(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=CACHE_COLUMNS)
    output=frame.copy()
    # Retained pre-v9.6 cache files used a generic ID column. It is treated only
    # as cache provenance; canonical identity always comes from the registry.
    legacy_id = "Facility ID"
    if "Campus ID" not in output.columns and legacy_id in output.columns:
        output = output.rename(columns={legacy_id:"Campus ID"})
    for column in CACHE_COLUMNS:
        if column not in output.columns: output[column]=""
    for column in ("Latitude","Longitude","Population Served","Service Connections"):
        output[column]=pd.to_numeric(output[column],errors="coerce")
    return output[CACHE_COLUMNS]


def load_cache(path: str | Path) -> pd.DataFrame:
    source=Path(path)
    if not source.exists() or not source.stat().st_size: return pd.DataFrame(columns=CACHE_COLUMNS)
    try: return normalize_cache(pd.read_csv(source,dtype={"PWSID":str,"Query Key":str}))
    except Exception: return pd.DataFrame(columns=CACHE_COLUMNS)


def refresh_campus_matches(campuses: pd.DataFrame | None, *, cache_path: str | Path, max_workers: int = 6, timeout: int = 25, attempts: int = 3, persist: bool = True) -> tuple[pd.DataFrame, dict]:
    cache_path=Path(cache_path); cache=load_cache(cache_path); frame=campuses.copy() if isinstance(campuses,pd.DataFrame) else pd.DataFrame()
    if frame.empty: return cache,{"source_mode":"retained","requested_points":0,"queried_points":0,"errors":{}}
    if "Campus ID" not in frame.columns or frame["Campus ID"].duplicated().any():
        raise ValueError("EPA PWS refresh requires one row per canonical Campus ID")
    requests_by_key: dict[str,tuple[str,float,float]]={}
    for _,row in frame.iterrows():
        lat=pd.to_numeric(row.get("Latitude"),errors="coerce"); lon=pd.to_numeric(row.get("Longitude"),errors="coerce"); campus_id=_text(row.get("Campus ID"))
        if not campus_id or pd.isna(lat) or pd.isna(lon): continue
        key=query_key(campus_id,float(lat),float(lon)); requests_by_key[key]=(campus_id,float(lat),float(lon))
    resolved_status=cache.get("Query Status",pd.Series(dtype=str)).fillna("").astype(str).isin({"matched","no_match"}); resolved_keys=set(cache.loc[resolved_status,"Query Key"].astype(str)) if not cache.empty else set(); pending={k:v for k,v in requests_by_key.items() if k not in resolved_keys}
    new_rows=[]; errors={}
    if pending:
        with ThreadPoolExecutor(max_workers=max(1,min(int(max_workers),12))) as executor:
            futures={executor.submit(_request_one,campus_id=campus_id,latitude=lat,longitude=lon,timeout=timeout,attempts=attempts):key for key,(campus_id,lat,lon) in pending.items()}
            for future in as_completed(futures):
                key=futures[future]
                try: rows=future.result()
                except Exception as exc: rows=[]; errors[key]=f"{type(exc).__name__}: {exc}"
                new_rows.extend(rows)
                for row in rows:
                    status=str(row.get("Query Status") or "")
                    if status.startswith("error:"): errors[key]=status.removeprefix("error:").strip()
    if pending and not cache.empty: cache=cache.loc[~cache["Query Key"].astype(str).isin(pending)].copy()
    additions=normalize_cache(pd.DataFrame(new_rows)) if new_rows else pd.DataFrame(columns=CACHE_COLUMNS); output=normalize_cache(pd.concat([cache,additions],ignore_index=True) if not cache.empty or not additions.empty else None)
    if not output.empty: output=output.sort_values(["Campus ID","Query Key","PWSID"],kind="stable").reset_index(drop=True)
    if persist: cache_path.parent.mkdir(parents=True,exist_ok=True); atomic_write_csv(output,cache_path,compression="gzip")
    report={"source_mode":"live_refresh" if pending and not errors else "partial_refresh" if pending else "retained_cache","requested_points":len(requests_by_key),"queried_points":len(pending),"cached_points":len(requests_by_key)-len(pending),"resolved_points":int(output.loc[output["Query Status"].isin(["matched","no_match"]),"Query Key"].nunique()) if not output.empty else 0,"matched_points":int(output.loc[output["Query Status"].eq("matched") & output["PWSID"].fillna("").astype(str).ne(""),"Query Key"].nunique()) if not output.empty else 0,"errors":errors}
    return output,report


__all__=["SERVICE_VERSION","QUERY_URL","SOURCE_URL","CACHE_COLUMNS","query_key","normalize_cache","load_cache","refresh_campus_matches"]
