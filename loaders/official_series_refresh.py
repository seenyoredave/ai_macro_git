from __future__ import annotations

from datetime import date
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import os
from pathlib import Path
import threading
import time
from typing import Iterable

import pandas as pd
import requests

from config.deployment import repository_writes_enabled
from helpers.atomic_io import atomic_write_csv

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FRED_API_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_TIMEOUT = 30
AUTOMATION_TIMEOUT = 12
_API_LOCK = threading.Lock()
_API_NEXT_REQUEST = 0.0


class FredSeriesBatch(dict):
    """Successful series plus individual failures; failed series are never erased."""

    def __init__(self, *args, errors=None, network_requests=0, **kwargs):
        super().__init__(*args, **kwargs)
        self.errors = dict(errors or {})
        self.network_requests = int(network_requests)


def _fred_api_key() -> str:
    key = str(os.getenv("FRED_API_KEY", "") or "").strip()
    if key:
        return key
    try:
        import streamlit as st
        return str(st.secrets.get("FRED_API_KEY", "") or "").strip()
    except Exception:
        return ""


def _wait_for_fred_slot() -> None:
    # Share the rate budget across domain loaders within this process.
    global _API_NEXT_REQUEST
    with _API_LOCK:
        now = time.monotonic()
        if _API_NEXT_REQUEST > now:
            time.sleep(_API_NEXT_REQUEST - now)
        _API_NEXT_REQUEST = time.monotonic() + 0.6


def _fetch_api_series(series_id: str, key: str, start_date: str | None, timeout: int) -> pd.DataFrame:
    params = {"api_key": key, "file_type": "json", "series_id": series_id,
              "sort_order": "asc", "limit": 100000}
    if start_date:
        params["observation_start"] = str(start_date)
    _wait_for_fred_slot()
    try:
        response = requests.get(FRED_API_URL, params=params, timeout=timeout)
        # Do not put the authenticated request URL into logs or retained reports.
        if response.status_code != 200:
            raise ValueError(f"FRED API HTTP {response.status_code} for {series_id}")
        payload = response.json()
        rows = payload.get("observations", [])
        if int(payload.get("count", len(rows))) > len(rows):
            raise ValueError(f"FRED API history was truncated for {series_id}")
        raw = pd.DataFrame(rows)
        if not {"date", "value"}.issubset(raw.columns):
            raise ValueError(f"FRED API returned no recognized observations for {series_id}")
        frame = pd.DataFrame({"Date": pd.to_datetime(raw["date"], errors="coerce"),
                              "Value": pd.to_numeric(raw["value"], errors="coerce")})
        frame = frame.replace([float("inf"), float("-inf")], float("nan"))
        frame = frame.dropna().sort_values("Date").drop_duplicates("Date", keep="last")
        if frame.empty:
            raise ValueError(f"FRED API returned no numeric observations for {series_id}")
        return frame.reset_index(drop=True)
    except Exception as exc:
        if isinstance(exc, ValueError) and str(exc).startswith("FRED API"):
            raise
        raise RuntimeError(f"FRED API {type(exc).__name__} for {series_id}") from None


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
    """Use the authenticated API when configured, otherwise the public CSV.

    API failures are isolated by series. A configured but failing API is reported
    directly instead of repeating a known-broken graph request for every series.
    """
    ids = list(dict.fromkeys(str(series_id).strip() for series_id in series_ids if str(series_id).strip()))
    if not ids:
        return FredSeriesBatch()
    key = _fred_api_key()
    if key:
        def fetch(series_id):
            try:
                return series_id, _fetch_api_series(series_id, key, start_date, _request_timeout(timeout)), None
            except Exception as exc:
                return series_id, None, str(exc)
        with ThreadPoolExecutor(max_workers=min(3, len(ids))) as pool:
            results = list(pool.map(fetch, ids))
        output = FredSeriesBatch(network_requests=len(ids))
        for series_id, frame, error in results:
            if error:
                output.errors[series_id] = error
            else:
                output[series_id] = frame
        if not output:
            raise RuntimeError("; ".join(output.errors.values()))
        return output
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
    output = FredSeriesBatch(_parse_fred_response(response.content, ids), network_requests=1)
    output.errors = {sid: "FRED CSV returned no numeric observations" for sid in ids
                     if sid not in output or output[sid].empty}
    return output


def fetch_fred_series(
    series_id: str,
    *,
    start_date: str | None = None,
    timeout: int | None = None,
) -> pd.DataFrame:
    """Return one official FRED series as Date/Value after contract validation."""
    clean_id = str(series_id).strip()
    batch = fetch_fred_series_batch(
        [clean_id],
        start_date=start_date,
        timeout=timeout,
    )
    result = batch.get(clean_id)
    if result is None or result.empty:
        raise ValueError(getattr(batch, "errors", {}).get(clean_id, f"FRED returned no observations for {clean_id}"))
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
        errors.update(getattr(fetched_by_series, "errors", {}))
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
        previous = pd.to_datetime(retained.loc[retained[series_id_column].astype(str).str.strip().eq(series_id), date_column], errors="coerce")
        if not previous.dropna().empty and fetched["Date"].max() < previous.max():
            errors[series_id] = "Source history is older than retained observations; retained series preserved"
            continue
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
        "network_requests": getattr(fetched_by_series, "network_requests", len(series_ids) if _fred_api_key() else int(bool(series_ids))),
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
        if target.exists() and target.stat().st_size:
            retained = pd.read_csv(target)
            previous = pd.to_datetime(retained[output_date_column], errors="coerce")
            if not previous.dropna().empty and fetched["Date"].max() < previous.max():
                raise ValueError("Source history is older than retained observations; retained series preserved")
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
