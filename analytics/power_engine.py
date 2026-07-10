import numpy as np
import pandas as pd


def calculate_power_stress_zscore(
    fred_history,
    column="Industrial Production",
    lookback=24
):
    """
    Calculates power stress as a z-score using historical FRED values.

    When the archive includes a FRED observation-date column, duplicate app-run
    snapshots for the same underlying FRED observation are collapsed before the
    z-score is calculated.
    """

    if fred_history is None or fred_history.empty:
        return np.nan

    if column not in fred_history.columns:
        return np.nan

    df = fred_history.copy()

    date_col = f"{column} Date"

    if date_col in df.columns:
        obs_dates = pd.to_datetime(
            df[date_col],
            errors="coerce",
            format="mixed",
        )

        if obs_dates.notna().any():
            df["_power_date"] = obs_dates
        elif "Date" in df.columns:
            df["_power_date"] = pd.to_datetime(
                df["Date"],
                errors="coerce",
                format="mixed",
            )
        else:
            df["_power_date"] = pd.RangeIndex(len(df))
    elif "Date" in df.columns:
        df["_power_date"] = pd.to_datetime(
            df["Date"],
            errors="coerce",
            format="mixed",
        )
    else:
        df["_power_date"] = pd.RangeIndex(len(df))

    df["_power_value"] = pd.to_numeric(
        df[column],
        errors="coerce"
    )

    df = df.dropna(subset=["_power_value"])

    if df.empty:
        return np.nan

    if "_power_date" in df.columns:
        df = df.sort_values("_power_date", kind="stable")
        df = df.drop_duplicates(subset=["_power_date"], keep="last")

    series = df["_power_value"].dropna()

    if len(series) < 2:
        return np.nan

    baseline = series.tail(lookback)

    current = series.iloc[-1]
    mean = baseline.mean()
    std = baseline.std()

    if pd.isna(std) or std == 0:
        return np.nan

    return (current - mean) / std
