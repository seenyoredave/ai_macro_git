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
from config.benchmark_config import BENCHMARK_VERSION
from analytics.trend_engine import (
    calc_acceleration,
    calc_metric_trend,
    calc_velocity,
    metric_series,
)
from archive.archive_reader import load_macro_history
from config.debug_config import DEBUG, debug_print

ADI_COMPONENT_COLUMNS = (
    "ADI Capital Deployment",
    "ADI Data Center Construction",
    "ADI Compute Supply Realization",
    "ADI Power Footprint",
)
POWER_STRESS_COMPONENT_COLUMNS = (
    "Power Nonresidential Load",
    "Power Grid Utilization",
    "Power Capacity Response",
)

def _latest_component_contract(history, component_columns):
    """Retain rows computed from the same available component set as the latest row."""
    if history is None or history.empty:
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()
    if any(column not in history.columns for column in component_columns):
        return history.iloc[0:0].copy()

    working = history.copy()
    masks = working.loc[:, list(component_columns)].notna().astype(int).astype(str).agg("".join, axis=1)
    dated = pd.to_datetime(working.get("Date"), errors="coerce", format="mixed")
    valid = dated.notna()
    if not valid.any():
        return working.iloc[0:0].copy()
    latest_index = dated.loc[valid].idxmax()
    return working.loc[masks == masks.loc[latest_index]].copy()

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
    compatible = (
        macro_history.loc[
            macro_history.get(
                "Benchmark Version",
                pd.Series(index=macro_history.index, dtype=object),
            ).astype(str).eq(str(BENCHMARK_VERSION))
        ].copy()
        if macro_history is not None and not macro_history.empty
        else pd.DataFrame()
    )
    trend = calc_metric_trend(
        compatible,
        "AI Equity Index",
        version_column="AEI Version",
        required_version=AEI_VERSION,
        required_filters={"Benchmark Version": BENCHMARK_VERSION},
    )

    history = metric_series(
        compatible,
        "AI Equity Index",
        version_column="AEI Version",
        required_version=AEI_VERSION,
        required_filters={"Benchmark Version": BENCHMARK_VERSION},
    )
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
            compatible,
            "AI Equity Index",
            version_column="AEI Version",
            required_version=AEI_VERSION,
            required_filters={"Benchmark Version": BENCHMARK_VERSION},
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
        trend["velocity"] = calc_velocity(native_values)
        trend["acceleration"] = calc_acceleration(native_values)

    trend["history"] = history.reset_index(drop=True)

    trend.setdefault("revision_date", None)
    trend.setdefault("revision_label", None)
    trend.setdefault(
        "history_note",
        "All retained observations use the universal AEI 4.0 construction.",
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
    compatible_adi_history = _latest_component_contract(
        macro_history,
        ADI_COMPONENT_COLUMNS,
    )
    compatible_power_history = _latest_component_contract(
        signed_power_history,
        POWER_STRESS_COMPONENT_COLUMNS,
    )
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
            compatible_adi_history,
            "AI Development Intensity",
            version_column="ADI Version",
            required_version=ADI_VERSION,
            distinct_observations=True,
            repeat_tolerance=1e-8,
        ),
        "power_stress_trend": calc_metric_trend(
            compatible_power_history,
            "Power Stress Index",
            version_column="Power Stress Version",
            required_version=POWER_STRESS_VERSION,
            distinct_observations=True,
            repeat_tolerance=1e-8,
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
            dynamics_window_days=365,
            dynamics_min_observations=3,
            dynamics_min_span_days=120,
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
            distinct_observations=True,
            repeat_tolerance=1e-8,
            dynamics_window_days=365,
            dynamics_min_observations=3,
            dynamics_min_span_days=120,
        ),
        "speculation_gap_trend": calc_metric_trend(
            macro_history,
            "Speculation Gap",
            version_column="AEI Version",
            required_version=AEI_VERSION,
            required_filters={
                "Benchmark Version": BENCHMARK_VERSION,
                "ADI Version": ADI_VERSION,
            },
            distinct_observations=True,
            repeat_tolerance=1e-8,
        ),
    }

    return {
        "macro_df": macro_df,
        "macro_history": macro_history,
        "trends": trends,
        "regime_metrics": regime_metrics,
    }
