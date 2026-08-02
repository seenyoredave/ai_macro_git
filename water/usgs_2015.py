from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from water.ledger import normalize_observations
from water.strict_xlsx import read_first_sheet

PARSER_VERSION = "usgs-2015-v1.0"
SOURCE_ID = "usgs-county-water-use-2015-v2"

CATEGORY_PREFIXES = {
    "public_supply": "PS",
    "domestic_self_supply": "DO",
    "industrial_self_supply": "IN",
    "irrigation": "IR",
    "livestock": "LI",
    "aquaculture": "AQ",
    "mining": "MI",
    "thermoelectric_power": "PT",
}

WITHDRAWAL_COMPONENTS = {
    "public_supply": {
        ("groundwater", "fresh"): "PS-WGWFr",
        ("groundwater", "saline"): "PS-WGWSa",
        ("surface_water", "fresh"): "PS-WSWFr",
        ("surface_water", "saline"): "PS-WSWSa",
    },
    "domestic_self_supply": {
        ("groundwater", "fresh"): "DO-WGWFr",
        ("surface_water", "fresh"): "DO-WSWFr",
    },
    "industrial_self_supply": {
        ("groundwater", "fresh"): "IN-WGWFr",
        ("groundwater", "saline"): "IN-WGWSa",
        ("surface_water", "fresh"): "IN-WSWFr",
        ("surface_water", "saline"): "IN-WSWSa",
    },
    "irrigation": {
        ("groundwater", "fresh"): "IR-WGWFr",
        ("surface_water", "fresh"): "IR-WSWFr",
    },
    "livestock": {
        ("groundwater", "fresh"): "LI-WGWFr",
        ("surface_water", "fresh"): "LI-WSWFr",
    },
    "aquaculture": {
        ("groundwater", "fresh"): "AQ-WGWFr",
        ("groundwater", "saline"): "AQ-WGWSa",
        ("surface_water", "fresh"): "AQ-WSWFr",
        ("surface_water", "saline"): "AQ-WSWSa",
    },
    "mining": {
        ("groundwater", "fresh"): "MI-WGWFr",
        ("groundwater", "saline"): "MI-WGWSa",
        ("surface_water", "fresh"): "MI-WSWFr",
        ("surface_water", "saline"): "MI-WSWSa",
    },
    "thermoelectric_power": {
        ("groundwater", "fresh"): "PT-WGWFr",
        ("groundwater", "saline"): "PT-WGWSa",
        ("surface_water", "fresh"): "PT-WSWFr",
        ("surface_water", "saline"): "PT-WSWSa",
    },
}

CONSUMPTIVE_COMPONENTS = {
    "irrigation": {("unknown", "fresh"): "IR-CUsFr"},
    "thermoelectric_power": {
        ("unknown", "fresh"): "PT-CUsFr",
        ("unknown", "saline"): "PT-CUsSa",
    },
}

OFFICIAL_CATEGORY_TOTAL_COLUMNS = {
    "public_supply": "PS-Wtotl",
    "domestic_self_supply": "DO-WFrTo",
    "industrial_self_supply": "IN-Wtotl",
    "irrigation": "IR-WFrTo",
    "livestock": "LI-WFrTo",
    "aquaculture": "AQ-Wtotl",
    "mining": "MI-Wtotl",
    "thermoelectric_power": "PT-Wtotl",
}

def load_raw_county_frame(path: str | Path) -> pd.DataFrame:
    frame = read_first_sheet(path)
    if frame.empty:
        return frame
    frame.columns = [str(column).strip() for column in frame.columns]
    required = {"STATE", "COUNTY", "FIPS", "YEAR", "TO-Wtotl"}
    if not required.issubset(frame.columns):
        raise ValueError(f"USGS workbook contract changed; missing {sorted(required - set(frame.columns))}")
    frame["FIPS"] = frame["FIPS"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(5)
    frame["YEAR"] = pd.to_numeric(frame["YEAR"], errors="coerce").astype("Int64")
    numeric_columns = sorted(
        set(
            ["TO-WGWFr", "TO-WGWSa", "TO-WGWTo", "TO-WSWFr", "TO-WSWSa", "TO-WSWTo", "TO-WFrTo", "TO-WSaTo", "TO-Wtotl", "TO-CUsFrPartial", "TO-CUsSaPartial", "TO-CUTotPartial"]
            + list(OFFICIAL_CATEGORY_TOTAL_COLUMNS.values())
            + [column for group in WITHDRAWAL_COMPONENTS.values() for column in group.values()]
            + [column for group in CONSUMPTIVE_COMPONENTS.values() for column in group.values()]
        )
    )
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column].replace("--", pd.NA), errors="coerce")
    return frame

def _observation_row(row, *, flow_type, use_category, source_category, quality, column, row_number):
    value = pd.to_numeric(row.get(column), errors="coerce")
    if pd.isna(value):
        return None
    year = int(row["YEAR"])
    fips = str(row["FIPS"]).zfill(5)
    return {
        "observation_id": f"{SOURCE_ID}:{fips}:{flow_type}:{use_category}:{source_category}:{quality}",
        "entity_id": f"aggregate:county:{fips}",
        "site_id": "",
        "geography_type": "county",
        "geography_id": fips,
        "state": str(row.get("STATE") or ""),
        "county": str(row.get("COUNTY") or ""),
        "period_start": f"{year}-01-01",
        "period_end": f"{year}-12-31",
        "temporal_resolution": "annual average daily rate",
        "flow_type": flow_type,
        "original_value": float(value),
        "original_unit": "million gallons per day",
        "volume_million_gallons": np.nan,
        "average_mgd": float(value),
        "source_category": source_category,
        "water_quality_class": quality,
        "use_category": use_category,
        "measurement_basis": "agency_model",
        "evidence_class": "agency_estimate",
        "source_id": SOURCE_ID,
        "source_record_id": f"row-{row_number}:{column}",
        "retrieved_at": "2026-07-31",
        "source_revision_date": "2018-06-19",
        "method_version": PARSER_VERSION,
        "quality_flag": "",
        "confidence_grade": "A",
        "missing_reason": "",
    }

def normalize_county_observations(raw: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row_number, (_, row) in enumerate(raw.iterrows(), start=2):
        for use_category, components in WITHDRAWAL_COMPONENTS.items():
            for (source_category, quality), column in components.items():
                item = _observation_row(
                    row,
                    flow_type="withdrawal",
                    use_category=use_category,
                    source_category=source_category,
                    quality=quality,
                    column=column,
                    row_number=row_number,
                )
                if item is not None:
                    rows.append(item)
        for use_category, components in CONSUMPTIVE_COMPONENTS.items():
            for (source_category, quality), column in components.items():
                item = _observation_row(
                    row,
                    flow_type="consumptive_use",
                    use_category=use_category,
                    source_category=source_category,
                    quality=quality,
                    column=column,
                    row_number=row_number,
                )
                if item is not None:
                    rows.append(item)
    return normalize_observations(pd.DataFrame(rows))

def reconciliation_table(raw: pd.DataFrame) -> pd.DataFrame:
    component_columns = [column for group in WITHDRAWAL_COMPONENTS.values() for column in group.values()]
    component_sum = raw[component_columns].sum(axis=1, min_count=1)
    reported = pd.to_numeric(raw["TO-Wtotl"], errors="coerce")
    residual = reported - component_sum
    relative = residual.abs() / reported.abs().replace(0, np.nan)
    return pd.DataFrame(
        {
            "FIPS": raw["FIPS"],
            "State": raw["STATE"],
            "County": raw["COUNTY"],
            "Component Sum Mgal/d": component_sum,
            "Official Total Mgal/d": reported,
            "Residual Mgal/d": residual,
            "Relative Residual": relative,
            "Reconciled": relative.fillna(0).le(1e-9),
        }
    )

def county_summary(raw: pd.DataFrame) -> pd.DataFrame:
    columns = ["STATE", "COUNTY", "FIPS", "YEAR", "TO-WGWTo", "TO-WSWTo", "TO-WFrTo", "TO-WSaTo", "TO-Wtotl", "TO-CUTotPartial"]
    output = raw[columns].rename(
        columns={
            "STATE": "State",
            "COUNTY": "County",
            "FIPS": "FIPS",
            "YEAR": "Year",
            "TO-WGWTo": "Groundwater Withdrawal Mgal/d",
            "TO-WSWTo": "Surface Water Withdrawal Mgal/d",
            "TO-WFrTo": "Freshwater Withdrawal Mgal/d",
            "TO-WSaTo": "Saline Withdrawal Mgal/d",
            "TO-Wtotl": "Total Withdrawal Mgal/d",
            "TO-CUTotPartial": "Partial Consumptive Use Mgal/d",
        }
    ).copy()
    return output

def category_summary(raw: pd.DataFrame, group: str = "national") -> pd.DataFrame:
    group_columns = [] if group == "national" else ["STATE"]
    rows = []
    groups = [("United States", raw)] if not group_columns else raw.groupby("STATE", dropna=False)
    for group_name, frame in groups:
        for category, total_column in OFFICIAL_CATEGORY_TOTAL_COLUMNS.items():
            components = WITHDRAWAL_COMPONENTS[category]
            row = {
                "Geography": group_name,
                "Use Category": category,
                "Total Withdrawal Mgal/d": pd.to_numeric(frame[total_column], errors="coerce").sum(min_count=1),
                "Fresh Groundwater Mgal/d": pd.to_numeric(frame[components.get(("groundwater", "fresh"), "")], errors="coerce").sum(min_count=1) if components.get(("groundwater", "fresh")) else 0.0,
                "Saline Groundwater Mgal/d": pd.to_numeric(frame[components.get(("groundwater", "saline"), "")], errors="coerce").sum(min_count=1) if components.get(("groundwater", "saline")) else 0.0,
                "Fresh Surface Water Mgal/d": pd.to_numeric(frame[components.get(("surface_water", "fresh"), "")], errors="coerce").sum(min_count=1) if components.get(("surface_water", "fresh")) else 0.0,
                "Saline Surface Water Mgal/d": pd.to_numeric(frame[components.get(("surface_water", "saline"), "")], errors="coerce").sum(min_count=1) if components.get(("surface_water", "saline")) else 0.0,
            }
            row["Component Sum Mgal/d"] = sum(row[key] for key in ["Fresh Groundwater Mgal/d", "Saline Groundwater Mgal/d", "Fresh Surface Water Mgal/d", "Saline Surface Water Mgal/d"])
            row["Residual Mgal/d"] = row["Total Withdrawal Mgal/d"] - row["Component Sum Mgal/d"]
            rows.append(row)
    return pd.DataFrame(rows)

def national_summary(raw: pd.DataFrame) -> dict:
    values = {column: pd.to_numeric(raw[column], errors="coerce").sum(min_count=1) for column in ["TO-WGWTo", "TO-WSWTo", "TO-WFrTo", "TO-WSaTo", "TO-Wtotl", "TO-CUTotPartial"]}
    total = float(values["TO-Wtotl"])
    return {
        "year": 2015,
        "county_records": int(len(raw)),
        "jurisdictions": int(raw["STATE"].nunique()),
        "total_withdrawal_mgd": total,
        "freshwater_withdrawal_mgd": float(values["TO-WFrTo"]),
        "saline_withdrawal_mgd": float(values["TO-WSaTo"]),
        "groundwater_withdrawal_mgd": float(values["TO-WGWTo"]),
        "surface_water_withdrawal_mgd": float(values["TO-WSWTo"]),
        "partial_consumptive_use_mgd": float(values["TO-CUTotPartial"]),
        "freshwater_share": float(values["TO-WFrTo"] / total) if total else np.nan,
        "groundwater_share": float(values["TO-WGWTo"] / total) if total else np.nan,
    }
