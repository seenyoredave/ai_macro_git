from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from water.schema import (
    OBSERVATION_COLUMNS,
    EVIDENCE_CLASSES,
    FLOW_TYPES,
    MEASUREMENT_BASES,
    SOURCE_CATEGORIES,
    WATER_LEDGER_VERSION,
    WATER_QUALITY_CLASSES,
)

UNIT_TO_MILLION_GALLONS = {
    "million gallons": 1.0,
    "mgal": 1.0,
    "billion gallons": 1000.0,
    "bgal": 1000.0,
    "gallons": 1e-6,
    "acre-feet": 0.325851,
    "acre foot": 0.325851,
    "cubic meters": 0.000264172052,
}

def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def volume_to_million_gallons(value, unit: str):
    numeric = pd.to_numeric(value, errors="coerce")
    normalized_unit = str(unit or "").strip().lower()
    factor = UNIT_TO_MILLION_GALLONS.get(normalized_unit)
    if pd.isna(numeric) or factor is None:
        return np.nan
    return float(numeric) * factor

def normalize_observations(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=OBSERVATION_COLUMNS)

    output = frame.copy()
    for column in OBSERVATION_COLUMNS:
        if column not in output.columns:
            output[column] = pd.NA

    for column in ["period_start", "period_end", "retrieved_at", "source_revision_date"]:
        output[column] = pd.to_datetime(output[column], errors="coerce", format="mixed")

    output["original_value"] = pd.to_numeric(output["original_value"], errors="coerce")
    output["volume_million_gallons"] = pd.to_numeric(
        output["volume_million_gallons"], errors="coerce"
    )
    missing_normalized = output["volume_million_gallons"].isna() & output["original_value"].notna()
    output.loc[missing_normalized, "volume_million_gallons"] = output.loc[missing_normalized].apply(
        lambda row: volume_to_million_gallons(row["original_value"], row["original_unit"]), axis=1
    )

    output["average_mgd"] = pd.to_numeric(output["average_mgd"], errors="coerce")
    period_days = (output["period_end"] - output["period_start"]).dt.days + 1
    computable_rate = (
        output["average_mgd"].isna()
        & output["volume_million_gallons"].notna()
        & period_days.gt(0)
    )
    output.loc[computable_rate, "average_mgd"] = (
        output.loc[computable_rate, "volume_million_gallons"] / period_days.loc[computable_rate]
    )

    for column, vocab in [
        ("flow_type", FLOW_TYPES),
        ("source_category", SOURCE_CATEGORIES),
        ("water_quality_class", WATER_QUALITY_CLASSES),
        ("measurement_basis", MEASUREMENT_BASES),
        ("evidence_class", EVIDENCE_CLASSES),
    ]:
        output[column] = output[column].astype("string").str.strip().str.lower()
        invalid = output[column].notna() & ~output[column].isin(vocab)
        if invalid.any():
            values = sorted(output.loc[invalid, column].dropna().unique().tolist())
            raise ValueError(f"Invalid {column} values: {values}")

    output["method_version"] = output["method_version"].fillna(WATER_LEDGER_VERSION)
    return output[OBSERVATION_COLUMNS].reset_index(drop=True)
