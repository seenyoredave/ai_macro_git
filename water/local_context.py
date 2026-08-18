"""Refresh and register local water-context sources used around mapped campuses."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from helpers.atomic_io import atomic_write_csv
from water.epa_pws import refresh_facility_matches
from water.schema import SOURCE_MANIFEST_COLUMNS, WATER_LEDGER_VERSION
from water.usdm_county import fetch_county_drought, persist_county_drought

ROOT = Path(__file__).resolve().parents[1]
WATER_ROOT = ROOT / "data" / "water"
DERIVED = WATER_ROOT / "derived"
MANIFEST_PATH = WATER_ROOT / "source_manifest.csv"
USDM_PATH = DERIVED / "usdm_county_drought_snapshot.csv.gz"
PWS_PATH = DERIVED / "epa_pws_facility_matches.csv.gz"


def _manifest() -> pd.DataFrame:
    if MANIFEST_PATH.exists() and MANIFEST_PATH.stat().st_size:
        frame = pd.read_csv(MANIFEST_PATH, dtype=str).fillna("")
    else:
        frame = pd.DataFrame(columns=SOURCE_MANIFEST_COLUMNS)
    for column in SOURCE_MANIFEST_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[SOURCE_MANIFEST_COLUMNS].copy()


def _upsert(frame: pd.DataFrame, source_id: str, values: dict[str, str]) -> pd.DataFrame:
    output = frame.copy()
    mask = output["source_id"].astype(str).eq(source_id) if not output.empty else pd.Series(dtype=bool)
    updates = {key: str(value or "") for key, value in values.items() if key in SOURCE_MANIFEST_COLUMNS}
    updates["source_id"] = source_id
    if mask.any():
        index = output.index[mask][0]
        for column, value in updates.items():
            output.at[index, column] = value
    else:
        row = {column: "" for column in SOURCE_MANIFEST_COLUMNS}
        row.update(updates)
        output = pd.concat([output, pd.DataFrame([row])], ignore_index=True)
    return output[SOURCE_MANIFEST_COLUMNS]


def _write_manifest(*, usdm_report: dict, pws_report: dict) -> pd.DataFrame:
    frame = _manifest()
    today = date.today().isoformat()

    usdm_mode = str(usdm_report.get("source_mode") or "")
    usdm_active = usdm_mode in {"live_refresh", "partial_refresh", "retained_fallback"} and int(usdm_report.get("county_rows", 0) or 0) > 0
    usdm_values = {
            "source_name": "U.S. Drought Monitor County Statistics",
            "custodian": "National Drought Mitigation Center / USDA / NOAA",
            "canonical_url": "https://droughtmonitor.unl.edu/DmData/DataDownload/WebServiceInfo.aspx",
            "acquisition_url": "https://usdmdataservices.unl.edu/api/CountyStatistics/GetDroughtSeverityStatisticsByAreaPercent",
            "coverage_period": "latest weekly county snapshot",
            "geographic_coverage": "U.S. counties in states represented by mapped data-center facilities",
            "data_role": "Current county drought exposure around mapped facilities",
            "evidence_grade": "A",
            "resilience_grade": "R1",
            "evidence_class": "agency_estimate",
            "source_kind": "REST API retained query snapshot",
            "license": "U.S. Drought Monitor terms; public statistics",
            "raw_retention_allowed": "yes",
            "parser_version": "usdm-county-v1.0",
            "schema_version": WATER_LEDGER_VERSION,
            "refresh_frequency": "weekly",
            "ingestion_status": "active" if usdm_active else "identified_not_ingested",
            "source_health": "retained_query_cache" if usdm_active else "identified",
            "notes": (
                "County percent-area statistics are cumulative D0-D4 exposure context. "
                "They do not establish facility water availability, shortage, or curtailment."
            ),
        }
    if int(usdm_report.get("refreshed_states", 0) or 0) > 0:
        usdm_values["retrieval_date"] = today
    frame = _upsert(frame, "usdm-county-statistics-current", usdm_values)

    pws_mode = str(pws_report.get("source_mode") or "")
    pws_resolved = int(pws_report.get("resolved_points", 0) or 0)
    pws_active = pws_resolved > 0 and pws_mode in {"live_refresh", "partial_refresh", "retained_cache"}
    pws_values = {
            "source_name": "Public Water System Service Areas, Version 3",
            "custodian": "U.S. Environmental Protection Agency",
            "canonical_url": "https://www.epa.gov/ground-water-and-drinking-water/public-water-system-service-areas",
            "acquisition_url": "https://services.arcgis.com/cJ9YHowT8TU7DUyn/ArcGIS/rest/services/Water_System_Boundaries/FeatureServer/0",
            "publication_date": "2026-03-17",
            "coverage_period": "Version 3; service data updated through 2025/2026 source vintages",
            "geographic_coverage": "Community-water-system service-area intersections for mapped facility points",
            "data_role": "Plausible public-water service geography and boundary provenance",
            "evidence_grade": "A/B",
            "resilience_grade": "R1",
            "evidence_class": "agency_estimate",
            "source_kind": "ArcGIS REST point-intersection query cache",
            "license": "U.S. government public data",
            "raw_retention_allowed": "yes",
            "parser_version": "epa-pws-v3-point-v1.1",
            "schema_version": WATER_LEDGER_VERSION,
            "refresh_frequency": "periodic",
            "ingestion_status": "active" if pws_active else "identified_not_ingested",
            "source_health": "retained_query_cache" if pws_active else "identified",
            "notes": (
                "EPA Version 3 combines community and non-community systems; Feature_Type is used when available "
                "to retain the community-water analytical layer. A point inside a service-area boundary is a "
                "geographic overlap, not proof that the facility is a customer. STATE boundaries are treated as "
                "authoritative-source overlap; MODELED boundaries remain modeled context."
            ),
        }
    if int(pws_report.get("queried_points", 0) or 0) > 0:
        pws_values["retrieval_date"] = today
    frame = _upsert(frame, "epa-pws-service-areas", pws_values)
    atomic_write_csv(frame, MANIFEST_PATH)
    return frame


def refresh_local_water_context(
    facilities: pd.DataFrame | None,
    *,
    pws_max_workers: int = 6,
) -> dict:
    """Refresh county drought and EPA service-area overlap for mapped facilities."""

    frame = facilities.copy() if isinstance(facilities, pd.DataFrame) else pd.DataFrame()
    states = (
        frame.get("State", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip().tolist()
        if not frame.empty
        else []
    )
    fresh_county, usdm_report = fetch_county_drought(states)
    retained_county = pd.DataFrame()
    if USDM_PATH.exists() and USDM_PATH.stat().st_size:
        try:
            retained_county = pd.read_csv(USDM_PATH, dtype={"FIPS": str})
        except Exception:
            retained_county = pd.DataFrame()

    requested_states = {str(value or "").upper().strip() for value in states if str(value or "").strip()}
    refreshed_states = set(fresh_county.get("State", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip()) if not fresh_county.empty else set()
    if retained_county.empty:
        county_drought = fresh_county
    elif fresh_county.empty:
        county_drought = retained_county
    else:
        keep_retained = ~retained_county.get("State", pd.Series("", index=retained_county.index)).fillna("").astype(str).str.upper().str.strip().isin(refreshed_states)
        county_drought = pd.concat([retained_county.loc[keep_retained], fresh_county], ignore_index=True)
    if not county_drought.empty:
        county_drought["FIPS"] = county_drought["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
        county_drought = county_drought.drop_duplicates("FIPS", keep="last").sort_values(["State", "FIPS"], kind="stable").reset_index(drop=True)
    if not fresh_county.empty:
        persist_county_drought(county_drought, USDM_PATH)

    retained_states = set(retained_county.get("State", pd.Series(dtype=str)).fillna("").astype(str).str.upper().str.strip()) if not retained_county.empty else set()
    unresolved_states = requested_states - refreshed_states - retained_states
    usdm_report["county_rows"] = int(len(county_drought))
    usdm_report["retained_fallback_states"] = int(len((requested_states - refreshed_states) & retained_states))
    if not fresh_county.empty and not unresolved_states and not (usdm_report.get("errors") or {}):
        usdm_report["source_mode"] = "live_refresh"
    elif not county_drought.empty:
        usdm_report["source_mode"] = "partial_refresh" if fresh_county is not None and not fresh_county.empty else "retained_fallback"

    pws_matches, pws_report = refresh_facility_matches(
        frame,
        cache_path=PWS_PATH,
        max_workers=pws_max_workers,
        persist=True,
    )
    manifest = _write_manifest(usdm_report=usdm_report, pws_report=pws_report)

    errors = {
        **{f"usdm:{key}": value for key, value in (usdm_report.get("errors") or {}).items()},
        **{f"epa_pws:{key}": value for key, value in (pws_report.get("errors") or {}).items()},
    }
    refreshed = []
    if not county_drought.empty:
        refreshed.append("usdm_county_drought")
    if int(pws_report.get("queried_points", 0) or 0) or int(pws_report.get("cached_points", 0) or 0):
        refreshed.append("epa_pws_service_area_overlap")

    component_modes = {str(usdm_report.get("source_mode") or ""), str(pws_report.get("source_mode") or "")}
    if errors or component_modes.intersection({"failed", "partial_refresh"}):
        overall_mode = "partial_refresh" if refreshed else "failed"
    elif "live_refresh" in component_modes:
        overall_mode = "live_refresh"
    elif refreshed:
        overall_mode = "retained_cache"
    else:
        overall_mode = "failed"

    return {
        "usdm_county_drought": county_drought,
        "epa_pws_matches": pws_matches,
        "source_manifest": manifest,
        "report": {
            "source_mode": overall_mode,
            "refreshed_datasets": refreshed,
            "usdm_county": usdm_report,
            "epa_pws": pws_report,
            "errors": errors,
        },
    }
