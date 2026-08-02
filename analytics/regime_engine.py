from __future__ import annotations

import math

import numpy as np
import pandas as pd

from analytics.borrower_strain_engine import (
    calculate_borrower_strain,
    normalize_borrower_strain_history,
)
from analytics.borrower_strain_history import combine_borrower_strain_history
from analytics.deployment_funding_mix import calculate_deployment_funding_mix
from analytics.development_engine import calculate_ai_development_intensity
from analytics.economic_validation import calculate_economic_validation_gap
from analytics.hhi_engine import calc_hhi_from_sector_data, normalize_hhi
from analytics.lender_strain_engine import (
    calculate_lender_strain,
    normalize_lender_strain_history,
)
from analytics.power_engine import (
    calculate_power_stress,
    normalize_power_stress_history,
)
from analytics.power_capacity_gap import (
    POWER_CAPACITY_GAP_VERSION,
    calculate_power_capacity_gap,
)

AEI_VERSION = "3.1"
ADI_VERSION = "1.0"
EVG_VERSION = "2.0"
POWER_STRESS_VERSION = "3.0"
BORROWER_STRAIN_VERSION = "3.0"
LENDER_STRAIN_VERSION = "3.1"
PRESSURE_VERSION = "3.0"

def calc_aei(sector_metrics):
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
    del fred_history

    current_aei = calc_aei(sector_metrics)
    avg_pressure = calc_avg_sector_pressure(sector_metrics)

    power_result = calculate_power_stress(fred_data or {})
    development_result = calculate_ai_development_intensity(
        sector_data or {},
        construction_data=construction_data,
        power_result=power_result,
    )
    validation_result = calculate_economic_validation_gap(
        sector_data or {},
        fred_data or {},
    )
    power_capacity_gap_result = calculate_power_capacity_gap(
        development_result,
        fred_data or {},
    )
    borrower_strain_result = calculate_borrower_strain(sector_data or {})
    funding_mix_result = calculate_deployment_funding_mix(sector_data or {})
    lender_strain_result = calculate_lender_strain(fred_data or {})

    current_adi = development_result.get("score", np.nan)
    current_validation_gap = validation_result.get("score", np.nan)
    current_power = power_result.get("score", np.nan)
    current_power_capacity_gap = power_capacity_gap_result.get("score", np.nan)
    current_borrower_strain = borrower_strain_result.get("score", np.nan)
    current_lender_strain = lender_strain_result.get("score", np.nan)

    aei, aei_source, aei_date = _resolve_with_archive(
        current_aei,
        macro_history,
        "AI Equity Index",
        version_column="AEI Version",
        required_version=AEI_VERSION,
    )
    adi, adi_source, adi_date = _resolve_with_archive(
        current_adi,
        macro_history,
        "AI Development Intensity",
        version_column="ADI Version",
        required_version=ADI_VERSION,
    )
    validation_gap, validation_gap_source, validation_gap_date = _resolve_with_archive(
        current_validation_gap,
        macro_history,
        "Economic Validation Gap",
        version_column="EVG Version",
        required_version=EVG_VERSION,
    )
    power_history = normalize_power_stress_history(macro_history)
    power_stress, power_source, power_date = _resolve_with_archive(
        current_power,
        power_history,
        "Power Stress Index",
        version_column="Power Stress Version",
        required_version=POWER_STRESS_VERSION,
    )
    power_capacity_gap, power_capacity_gap_source, power_capacity_gap_date = _resolve_with_archive(
        current_power_capacity_gap,
        macro_history,
        "Power Capacity Gap",
        version_column="Power Capacity Gap Version",
        required_version=POWER_CAPACITY_GAP_VERSION,
    )
    borrower_strain_history = normalize_borrower_strain_history(
        combine_borrower_strain_history(macro_history)
    )
    borrower_strain, borrower_strain_source, borrower_strain_date = _resolve_with_archive(
        current_borrower_strain,
        borrower_strain_history,
        "Borrower Strain",
        version_column="Borrower Strain Version",
        required_version=BORROWER_STRAIN_VERSION,
    )
    lender_strain_history = normalize_lender_strain_history(macro_history)
    lender_strain, lender_strain_source, lender_strain_date = _resolve_with_archive(
        current_lender_strain,
        lender_strain_history,
        "Lender Strain",
        version_column="Lender Strain Version",
        required_version=LENDER_STRAIN_VERSION,
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
        "Economic Validation Gap": validation_gap,
        "Economic Validation Gap Current": current_validation_gap,
        "Economic Validation Gap Source": validation_gap_source,
        "Economic Validation Gap Fallback Date": validation_gap_date,
        "Power Stress Index": power_stress,
        "Power Stress Index Current": current_power,
        "Power Stress Source": power_source,
        "Power Stress Fallback Date": power_date,
        "Power Capacity Gap": power_capacity_gap,
        "Power Capacity Gap Current": current_power_capacity_gap,
        "Power Capacity Gap Source": power_capacity_gap_source,
        "Power Capacity Gap Fallback Date": power_capacity_gap_date,
        "Borrower Strain": borrower_strain,
        "Borrower Strain Current": current_borrower_strain,
        "Borrower Strain Source": borrower_strain_source,
        "Borrower Strain Fallback Date": borrower_strain_date,
        "Lender Strain": lender_strain,
        "Lender Strain Current": current_lender_strain,
        "Lender Strain Source": lender_strain_source,
        "Lender Strain Fallback Date": lender_strain_date,
        "Concentration HHI": normalize_hhi(raw_hhi),
        "Raw AI HHI": raw_hhi,
        "Avg Sector Pressure": avg_pressure,
        "ADI Components": development_result,
        "Economic Validation Gap Components": validation_result,
        "Power Stress Components": power_result,
        "Power Capacity Gap Components": power_capacity_gap_result,
        "Borrower Strain Components": borrower_strain_result,
        "Deployment Funding Mix": funding_mix_result,
        "Lender Strain Components": lender_strain_result,
        "AEI Version": AEI_VERSION,
        "ADI Version": ADI_VERSION,
        "EVG Version": EVG_VERSION,
        "Power Stress Version": POWER_STRESS_VERSION,
        "Power Capacity Gap Version": POWER_CAPACITY_GAP_VERSION,
        "Borrower Strain Version": BORROWER_STRAIN_VERSION,
        "Lender Strain Version": LENDER_STRAIN_VERSION,
        "Pressure Version": PRESSURE_VERSION,
    }
