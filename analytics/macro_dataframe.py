from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.borrower_strain_engine import normalize_borrower_strain_history
from analytics.borrower_strain_history import combine_borrower_strain_history
from analytics.lender_strain_engine import normalize_lender_strain_history
from analytics.power_engine import normalize_power_stress_history
from analytics.regime_engine import (
    AEI_VERSION,
    ADI_VERSION,
    BORROWER_STRAIN_VERSION,
    LENDER_STRAIN_VERSION,
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

def _append_current_metric_observation(
    history,
    metric_col,
    current_value,
    *,
    version_column=None,
    version=None,
):
    numeric = pd.to_numeric(current_value, errors="coerce")
    if pd.isna(numeric) or not np.isfinite(numeric):
        return history

    working = history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()
    row = {"Date": pd.Timestamp.today().normalize(), metric_col: float(numeric)}
    if version_column and version is not None:
        row[version_column] = str(version)

    working = pd.concat([working, pd.DataFrame([row])], ignore_index=True, sort=False)
    working["_current_date"] = pd.to_datetime(
        working.get("Date"), errors="coerce", format="mixed"
    )
    working = (
        working.loc[working["_current_date"].notna()]
        .sort_values("_current_date", kind="stable")
        .drop_duplicates(subset=["_current_date"], keep="last")
        .drop(columns="_current_date")
        .reset_index(drop=True)
    )
    return working

def _build_version_aware_aei_trend(macro_history, current_value=np.nan):
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
            "Sector Basket Concentration": metrics.get("Sector Basket Concentration", np.nan),
            "Sector Raw HHI": metrics.get("Sector Raw HHI", np.nan),
            "Sector Effective Firms": metrics.get("Sector Effective Firms", np.nan),
            "Sector Concentration Company Count": metrics.get("Sector Concentration Company Count", 0),
            "Sector Concentration Coverage": metrics.get("Sector Concentration Coverage", np.nan),
            "Sector Concentration Version": metrics.get("Sector Concentration Version", ""),
        })

    macro_df = pd.DataFrame(rows)

    if DEBUG:
        debug_print("\n=== MACRO DATAFRAME ===")
        debug_print(macro_df)

    return macro_df

def build_macro_dashboard_data(sector_metrics, regime_metrics=None):
    macro_df = build_macro_dataframe(sector_metrics)
    macro_history = load_macro_history()
    regime_metrics = regime_metrics or {}
    signed_power_history = normalize_power_stress_history(macro_history)
    signed_capital_history = normalize_borrower_strain_history(
        combine_borrower_strain_history(macro_history)
    )
    signed_lender_strain_history = normalize_lender_strain_history(macro_history)

    if regime_metrics.get("Borrower Strain Source") == "Current":
        signed_capital_history = _append_current_metric_observation(
            signed_capital_history,
            "Borrower Strain",
            regime_metrics.get("Borrower Strain", np.nan),
            version_column="Borrower Strain Version",
            version=BORROWER_STRAIN_VERSION,
        )

    native_lender_strain_history = (
        (regime_metrics.get("Lender Strain Components", {}) or {})
        .get("history")
    )
    if not isinstance(native_lender_strain_history, pd.DataFrame) or native_lender_strain_history.empty:
        native_lender_strain_history = signed_lender_strain_history

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
        "borrower_strain_trend": calc_metric_trend(
            signed_capital_history,
            "Borrower Strain",
            version_column="Borrower Strain Version",
            required_version=BORROWER_STRAIN_VERSION,
            distinct_observations=True,
            repeat_tolerance=1e-8,
        ),
        "lender_strain_trend": calc_metric_trend(
            native_lender_strain_history,
            "Lender Strain",
            version_column=(
                "Lender Strain Version"
                if "Lender Strain Version" in native_lender_strain_history.columns
                else None
            ),
            required_version=(
                LENDER_STRAIN_VERSION
                if "Lender Strain Version" in native_lender_strain_history.columns
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
