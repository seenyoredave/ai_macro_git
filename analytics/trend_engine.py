import numpy as np
import pandas as pd


def calc_velocity(series):
    clean = pd.to_numeric(series, errors="coerce").dropna()

    if len(clean) < 2:
        return 0

    return clean.iloc[-1] - clean.iloc[-2]


def calc_acceleration(series):

    clean = pd.to_numeric(
        series,
        errors="coerce"
    ).dropna()

    if len(clean) < 3:
        return 0

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


def calc_metric_trend(df, metric_col):

    if df is None or df.empty:
        return {
            "current": 0,
            "velocity": 0,
            "acceleration": 0,
        }

    if metric_col not in df.columns:
        return {
            "current": 0,
            "velocity": 0,
            "acceleration": 0,
        }

    series = (
        pd.to_numeric(
            df[metric_col],
            errors="coerce"
        )
        .dropna()
    )

    if series.empty:
        return {
            "current": 0,
            "velocity": 0,
            "acceleration": 0,
        }

    current = series.iloc[-1]

    velocity = (
        series.iloc[-1] - series.iloc[-2]
        if len(series) >= 2
        else 0
    )

    acceleration = (
        (series.iloc[-1] - series.iloc[-2])
        -
        (series.iloc[-2] - series.iloc[-3])
        if len(series) >= 3
        else 0
    )

    return {
        "current": current,
        "velocity": velocity,
        "acceleration": acceleration,
    }