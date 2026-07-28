"""Macro dashboard data products."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.capital_stress_engine import normalize_capital_stress_history
from analytics.capital_stress_history import combine_capital_stress_history
from analytics.intermediation_stress_engine import normalize_intermediation_stress_history
from analytics.power_engine import normalize_power_stress_history
from analytics.regime_engine import (
    AEI_VERSION,
    ADI_VERSION,
    CAPITAL_STRESS_VERSION,
    INTERMEDIATION_STRESS_VERSION,
    POWER_STRESS_VERSION,
)
from analytics.trend_engine import (
    calc_acceleration,
    calc_metric_trend,
    calc_velocity,
    metric_series,
)
from archive.archive_reader import load_macro_history
from config.debug_config import DEBUG, debug_print


AEI_HISTORY_START = pd.Timestamp("2026-06-14")


def _build_version_aware_aei_trend(macro_history, current_value=np.nan):
    """Return native AEI-v3.1 trend statistics with the full archived chart history.

    Values before the first AEI-v3.1 observation remain explicitly legacy data.
    They are shown for continuity but are not used to calculate current-model
    velocity or acceleration.
    """
    trend = calc_metric_trend(
        macro_history,
        "AI Equity Index",
        version_column="AEI Version",
        required_version=AEI_VERSION,
    )

    history = metric_series(macro_history, "AI Equity Index")
    if not history.empty:
        history = history.loc[history["Date"] >= AEI_HISTORY_START].copy()

    current_value = pd.to_numeric(current_value, errors="coerce")
    current_date = pd.Timestamp.today().normalize()
    if pd.notna(current_value) and np.isfinite(current_value):
        current_row = pd.DataFrame(
            {"Date": [current_date], "Value": [float(current_value)]}
        )
        history = pd.concat([history, current_row], ignore_index=True)
        history = (
            history.sort_values("Date", kind="stable")
            .drop_duplicates("Date", keep="last")
            .reset_index(drop=True)
        )

        native_values = metric_series(
            macro_history.loc[
                macro_history.get("AEI Version", pd.Series(index=macro_history.index, dtype=object))
                .astype(str)
                .eq(str(AEI_VERSION))
            ].copy()
            if macro_history is not None and not macro_history.empty
            else pd.DataFrame(),
            "AI Equity Index",
        )
        native_values = (
            current_row.copy()
            if native_values.empty
            else pd.concat([native_values, current_row], ignore_index=True)
        )
        native_values = (
            native_values.sort_values("Date", kind="stable")
            .drop_duplicates("Date", keep="last")
        )
        trend["current"] = float(current_value)
        trend["velocity"] = calc_velocity(native_values["Value"])
        trend["acceleration"] = calc_acceleration(native_values["Value"])

    trend["history"] = history.reset_index(drop=True)
    # AEI v3.1 starts a clean native calculation series without a chart revision marker.
    trend.setdefault("revision_date", None)
    trend.setdefault("revision_label", None)
    trend.setdefault(
        "history_note",
        "Chart history includes AEI 2.0 observations for continuity; "
        "current velocity and acceleration use AEI 3.1 observations only.",
    )

    return trend


def build_macro_dataframe(sector_metrics):
    rows = []

    for sector, metrics in sector_metrics.items():
        rows.append({
            "Sector": sector,
            "Sector Score": metrics.get("Sector Score", np.nan),
            "AEI Score": metrics.get("Sector Score", np.nan),
            "Pressure": metrics.get("Sector Pressure", np.nan),
            "Avg Return": metrics.get("Avg Return", np.nan),
            "Forward EV/EBIT": metrics.get("Forward EV/EBIT", np.nan),
            "Forward EV/EBIT Status": metrics.get("Forward EV/EBIT Status", ""),
            "Sector Valuation Version": metrics.get("Sector Valuation Version", ""),
            "Forward EBIT Yield": metrics.get("Forward EBIT Yield", np.nan),
            "Forward EBIT Coverage": metrics.get("Forward EBIT Coverage", np.nan),
            "Forward EV/EBIT Coverage": metrics.get("Forward EV/EBIT Coverage", np.nan),
            "Forward EV/EBIT Data Coverage": metrics.get("Forward EV/EBIT Data Coverage", np.nan),
            "Loss-Making EV Share": metrics.get("Loss-Making EV Share", np.nan),
            "Loss-Making Company Count": metrics.get("Loss-Making Company Count", 0),
            "Beta": metrics.get("Beta", np.nan),
        })

    macro_df = pd.DataFrame(rows)

    if DEBUG:
        debug_print("\n=== MACRO DATAFRAME ===")
        debug_print(macro_df)

    return macro_df


def build_macro_dashboard_data(sector_metrics, regime_metrics=None):
    """Prepare macro-level data products without rendering."""
    macro_df = build_macro_dataframe(sector_metrics)
    macro_history = load_macro_history()
    regime_metrics = regime_metrics or {}
    signed_power_history = normalize_power_stress_history(macro_history)
    signed_capital_history = normalize_capital_stress_history(
        combine_capital_stress_history(macro_history)
    )
    signed_intermediation_history = normalize_intermediation_stress_history(macro_history)

    native_intermediation_history = (
        (regime_metrics.get("Credit Intermediation Stress Components", {}) or {})
        .get("history")
    )
    if not isinstance(native_intermediation_history, pd.DataFrame) or native_intermediation_history.empty:
        native_intermediation_history = signed_intermediation_history

    trends = {
        "aei_trend": _build_version_aware_aei_trend(
            macro_history,
            regime_metrics.get("AI Equity Index", np.nan),
        ),
        "adi_trend": calc_metric_trend(
            macro_history,
            "AI Development Intensity",
            version_column="ADI Version",
            required_version=ADI_VERSION,
        ),
        "power_stress_trend": calc_metric_trend(
            signed_power_history,
            "Power Stress Index",
            version_column="Power Stress Version",
            required_version=POWER_STRESS_VERSION,
        ),
        "concentration_trend": calc_metric_trend(
            macro_history,
            "Concentration HHI",
        ),
        "capital_stress_trend": calc_metric_trend(
            signed_capital_history,
            "Capital Stress",
            version_column="Capital Stress Version",
            required_version=CAPITAL_STRESS_VERSION,
        ),
        "intermediation_stress_trend": calc_metric_trend(
            native_intermediation_history,
            "Credit Intermediation Stress",
            version_column=(
                "Credit Intermediation Stress Version"
                if "Credit Intermediation Stress Version" in native_intermediation_history.columns
                else None
            ),
            required_version=(
                INTERMEDIATION_STRESS_VERSION
                if "Credit Intermediation Stress Version" in native_intermediation_history.columns
                else None
            ),
        ),
        "speculation_gap_trend": calc_metric_trend(
            macro_history,
            "Speculation Gap",
            version_column="AEI Version",
            required_version=AEI_VERSION,
        ),
    }

    return {
        "macro_df": macro_df,
        "macro_history": macro_history,
        "trends": trends,
        "regime_metrics": regime_metrics,
    }
