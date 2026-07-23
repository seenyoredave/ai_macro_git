"""Power Stress Index and power-footprint calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score, weighted_available_score


POWER_STRESS_WEIGHTS = {
    "Nonresidential Load Pressure": 0.40,
    "Grid Utilization Pressure": 0.35,
    "Capacity Response Gap": 0.25,
}

POWER_FOOTPRINT_WEIGHTS = {
    "Commercial Load Growth": 0.60,
    "Electric Output Growth": 0.40,
}


def power_stress_to_signed(value):
    """Map the internal 0-100 stress score to a centered -100 to +100 scale."""
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip(2.0 * (float(value) - 50.0), -100.0, 100.0))


def normalize_power_stress_history(history):
    """Normalize current-version Power Stress archive metadata.

    Historical values are rebuilt offline from retained raw inputs. Runtime
    code does not migrate or rescale legacy calculated values.
    """
    if history is None or history.empty or "Power Stress Index" not in history.columns:
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()

    out = history.copy()
    out["Power Stress Index"] = pd.to_numeric(
        out["Power Stress Index"], errors="coerce"
    )
    if "Power Stress Version" in out.columns:
        out["Power Stress Version"] = out["Power Stress Version"].astype("string")
    else:
        out["Power Stress Version"] = pd.Series(pd.NA, index=out.index, dtype="string")
    return out


def _fred_value(fred_data, name):
    if not fred_data or name not in fred_data:
        return np.nan

    payload = fred_data[name]
    value = payload.get("value", np.nan) if isinstance(payload, dict) else payload
    return pd.to_numeric(value, errors="coerce")


def calculate_power_stress(fred_data) -> dict:
    """Calculate Power Stress from three observable system effects.

    Components:
      1. commercial electricity-sales growth minus residential growth;
      2. electric-power capacity utilization;
      3. electric-power output growth minus capacity growth.

    Two of three stress components are sufficient. A separate power-footprint
    score is returned for ADI so development does not directly reuse the entire
    stress score.
    """
    commercial_yoy = _fred_value(fred_data, "Commercial Electricity Sales YoY")
    residential_yoy = _fred_value(fred_data, "Residential Electricity Sales YoY")
    utilization = _fred_value(fred_data, "Electric Power Capacity Utilization")
    output_yoy = _fred_value(fred_data, "Electric Power Output YoY")
    capacity_yoy = _fred_value(fred_data, "Electric Power Capacity YoY")

    load_gap = (
        float(commercial_yoy - residential_yoy)
        if pd.notna(commercial_yoy) and pd.notna(residential_yoy)
        else np.nan
    )
    capacity_gap = (
        float(output_yoy - capacity_yoy)
        if pd.notna(output_yoy) and pd.notna(capacity_yoy)
        else np.nan
    )

    base_stress_scores = {
        "Nonresidential Load Pressure": tanh_score(load_gap, center=0.0, scale=0.04),
        "Grid Utilization Pressure": tanh_score(utilization, center=75.0, scale=10.0),
        "Capacity Response Gap": tanh_score(capacity_gap, center=0.0, scale=0.03),
    }
    stress_combined = weighted_available_score(
        base_stress_scores,
        POWER_STRESS_WEIGHTS,
        min_components=2,
    )
    signed_stress_scores = {
        name: power_stress_to_signed(score)
        for name, score in base_stress_scores.items()
    }
    signed_stress = power_stress_to_signed(stress_combined["score"])

    footprint_scores = {
        "Commercial Load Growth": tanh_score(commercial_yoy, center=0.02, scale=0.06),
        "Electric Output Growth": tanh_score(output_yoy, center=0.01, scale=0.04),
    }
    footprint_combined = weighted_available_score(
        footprint_scores,
        POWER_FOOTPRINT_WEIGHTS,
        min_components=2,
    )

    return {
        "score": signed_stress,
        "base_score": stress_combined["score"],
        "valid_components": stress_combined["valid_components"],
        "coverage": stress_combined["coverage"],
        "footprint_score": footprint_combined["score"],
        "footprint_valid_components": footprint_combined["valid_components"],
        "components": {
            "Nonresidential Load Pressure": {
                "raw": load_gap,
                "score": signed_stress_scores["Nonresidential Load Pressure"],
                "base_score": base_stress_scores["Nonresidential Load Pressure"],
                "weight": POWER_STRESS_WEIGHTS["Nonresidential Load Pressure"],
            },
            "Grid Utilization Pressure": {
                "raw": utilization,
                "score": signed_stress_scores["Grid Utilization Pressure"],
                "base_score": base_stress_scores["Grid Utilization Pressure"],
                "weight": POWER_STRESS_WEIGHTS["Grid Utilization Pressure"],
            },
            "Capacity Response Gap": {
                "raw": capacity_gap,
                "score": signed_stress_scores["Capacity Response Gap"],
                "base_score": base_stress_scores["Capacity Response Gap"],
                "weight": POWER_STRESS_WEIGHTS["Capacity Response Gap"],
            },
        },
        "footprint_components": {
            "Commercial Load Growth": {
                "raw": commercial_yoy,
                "score": footprint_scores["Commercial Load Growth"],
                "weight": POWER_FOOTPRINT_WEIGHTS["Commercial Load Growth"],
            },
            "Electric Output Growth": {
                "raw": output_yoy,
                "score": footprint_scores["Electric Output Growth"],
                "weight": POWER_FOOTPRINT_WEIGHTS["Electric Output Growth"],
            },
        },
    }

