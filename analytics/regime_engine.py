### These functions build the regime-level calculations: AMI, divergence, and cycle_strategy


import pandas as pd
import numpy as np

from analytics.hhi_engine import calc_hhi_from_sector_data
from analytics.power_engine import calculate_power_stress_zscore
from helpers.macro_normalization import (
    normalize_power_stress, 
    normalize_hhi,
)

def calc_ami(sector_metrics):
    """
    Calculate the AI Maturation Index.

    AMI = mean Sector Score across sectors.
    """

    if not sector_metrics:
        return np.nan

    sector_scores = [
        metrics.get("Sector Score", np.nan)
        for metrics in sector_metrics.values()
    ]

    sector_scores = pd.to_numeric(
        pd.Series(sector_scores),
        errors="coerce"
    ).dropna()

    if sector_scores.empty:
        return np.nan

    return sector_scores.mean()

def calc_avg_sector_pressure(sector_metrics):
    """
    Calculate average sector pressure across sectors.
    """

    if not sector_metrics:
        return np.nan

    pressures = [
        metrics.get("Sector Pressure", np.nan)
        for metrics in sector_metrics.values()
    ]

    pressures = pd.to_numeric(
        pd.Series(pressures),
        errors="coerce"
    ).dropna()

    if pressures.empty:
        return np.nan

    return pressures.mean()

def calc_divergence(ami, avg_pressure):
    """
    Divergence = AMI - average Sector Pressure.
    """

    if pd.isna(ami) or pd.isna(avg_pressure):
        return np.nan

    return ami - avg_pressure

def cycle_strategy(score):
    
    if pd.isna(score): 
            return {
                "regime": "No Data",
                "action": "Insufficient data",
                "risk": "Unable to assess",
                "positioning": "No signal"
            }
    if score < 30:
        return {
            "regime": "Early Cycle",
            "action": "🟢 Accumulate aggressively on dips",
            "risk": "Low valuation risk, demand accelerating",
            "positioning": "Overweight semicap (KLAC/ASML)"
        }
    elif score < 60:
        return {
            "regime": "Expansion Cycle",
            "action": "🟡 Hold core, add selectively",
            "risk": "Healthy growth, volatility normal",
            "positioning": "Neutral to overweight"
        }
    elif score < 80:
        return {
            "regime": "Late Cycle",
            "action": "🟠 Trim into strength, avoid chasing",
            "risk": "Valuation compression risk rising",
            "positioning": "Neutral / tactical only"
        }
    else:
        return {
            "regime": "Peak Cycle",
            "action": "🔴 Reduce exposure, raise cash buffer",
            "risk": "High drawdown probability",
            "positioning": "Underweight / defensive tilt"
        }

def build_regime_metrics(
    sector_metrics,
    sector_data=None,
    fred_history=None,
):
    ami = calc_ami(sector_metrics)
    avg_pressure = calc_avg_sector_pressure(sector_metrics)
    divergence = calc_divergence(ami, avg_pressure)

    raw_power_stress = (
        calculate_power_stress_zscore(
            fred_history,
            column="Industrial Production",
            lookback=24
        )
        if fred_history is not None
        else np.nan
    )

    power_stress = normalize_power_stress(raw_power_stress)

    raw_hhi = (
        calc_hhi_from_sector_data(sector_data)
        if sector_data is not None
        else np.nan
    )

    ai_concentration_hhi = normalize_hhi(raw_hhi)

    return {
        "Maturation Index": ami,
        "Divergence": divergence,

        "Power Stress Index": power_stress,
        "Raw Power Stress Z": raw_power_stress,

        "Concentration HHI": ai_concentration_hhi,
        "Raw AI HHI": raw_hhi,

        "Avg Sector Pressure": avg_pressure,
    }
