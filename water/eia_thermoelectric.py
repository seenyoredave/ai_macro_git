from __future__ import annotations

import calendar
from pathlib import Path

import pandas as pd

from water.ledger import normalize_observations

PARSER_VERSION = "eia-thermoelectric-2024-v1.0"
SOURCE_ID = "eia-thermoelectric-cooling-water-2024-summary"
WITHDRAWAL_COLUMN = "Water Withdrawal Volume (Million Gallons)"
CONSUMPTION_COLUMN = "Water Consumption Volume (Million Gallons)"

SOURCE_MAP = {
    "Surface": "surface_water",
    "Ground": "groundwater",
    "Discharge": "reclaimed_wastewater",
    "Mixed": "mixed",
    "Other": "other",
}
QUALITY_MAP = {
    "Fresh": "fresh",
    "Saline": "saline",
    "Brackish": "brackish",
    "Reclaimed": "reclaimed",
    "Mixed": "mixed",
    "Other": "other",
}

def load_raw_frame(path: str | Path) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name="Summary", header=2, dtype=object, engine="openpyxl")
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"Plant Code", "Plant Name", "State", "Year", "Month", WITHDRAWAL_COLUMN, CONSUMPTION_COLUMN}
    if not required.issubset(frame.columns):
        raise ValueError(f"EIA cooling-water contract changed; missing {sorted(required - set(frame.columns))}")
    for column in [WITHDRAWAL_COLUMN, CONSUMPTION_COLUMN]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["Year"] = pd.to_numeric(frame["Year"], errors="coerce").astype("Int64")
    frame["Month"] = pd.to_numeric(frame["Month"], errors="coerce").astype("Int64")
    return frame

def _quality_flag(withdrawal, consumption) -> str:
    flags = []
    if pd.notna(withdrawal) and withdrawal < 0:
        flags.append("negative_withdrawal")
    if pd.notna(consumption) and consumption < 0:
        flags.append("negative_consumption")
    if pd.notna(withdrawal) and pd.notna(consumption) and consumption > withdrawal:
        flags.append("consumption_exceeds_withdrawal")
    return ";".join(flags)

def normalize_observation_ledger(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row_number, (_, row) in enumerate(raw.iterrows(), start=4):
        year = int(row["Year"])
        month = int(row["Month"])
        start = pd.Timestamp(year=year, month=month, day=1)
        end = pd.Timestamp(year=year, month=month, day=calendar.monthrange(year, month)[1])
        plant_numeric = pd.to_numeric(row.get("Plant Code"), errors="coerce")
        plant_code = str(int(plant_numeric)) if pd.notna(plant_numeric) else str(row.get("Plant Code") or "").strip()
        generator = str(row.get("Generator ID") or "").strip()
        boiler = str(row.get("Boiler ID") or "").strip()
        cooling = str(row.get("Cooling ID") or "").strip()
        source_category = SOURCE_MAP.get(str(row.get("Water Source") or "").strip(), "unknown")
        quality = QUALITY_MAP.get(str(row.get("Water Type") or "").strip(), "unknown")
        withdrawal = pd.to_numeric(row.get(WITHDRAWAL_COLUMN), errors="coerce")
        consumption = pd.to_numeric(row.get(CONSUMPTION_COLUMN), errors="coerce")
        flag = _quality_flag(withdrawal, consumption)
        for flow_type, value, column in [
            ("withdrawal", withdrawal, WITHDRAWAL_COLUMN),
            ("consumptive_use", consumption, CONSUMPTION_COLUMN),
        ]:
            if pd.isna(value):
                continue
            rows.append({
                "observation_id": f"{SOURCE_ID}:{plant_code}:{year}-{month:02d}:{generator}:{boiler}:{cooling}:{flow_type}",
                "entity_id": f"eia:plant:{plant_code}",
                "site_id": f"eia:cooling:{plant_code}:{cooling}:{boiler}:{generator}",
                "geography_type": "power_plant",
                "geography_id": plant_code,
                "state": str(row.get("State") or "").strip(),
                "county": "",
                "period_start": start,
                "period_end": end,
                "temporal_resolution": "monthly",
                "flow_type": flow_type,
                "original_value": float(value),
                "original_unit": "million gallons",
                "volume_million_gallons": float(value),
                "average_mgd": float(value) / end.days_in_month,
                "source_category": source_category,
                "water_quality_class": quality,
                "use_category": "thermoelectric_power",
                "measurement_basis": "reported_estimate",
                "evidence_class": "reported",
                "source_id": SOURCE_ID,
                "source_record_id": f"row-{row_number}:{column}",
                "retrieved_at": "2026-07-31",
                "source_revision_date": pd.NaT,
                "method_version": PARSER_VERSION,
                "quality_flag": flag,
                "confidence_grade": "A" if not flag else "A-flagged",
                "missing_reason": "",
            })
    return normalize_observations(pd.DataFrame(rows))

def plant_summary(raw: pd.DataFrame) -> pd.DataFrame:
    frame = raw.copy()
    for column in [WITHDRAWAL_COLUMN, CONSUMPTION_COLUMN]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame["Quality Flag"] = [
        _quality_flag(withdrawal, consumption)
        for withdrawal, consumption in zip(frame[WITHDRAWAL_COLUMN], frame[CONSUMPTION_COLUMN])
    ]
    def joined(series):
        values = sorted({str(value).strip() for value in series.dropna() if str(value).strip()})
        return " / ".join(values)
    output = frame.groupby(["Plant Code", "Plant Name", "State"], dropna=False).agg(
        **{
            "Withdrawal Million Gallons": (WITHDRAWAL_COLUMN, lambda x: x.sum(min_count=1)),
            "Consumption Million Gallons": (CONSUMPTION_COLUMN, lambda x: x.sum(min_count=1)),
            "Withdrawal Records": (WITHDRAWAL_COLUMN, "count"),
            "Consumption Records": (CONSUMPTION_COLUMN, "count"),
            "Water Type": ("Water Type", joined),
            "Water Source": ("Water Source", joined),
            "Cooling System": ("Cooling System Type", joined),
            "Quality Flags": ("Quality Flag", lambda x: joined(x[x.astype(str).str.len() > 0])),
        }
    ).reset_index()
    output["Withdrawal Bgal/day"] = output["Withdrawal Million Gallons"] / 365000.0
    output["Consumption Bgal/day"] = output["Consumption Million Gallons"] / 365000.0
    return output

def group_summary(raw: pd.DataFrame, field: str) -> pd.DataFrame:
    if field not in {"Water Type", "Water Source", "Cooling System Type", "State"}:
        raise ValueError(f"Unsupported EIA grouping: {field}")
    frame = raw.copy()
    frame[field] = frame[field].fillna("Unknown").replace("", "Unknown")
    output = frame.groupby(field, dropna=False).agg(
        **{
            "Withdrawal Million Gallons": (WITHDRAWAL_COLUMN, lambda x: pd.to_numeric(x, errors="coerce").sum(min_count=1)),
            "Consumption Million Gallons": (CONSUMPTION_COLUMN, lambda x: pd.to_numeric(x, errors="coerce").sum(min_count=1)),
            "Plants": ("Plant Code", "nunique"),
            "Records": ("Plant Code", "size"),
        }
    ).reset_index().rename(columns={field: "Group"})
    output["Grouping"] = field
    output["Withdrawal Bgal/day"] = output["Withdrawal Million Gallons"] / 365000.0
    output["Consumption Bgal/day"] = output["Consumption Million Gallons"] / 365000.0
    return output

def national_summary(raw: pd.DataFrame) -> dict:
    withdrawal = pd.to_numeric(raw[WITHDRAWAL_COLUMN], errors="coerce")
    consumption = pd.to_numeric(raw[CONSUMPTION_COLUMN], errors="coerce")
    flags = pd.Series([_quality_flag(w, c) for w, c in zip(withdrawal, consumption)])
    plant_withdrawal = raw.loc[withdrawal.notna(), "Plant Code"].nunique()
    plant_consumption = raw.loc[consumption.notna(), "Plant Code"].nunique()
    return {
        "year": 2024,
        "records": int(len(raw)),
        "plants": int(raw["Plant Code"].nunique()),
        "plants_with_withdrawal": int(plant_withdrawal),
        "plants_with_consumption": int(plant_consumption),
        "withdrawal_million_gallons": float(withdrawal.sum(min_count=1)),
        "consumption_million_gallons": float(consumption.sum(min_count=1)),
        "withdrawal_bgal_day": float(withdrawal.sum(min_count=1) / 365000.0),
        "consumption_bgal_day": float(consumption.sum(min_count=1) / 365000.0),
        "flagged_records": int(flags.astype(bool).sum()),
        "consumption_exceeds_withdrawal_records": int(flags.str.contains("consumption_exceeds_withdrawal", na=False).sum()),
        "negative_consumption_records": int(flags.str.contains("negative_consumption", na=False).sum()),
    }
