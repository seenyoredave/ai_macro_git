from __future__ import annotations

import numpy as np
import pandas as pd

BUILDOUT_SERIES = [
    ("Data Center Construction", "Data centers"),
    ("Computer, Electronic & Electrical Manufacturing Construction", "Compute manufacturing"),
    ("Electric Power Construction", "Electric power"),
    ("Communication Construction", "Communications"),
    ("Public Water Supply Construction", "Public water"),
]


def construction_momentum(history: pd.DataFrame | None) -> pd.DataFrame:
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Observation Date", "Series", "YoY Growth"])
    frame = history.copy()
    frame["Observation Date"] = pd.to_datetime(frame.get("Observation Date"), errors="coerce", format="mixed")
    frame = frame.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
    rows = []
    for column, label in BUILDOUT_SERIES:
        values = pd.to_numeric(frame.get(column), errors="coerce")
        growth = values / values.shift(12) - 1.0
        valid = pd.DataFrame({
            "Observation Date": frame["Observation Date"],
            "Series": label,
            "YoY Growth": growth,
            "Level": values,
        }).dropna(subset=["YoY Growth"])
        rows.append(valid)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(
        columns=["Observation Date", "Series", "YoY Growth", "Level"]
    )


def current_buildout_momentum(history: pd.DataFrame | None) -> pd.DataFrame:
    momentum = construction_momentum(history)
    if momentum.empty:
        return pd.DataFrame(columns=["Series", "YoY Growth", "Level", "Observation Date"])
    return (
        momentum.sort_values("Observation Date", kind="stable")
        .groupby("Series", as_index=False, sort=False)
        .tail(1)
        .sort_values("YoY Growth", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def quarterly_rotation_matrix(history: pd.DataFrame | None, *, years: int = 6) -> pd.DataFrame:
    momentum = construction_momentum(history)
    if momentum.empty:
        return pd.DataFrame()
    latest = momentum["Observation Date"].max()
    if years:
        momentum = momentum.loc[momentum["Observation Date"] >= latest - pd.DateOffset(years=years)].copy()
    momentum["Quarter"] = momentum["Observation Date"].dt.to_period("Q")
    quarter_end = (
        momentum.sort_values("Observation Date", kind="stable")
        .groupby(["Series", "Quarter"], as_index=False, sort=False)
        .tail(1)
    )
    pivot = quarter_end.pivot(index="Series", columns="Quarter", values="YoY Growth") * 100.0
    order = [label for _, label in BUILDOUT_SERIES]
    return pivot.reindex([label for label in order if label in pivot.index])


def supporting_balance(components: pd.DataFrame | None) -> dict:
    if components is None or not isinstance(components, pd.DataFrame) or components.empty:
        return {
            "gross_positive_excess": np.nan,
            "gross_shortfall": np.nan,
            "net_support_balance": np.nan,
            "components_above": 0,
            "components_below": 0,
        }
    deviation = pd.to_numeric(components.get("Deviation from Baseline"), errors="coerce")
    if deviation.isna().all() and {"Observed", "Expected Baseline"}.issubset(components.columns):
        deviation = pd.to_numeric(components["Observed"], errors="coerce") - pd.to_numeric(
            components["Expected Baseline"], errors="coerce"
        )
    return {
        "gross_positive_excess": float(deviation.clip(lower=0).sum(min_count=1)),
        "gross_shortfall": float(deviation.clip(upper=0).sum(min_count=1)),
        "net_support_balance": float(deviation.sum(min_count=1)),
        "components_above": int(deviation.gt(0).sum()),
        "components_below": int(deviation.lt(0).sum()),
    }
