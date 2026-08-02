from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta
from io import BytesIO
import json
from pathlib import Path
import time as time_module

import numpy as np
import pandas as pd
import requests
import streamlit as st

from config.debt_markets_config import (
    DEBT_MARKETS_DATA_VERSION,
    DEBT_MARKETS_REQUEST_TIMEOUT,
    DEBT_MARKETS_SOURCE_URL,
    DEBT_MARKET_SERIES,
)
from config.debug_config import debug_print
from config.market_clock import EASTERN_TIME, eastern_now, utc_now

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEBT_MARKETS_HISTORY_PATH = PROJECT_ROOT / "data" / "debt_markets_history.csv"
DEBT_MARKETS_METADATA_PATH = PROJECT_ROOT / "data" / "debt_markets_metadata.json"

def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    last = date(year, month, monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)

def completed_debt_market_release(now: datetime | None = None) -> date:
    current = eastern_now(now)
    release_date = _last_weekday_of_month(current.year, current.month, 2)
    cutoff = datetime.combine(release_date, time(10, 0), tzinfo=EASTERN_TIME)
    if current >= cutoff:
        return release_date

    previous_month_end = date(current.year, current.month, 1) - timedelta(days=1)
    return _last_weekday_of_month(
        previous_month_end.year,
        previous_month_end.month,
        2,
    )

def debt_markets_cache_token(now: datetime | None = None) -> str:
    return completed_debt_market_release(now).isoformat()

def _empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=["Date", *DEBT_MARKET_SERIES])

def _normalize_history(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty or "Date" not in frame.columns:
        return _empty_history()
    out = frame[
        [column for column in ["Date", *DEBT_MARKET_SERIES] if column in frame.columns]
    ].copy()
    for name in DEBT_MARKET_SERIES:
        if name not in out.columns:
            out[name] = np.nan
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    for name in DEBT_MARKET_SERIES:
        out[name] = pd.to_numeric(out[name], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
    out = out.dropna(subset=["Date"])
    out = out.dropna(subset=list(DEBT_MARKET_SERIES), how="all")
    return (
        out[["Date", *DEBT_MARKET_SERIES]]
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )

def _load_local_history() -> pd.DataFrame:
    if (
        not DEBT_MARKETS_HISTORY_PATH.exists()
        or DEBT_MARKETS_HISTORY_PATH.stat().st_size == 0
    ):
        return _empty_history()
    try:
        return _normalize_history(pd.read_csv(DEBT_MARKETS_HISTORY_PATH))
    except Exception as exc:
        debug_print(f"Debt-markets local history load failed -> {exc}")
        return _empty_history()

def _load_metadata() -> dict:
    if not DEBT_MARKETS_METADATA_PATH.exists():
        return {}
    try:
        payload = json.loads(DEBT_MARKETS_METADATA_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        debug_print(f"Debt-markets metadata load failed -> {exc}")
        return {}

def _persist_local_history(frame: pd.DataFrame, *, release_date: date) -> None:
    clean = _normalize_history(frame)
    if clean.empty:
        return

    output = clean.copy()
    output["Date"] = output["Date"].dt.date.astype(str)
    temporary = DEBT_MARKETS_HISTORY_PATH.with_suffix(".csv.tmp")
    output.to_csv(temporary, index=False)
    temporary.replace(DEBT_MARKETS_HISTORY_PATH)

    metadata = {
        "release_date": release_date.isoformat(),
        "retrieved_at_utc": utc_now().isoformat(),
        "latest_observation_date": clean["Date"].max().date().isoformat(),
        "data_version": DEBT_MARKETS_DATA_VERSION,
    }
    metadata_temporary = DEBT_MARKETS_METADATA_PATH.with_suffix(".json.tmp")
    metadata_temporary.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata_temporary.replace(DEBT_MARKETS_METADATA_PATH)

def _normalize_workbook(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty:
        return _empty_history()
    required = {
        "eow_friday",
        *[spec["source_column"] for spec in DEBT_MARKET_SERIES.values()],
    }
    if not required.issubset(frame.columns):
        return _empty_history()
    out = pd.DataFrame({"Date": frame["eow_friday"]})
    for name, spec in DEBT_MARKET_SERIES.items():
        out[name] = frame[spec["source_column"]]
    return _normalize_history(out)

def _fetch_history() -> pd.DataFrame:
    response = requests.get(
        DEBT_MARKETS_SOURCE_URL,
        timeout=DEBT_MARKETS_REQUEST_TIMEOUT,
        headers={"User-Agent": "ai-macro-debt-markets/1.0"},
    )
    response.raise_for_status()
    workbook = pd.read_excel(
        BytesIO(response.content),
        sheet_name="Index Data",
        skiprows=5,
    )
    history = _normalize_workbook(workbook)
    if history.empty:
        raise ValueError("New York Fed workbook returned no recognized CMDI history")
    return history

def _series_payload(history: pd.DataFrame, name: str, source: str) -> dict:
    if history.empty or name not in history.columns:
        series = pd.DataFrame(columns=["Date", "Value"])
    else:
        series = history[["Date", name]].rename(columns={name: "Value"}).copy()
        series = series.dropna(subset=["Date", "Value"]).reset_index(drop=True)
    if series.empty:
        return {
            "value": np.nan,
            "date": None,
            "source": "Unavailable",
            "history": series,
        }
    latest = series.iloc[-1]
    return {
        "value": float(latest["Value"]),
        "date": pd.Timestamp(latest["Date"]).date().isoformat(),
        "source": source,
        "history": series,
    }

def _snapshot(
    history: pd.DataFrame,
    *,
    source_mode: str,
    elapsed: float,
    release_date: date,
    error: str | None = None,
) -> dict:
    latest_date = history["Date"].max() if not history.empty else None
    source = (
        "New York Fed"
        if source_mode in {"live", "live_manual"}
        else "New York Fed archive"
    )
    series = {
        name: _series_payload(history, name, source)
        for name in DEBT_MARKET_SERIES
    }
    return {
        "version": DEBT_MARKETS_DATA_VERSION,
        "source_mode": source_mode,
        "snapshot_date": latest_date.date().isoformat() if pd.notna(latest_date) else None,
        "release_date": release_date.isoformat(),
        "series": series,
        "history": history,
        "load_report": {
            "source_mode": source_mode,
            "elapsed_sec": elapsed,
            "returned_series": int(sum(
                bool(np.isfinite(pd.to_numeric(payload["value"], errors="coerce")))
                for payload in series.values()
            )),
            "latest_complete_date": (
                latest_date.date().isoformat() if pd.notna(latest_date) else None
            ),
            "decision": "manual_refresh" if source_mode == "live_manual" else source_mode,
            "refresh_trigger": release_date.isoformat(),
            "requested_at_utc": utc_now().isoformat(),
            "error": error,
        },
    }

@st.cache_data(ttl=86400)
def _load_debt_markets_cached(
    clock_token: str,
    force_refresh: bool,
    refresh_token: int,
) -> dict:
    del clock_token, refresh_token
    started = time_module.perf_counter()
    local = _load_local_history()
    metadata = _load_metadata()
    required_release = completed_debt_market_release()
    metadata_release = pd.to_datetime(
        metadata.get("release_date"), errors="coerce"
    )
    has_current_release = (
        not local.empty
        and pd.notna(metadata_release)
        and metadata_release.date() >= required_release
    )

    if has_current_release and not force_refresh:
        return _snapshot(
            local,
            source_mode="archive_current_release",
            elapsed=time_module.perf_counter() - started,
            release_date=required_release,
        )

    try:
        live = _fetch_history()
        merged = _normalize_history(
            pd.concat([local, live], ignore_index=True, sort=False)
        )
        _persist_local_history(merged, release_date=required_release)
        return _snapshot(
            merged,
            source_mode="live_manual" if force_refresh else "live",
            elapsed=time_module.perf_counter() - started,
            release_date=required_release,
        )
    except Exception as exc:
        debug_print(f"Debt-markets live load failed -> {exc}")
        return _snapshot(
            local,
            source_mode="archive_fallback" if not local.empty else "unavailable",
            elapsed=time_module.perf_counter() - started,
            release_date=required_release,
            error=str(exc),
        )

def load_debt_markets_data(
    *,
    force_refresh: bool = False,
    refresh_token: int = 0,
    clock_token: str | None = None,
) -> dict:
    return _load_debt_markets_cached(
        clock_token or debt_markets_cache_token(),
        bool(force_refresh),
        int(refresh_token),
    )
