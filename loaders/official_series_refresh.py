from __future__ import annotations

from datetime import date
from io import BytesIO
import os
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
DEFAULT_TIMEOUT = 30
AUTOMATION_TIMEOUT = 12


def _request_timeout(timeout: int | None = None) -> int:
    if timeout is not None:
        return max(1, int(timeout))
    if str(os.getenv("AI_MACRO_MODE", "") or "").strip().lower() == "automation":
        return AUTOMATION_TIMEOUT
    return DEFAULT_TIMEOUT


def _parse_fred_response(content: bytes, series_ids: list[str]) -> dict[str, pd.DataFrame]:
    raw = pd.read_csv(BytesIO(content))
    date_column = next(
        (column for column in ("DATE", "observation_date", "Date") if column in raw.columns),
        None,
    )
    if date_column is None:
        raise ValueError("FRED contract changed; observation date column not found")

    dates = pd.to_datetime(raw[date_column], errors="coerce", format="mixed")
    output: dict[str, pd.DataFrame] = {}
    for series_id in series_ids:
        if series_id not in raw.columns:
            continue
        frame = pd.DataFrame(
            {
                "Date": dates,
                "Value": pd.to_numeric(raw[series_id], errors="coerce"),
            }
        )
        output[series_id] = (
            frame.dropna(subset=["Date", "Value"])
            .sort_values("Date", kind="stable")
            .drop_duplicates("Date", keep="last")
            .reset_index(drop=True)
        )
    return output


def fetch_fred_series_batch(
    series_ids: Iterable[str],
    *,
    start_date: str | None = None,
    timeout: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Return multiple official FRED series with one network request.

    The graph CSV endpoint accepts comma-separated series IDs.  Batching keeps
    unattended refreshes from paying one full network timeout per retained
    series when FRED is slow or unreachable.
    """
    ids = list(dict.fromkeys(str(series_id).strip() for series_id in series_ids if str(series_id).strip()))
    if not ids:
        return {}
    params = {"id": ",".join(ids)}
    if start_date:
        params["cosd"] = str(start_date)
    response = requests.get(
        FRED_CSV_URL,
        params=params,
        timeout=_request_timeout(timeout),
        headers={"User-Agent": "ai-macro-domain-refresh/1.1"},
    )
    response.raise_for_status()
    return _parse_fred_response(response.content, ids)


def fetch_fred_series(
    series_id: str,
    *,
    start_date: str | None = None,
    timeout: int | None = None,
) -> pd.DataFrame:
    """Return one official FRED series as Date/Value after contract validation."""
    clean_id = str(series_id).strip()
    result = fetch_fred_series_batch(
        [clean_id],
        start_date=start_date,
        timeout=timeout,
    ).get(clean_id)
    if result is None:
        raise ValueError(f"FRED contract changed for {clean_id}; series column not found")
    return result


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

    The retained row for each series supplies stable labels and units.  All
    represented FRED series are fetched in one request; successfully returned
    series replace their prior chronology while missing/failed series remain
    intact from retained state.
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
    series_ids = [str(value).strip() for value in templates[series_id_column].tolist()]
    refreshed_frames: list[pd.DataFrame] = []
    successful: list[str] = []
    errors: dict[str, str] = {}

    try:
        fetched_by_series = fetch_fred_series_batch(series_ids, start_date=start_date)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        fetched_by_series = {}
        errors.update({series_id: message for series_id in series_ids})

    template_rows = {
        str(row[series_id_column]).strip(): row
        for _, row in templates.iterrows()
    }
    for series_id in series_ids:
        fetched = fetched_by_series.get(series_id)
        if fetched is None or fetched.empty:
            errors.setdefault(series_id, "ValueError: source returned no numeric observations")
            continue
        template = template_rows[series_id]
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
        errors.pop(series_id, None)

    retained_ids = retained[series_id_column].fillna("").astype(str).str.strip()
    fallback = retained.loc[~retained_ids.isin(successful)].copy()
    concat_parts = [frame for frame in [fallback, *refreshed_frames] if frame is not None and not frame.empty]
    combined = (
        pd.concat(concat_parts, ignore_index=True, sort=False)
        if concat_parts
        else retained.iloc[0:0].copy()
    )
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
        "network_requests": 1 if series_ids else 0,
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
            "network_requests": 1,
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
            "network_requests": 1,
        }
