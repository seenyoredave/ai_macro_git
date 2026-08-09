"""Small presentation helpers for available commercialization disclosures."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def ledger_frame(payload: dict | None) -> pd.DataFrame:
    frame = (payload or {}).get("ledger")
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def metric_row(payload: dict | None, provider: str, metric: str) -> dict:
    frame = ledger_frame(payload)
    if frame.empty or not {"Provider", "Metric"}.issubset(frame.columns):
        return {}
    match = frame.loc[
        frame["Provider"].astype(str).eq(str(provider))
        & frame["Metric"].astype(str).eq(str(metric))
    ]
    if match.empty:
        return {}
    row = match.sort_values("Observation Date", kind="stable").iloc[-1]
    return row.to_dict()


def metric_value(payload: dict | None, provider: str, metric: str) -> float:
    value = pd.to_numeric(metric_row(payload, provider, metric).get("Value"), errors="coerce")
    return float(value) if pd.notna(value) and np.isfinite(value) else np.nan


def filtered_ledger(
    payload: dict | None,
    *,
    pillars: Iterable[str] | None = None,
    providers: Iterable[str] | None = None,
) -> pd.DataFrame:
    frame = ledger_frame(payload)
    if frame.empty:
        return frame
    if pillars and "Pillar" in frame.columns:
        allowed = {str(value) for value in pillars}
        frame = frame.loc[frame["Pillar"].astype(str).isin(allowed)]
    if providers and "Provider" in frame.columns:
        allowed = {str(value) for value in providers}
        frame = frame.loc[frame["Provider"].astype(str).isin(allowed)]
    display = [
        "Provider",
        "Product / Scope",
        "Pillar",
        "Metric",
        "Value",
        "Unit",
        "Observation Date",
        "Notes",
        "Evidence Grade",
        "Source Label",
        "Source URL",
    ]
    return frame[[column for column in display if column in frame.columns]].reset_index(drop=True)
