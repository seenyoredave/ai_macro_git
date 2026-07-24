"""Macro dashboard data products."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.capital_stress_engine import normalize_capital_stress_history
from analytics.intermediation_stress_engine import normalize_intermediation_stress_history
from analytics.power_engine import normalize_power_stress_history
from analytics.regime_engine import (
    ADI_VERSION,
    CAPITAL_STRESS_VERSION,
    INTERMEDIATION_STRESS_VERSION,
    POWER_STRESS_VERSION,
)
from analytics.trend_engine import calc_metric_trend
from archive.archive_reader import load_macro_history
from config.debug_config import DEBUG, debug_print


def build_macro_dataframe(sector_metrics):
    rows = []

    for sector, metrics in sector_metrics.items():
        rows.append({
            "Sector": sector,
            "Sector Score": metrics.get("Sector Score", np.nan),
            "AEI Score": metrics.get("Sector Score", np.nan),
            "Pressure": metrics.get("Sector Pressure", np.nan),
            "Avg Return": metrics.get("Avg Return", np.nan),
            "Forward P/E": metrics.get("Forward P/E", np.nan),
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
    signed_capital_history = normalize_capital_stress_history(macro_history)
    signed_intermediation_history = normalize_intermediation_stress_history(macro_history)

    native_intermediation_history = (
        (regime_metrics.get("Credit Intermediation Stress Components", {}) or {})
        .get("history")
    )
    if not isinstance(native_intermediation_history, pd.DataFrame) or native_intermediation_history.empty:
        native_intermediation_history = signed_intermediation_history

    trends = {
        "aei_trend": calc_metric_trend(macro_history, "AI Equity Index"),
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
        ),
    }

    return {
        "macro_df": macro_df,
        "macro_history": macro_history,
        "trends": trends,
        "regime_metrics": regime_metrics,
    }
