"""Archive trend helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd


METRIC_ALIASES = {
    "AI Equity Index": ["AI Equity Index", "Sector Score"],
    "Sector Score": ["Sector Score", "AI Equity Index"],
}



def resolve_metric_col(df, metric_col):
    if df is None or df.empty:
        return None

    candidates = METRIC_ALIASES.get(metric_col, [metric_col])
    return next((col for col in candidates if col in df.columns), None)


def metric_series(
    df,
    metric_col,
    date_col="Date",
    *,
    version_column=None,
    required_version=None,
):
    """Return a dated, finite metric series using row-wise alias fallback."""
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


def sort_history_for_trend(df, date_col="Date", group_cols=None):
    if df is None or df.empty:
        return df

    working = df.copy()
    if date_col in working.columns:
        working["_trend_date"] = pd.to_datetime(
            working[date_col], errors="coerce", format="mixed"
        )
        working = working.loc[working["_trend_date"].notna()].copy()
        sort_cols = [col for col in (group_cols or []) if col in working.columns]
        sort_cols.append("_trend_date")
        working = working.sort_values(sort_cols, kind="stable")
        working = working.drop(columns=["_trend_date"], errors="ignore")

    return working


def calc_velocity(series):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    return clean.iloc[-1] - clean.iloc[-2] if len(clean) >= 2 else np.nan


def calc_acceleration(series):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 3:
        return np.nan
    return (clean.iloc[-1] - clean.iloc[-2]) - (clean.iloc[-2] - clean.iloc[-3])


def calc_metric_trend(
    df,
    metric_col,
    date_col="Date",
    group_cols=None,
    *,
    version_column=None,
    required_version=None,
):
    del group_cols  # retained for public-signature compatibility
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
        }

    series = series_df["Value"]
    return {
        "current": float(series.iloc[-1]),
        "velocity": calc_velocity(series),
        "acceleration": calc_acceleration(series),
        "history": series_df,
    }
