"""Financial-conditions confirmation helpers.

This module keeps NFCI interpretation independent from Streamlit rendering so
current-state labels and direction calculations remain testable and reusable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


NFCI_KEYS = [
    "Financial Conditions NFCI",
    "NFCI",
    "National Financial Conditions Index",
    "Chicago Fed NFCI",
]


def clean_nfci_history(history):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if "Date" not in history.columns or "Value" not in history.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    clean = history[["Date", "Value"]].copy()
    clean["Date"] = pd.to_datetime(
        clean["Date"], errors="coerce", format="mixed"
    )
    clean["Value"] = pd.to_numeric(
        clean["Value"], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    return (
        clean.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _payload_value(fred_data):
    for key in NFCI_KEYS:
        if key not in (fred_data or {}):
            continue
        payload = fred_data[key]
        value = payload.get("value", np.nan) if isinstance(payload, dict) else payload
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric):
            return float(numeric), payload if isinstance(payload, dict) else {}
    return np.nan, {}


def nfci_snapshot(fred_data, history):
    current, payload = _payload_value(fred_data)
    as_of = payload.get("date")
    source = payload.get("source")

    clean = clean_nfci_history(history)
    if pd.isna(current) and not clean.empty:
        current = float(clean["Value"].iloc[-1])
        as_of = clean["Date"].iloc[-1].date().isoformat()

    if pd.notna(current):
        current_date = pd.to_datetime(as_of, errors="coerce")
        if pd.isna(current_date):
            current_date = clean["Date"].max() if not clean.empty else pd.NaT
        if pd.notna(current_date):
            current_row = pd.DataFrame(
                {"Date": [current_date], "Value": [float(current)]}
            )
            clean = clean_nfci_history(
                pd.concat([clean, current_row], ignore_index=True)
            )
            as_of = pd.Timestamp(current_date).date().isoformat()

    if not source:
        source = getattr(history, "attrs", {}).get("source", "FRED")

    delta = np.nan
    if len(clean) >= 2:
        latest_date = clean["Date"].iloc[-1]
        target_date = latest_date - pd.DateOffset(months=3)
        prior = clean.loc[clean["Date"] <= target_date]
        if not prior.empty:
            delta = float(
                clean["Value"].iloc[-1] - prior["Value"].iloc[-1]
            )

    return {
        "value": current,
        "as_of": as_of,
        "source": source or "FRED",
        "three_month_change": delta,
        "history": clean,
    }


def nfci_condition(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value):
        return "No Data"
    if value <= -0.50:
        return "Highly Supportive"
    if value < -0.10:
        return "Looser Than Average"
    if value <= 0.10:
        return "Near Average"
    if value < 0.50:
        return "Tighter Than Average"
    if value < 1.00:
        return "Stressed"
    return "Acute Stress"


def nfci_direction(change):
    change = pd.to_numeric(change, errors="coerce")
    if pd.isna(change):
        return "No Data"
    if change >= 0.10:
        return "Tightening ↑"
    if change <= -0.10:
        return "Easing ↓"
    return "Stable →"


def nfci_summary(value, change):
    value = pd.to_numeric(value, errors="coerce")
    change = pd.to_numeric(change, errors="coerce")
    if pd.isna(value):
        return "Financial-conditions confirmation is unavailable."

    if value < -0.10:
        base = "Conditions remain looser than their long-run average"
    elif value > 0.10:
        base = "Conditions are tighter than their long-run average"
    else:
        base = "Conditions are near their long-run average"

    if pd.isna(change):
        return f"{base}."
    if change >= 0.10:
        return f"{base}, but have tightened over the past three months."
    if change <= -0.10:
        return f"{base}, and have eased over the past three months."
    return f"{base}, with little net change over the past three months."
