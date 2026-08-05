from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from loaders.census import clean_header, parse_census_month
from loaders.data_center_inventory_loader import build_data_center_national_database, load_data_center_inventory
from loaders.facility_registry_loader import normalize_us_state

RAW = ROOT / "data" / "infrastructure" / "raw"
DERIVED = ROOT / "data" / "infrastructure" / "derived"
CONSTRUCTION_OUTPUT = ROOT / "data" / "infrastructure_construction_history.csv"
SOURCE_MANIFEST = ROOT / "data" / "infrastructure" / "source_manifest.csv"

PRIVATE_PATH = RAW / "census" / "privsatime.xlsx"
PUBLIC_PATH = RAW / "census" / "pubsatime.xlsx"
GIGAWATT_PATH = RAW / "gigawattmap" / "datacenters.csv"
COMPUTE_HISTORY = DERIVED / "compute_manufacturing_history.csv"
COMPUTE_SERIES_CONTRACT = DERIVED / "compute_series_contract.csv"
COMPUTE_SERIES_VALIDATION = DERIVED / "compute_series_validation.csv"
COMPUTE_PROJECTS = DERIVED / "compute_project_ledger.csv"
GIGAWATT_VERIFIED_PROJECTS = DERIVED / "gigawatt_verified_us_projects.csv"
G17_RELEASE_PDF = RAW / "federal_reserve" / "g17_2026-07-17.pdf"
G17_LATEST_SNAPSHOT = RAW / "federal_reserve" / "g17_compute_latest_observations_2026-07-17.csv"
FRACTRACKER_NATIONAL = RAW / "fractracker" / "us_national_stage_2026-06-03.csv"
FRACTRACKER_STATES = RAW / "fractracker" / "us_state_stage_2026-03-26.csv"
FRACTRACKER_FACILITIES = RAW / "fractracker" / "data_center_facilities_latest.csv"
PEW_REGIONS = RAW / "pew" / "us_region_stage_2026-02-19.csv"
PEW_TOP_STATES = RAW / "pew" / "us_top15_state_stage_2026-02-19.csv"
DATA_CENTER_DATABASE = DERIVED / "data_center_national_database.csv"

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

def checksum(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def parse_census(path: Path, *, sheet: str, series: dict[str, str]) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    raw = pd.read_excel(BytesIO(path.read_bytes()), sheet_name=sheet, header=3, engine="openpyxl")
    raw.columns = [clean_header(column) for column in raw.columns]
    required = ["Date", *series]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise ValueError(f"Census source contract changed; missing {missing}")
    output = raw[required].copy().rename(columns=series)
    output["Observation Date"] = output.pop("Date").map(parse_census_month)
    for column in series.values():
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")

def rebuild_construction() -> pd.DataFrame:
    private = parse_census(PRIVATE_PATH, sheet="Private SA", series=PRIVATE_SERIES)
    public = parse_census(PUBLIC_PATH, sheet="Public SA", series=PUBLIC_SERIES)
    output = private.merge(public, on="Observation Date", how="outer")
    output = output.sort_values("Observation Date", kind="stable").drop_duplicates("Observation Date", keep="last")
    for column in PUBLIC_SERIES.values():
        values = pd.to_numeric(output[column], errors="coerce")
        positive = values.gt(0)
        if positive.any():
            first_positive = positive.idxmax()
            output.loc[output.index < first_positive, column] = np.nan
    export = output.copy()
    export["Observation Date"] = export["Observation Date"].dt.date.astype(str)
    export.to_csv(CONSTRUCTION_OUTPUT, index=False)
    return output

def validate_gigawatt() -> pd.DataFrame:
    if not GIGAWATT_PATH.exists():
        raise FileNotFoundError(GIGAWATT_PATH)
    frame = pd.read_csv(GIGAWATT_PATH)
    required = {
        "id", "name", "lon", "lat", "confidence", "country", "region",
        "status", "source_url", "sources", "mw_source",
        "est_mw_low", "est_mw_mid", "est_mw_high",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Gigawatt source contract changed; missing {sorted(missing)}")
    if frame["id"].duplicated().any():
        raise ValueError("Gigawatt source contains duplicate IDs")
    for column in ["lon", "lat", "est_mw_low", "est_mw_mid", "est_mw_high"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    bounded = frame.dropna(subset=["est_mw_low", "est_mw_mid", "est_mw_high"])
    invalid_bounds = bounded.loc[
        (bounded["est_mw_low"] > bounded["est_mw_mid"])
        | (bounded["est_mw_mid"] > bounded["est_mw_high"])
    ]
    if not invalid_bounds.empty:
        raise ValueError("Gigawatt capacity estimate bounds are not ordered")
    frame["normalized_state"] = frame["region"].map(normalize_us_state)
    country = frame["country"].fillna("").astype(str).str.upper()
    frame["active_us_filter"] = country.eq("US") | (country.eq("XX") & frame["normalized_state"].ne(""))
    return frame

def validate_compute_history() -> pd.DataFrame:
    frame = pd.read_csv(COMPUTE_HISTORY)
    required = {
        "Observation Date",
        "Computer and Peripheral Equipment Output",
        "Communications Equipment Output",
        "Semiconductor and Electronic Component Output",
        "Computer and Peripheral Equipment Capacity Utilization",
        "Semiconductor and Electronic Component Capacity Utilization",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Compute history contract changed; missing {sorted(missing)}")
    dates = pd.to_datetime(frame["Observation Date"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("Compute history has invalid or duplicate observation dates")
    return frame

def validate_compute_series_contract() -> pd.DataFrame:
    frame = pd.read_csv(COMPUTE_SERIES_CONTRACT)
    required = {
        "metric", "display_label", "series_id", "official_title", "source_url",
        "unit", "frequency", "seasonal_adjustment", "geography",
        "evidence_grade", "interpretation_limit",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Compute series contract changed; missing {sorted(missing)}")
    expected_ids = {
        "IPG3341S", "IPG3342S", "IPG3344S",
        "CAPG3341S", "CAPG3342S", "CAPG3344S",
        "CAPUTLG3341S", "CAPUTLG3342S", "CAPUTLG3344S",
        "A34SVS", "A34SNO", "A34SIS", "A34SUS",
    }
    if set(frame["series_id"].astype(str)) != expected_ids:
        raise ValueError("Compute series contract does not contain the expected G.17 and M3 series IDs")
    if frame["metric"].duplicated().any() or frame["series_id"].duplicated().any():
        raise ValueError("Compute series contract contains duplicate metric or series IDs")
    return frame

def validate_compute_series_validation(history: pd.DataFrame, contract: pd.DataFrame) -> pd.DataFrame:
    frame = pd.read_csv(COMPUTE_SERIES_VALIDATION)
    required = {
        "series_id", "metric", "official_latest_observation_date", "official_latest_value",
        "official_release_updated_date", "retained_latest_observation_date", "retained_latest_value",
        "comparison_status", "checked_on", "source_url", "notes",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Compute latest-release validation changed; missing {sorted(missing)}")
    expected_validation_ids = {
        "IPG3341S", "IPG3342S", "IPG3344S",
        "CAPUTLG3341S", "CAPUTLG3344S",
    }
    validation_ids = set(frame["series_id"].astype(str))
    contract_ids = set(contract["series_id"].astype(str))
    if validation_ids != expected_validation_ids:
        raise ValueError("Compute latest-release validation does not contain the expected retained G.17 series IDs")
    if not validation_ids.issubset(contract_ids):
        raise ValueError("Compute latest-release validation references a series outside the compute contract")
    for _, row in frame.iterrows():
        metric = str(row["metric"])
        if metric not in history.columns:
            raise ValueError(f"Compute validation references unknown metric: {metric}")
        clean = history[["Observation Date", metric]].copy()
        clean["Observation Date"] = pd.to_datetime(clean["Observation Date"], errors="coerce")
        clean[metric] = pd.to_numeric(clean[metric], errors="coerce")
        clean = clean.dropna().sort_values("Observation Date", kind="stable")
        if clean.empty:
            raise ValueError(f"Compute validation references empty metric: {metric}")
        latest = clean.iloc[-1]
        retained_date = pd.to_datetime(row["retained_latest_observation_date"], errors="coerce")
        retained_value = pd.to_numeric(row["retained_latest_value"], errors="coerce")
        if pd.isna(retained_date) or retained_date != latest["Observation Date"]:
            raise ValueError(f"Compute validation retained date is stale for {metric}")
        if pd.isna(retained_value) or not np.isclose(float(retained_value), float(latest[metric]), rtol=0, atol=1e-8):
            raise ValueError(f"Compute validation retained value is stale for {metric}")
    return frame

def validate_compute_projects() -> pd.DataFrame:
    frame = pd.read_csv(COMPUTE_PROJECTS)
    required = {
        "Project ID", "Portfolio ID", "Recipient", "Facility", "State", "Status",
        "Component Layer", "AI Relevance", "Expected CapEx USD B", "Direct Funding USD B",
        "Source URL", "Evidence Grade", "Resilience Grade",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Compute-project contract changed; missing {sorted(missing)}")
    if frame["Project ID"].duplicated().any():
        raise ValueError("Compute project ledger contains duplicate Project IDs")

    for field in ["Expected CapEx USD B", "Available Loan USD B"]:
        counts = frame.groupby("Portfolio ID", dropna=False)[field].apply(lambda values: pd.to_numeric(values, errors="coerce").notna().sum())
        if (counts > 1).any():
            bad = counts[counts > 1].index.tolist()
            raise ValueError(f"Duplicate {field} values within portfolios: {bad}")
    for portfolio, group in frame.groupby("Portfolio ID", dropna=False):
        values = pd.to_numeric(group["Direct Funding USD B"], errors="coerce")
        portfolio_scope = ~group["Funding Scope"].fillna("").astype(str).str.lower().eq("site allocation")
        if values.loc[portfolio_scope].notna().sum() > 1:
            raise ValueError(f"Duplicate portfolio-level direct funding within {portfolio}")
    return frame

def update_manifest() -> pd.DataFrame:
    manifest = pd.read_csv(SOURCE_MANIFEST)
    raw_mapping = {
        "census-vip-construction": [PRIVATE_PATH, PUBLIC_PATH],
        "gigawattmap-datacenters": [GIGAWATT_PATH],
        "fed-g17-compute": [G17_RELEASE_PDF, G17_LATEST_SNAPSHOT],
        "fractracker-data-center-tracker": [FRACTRACKER_NATIONAL, FRACTRACKER_STATES, FRACTRACKER_FACILITIES],
        "pew-data-center-census": [PEW_REGIONS, PEW_TOP_STATES],
    }
    derived_mapping = {
        "census-vip-construction": [CONSTRUCTION_OUTPUT],
        "gigawattmap-datacenters": [GIGAWATT_VERIFIED_PROJECTS],
        "fed-g17-compute": [COMPUTE_HISTORY, COMPUTE_SERIES_CONTRACT, COMPUTE_SERIES_VALIDATION],
        "nist-chips-projects": [COMPUTE_PROJECTS],
        "fractracker-data-center-tracker": [DATA_CENTER_DATABASE],
        "pew-data-center-census": [DATA_CENTER_DATABASE],
    }
    for column in [
        "retained_files", "sha256", "raw_path", "raw_sha256",
        "derived_artifacts", "derived_sha256",
    ]:
        if column not in manifest.columns:
            manifest[column] = ""
        manifest[column] = manifest[column].fillna("").astype(str)

    for source_id in manifest["source_id"].astype(str):
        mask = manifest["source_id"].eq(source_id)
        raw_paths = raw_mapping.get(source_id, [])
        derived_paths = derived_mapping.get(source_id, [])
        manifest.loc[mask, "retained_files"] = ";".join(str(path.relative_to(ROOT)) for path in raw_paths)
        manifest.loc[mask, "sha256"] = ";".join(checksum(path) for path in raw_paths)
        manifest.loc[mask, "raw_path"] = ";".join(str(path.relative_to(ROOT)) for path in raw_paths)
        manifest.loc[mask, "raw_sha256"] = ";".join(checksum(path) for path in raw_paths)
        manifest.loc[mask, "derived_artifacts"] = ";".join(str(path.relative_to(ROOT)) for path in derived_paths)
        manifest.loc[mask, "derived_sha256"] = ";".join(checksum(path) for path in derived_paths)

    manifest.to_csv(SOURCE_MANIFEST, index=False)
    return manifest

def main() -> None:
    construction = rebuild_construction()
    gigawatt = validate_gigawatt()
    history = validate_compute_history()
    series_contract = validate_compute_series_contract()
    series_validation = validate_compute_series_validation(history, series_contract)
    projects = validate_compute_projects()
    data_centers = load_data_center_inventory()
    national_database = build_data_center_national_database()
    if len(national_database) < 470:
        raise ValueError("National data-center evidence database lost expected geography/stage coverage")
    if int(data_centers["broad_summary"]["total"]) != 4624:
        raise ValueError("Broad data-center census no longer reconciles to 4,624 facilities")
    if int(data_centers["open_tracker_summary"]["tracked_sites"]) != 1523:
        raise ValueError("Open data-center tracker no longer reconciles to 1,523 sites")
    manifest = update_manifest()
    print(
        "Infrastructure ledger rebuilt:",
        f"{len(construction):,} construction months;",
        f"{len(gigawatt):,} retained third-party source rows;",
        f"{int((gigawatt['active_us_filter'] & gigawatt['confidence'].fillna('').astype(str).str.lower().eq('verified')).sum()):,} verified U.S. project rows active as a bounded secondary layer;",
        f"{int((gigawatt['active_us_filter'] & ~gigawatt['confidence'].fillna('').astype(str).str.lower().eq('verified')).sum()):,} footprint-only open-geospatial U.S. rows;",
        f"{len(history):,} compute observations;",
        f"{len(series_contract):,} contracted G.17 series;",
        f"{int(series_validation['comparison_status'].ne('pass_current').sum()):,} latest-release mismatches;",
        f"{len(projects):,} official compute project records;",
        f"{int(data_centers['broad_summary']['total']):,} broad-census data-center facilities;",
        f"{int(data_centers['open_tracker_summary']['tracked_sites']):,} open-tracker sites;",
        f"{len(national_database):,} national evidence rows;",
        f"{len(manifest):,} source-register rows.",
    )

if __name__ == "__main__":
    main()
