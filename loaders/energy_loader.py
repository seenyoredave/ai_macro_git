"""Weekly Energy-tab source loader.

The loader refreshes four Energy-only FRED series once per completed week. The
three electric-power readings already owned by the application's primary FRED
pipeline are reused rather than fetched a second time. A completed week rolls
after Friday 16:00 America/New_York; Refresh Energy bypasses the weekly gate.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from io import StringIO
from pathlib import Path
import time as time_module

import numpy as np
import pandas as pd
import requests
import streamlit as st

from archive.archive_reader import load_energy_history
from config.debug_config import debug_print
from config.energy_config import (
    ENERGY_DATA_VERSION,
    ENERGY_FRED_CSV_URL,
    ENERGY_POWER_SERIES,
    ENERGY_PUBLIC_SERIES,
    ENERGY_SERIES,
    ENERGY_WEEKLY_CUTOFF_HOUR,
    ENERGY_WEEKLY_CUTOFF_WEEKDAY,
)
from config.market_clock import EASTERN_TIME, eastern_now, utc_now


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENERGY_SERIES_HISTORY_PATH = PROJECT_ROOT / "data" / "energy_series_history.csv"
POWER_SERIES_HISTORY_PATH = PROJECT_ROOT / "data" / "power_series_history.csv"
ENERGY_REQUEST_TIMEOUT = 25


def completed_energy_week(now: datetime | None = None):
    """Return the Friday date representing the latest completed Energy week."""
    current = eastern_now(now)
    days_since_friday = (current.weekday() - ENERGY_WEEKLY_CUTOFF_WEEKDAY) % 7
    friday_date = current.date() - timedelta(days=days_since_friday)
    friday_cutoff = datetime.combine(
        friday_date,
        time(ENERGY_WEEKLY_CUTOFF_HOUR, 0),
        tzinfo=EASTERN_TIME,
    )
    if current < friday_cutoff:
        friday_date -= timedelta(days=7)
    return friday_date


def energy_cache_token(now: datetime | None = None) -> str:
    """Invalidate the cached decision when the completed Energy week changes."""
    return completed_energy_week(now).isoformat()


def energy_load_decision(
    *, force_refresh: bool, has_current_archive: bool, has_any_archive: bool
) -> str:
    if force_refresh:
        return "manual_live"
    if has_current_archive:
        return "archive_current_week"
    if has_any_archive:
        return "automatic_live"
    return "bootstrap_live"


def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=["Date", "Series", "Value"])


def _normalize_long_history(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_history()
    required = {"Date", "Series", "Value"}
    if not required.issubset(frame.columns):
        return _empty_history()
    out = frame[["Date", "Series", "Value"]].copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Series"] = out["Series"].astype(str).str.strip()
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    out = out.dropna(subset=["Date", "Value"])
    out = out[out["Series"].isin(ENERGY_SERIES)]
    return (
        out.sort_values(["Series", "Date"], kind="stable")
        .drop_duplicates(["Date", "Series"], keep="last")
        .reset_index(drop=True)
    )


def _load_local_history() -> pd.DataFrame:
    if (
        not ENERGY_SERIES_HISTORY_PATH.exists()
        or ENERGY_SERIES_HISTORY_PATH.stat().st_size == 0
    ):
        return _empty_history()
    try:
        return _normalize_long_history(pd.read_csv(ENERGY_SERIES_HISTORY_PATH))
    except Exception as exc:
        debug_print(f"Energy local history load failed -> {exc}")
        return _empty_history()


def _persist_local_history(frame: pd.DataFrame) -> None:
    clean = _normalize_long_history(frame)
    clean = clean[clean["Series"].isin(ENERGY_PUBLIC_SERIES)]
    if clean.empty:
        return
    output = clean.copy()
    output["Date"] = output["Date"].dt.date.astype(str)
    ENERGY_SERIES_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = ENERGY_SERIES_HISTORY_PATH.with_suffix(".csv.tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(ENERGY_SERIES_HISTORY_PATH)


def _load_power_history() -> pd.DataFrame:
    if not POWER_SERIES_HISTORY_PATH.exists():
        return _empty_history()
    try:
        frame = pd.read_csv(POWER_SERIES_HISTORY_PATH)
    except Exception as exc:
        debug_print(f"Power local history load failed -> {exc}")
        return _empty_history()

    date_column = next(
        (
            column
            for column in ("Observation Date", "Date", "DATE", "date")
            if column in frame.columns
        ),
        None,
    )
    if date_column is None:
        return _empty_history()

    dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed")
    rows = []
    for name, spec in ENERGY_POWER_SERIES.items():
        column = spec["history_column"]
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        valid = dates.notna() & values.notna() & np.isfinite(values)
        if valid.any():
            rows.append(
                pd.DataFrame(
                    {
                        "Date": dates.loc[valid],
                        "Series": name,
                        "Value": values.loc[valid].astype(float),
                    }
                )
            )
    return _empty_history() if not rows else _normalize_long_history(pd.concat(rows, ignore_index=True))


def _normalize_fred_csv(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_history()
    date_column = next(
        (
            column
            for column in ("observation_date", "DATE", "Date", "date")
            if column in frame.columns
        ),
        None,
    )
    if date_column is None:
        return _empty_history()

    dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed")
    rows = []
    normalized_columns = {str(column).strip().upper(): column for column in frame.columns}
    for series_name, spec in ENERGY_PUBLIC_SERIES.items():
        original_column = normalized_columns.get(spec["series_id"].upper())
        if original_column is None:
            continue
        values = pd.to_numeric(frame[original_column], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        valid = dates.notna() & values.notna()
        if not valid.any():
            continue
        rows.append(
            pd.DataFrame(
                {
                    "Date": dates.loc[valid],
                    "Series": series_name,
                    "Value": values.loc[valid].astype(float),
                }
            )
        )
    if not rows:
        return _empty_history()
    return _normalize_long_history(pd.concat(rows, ignore_index=True))


def _fetch_public_energy_history() -> pd.DataFrame:
    response = requests.get(
        ENERGY_FRED_CSV_URL,
        timeout=ENERGY_REQUEST_TIMEOUT,
        headers={"User-Agent": "ai-macro-energy-tab/1.1"},
    )
    response.raise_for_status()
    history = _normalize_fred_csv(pd.read_csv(StringIO(response.text)))
    if history.empty:
        raise ValueError("FRED returned no recognized Energy series")
    return history


def _merge_histories(*frames: pd.DataFrame) -> pd.DataFrame:
    usable = [frame for frame in frames if frame is not None and not frame.empty]
    if not usable:
        return _empty_history()
    return _normalize_long_history(pd.concat(usable, ignore_index=True))


def _series_history(history: pd.DataFrame, name: str) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    subset = history.loc[history["Series"].eq(name), ["Date", "Value"]].copy()
    return subset.sort_values("Date", kind="stable").reset_index(drop=True)


def _prior_value(history: pd.DataFrame, latest_date: pd.Timestamp, spec: dict):
    if history.empty:
        return np.nan
    if spec.get("change_days"):
        target = latest_date - pd.Timedelta(days=int(spec["change_days"]))
    else:
        target = latest_date - pd.DateOffset(months=int(spec.get("change_months") or 0))
    prior = history.loc[history["Date"] <= target]
    return np.nan if prior.empty else float(prior.iloc[-1]["Value"])


def _series_payload(history: pd.DataFrame, name: str, *, source: str | None = None) -> dict:
    spec = ENERGY_SERIES[name]
    series_history = _series_history(history, name)
    if series_history.empty:
        return {
            "value": np.nan,
            "date": None,
            "change_pct": np.nan,
            "frequency": spec["frequency"],
            "unit": spec["unit"],
            "source": source or "Unavailable",
            "history": series_history,
        }

    latest = series_history.iloc[-1]
    latest_value = float(latest["Value"])
    latest_date = pd.Timestamp(latest["Date"])
    prior_value = _prior_value(series_history, latest_date, spec)
    change_pct = (
        ((latest_value / prior_value) - 1.0) * 100.0
        if np.isfinite(prior_value) and prior_value != 0
        else np.nan
    )
    return {
        "value": latest_value,
        "date": latest_date.date().isoformat(),
        "change_pct": float(change_pct) if np.isfinite(change_pct) else np.nan,
        "frequency": spec["frequency"],
        "unit": spec["unit"],
        "source": source or "FRED",
        "history": series_history,
    }


def _snapshot_from_history(
    history: pd.DataFrame,
    *,
    source_mode: str,
    snapshot_date,
    decision: str,
    elapsed: float,
    error: str | None = None,
) -> dict:
    series = {
        name: _series_payload(history, name, source="FRED" if source_mode.startswith("live") else "Energy archive")
        for name in ENERGY_PUBLIC_SERIES
    }
    return {
        "version": ENERGY_DATA_VERSION,
        "source_mode": source_mode,
        "snapshot_date": snapshot_date.isoformat()
        if hasattr(snapshot_date, "isoformat")
        else str(snapshot_date),
        "series": series,
        "history": history,
        "load_report": {
            "source_mode": source_mode,
            "decision": decision,
            "elapsed_sec": float(elapsed),
            "returned_series": int(
                sum(
                    np.isfinite(pd.to_numeric(payload.get("value"), errors="coerce"))
                    for payload in series.values()
                )
            ),
            "latest_complete_date": _latest_observation_date(series),
            "requested_at_utc": utc_now().isoformat(),
            "error": error,
        },
    }


def _history_from_archive(archive: pd.DataFrame | None) -> pd.DataFrame:
    if archive is None or archive.empty:
        return _empty_history()
    rows = []
    for name in ENERGY_PUBLIC_SERIES:
        if name not in archive.columns:
            continue
        values = pd.to_numeric(archive[name], errors="coerce")
        date_column = f"{name} Date"
        dates = pd.to_datetime(
            archive[date_column] if date_column in archive.columns else archive.get("Date"),
            errors="coerce",
            format="mixed",
        )
        valid = dates.notna() & values.notna() & np.isfinite(values)
        if valid.any():
            rows.append(
                pd.DataFrame(
                    {
                        "Date": dates.loc[valid],
                        "Series": name,
                        "Value": values.loc[valid].astype(float),
                    }
                )
            )
    return _empty_history() if not rows else _normalize_long_history(pd.concat(rows, ignore_index=True))


def _archive_row_is_complete(row: pd.Series | None) -> bool:
    if row is None:
        return False
    for name in ENERGY_PUBLIC_SERIES:
        value = pd.to_numeric(row.get(name, np.nan), errors="coerce")
        if pd.isna(value) or not np.isfinite(value):
            return False
    return True


def _archive_row_for_week(archive: pd.DataFrame, week_date) -> pd.Series | None:
    if archive is None or archive.empty or "Date" not in archive.columns:
        return None
    target = week_date.isoformat() if hasattr(week_date, "isoformat") else str(week_date)
    rows = archive.loc[archive["Date"].astype(str).eq(target)]
    if rows.empty:
        return None
    row = rows.iloc[-1]
    return row if _archive_row_is_complete(row) else None


def _latest_archive_row(archive: pd.DataFrame) -> pd.Series | None:
    if archive is None or archive.empty or "Date" not in archive.columns:
        return None
    working = archive.copy()
    working["_date"] = pd.to_datetime(working["Date"], errors="coerce", format="mixed")
    working = working.loc[working["_date"].notna()].sort_values("_date", kind="stable")
    if working.empty:
        return None
    complete = working.apply(_archive_row_is_complete, axis=1)
    working = working.loc[complete]
    return None if working.empty else working.iloc[-1]


def _snapshot_from_archive_row(
    row: pd.Series,
    history: pd.DataFrame,
    *,
    mode: str,
    decision: str,
    elapsed: float,
    error: str | None = None,
) -> dict:
    series = {}
    for name, spec in ENERGY_PUBLIC_SERIES.items():
        value = pd.to_numeric(row.get(name, np.nan), errors="coerce")
        change = pd.to_numeric(row.get(f"{name} Change", np.nan), errors="coerce")
        observation_date = row.get(f"{name} Date", None)
        series[name] = {
            "value": float(value) if pd.notna(value) and np.isfinite(value) else np.nan,
            "date": None if pd.isna(observation_date) else str(observation_date),
            "change_pct": float(change)
            if pd.notna(change) and np.isfinite(change)
            else np.nan,
            "frequency": spec["frequency"],
            "unit": spec["unit"],
            "source": "Energy archive",
            "history": _series_history(history, name),
        }
    return {
        "version": str(row.get("Version", ENERGY_DATA_VERSION)),
        "source_mode": mode,
        "snapshot_date": str(row.get("Date", "")),
        "series": series,
        "history": history,
        "load_report": {
            "source_mode": mode,
            "decision": decision,
            "elapsed_sec": float(elapsed),
            "returned_series": int(
                sum(
                    np.isfinite(pd.to_numeric(payload.get("value"), errors="coerce"))
                    for payload in series.values()
                )
            ),
            "latest_complete_date": _latest_observation_date(series),
            "requested_at_utc": utc_now().isoformat(),
            "error": error,
        },
    }


def _fred_item(fred_data: dict | None, name: str) -> dict:
    payload = (fred_data or {}).get(name, {})
    return payload if isinstance(payload, dict) else {"value": payload}


def _append_observation(history: pd.DataFrame, name: str, value, date) -> pd.DataFrame:
    numeric = pd.to_numeric(value, errors="coerce")
    parsed_date = pd.to_datetime(date, errors="coerce", format="mixed")
    if pd.isna(numeric) or not np.isfinite(numeric) or pd.isna(parsed_date):
        return history
    row = pd.DataFrame([{"Date": parsed_date, "Series": name, "Value": float(numeric)}])
    return _merge_histories(history, row)


def _attach_power_series(snapshot: dict, fred_data: dict | None) -> dict:
    power_history = _load_power_history()
    for name, spec in ENERGY_POWER_SERIES.items():
        fred_item = _fred_item(fred_data, spec["fred_name"])
        power_history = _append_observation(
            power_history,
            name,
            fred_item.get("value"),
            fred_item.get("date"),
        )
        item = _series_payload(
            power_history,
            name,
            source=str(fred_item.get("source") or "FRED archive"),
        )
        # If the current FRED payload is finite, it is authoritative even when
        # its date format differs from the bundled history.
        current_value = pd.to_numeric(fred_item.get("value"), errors="coerce")
        if pd.notna(current_value) and np.isfinite(current_value):
            item["value"] = float(current_value)
            if fred_item.get("date"):
                parsed = pd.to_datetime(fred_item.get("date"), errors="coerce", format="mixed")
                item["date"] = (
                    parsed.date().isoformat() if pd.notna(parsed) else str(fred_item.get("date"))
                )
        snapshot.setdefault("series", {})[name] = item

    combined_history = _merge_histories(snapshot.get("history"), power_history)
    snapshot["history"] = combined_history
    report = snapshot.setdefault("load_report", {})
    report["returned_series"] = int(
        sum(
            np.isfinite(pd.to_numeric(item.get("value"), errors="coerce"))
            for item in snapshot.get("series", {}).values()
        )
    )
    report["latest_complete_date"] = _latest_observation_date(snapshot.get("series", {}))
    return snapshot


def _latest_observation_date(series: dict) -> str | None:
    dates = []
    for payload in (series or {}).values():
        parsed = pd.to_datetime((payload or {}).get("date"), errors="coerce", format="mixed")
        if pd.notna(parsed):
            dates.append(parsed)
    return None if not dates else max(dates).date().isoformat()


def load_energy_data(
    *,
    fred_data: dict | None = None,
    force_refresh: bool = False,
    refresh_token: int = 0,
    clock_token: str | None = None,
) -> dict:
    supply_snapshot = _load_energy_data_cached(
        force_refresh=bool(force_refresh),
        refresh_token=int(refresh_token),
        clock_token=clock_token or energy_cache_token(),
    )
    return _attach_power_series(dict(supply_snapshot), fred_data)


@st.cache_data(ttl=3600)
def _load_energy_data_cached(
    *, force_refresh: bool, refresh_token: int, clock_token: str
) -> dict:
    del refresh_token, clock_token
    started = time_module.perf_counter()
    week_date = completed_energy_week()
    archive = load_energy_history()
    current_row = _archive_row_for_week(archive, week_date)
    latest_row = _latest_archive_row(archive)
    decision = energy_load_decision(
        force_refresh=force_refresh,
        has_current_archive=current_row is not None,
        has_any_archive=latest_row is not None,
    )
    local_history = _merge_histories(_load_local_history(), _history_from_archive(archive))

    if decision == "archive_current_week":
        return _snapshot_from_archive_row(
            current_row,
            local_history,
            mode="archive_current_week",
            decision=decision,
            elapsed=time_module.perf_counter() - started,
        )

    try:
        fresh_history = _fetch_public_energy_history()
        merged = _merge_histories(local_history, fresh_history)
        _persist_local_history(merged)
        mode = "live_manual" if decision == "manual_live" else "live_weekly"
        return _snapshot_from_history(
            merged,
            source_mode=mode,
            snapshot_date=week_date,
            decision=decision,
            elapsed=time_module.perf_counter() - started,
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        debug_print(f"Energy live load failed -> {error}")
        if latest_row is not None:
            return _snapshot_from_archive_row(
                latest_row,
                local_history,
                mode="archive_fallback",
                decision=decision,
                elapsed=time_module.perf_counter() - started,
                error=error,
            )
        if not local_history.empty:
            return _snapshot_from_history(
                local_history,
                source_mode="local_history_fallback",
                snapshot_date=week_date,
                decision=decision,
                elapsed=time_module.perf_counter() - started,
                error=error,
            )
        return _snapshot_from_history(
            _empty_history(),
            source_mode="unavailable",
            snapshot_date=week_date,
            decision=decision,
            elapsed=time_module.perf_counter() - started,
            error=error,
        )
