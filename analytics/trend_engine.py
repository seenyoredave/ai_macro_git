import numpy as np
import pandas as pd


METRIC_ALIASES = {
    "Maturation Index": [
        "Maturation Index",
        "Sector Score",
        "AMI",
        "Cycle Score",
    ],
    "Sector Score": [
        "Sector Score",
        "Maturation Index",
        "AMI",
        "Cycle Score",
    ],
}


def resolve_metric_col(df, metric_col):
    if df is None or df.empty:
        return None

    candidates = METRIC_ALIASES.get(
        metric_col,
        [metric_col]
    )

    for col in candidates:
        if col in df.columns:
            return col

    return None


def sort_history_for_trend(df, date_col="Date", group_cols=None):
    if df is None or df.empty:
        return df

    working = df.copy()

    if date_col in working.columns:
        working["_trend_date"] = pd.to_datetime(
            working[date_col],
            errors="coerce",
            format="mixed",
        )

        working = working.loc[working["_trend_date"].notna()].copy()

        sort_cols = []
        if group_cols:
            sort_cols.extend([col for col in group_cols if col in working.columns])
        sort_cols.append("_trend_date")

        working = working.sort_values(sort_cols, kind="stable")
        working = working.drop(columns=["_trend_date"], errors="ignore")

    return working


def calc_velocity(series):
    clean = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna()

    if len(clean) < 2:
        return np.nan

    return clean.iloc[-1] - clean.iloc[-2]


def calc_acceleration(series):
    clean = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna()

    if len(clean) < 3:
        return np.nan

    current_velocity = (
        clean.iloc[-1]
        - clean.iloc[-2]
    )

    previous_velocity = (
        clean.iloc[-2]
        - clean.iloc[-3]
    )

    return (
        current_velocity
        - previous_velocity
    )


def calc_metric_trend(df, metric_col, date_col="Date", group_cols=None):
    if df is None or df.empty:
        return {
            "current": np.nan,
            "velocity": np.nan,
            "acceleration": np.nan,
        }

    df = sort_history_for_trend(
        df,
        date_col=date_col,
        group_cols=group_cols,
    )

    if df is None or df.empty:
        return {
            "current": np.nan,
            "velocity": np.nan,
            "acceleration": np.nan,
        }

    resolved_col = resolve_metric_col(
        df,
        metric_col
    )

    if resolved_col is None:
        return {
            "current": np.nan,
            "velocity": np.nan,
            "acceleration": np.nan,
        }

    series = (
        pd.to_numeric(
            df[resolved_col],
            errors="coerce"
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if series.empty:
        return {
            "current": np.nan,
            "velocity": np.nan,
            "acceleration": np.nan,
        }

    return {
        "current": series.iloc[-1],
        "velocity": calc_velocity(series),
        "acceleration": calc_acceleration(series),
    }
