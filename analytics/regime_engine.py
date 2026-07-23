"""Macro regime calculations: AEI, ADI, Power Stress, and Capital Stress."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from analytics.capital_stress_engine import (
    calculate_capital_stress,
    normalize_capital_stress_history,
)
from analytics.development_engine import calculate_ai_development_intensity
from analytics.hhi_engine import calc_hhi_from_sector_data, normalize_hhi
from analytics.power_engine import (
    calculate_power_stress,
    normalize_power_stress_history,
)


AEI_VERSION = "2.0"
ADI_VERSION = "1.0"
POWER_STRESS_VERSION = "3.0"
CAPITAL_STRESS_VERSION = "2.0"
PRESSURE_VERSION = "2.0"


def calc_aei(sector_metrics):
    """AI Equity Index = equal mean of valid sector AEI scores.

    At least 75% of configured sector scores must be valid. Remaining sectors
    retain equal weighting; missing sectors are not treated as zero.
    """
    if not sector_metrics:
        return np.nan

    scores = pd.to_numeric(
        pd.Series([
            metrics.get("Sector Score", np.nan)
            for metrics in sector_metrics.values()
        ]),
        errors="coerce",
    ).replace([np.inf, -np.inf], np.nan)

    minimum = max(1, math.ceil(len(scores) * 0.75))
    valid = scores.dropna()

    if len(valid) < minimum:
        return np.nan

    return float(valid.mean())


def calc_avg_sector_pressure(sector_metrics):
    if not sector_metrics:
        return np.nan

    pressures = pd.to_numeric(
        pd.Series([
            metrics.get("Sector Pressure", np.nan)
            for metrics in sector_metrics.values()
        ]),
        errors="coerce",
    ).replace([np.inf, -np.inf], np.nan)

    minimum = max(1, math.ceil(len(pressures) * 0.75))
    valid = pressures.dropna()

    if len(valid) < minimum:
        return np.nan

    return float(valid.mean())


def cycle_strategy(score):
    """Non-prescriptive AEI regime labels."""
    if pd.isna(score):
        return {
            "regime": "No Data",
            "action": "Insufficient data",
            "risk": "Unable to assess",
            "positioning": "No signal",
        }

    if score < 30:
        label = "Weak"
    elif score < 60:
        label = "Neutral"
    elif score < 80:
        label = "Strong"
    else:
        label = "Extended"

    return {
        "regime": label,
        "action": "Analytical regime only",
        "risk": "Not a trading directive",
        "positioning": "No prescribed positioning",
    }


def _latest_valid_archive_value(
    history,
    column,
    *,
    aliases=None,
    version_column=None,
    required_version=None,
):
    if history is None or history.empty:
        return np.nan, None

    working = history.copy()

    if version_column and required_version:
        if version_column not in working.columns:
            return np.nan, None
        working = working[
            working[version_column].astype(str) == str(required_version)
        ].copy()

    candidates = [column] + list(aliases or [])
    existing = [name for name in candidates if name in working.columns]
    if not existing or working.empty:
        return np.nan, None

    values = pd.Series(np.nan, index=working.index, dtype=float)
    for name in existing:
        candidate = pd.to_numeric(working[name], errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        )
        values = values.fillna(candidate)

    working["_metric_value"] = values
    working = working.dropna(subset=["_metric_value"])
    if working.empty:
        return np.nan, None

    as_of = None
    if "Date" in working.columns:
        working["_metric_date"] = pd.to_datetime(
            working["Date"], errors="coerce", format="mixed"
        )
        working = working.sort_values("_metric_date", kind="stable")
        date_value = working.iloc[-1]["_metric_date"]
        as_of = date_value.date().isoformat() if pd.notna(date_value) else None

    return float(working.iloc[-1]["_metric_value"]), as_of


def _resolve_with_archive(
    current,
    history,
    column,
    *,
    aliases=None,
    version_column=None,
    required_version=None,
):
    current = pd.to_numeric(current, errors="coerce")

    if pd.notna(current) and np.isfinite(current):
        return float(current), "Current", None

    fallback, fallback_date = _latest_valid_archive_value(
        history,
        column,
        aliases=aliases,
        version_column=version_column,
        required_version=required_version,
    )

    if pd.notna(fallback):
        return fallback, "Archive Fallback", fallback_date

    return np.nan, "Unavailable", None


def build_regime_metrics(
    sector_metrics,
    sector_data=None,
    fred_history=None,
    fred_data=None,
    construction_data=None,
    macro_history=None,
):
    """Build current macro metrics while preserving the legacy signature."""
    del fred_history  # retained in the public signature for compatibility

    current_aei = calc_aei(sector_metrics)
    avg_pressure = calc_avg_sector_pressure(sector_metrics)

    power_result = calculate_power_stress(fred_data or {})
    development_result = calculate_ai_development_intensity(
        sector_data or {},
        construction_data=construction_data,
        power_result=power_result,
    )
    capital_result = calculate_capital_stress(sector_data or {})

    current_adi = development_result.get("score", np.nan)
    current_power = power_result.get("score", np.nan)
    current_capital = capital_result.get("score", np.nan)

    aei, aei_source, aei_date = _resolve_with_archive(
        current_aei,
        macro_history,
        "AI Equity Index",
    )
    adi, adi_source, adi_date = _resolve_with_archive(
        current_adi,
        macro_history,
        "AI Development Intensity",
        version_column="ADI Version",
        required_version=ADI_VERSION,
    )
    power_history = normalize_power_stress_history(macro_history)
    power_stress, power_source, power_date = _resolve_with_archive(
        current_power,
        power_history,
        "Power Stress Index",
        version_column="Power Stress Version",
        required_version=POWER_STRESS_VERSION,
    )
    capital_history = normalize_capital_stress_history(macro_history)
    capital_stress, capital_source, capital_date = _resolve_with_archive(
        current_capital,
        capital_history,
        "Capital Stress",
        version_column="Capital Stress Version",
        required_version=CAPITAL_STRESS_VERSION,
    )

    speculation_gap = (
        float(np.clip(aei - adi, -100, 100))
        if pd.notna(aei) and pd.notna(adi)
        else np.nan
    )
    speculation_source = (
        "Current"
        if aei_source == "Current" and adi_source == "Current"
        else "Archive-Assisted"
        if pd.notna(speculation_gap)
        else "Unavailable"
    )

    raw_hhi = (
        calc_hhi_from_sector_data(sector_data)
        if sector_data is not None
        else np.nan
    )

    return {
        "AI Equity Index": aei,
        "AI Equity Index Current": current_aei,
        "AEI Source": aei_source,
        "AEI Fallback Date": aei_date,
        "AI Development Intensity": adi,
        "AI Development Intensity Current": current_adi,
        "ADI Source": adi_source,
        "ADI Fallback Date": adi_date,
        "Speculation Gap": speculation_gap,
        "Speculation Gap Source": speculation_source,
        "Power Stress Index": power_stress,
        "Power Stress Index Current": current_power,
        "Power Stress Source": power_source,
        "Power Stress Fallback Date": power_date,
        "Capital Stress": capital_stress,
        "Capital Stress Current": current_capital,
        "Capital Stress Source": capital_source,
        "Capital Stress Fallback Date": capital_date,
        "Concentration HHI": normalize_hhi(raw_hhi),
        "Raw AI HHI": raw_hhi,
        "Avg Sector Pressure": avg_pressure,
        "ADI Components": development_result,
        "Power Stress Components": power_result,
        "Capital Stress Components": capital_result,
        "AEI Version": AEI_VERSION,
        "ADI Version": ADI_VERSION,
        "Power Stress Version": POWER_STRESS_VERSION,
        "Capital Stress Version": CAPITAL_STRESS_VERSION,
        "Pressure Version": PRESSURE_VERSION,
    }
