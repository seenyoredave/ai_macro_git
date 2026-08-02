from __future__ import annotations

import numpy as np
import pandas as pd

METRIC_ALIASES = {
    "AI Equity Index": ["AI Equity Index", "Sector Score"],
    "Sector Score": ["Sector Score", "AI Equity Index"],
}

def metric_series(
    df,
    metric_col,
    date_col="Date",
    *,
    version_column=None,
    required_version=None,
):
    if df is None or df.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    working = df.copy()

    if version_column and required_version:
        if version_column not in working.columns:
            return pd.DataFrame(columns=["Date", "Value"])
        working = working[
            working[version_column].astype(str) == str(required_version)
        ].copy()

    candidates = METRIC_ALIASES.get(metric_col, [metric_col])
    existing = [col for col in candidates if col in working.columns]

    if not existing:
        return pd.DataFrame(columns=["Date", "Value"])

    values = pd.Series(np.nan, index=working.index, dtype=float)
    for col in existing:
        candidate = pd.to_numeric(working[col], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        values = values.fillna(candidate)

    dates = (
        pd.to_datetime(working[date_col], errors="coerce", format="mixed")
        if date_col in working.columns
        else pd.Series(pd.RangeIndex(len(working)), index=working.index)
    )

    out = pd.DataFrame({"Date": dates, "Value": values})
    out = out.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    return out.drop_duplicates(subset=["Date"], keep="last").reset_index(drop=True)

def distinct_metric_observations(series_df, *, tolerance=1e-9):
    if series_df is None or series_df.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    working = series_df.copy().reset_index(drop=True)
    values = pd.to_numeric(working["Value"], errors="coerce")
    previous = values.shift(1)
    repeated = pd.Series(
        np.isclose(values, previous, rtol=0.0, atol=float(tolerance), equal_nan=False),
        index=working.index,
    )
    keep = previous.isna() | ~repeated
    return working.loc[keep].reset_index(drop=True)

def calc_velocity(series):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return clean.iloc[-1] - clean.iloc[-2] if len(clean) >= 2 else np.nan

def calc_acceleration(series):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 3:
        return np.nan
    return (clean.iloc[-1] - clean.iloc[-2]) - (clean.iloc[-2] - clean.iloc[-3])

def calc_trailing_directional_pct(series_df, *, months, tolerance=1e-9):
    if series_df is None or series_df.empty:
        return np.nan
    if not {"Date", "Value"}.issubset(series_df.columns):
        return np.nan

    frame = series_df[["Date", "Value"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    frame = (
        frame.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )
    frame = distinct_metric_observations(frame, tolerance=tolerance)
    if len(frame) < 2:
        return np.nan

    end = frame.iloc[-1]
    target_date = end["Date"] - pd.DateOffset(months=int(months))
    prior = frame.loc[frame["Date"] <= target_date]
    if prior.empty:
        return np.nan

    start_value = float(prior.iloc[-1]["Value"])
    end_value = float(end["Value"])
    if abs(start_value) <= float(tolerance):
        return np.nan
    return (end_value - start_value) / abs(start_value) * 100.0

def calc_metric_trend(
    df,
    metric_col,
    date_col="Date",
    group_cols=None,
    *,
    version_column=None,
    required_version=None,
    distinct_observations=False,
    repeat_tolerance=1e-9,
):
    del group_cols
    series_df = metric_series(
        df,
        metric_col,
        date_col=date_col,
        version_column=version_column,
        required_version=required_version,
    )

    if series_df.empty:
        return {
            "current": np.nan,
            "velocity": np.nan,
            "acceleration": np.nan,
            "history": series_df,
            "dynamics_observations": 0,
        }

    dynamics_df = (
        distinct_metric_observations(series_df, tolerance=repeat_tolerance)
        if distinct_observations
        else series_df
    )
    series = dynamics_df["Value"]
    return {
        "current": float(series_df["Value"].iloc[-1]),
        "velocity": calc_velocity(series),
        "acceleration": calc_acceleration(series),
        "history": series_df,
        "dynamics_observations": int(len(dynamics_df)),
    }
