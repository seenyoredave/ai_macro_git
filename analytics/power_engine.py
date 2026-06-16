import numpy as np
import pandas as pd


def calculate_power_stress_zscore(
    fred_history,
    column="Industrial Production",
    lookback=24
):
    """
    Calculates power stress as a z-score:

    current value compared to trailing historical baseline.

    Returns:
        raw z-score
    """

    if fred_history is None or fred_history.empty:
        return np.nan

    if column not in fred_history.columns:
        return np.nan

    series = (
        pd.to_numeric(
            fred_history[column],
            errors="coerce"
        )
        .dropna()
    )

    if len(series) < 1:
        return np.nan

    baseline = series.tail(lookback)

    current = series.iloc[-1]
    mean = baseline.mean()
    std = baseline.std()

    if pd.isna(std) or std == 0:
        return np.nan

    return (current - mean) / std