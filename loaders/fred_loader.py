from __future__ import annotations

from io import StringIO
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import streamlit as st
from fredapi import Fred

from archive.archive_reader import (
    latest_nonempty_row,
    load_fred_history,
    rows_for_current_week,
)
from config import fred_indicators
from config.debug_config import debug_print


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDPRO_HISTORY_PATH = PROJECT_ROOT / "data" / "industrial_production_history.csv"
INDPRO_PUBLIC_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=INDPRO"
)
NFCI_PUBLIC_CSV_URL = (
    "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NFCI"
)


def _optional_streamlit_secret(name, default=None):
    """Read an optional Streamlit secret without requiring secrets.toml.

    Accessing ``st.secrets`` raises StreamlitSecretNotFoundError when the
    project has no secrets file at all, including through ``.get()``.  This
    helper keeps local/offline runs on the archive fallback path instead of
    crashing during startup.
    """
    try:
        return st.secrets.get(name, default)
    except Exception as exc:
        debug_print(f"Optional Streamlit secret unavailable: {name} -> {exc}")
        return default


def get_fred_client():
    key = os.getenv("FRED_API_KEY") or _optional_streamlit_secret("FRED_API_KEY")
    return Fred(api_key=key) if key else None


def _normalize_nfci_history(frame):
    """Return a clean Date/Value NFCI history frame."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    date_column = next(
        (column for column in ["Date", "DATE", "Observation Date", "date"] if column in frame.columns),
        None,
    )
    value_column = next(
        (column for column in ["Value", "NFCI", "Financial Conditions NFCI", "VALUE"] if column in frame.columns),
        None,
    )
    if date_column is None or value_column is None:
        return pd.DataFrame(columns=["Date", "Value"])

    out = frame[[date_column, value_column]].copy()
    out.columns = ["Date", "Value"]
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    out = out.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    return out.drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)


def _archived_nfci_history():
    archive = load_fred_history()
    if archive is None or archive.empty or "Financial Conditions NFCI" not in archive.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    date_column = (
        "Financial Conditions NFCI Date"
        if "Financial Conditions NFCI Date" in archive.columns
        else "Date"
    )
    frame = archive[[date_column, "Financial Conditions NFCI"]].copy()
    frame.columns = ["Date", "Value"]
    return _normalize_nfci_history(frame)


@st.cache_data(ttl=86400)
def load_nfci_history():
    """Load the weekly NFCI history for confirmation-strip charts.

    Resolution order is authenticated FRED, the public FRED CSV endpoint,
    and finally the locally retained FRED archive. The return contract is a
    simple Date/Value dataframe so rendering code remains source-agnostic.
    """
    fred = get_fred_client()
    if fred is not None:
        try:
            series = fred.get_series(fred_indicators.FRED_INDICATORS["Financial Conditions NFCI"])
            frame = pd.DataFrame({"Date": series.index, "Value": series.to_numpy()})
            normalized = _normalize_nfci_history(frame)
            if not normalized.empty:
                normalized.attrs["source"] = "FRED Live"
                return normalized
        except Exception as exc:
            debug_print(f"FRED failed: NFCI history -> {exc}")

    try:
        response = requests.get(NFCI_PUBLIC_CSV_URL, timeout=20)
        response.raise_for_status()
        normalized = _normalize_nfci_history(pd.read_csv(StringIO(response.text)))
        if not normalized.empty:
            normalized.attrs["source"] = "FRED Public CSV"
            return normalized
    except Exception as exc:
        debug_print(f"Public NFCI history load failed -> {exc}")

    archived = _archived_nfci_history()
    archived.attrs["source"] = "FRED Archive" if not archived.empty else "Unavailable"
    return archived


def _row_to_fred_payload(row, source):
    data = {}

    for name in fred_indicators.all_indicator_names():
        value = row.get(name, np.nan)
        obs_date = row.get(f"{name} Date", None)

        if obs_date is None or str(obs_date).strip() == "" or str(obs_date).lower() == "nan":
            obs_date = row.get("Date", None)

        data[name] = {
            "value": value,
            "date": obs_date,
            "source": source,
        }

    return data


def _payload_has_required_values(payload, required):
    if not payload:
        return False

    for name in required:
        item = payload.get(name, {})
        value = item.get("value", np.nan) if isinstance(item, dict) else item

        try:
            if not np.isfinite(float(value)):
                return False
        except (TypeError, ValueError):
            return False

    return True


def _latest_weekly_fred_archive():
    df = load_fred_history()

    if df is None or df.empty:
        return None

    current_week = rows_for_current_week(df)

    if current_week.empty:
        return None

    row = latest_nonempty_row(current_week)

    if row is None:
        return None

    payload = _row_to_fred_payload(row, "FRED Archive")

    # A pre-Power Stress archive cannot satisfy the current engine contract.
    if not _payload_has_required_values(
        payload,
        fred_indicators.POWER_REQUIRED_INDICATORS,
    ):
        return None

    return payload


def _latest_fred_archive_fallback():
    df = load_fred_history()

    if df is None or df.empty:
        return None

    row = latest_nonempty_row(df)

    if row is None:
        return None

    return _row_to_fred_payload(row, "FRED Archive Fallback")


def _year_over_year_growth(series):
    clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()

    if clean.empty:
        return np.nan, None

    latest_date = pd.Timestamp(clean.index[-1])
    latest_value = float(clean.iloc[-1])
    target = latest_date - pd.DateOffset(years=1)
    prior = clean.loc[clean.index <= target]

    if prior.empty:
        return np.nan, latest_date

    prior_date = pd.Timestamp(prior.index[-1])
    prior_value = float(prior.iloc[-1])
    day_gap = (latest_date - prior_date).days

    if prior_value == 0 or not 330 <= day_gap <= 400:
        return np.nan, latest_date

    return (latest_value / prior_value) - 1, latest_date


def _derived_payload(series_cache, base_name, derived_name):
    series = series_cache.get(base_name)

    if series is None:
        return {
            "value": np.nan,
            "date": None,
            "source": "FRED Live Failed",
        }

    growth, latest_date = _year_over_year_growth(series)

    return {
        "value": growth,
        "date": latest_date.isoformat() if latest_date is not None else None,
        "source": "FRED Live Derived",
    }


def _payload_value_is_finite(payload, key):
    item = (payload or {}).get(key, {})
    value = item.get("value", np.nan) if isinstance(item, dict) else item

    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _normalize_indpro_frame(frame):
    if frame is None or frame.empty:
        return None

    date_column = next(
        (
            column
            for column in ["Observation Date", "DATE", "Date", "date"]
            if column in frame.columns
        ),
        None,
    )
    value_column = next(
        (
            column
            for column in ["Industrial Production", "INDPRO", "VALUE", "Value"]
            if column in frame.columns
        ),
        None,
    )

    if date_column is None or value_column is None:
        return None

    out = frame[[date_column, value_column]].copy()
    out.columns = ["Observation Date", "Industrial Production"]
    out["Observation Date"] = pd.to_datetime(
        out["Observation Date"], errors="coerce"
    )
    out["Industrial Production"] = pd.to_numeric(
        out["Industrial Production"], errors="coerce"
    )
    out = out.dropna().sort_values("Observation Date")
    out = out.drop_duplicates(subset=["Observation Date"], keep="last")

    return out if not out.empty else None


def _persist_indpro_history(frame):
    normalized = _normalize_indpro_frame(frame)
    if normalized is None:
        return

    out = normalized.copy()
    out["Observation Date"] = out["Observation Date"].dt.date.astype(str)
    INDPRO_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = INDPRO_HISTORY_PATH.with_suffix(".csv.tmp")
    out.to_csv(temporary, index=False)
    temporary.replace(INDPRO_HISTORY_PATH)


def _series_from_indpro_frame(frame):
    normalized = _normalize_indpro_frame(frame)
    if normalized is None:
        return None

    return pd.Series(
        normalized["Industrial Production"].to_numpy(dtype=float),
        index=pd.DatetimeIndex(normalized["Observation Date"]),
        name="INDPRO",
    )


def _load_local_indpro_series():
    if not INDPRO_HISTORY_PATH.exists() or INDPRO_HISTORY_PATH.stat().st_size == 0:
        return None

    try:
        return _series_from_indpro_frame(pd.read_csv(INDPRO_HISTORY_PATH))
    except Exception as exc:
        debug_print(f"Local INDPRO history load failed -> {exc}")
        return None


def _fetch_public_indpro_series():
    """Fetch INDPRO without requiring an API key.

    The public CSV endpoint is used only to complete the missing YoY data
    contract. The bundled local history remains the deterministic fallback.
    """
    try:
        response = requests.get(INDPRO_PUBLIC_CSV_URL, timeout=20)
        response.raise_for_status()
        frame = pd.read_csv(StringIO(response.text))
        series = _series_from_indpro_frame(frame)

        if series is not None:
            _persist_indpro_history(frame)

        return series
    except Exception as exc:
        debug_print(f"Public INDPRO history load failed -> {exc}")
        return None


def _load_indpro_series(fred=None):
    if fred is not None:
        try:
            series_id = fred_indicators.FRED_INDICATORS["Industrial Production"]
            series = fred.get_series(series_id)
            clean = pd.to_numeric(series, errors="coerce").dropna().sort_index()

            if not clean.empty:
                frame = pd.DataFrame(
                    {
                        "Observation Date": pd.DatetimeIndex(clean.index),
                        "Industrial Production": clean.to_numpy(dtype=float),
                    }
                )
                _persist_indpro_history(frame)
                return clean, "FRED Live"
        except Exception as exc:
            debug_print(f"FRED failed: Industrial Production history -> {exc}")

    public_series = _fetch_public_indpro_series()
    if public_series is not None and not public_series.empty:
        return public_series, "FRED Public CSV"

    local_series = _load_local_indpro_series()
    if local_series is not None and not local_series.empty:
        return local_series, "FRED Local History"

    return None, "FRED Unavailable"


def _hydrate_industrial_growth(payload, fred=None):
    """Guarantee the AI-Industrial Growth Gap input when history is available.

    Resolution order:
      1. authenticated FRED client, when configured;
      2. public no-key FRED CSV endpoint;
      3. bundled/persisted raw INDPRO history.

    Every other archived FRED field is preserved unchanged.
    """
    if _payload_value_is_finite(payload, "Industrial Production YoY"):
        return payload

    series, source = _load_indpro_series(fred)
    if series is None or series.empty:
        return payload

    growth, latest_date = _year_over_year_growth(series)

    try:
        growth_is_valid = bool(np.isfinite(float(growth)))
    except (TypeError, ValueError):
        growth_is_valid = False

    if not growth_is_valid:
        return payload

    out = dict(payload or {})
    latest_observation_date = pd.Timestamp(series.index[-1])
    out["Industrial Production"] = {
        "value": float(series.iloc[-1]),
        "date": latest_observation_date.isoformat(),
        "source": source,
    }
    out["Industrial Production YoY"] = {
        "value": float(growth),
        "date": latest_date.isoformat() if latest_date is not None else None,
        "source": f"{source} Derived",
    }
    return out


def _fill_failed_from_archive(data, fallback):
    if not fallback:
        return data

    out = dict(data)

    for name, payload in out.items():
        value = payload.get("value", np.nan) if isinstance(payload, dict) else payload

        try:
            valid = np.isfinite(float(value))
        except (TypeError, ValueError):
            valid = False

        if not valid and name in fallback:
            fallback_payload = fallback[name]
            fallback_value = (
                fallback_payload.get("value", np.nan)
                if isinstance(fallback_payload, dict)
                else fallback_payload
            )

            try:
                fallback_valid = np.isfinite(float(fallback_value))
            except (TypeError, ValueError):
                fallback_valid = False

            if fallback_valid:
                out[name] = fallback_payload

    return out


@st.cache_data(ttl=86400)
def load_fred():
    archived = _latest_weekly_fred_archive()

    if archived is not None:
        debug_print("Loading current-week FRED snapshot from fred_history.csv")
        return _hydrate_industrial_growth(archived, get_fred_client())

    fred = get_fred_client()
    fallback = _latest_fred_archive_fallback()

    if fred is None:
        return _hydrate_industrial_growth(fallback or {}, fred=None)

    data = {}
    series_cache = {}

    for name, series_id in fred_indicators.FRED_INDICATORS.items():
        try:
            series = fred.get_series(series_id)
            clean = series.dropna().sort_index()

            if clean.empty:
                raise ValueError("No data returned")

            series_cache[name] = clean
            latest_date = pd.Timestamp(clean.index[-1])

            data[name] = {
                "value": float(clean.iloc[-1]),
                "date": latest_date.isoformat(),
                "source": "FRED Live",
            }
        except Exception as exc:
            debug_print(f"FRED failed: {name} ({series_id}) -> {exc}")
            data[name] = {
                "value": np.nan,
                "date": None,
                "source": "FRED Live Failed",
            }

    derived_map = {
        "Industrial Production YoY": "Industrial Production",
        "Commercial Electricity Sales YoY": "Commercial Electricity Sales",
        "Residential Electricity Sales YoY": "Residential Electricity Sales",
        "Electric Power Output YoY": "Electric Power Output",
        "Electric Power Capacity YoY": "Electric Power Capacity",
    }

    for derived_name, base_name in derived_map.items():
        data[derived_name] = _derived_payload(
            series_cache,
            base_name,
            derived_name,
        )

    data = _fill_failed_from_archive(data, fallback)
    data = _hydrate_industrial_growth(data, fred)

    has_any_value = any(
        isinstance(payload, dict)
        and pd.notna(pd.to_numeric(payload.get("value"), errors="coerce"))
        for payload in data.values()
    )

    return data if has_any_value else (fallback or data or {})
