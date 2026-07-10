import streamlit as st
import numpy as np
from fredapi import Fred

from archive.archive_reader import (
    latest_nonempty_row,
    load_fred_history,
    rows_for_current_week,
)
from config import fred_indicators
from config.debug_config import debug_print


def get_fred_client():

    key = st.secrets.get("FRED_API_KEY")

    if not key:
        return None

    return Fred(api_key=key)


def _row_to_fred_payload(row, source):
    data = {}

    for name in fred_indicators.FRED_INDICATORS.keys():
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

    return _row_to_fred_payload(row, "FRED Archive")


def _latest_fred_archive_fallback():
    df = load_fred_history()

    if df is None or df.empty:
        return None

    row = latest_nonempty_row(df)

    if row is None:
        return None

    return _row_to_fred_payload(row, "FRED Archive Fallback")


@st.cache_data(ttl=86400)
def load_fred():

    archived = _latest_weekly_fred_archive()

    if archived is not None:
        debug_print("Loading current-week FRED snapshot from fred_history.csv")
        return archived

    fred = get_fred_client()

    if fred is None:
        fallback = _latest_fred_archive_fallback()
        return fallback or {}

    data = {}

    for name, series_id in fred_indicators.FRED_INDICATORS.items():

        try:

            series = fred.get_series(series_id)

            clean = series.dropna()

            if clean.empty:
                raise ValueError("No data returned")

            data[name] = {
                "value": float(clean.iloc[-1]),
                "date": clean.index[-1].isoformat() if hasattr(clean.index[-1], "isoformat") else str(clean.index[-1]),
                "source": "FRED Live",
            }

        except Exception as e:

            debug_print(
                f"FRED failed: {name} ({series_id}) -> {e}"
            )

            data[name] = {
                "value": np.nan,
                "date": None,
                "source": "FRED Live Failed",
            }

    if data:
        has_any_value = any(
            not np.isnan(payload.get("value", np.nan))
            for payload in data.values()
            if isinstance(payload, dict)
        )

        if has_any_value:
            return data

    fallback = _latest_fred_archive_fallback()
    return fallback or data or {}
