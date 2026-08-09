from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DEFAULT_TIMEOUT = 30


def fetch_fred_series(
    series_id: str,
    *,
    start_date: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> pd.DataFrame:
    """Return one official FRED series as Date/Value after contract validation."""
    params = {"id": str(series_id).strip()}
    if start_date:
        params["cosd"] = str(start_date)
    response = requests.get(
        FRED_CSV_URL,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "ai-macro-domain-refresh/1.0"},
    )
    response.raise_for_status()
    raw = pd.read_csv(BytesIO(response.content))
    date_column = next(
        (column for column in ("DATE", "observation_date", "Date") if column in raw.columns),
        None,
    )
    value_column = series_id if series_id in raw.columns else next(
        (column for column in raw.columns if column != date_column),
        None,
    )
    if date_column is None or value_column is None:
        raise ValueError(f"FRED contract changed for {series_id}; Date/Value columns not found")
    output = pd.DataFrame(
        {
            "Date": pd.to_datetime(raw[date_column], errors="coerce", format="mixed"),
            "Value": pd.to_numeric(raw[value_column], errors="coerce"),
        }
    )
    return (
        output.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )


def refresh_templated_history(
    path: str | Path,
    *,
    series_id_column: str = "Series ID",
    date_column: str = "Date",
    value_column: str = "Value",
    start_date: str | None = None,
    required_columns: Iterable[str] = (),
) -> tuple[pd.DataFrame, dict]:
    """Refresh every series represented in a retained long-form history.

    The retained row for each series supplies stable labels and units. Successfully
    refreshed series replace their prior chronology; failed series remain intact.
    """
    target = Path(path)
    retained = pd.read_csv(target) if target.exists() and target.stat().st_size else pd.DataFrame()
    required = {series_id_column, date_column, value_column, *required_columns}
    if retained.empty or not required.issubset(retained.columns):
        missing = sorted(required - set(retained.columns))
        raise ValueError(f"Refresh template is unavailable for {target.name}; missing {missing}")

    templates = (
        retained.loc[retained[series_id_column].fillna("").astype(str).str.strip().ne("")]
        .sort_values([series_id_column, date_column], kind="stable")
        .drop_duplicates(series_id_column, keep="last")
    )
    refreshed_frames: list[pd.DataFrame] = []
    successful: list[str] = []
    errors: dict[str, str] = {}

    for _, template in templates.iterrows():
        series_id = str(template[series_id_column]).strip()
        try:
            fetched = fetch_fred_series(series_id, start_date=start_date)
            if fetched.empty:
                raise ValueError("source returned no numeric observations")
            metadata = {
                column: template[column]
                for column in retained.columns
                if column not in {date_column, value_column}
            }
            output = fetched.rename(columns={"Date": date_column, "Value": value_column})
            if "Retrieved" in metadata:
                metadata["Retrieved"] = date.today().isoformat()
            for column, value in metadata.items():
                output[column] = value
            refreshed_frames.append(output[retained.columns])
            successful.append(series_id)
        except Exception as exc:
            errors[series_id] = f"{type(exc).__name__}: {exc}"

    retained_ids = retained[series_id_column].fillna("").astype(str).str.strip()
    fallback = retained.loc[~retained_ids.isin(successful)].copy()
    combined = pd.concat([fallback, *refreshed_frames], ignore_index=True, sort=False)
    combined[date_column] = pd.to_datetime(combined[date_column], errors="coerce", format="mixed")
    combined[value_column] = pd.to_numeric(combined[value_column], errors="coerce")
    combined = (
        combined.dropna(subset=[date_column, value_column])
        .sort_values([series_id_column, date_column], kind="stable")
        .drop_duplicates([series_id_column, date_column], keep="last")
        .reset_index(drop=True)
    )
    if repository_writes_enabled() and successful:
        persisted = combined.copy()
        persisted[date_column] = persisted[date_column].dt.date.astype(str)
        atomic_write_csv(persisted, target)

    report = {
        "source_mode": (
            "live_refresh" if successful and not errors
            else "partial_refresh" if successful
            else "retained_fallback"
        ),
        "requested_series": int(len(templates)),
        "refreshed_series": successful,
        "errors": errors,
        "returned_rows": int(len(combined)),
    }
    return combined, report


def refresh_single_series(
    path: str | Path,
    *,
    series_id: str,
    output_date_column: str,
    output_value_column: str,
    start_date: str | None = None,
) -> tuple[pd.DataFrame, dict]:
    target = Path(path)
    try:
        fetched = fetch_fred_series(series_id, start_date=start_date)
        if fetched.empty:
            raise ValueError("source returned no numeric observations")
        output = fetched.rename(
            columns={"Date": output_date_column, "Value": output_value_column}
        )
        if repository_writes_enabled():
            persisted = output.copy()
            persisted[output_date_column] = persisted[output_date_column].dt.date.astype(str)
            atomic_write_csv(persisted, target)
        return output, {
            "source_mode": "live_refresh",
            "requested_series": 1,
            "refreshed_series": [series_id],
            "errors": {},
            "returned_rows": int(len(output)),
        }
    except Exception as exc:
        if target.exists() and target.stat().st_size:
            output = pd.read_csv(target)
            output[output_date_column] = pd.to_datetime(
                output[output_date_column], errors="coerce", format="mixed"
            )
            output[output_value_column] = pd.to_numeric(
                output[output_value_column], errors="coerce"
            )
        else:
            output = pd.DataFrame(columns=[output_date_column, output_value_column])
        return output, {
            "source_mode": "retained_fallback",
            "requested_series": 1,
            "refreshed_series": [],
            "errors": {series_id: f"{type(exc).__name__}: {exc}"},
            "returned_rows": int(len(output)),
        }
