from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data" / "infrastructure" / "raw"
DERIVED_ROOT = ROOT / "data" / "infrastructure" / "derived"

FRACTRACKER_NATIONAL_PATH = RAW_ROOT / "fractracker" / "us_national_stage_2026-06-03.csv"
FRACTRACKER_STATE_PATH = RAW_ROOT / "fractracker" / "us_state_stage_2026-03-26.csv"
PEW_REGION_PATH = RAW_ROOT / "pew" / "us_region_stage_2026-02-19.csv"
PEW_TOP_STATE_PATH = RAW_ROOT / "pew" / "us_top15_state_stage_2026-02-19.csv"
NATIONAL_DATABASE_PATH = DERIVED_ROOT / "data_center_national_database.csv"

STATE_ABBREVIATIONS = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}

def _read_csv(path: Path, required: set[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        raise FileNotFoundError(f"Required retained data-center source is missing: {path}")
    frame = pd.read_csv(path)
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Data-center source contract changed for {path.name}; missing {sorted(missing)}")
    return frame

def _load_fractracker_national() -> pd.DataFrame:
    frame = _read_csv(
        FRACTRACKER_NATIONAL_PATH,
        {"Stage", "Sites", "Published MW", "Published Square Feet", "Observation Date", "Source", "Source URL"},
    ).copy()
    for column in ["Sites", "Published MW", "Published Square Feet"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["Observation Date"] = pd.to_datetime(frame["Observation Date"], errors="coerce").dt.date.astype(str)
    expected = {
        "Proposed", "Approved / under construction", "Expanding", "Operating", "Suspended", "Cancelled"
    }
    if set(frame["Stage"].astype(str)) != expected:
        raise ValueError("FracTracker national stage labels changed")
    if int(frame["Sites"].sum()) != 1523:
        raise ValueError("FracTracker retained national total no longer reconciles to 1,523 sites")
    return frame

def _load_fractracker_states() -> pd.DataFrame:
    stage_columns = [
        "Proposed", "Approved or Under Construction", "Expanding", "Operating", "Suspended", "Cancelled"
    ]
    frame = _read_csv(
        FRACTRACKER_STATE_PATH,
        {"State", "Total", *stage_columns, "Observation Date", "Source", "Source URL"},
    ).copy()
    for column in ["Total", *stage_columns]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    row_sum = frame[stage_columns].sum(axis=1)
    if not row_sum.equals(frame["Total"]):
        bad = frame.loc[row_sum.ne(frame["Total"]), "State"].tolist()
        raise ValueError(f"FracTracker state-stage rows do not reconcile: {bad}")
    if int(frame["Total"].sum()) != 1415:
        raise ValueError("FracTracker retained state snapshot no longer reconciles to 1,415 sites")
    if set(frame["State"]) != set(STATE_ABBREVIATIONS):
        raise ValueError("FracTracker state snapshot must contain exactly the 50 states")
    frame["State Code"] = frame["State"].map(STATE_ABBREVIATIONS)
    frame["Active Pipeline"] = (
        frame["Proposed"] + frame["Approved or Under Construction"] + frame["Expanding"]
    )
    frame["Observation Date"] = pd.to_datetime(frame["Observation Date"], errors="coerce").dt.date.astype(str)
    return frame

def _load_pew_regions() -> pd.DataFrame:
    frame = _read_csv(
        PEW_REGION_PATH,
        {"Region", "Operating", "Development", "Total", "Observation Date", "Source", "Source URL"},
    ).copy()
    for column in ["Operating", "Development", "Total"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    if not (frame["Operating"] + frame["Development"]).equals(frame["Total"]):
        raise ValueError("Pew regional facility totals do not reconcile")
    if int(frame["Operating"].sum()) != 3068 or int(frame["Development"].sum()) != 1556:
        raise ValueError("Pew retained regional totals no longer reconcile to the published census")
    frame["Observation Date"] = pd.to_datetime(frame["Observation Date"], errors="coerce").dt.date.astype(str)
    return frame

def _load_pew_top_states() -> pd.DataFrame:
    frame = _read_csv(
        PEW_TOP_STATE_PATH,
        {"State", "Operating", "Development", "Total", "Observation Date", "Source", "Source URL"},
    ).copy()
    for column in ["Operating", "Development", "Total"]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    if not (frame["Operating"] + frame["Development"]).equals(frame["Total"]):
        raise ValueError("Pew top-state facility totals do not reconcile")
    frame["State Code"] = frame["State"].map(STATE_ABBREVIATIONS)
    frame["Observation Date"] = pd.to_datetime(frame["Observation Date"], errors="coerce").dt.date.astype(str)
    return frame

def _long_database(
    national_stage: pd.DataFrame,
    state_stage: pd.DataFrame,
    regions: pd.DataFrame,
    top_states: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []

    def add(*, layer, level, geography, metric, value, unit, date, source, url, boundary):
        rows.append({
            "Dataset": layer,
            "Geography Level": level,
            "Geography": geography,
            "Metric": metric,
            "Value": value,
            "Unit": unit,
            "Observation Date": date,
            "Source": source,
            "Source URL": url,
            "Boundary": boundary,
        })

    for row in national_stage.to_dict("records"):
        boundary = "Open proposal-focused tracker; stage categories are source-defined and are not a complete operating-facility census."
        add(layer="Project development records", level="United States", geography="United States", metric=f"{row['Stage']} sites", value=row["Sites"], unit="facilities/projects", date=row["Observation Date"], source=row["Source"], url=row["Source URL"], boundary=boundary)
        if pd.notna(row["Published MW"]):
            add(layer="Project development records", level="United States", geography="United States", metric=f"{row['Stage']} published capacity", value=row["Published MW"], unit="MW", date=row["Observation Date"], source=row["Source"], url=row["Source URL"], boundary="Published capacity is partial and missing values remain missing; it is not energized load.")
        if pd.notna(row["Published Square Feet"]):
            add(layer="Project development records", level="United States", geography="United States", metric=f"{row['Stage']} published floor area", value=row["Published Square Feet"], unit="square feet", date=row["Observation Date"], source=row["Source"], url=row["Source URL"], boundary="Published floor area is partial and source-reported.")

    state_metrics = ["Total", "Proposed", "Approved or Under Construction", "Expanding", "Operating", "Suspended", "Cancelled", "Active Pipeline"]
    for row in state_stage.to_dict("records"):
        for metric in state_metrics:
            add(layer="Project development records", level="State", geography=row["State"], metric=metric, value=row[metric], unit="facilities/projects", date=row["Observation Date"], source=row["Source"], url=row["Source URL"], boundary="State snapshot predates the national June update and should be interpreted on its own date.")

    for row in regions.to_dict("records"):
        for metric in ["Operating", "Development", "Total"]:
            add(layer="National facility totals", level="Census region", geography=row["Region"], metric=metric, value=row[metric], unit="facilities", date=row["Observation Date"], source=row["Source"], url=row["Source URL"], boundary="Development combines under construction, planned, and land-banked sites; canceled and uncertain records excluded.")

    for row in top_states.to_dict("records"):
        for metric in ["Operating", "Development", "Total"]:
            add(layer="National facility totals", level="State", geography=row["State"], metric=metric, value=row[metric], unit="facilities", date=row["Observation Date"], source=row["Source"], url=row["Source URL"], boundary="Published top-15 state subset from the national facility analysis; not combined with project-development records.")

    output = pd.DataFrame(rows)
    output["Value"] = pd.to_numeric(output["Value"], errors="coerce")
    return output.sort_values(["Dataset", "Geography Level", "Geography", "Metric"], kind="stable").reset_index(drop=True)

def load_data_center_inventory() -> dict:
    national_stage = _load_fractracker_national()
    state_stage = _load_fractracker_states()
    regions = _load_pew_regions()
    top_states = _load_pew_top_states()
    database = _long_database(national_stage, state_stage, regions, top_states)

    broad_operating = int(regions["Operating"].sum())
    broad_development = int(regions["Development"].sum())
    broad_total = int(regions["Total"].sum())
    stage_index = national_stage.set_index("Stage")
    active_stages = ["Proposed", "Approved / under construction", "Expanding"]
    active_pipeline = int(stage_index.loc[active_stages, "Sites"].sum())
    active_pipeline_mw = float(stage_index.loc[active_stages, "Published MW"].sum(min_count=1))

    return {
        "broad_summary": {
            "operating": broad_operating,
            "development": broad_development,
            "total": broad_total,
            "development_to_operating": broad_development / broad_operating if broad_operating else np.nan,
            "observation_date": str(regions["Observation Date"].max()),
            "source": str(regions.iloc[0]["Source"]),
            "source_url": str(regions.iloc[0]["Source URL"]),
        },
        "open_tracker_summary": {
            "tracked_sites": int(national_stage["Sites"].sum()),
            "operating": int(stage_index.loc["Operating", "Sites"]),
            "operating_published_mw": float(stage_index.loc["Operating", "Published MW"]),
            "proposed": int(stage_index.loc["Proposed", "Sites"]),
            "approved_or_construction": int(stage_index.loc["Approved / under construction", "Sites"]),
            "expanding": int(stage_index.loc["Expanding", "Sites"]),
            "active_pipeline": active_pipeline,
            "active_pipeline_published_mw": active_pipeline_mw,
            "observation_date": str(national_stage["Observation Date"].max()),
            "source": str(national_stage.iloc[0]["Source"]),
            "source_url": str(national_stage.iloc[0]["Source URL"]),
        },
        "national_stage": national_stage,
        "state_stage": state_stage,
        "regions": regions,
        "top_states": top_states,
        "database": database,
        "database_path": str(NATIONAL_DATABASE_PATH.relative_to(ROOT)),
    }

def build_data_center_national_database(path: Path | None = None) -> pd.DataFrame:
    payload = load_data_center_inventory()
    output = payload["database"].copy()
    target = Path(path or NATIONAL_DATABASE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(target, index=False)
    return output
