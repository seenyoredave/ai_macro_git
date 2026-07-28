"""Deterministic dataframe preparation for Streamlit/PyArrow display."""

from __future__ import annotations

import json
from decimal import Decimal

import numpy as np
import pandas as pd


def _is_missing_scalar(value) -> bool:
    if value is None:
        return True
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return isinstance(missing, (bool, np.bool_)) and bool(missing)


def _text_value(value) -> str:
    """Flatten arbitrary Python values into deterministic display text."""
    if _is_missing_scalar(value):
        return ""
    if isinstance(value, dict):
        try:
            return json.dumps(value, sort_keys=True, default=str)
        except TypeError:
            return "; ".join(f"{key}: {item}" for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return ", ".join(str(item) for item in value)
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        timestamp = pd.to_datetime(value, errors="coerce")
        return "" if pd.isna(timestamp) else timestamp.isoformat()
    return str(value)


def _all_instances(values, types) -> bool:
    return all(isinstance(value, types) and not isinstance(value, (bool, np.bool_)) for value in values)


def arrow_safe_dataframe(frame: pd.DataFrame | None) -> pd.DataFrame:
    """Return a display copy with deterministic Arrow-compatible column types.

    PyArrow cannot serialize a Pandas ``object`` column that mixes physical
    types, such as integers and labels. This function makes the intended
    display schema explicit instead of letting Arrow infer it.
    """
    if frame is None:
        return pd.DataFrame()
    if not isinstance(frame, pd.DataFrame):
        frame = pd.DataFrame(frame)

    out = frame.copy()
    out.columns = [str(column) for column in out.columns]

    for column in out.columns:
        series = out[column]

        if isinstance(series.dtype, pd.CategoricalDtype):
            out[column] = series.astype("string").fillna("")
            continue

        if pd.api.types.is_datetime64_any_dtype(series.dtype):
            converted = pd.to_datetime(series, errors="coerce")
            if getattr(converted.dt, "tz", None) is not None:
                converted = converted.dt.tz_convert("UTC").dt.tz_localize(None)
            out[column] = converted
            continue

        if pd.api.types.is_timedelta64_dtype(series.dtype):
            out[column] = series.astype("string").fillna("")
            continue

        if series.dtype != "object":
            continue

        values = [value for value in series.tolist() if not _is_missing_scalar(value)]
        if not values:
            out[column] = series.map(_text_value).astype("string")
            continue

        if _all_instances(values, (int, np.integer)):
            out[column] = pd.to_numeric(series, errors="coerce").astype("Int64")
            continue

        if _all_instances(values, (int, float, np.integer, np.floating, Decimal)):
            out[column] = pd.to_numeric(series, errors="coerce").astype("Float64")
            continue

        if all(isinstance(value, (pd.Timestamp, np.datetime64)) for value in values):
            out[column] = pd.to_datetime(series, errors="coerce")
            continue

        # Mixed semantic columns are presentation text by design.
        out[column] = series.map(_text_value).astype("string")

    return out
