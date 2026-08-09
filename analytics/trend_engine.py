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
    required_filters=None,
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

    for column, required_value in (required_filters or {}).items():
        if column not in working.columns:
            return pd.DataFrame(columns=["Date", "Value"])
        working = working[
            working[column].astype(str) == str(required_value)
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

def _calendar_slope(
    series_df,
    *,
    end_date=None,
    window_days=90,
    min_observations=3,
    min_span_days=30,
):
    if series_df is None or not isinstance(series_df, pd.DataFrame):
        return np.nan
    if not {"Date", "Value"}.issubset(series_df.columns):
        return np.nan
    frame = series_df[["Date", "Value"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    frame = frame.dropna().sort_values("Date", kind="stable").drop_duplicates("Date", keep="last")
    if frame.empty:
        return np.nan
    end = pd.to_datetime(end_date, errors="coerce")
    if pd.isna(end):
        end = frame["Date"].max()
    start = end - pd.Timedelta(days=int(window_days))
    window = frame.loc[frame["Date"].between(start, end)].copy()
    if len(window) < int(min_observations):
        return np.nan
    span = (window["Date"].max() - window["Date"].min()).days
    if span < int(min_span_days):
        return np.nan
    x = (window["Date"] - window["Date"].min()).dt.total_seconds() / 86400.0
    slope_per_day = np.polyfit(x.to_numpy(dtype=float), window["Value"].to_numpy(dtype=float), 1)[0]
    return float(slope_per_day * 30.4375)


def calc_velocity(
    series_df,
    *,
    window_days=90,
    min_observations=3,
    min_span_days=30,
):
    """Trailing OLS slope in index points per average month."""
    return _calendar_slope(
        series_df,
        window_days=window_days,
        min_observations=min_observations,
        min_span_days=min_span_days,
    )


def calc_acceleration(
    series_df,
    *,
    window_days=90,
    min_observations=3,
    min_span_days=30,
):
    """Change between the current and immediately prior calendar-window slopes."""
    if series_df is None or not isinstance(series_df, pd.DataFrame) or series_df.empty:
        return np.nan
    dates = pd.to_datetime(series_df.get("Date"), errors="coerce", format="mixed")
    if dates.dropna().empty:
        return np.nan
    current_end = dates.max()
    prior_end = current_end - pd.Timedelta(days=int(window_days))
    current = _calendar_slope(
        series_df,
        end_date=current_end,
        window_days=window_days,
        min_observations=min_observations,
        min_span_days=min_span_days,
    )
    prior = _calendar_slope(
        series_df,
        end_date=prior_end,
        window_days=window_days,
        min_observations=min_observations,
        min_span_days=min_span_days,
    )
    return float(current - prior) if pd.notna(current) and pd.notna(prior) else np.nan

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


def calc_trailing_point_change(series_df, *, months, tolerance=1e-9):
    if series_df is None or series_df.empty:
        return np.nan
    if not {"Date", "Value"}.issubset(series_df.columns):
        return np.nan
    frame = series_df[["Date", "Value"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame["Value"] = pd.to_numeric(frame["Value"], errors="coerce")
    frame = (
        frame.dropna()
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )
    frame = distinct_metric_observations(frame, tolerance=tolerance)
    if len(frame) < 2:
        return np.nan
    end = frame.iloc[-1]
    target = end["Date"] - pd.DateOffset(months=int(months))
    prior = frame.loc[frame["Date"] <= target]
    if prior.empty:
        return np.nan
    return float(end["Value"] - prior.iloc[-1]["Value"])

def calc_metric_trend(
    df,
    metric_col,
    date_col="Date",
    group_cols=None,
    *,
    version_column=None,
    required_version=None,
    required_filters=None,
    distinct_observations=False,
    repeat_tolerance=1e-9,
    dynamics_window_days=90,
    dynamics_min_observations=3,
    dynamics_min_span_days=30,
):
    del group_cols
    series_df = metric_series(
        df,
        metric_col,
        date_col=date_col,
        version_column=version_column,
        required_version=required_version,
        required_filters=required_filters,
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
    return {
        "current": float(series_df["Value"].iloc[-1]),
        "velocity": calc_velocity(
            dynamics_df,
            window_days=dynamics_window_days,
            min_observations=dynamics_min_observations,
            min_span_days=dynamics_min_span_days,
        ),
        "acceleration": calc_acceleration(
            dynamics_df,
            window_days=dynamics_window_days,
            min_observations=dynamics_min_observations,
            min_span_days=dynamics_min_span_days,
        ),
        "history": series_df,
        "dynamics_observations": int(len(dynamics_df)),
    }
