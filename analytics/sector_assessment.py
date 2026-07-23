"""Current Sector Assessment selection logic.

This module keeps sector-selection methods out of the display layer.
The assessment cards present current crowding, movement, and financial
deterioration breadth without exposing implementation details in the UI.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from archive.archive_reader import load_sector_history


ASSESSMENT_VERSION = "CSA_v3.0"
PRESSURE_VERSION = "2.0"
SECTOR_MOVEMENT_LOOKBACK = 10
RISK_COVERAGE_THRESHOLD = 0.50


def _as_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _sector_row(macro_df: pd.DataFrame, sector: str) -> pd.Series | None:
    if macro_df is None or macro_df.empty or "Sector" not in macro_df.columns:
        return None

    rows = macro_df[macro_df["Sector"].astype(str) == str(sector)]

    if rows.empty:
        return None

    return rows.iloc[-1]


def _empty_selection() -> dict[str, Any]:
    return {
        "rows": {
            "Most Crowded": None,
            "Fastest Mover": None,
            "Biggest Risk": None,
        },
        "metadata": {
            "assessment_version": ASSESSMENT_VERSION,
            "sector_movement_lookback": SECTOR_MOVEMENT_LOOKBACK,
            "risk_coverage_threshold": RISK_COVERAGE_THRESHOLD,
        },
        "movement": pd.DataFrame(),
        "risk": pd.DataFrame(),
    }


def _current_sector_snapshot(macro_df: pd.DataFrame) -> pd.DataFrame:
    if macro_df is None or macro_df.empty:
        return pd.DataFrame()

    required = ["Sector", "Sector Score", "Pressure"]
    missing = [col for col in required if col not in macro_df.columns]

    if missing:
        return pd.DataFrame()

    snapshot = macro_df[required].copy()
    snapshot.insert(0, "Date", date.today().isoformat())
    snapshot["Pressure Version"] = PRESSURE_VERSION

    return snapshot


def _prepare_sector_history(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Normalize sector-history frames to the movement calculation contract."""
    usable_frames = [frame.copy() for frame in frames if frame is not None and not frame.empty]
    if not usable_frames:
        return pd.DataFrame()

    combined = pd.concat(usable_frames, ignore_index=True, sort=False)
    required = ["Date", "Sector", "Sector Score", "Pressure"]
    missing = [col for col in required if col not in combined.columns]
    if missing:
        return pd.DataFrame()

    combined["_assessment_date"] = pd.to_datetime(
        combined["Date"],
        errors="coerce",
        format="mixed",
    )
    combined = combined.loc[combined["_assessment_date"].notna()].copy()
    if combined.empty:
        return pd.DataFrame()

    combined["Sector"] = combined["Sector"].astype(str)
    combined["Sector Score"] = _as_numeric(combined["Sector Score"])
    combined["Pressure"] = _as_numeric(combined["Pressure"])
    combined = combined.sort_values(["Sector", "_assessment_date"], kind="stable")
    combined = combined.drop_duplicates(
        subset=["Sector", "_assessment_date"],
        keep="last",
    )
    return combined


def _sector_history_with_current(macro_df: pd.DataFrame) -> pd.DataFrame:
    """Return Pressure-v2 history plus the current in-memory snapshot."""
    history = load_sector_history()
    current = _current_sector_snapshot(macro_df)

    if history is not None and not history.empty:
        history = history.copy()
        if "Pressure Version" not in history.columns:
            history = history.iloc[0:0].copy()
        else:
            history = history[
                history["Pressure Version"].astype(str) == PRESSURE_VERSION
            ].copy()

    return _prepare_sector_history([history, current])


def _legacy_sector_history() -> pd.DataFrame:
    """Return the most recent internally consistent legacy movement history.

    Legacy pressure values are never mixed with Pressure v2. This fallback keeps
    Fastest Mover useful while the new formulation accumulates enough archived
    observations to calculate movement on its own terms.
    """
    history = load_sector_history()
    if history is None or history.empty:
        return pd.DataFrame()

    history = history.copy()

    # Rebuilt archives keep incompatible historical pressure in an explicit
    # Legacy Pressure column. This prevents the live Pressure column from
    # mixing two different formulas while preserving Fastest Mover continuity.
    if "Legacy Pressure" in history.columns:
        history["Pressure"] = pd.to_numeric(
            history["Legacy Pressure"],
            errors="coerce",
        )
    elif "Pressure Version" in history.columns:
        legacy_mask = history["Pressure Version"].isna() | (
            history["Pressure Version"].astype(str) != PRESSURE_VERSION
        )
        history = history.loc[legacy_mask].copy()

    return _prepare_sector_history([history])


def _movement_from_history(
    history: pd.DataFrame,
    *,
    lookback: int,
    source: str,
) -> pd.DataFrame:
    if history is None or history.empty:
        return pd.DataFrame()

    rows = []
    for sector, group in history.groupby("Sector", sort=False):
        group = group.dropna(subset=["Sector Score", "Pressure"]).copy()
        group = group.sort_values("_assessment_date", kind="stable")
        if len(group) < 2:
            continue

        latest = group.iloc[-1]
        if len(group) > lookback:
            prior = group.iloc[-(lookback + 1)]
            observations_used = lookback
        else:
            prior = group.iloc[0]
            observations_used = len(group) - 1

        delta_score = latest["Sector Score"] - prior["Sector Score"]
        delta_pressure = latest["Pressure"] - prior["Pressure"]
        sector_movement = delta_score + delta_pressure

        rows.append({
            "Sector": sector,
            "Sector Movement": sector_movement,
            "Abs Sector Movement": abs(sector_movement),
            "Delta Sector Score": delta_score,
            "Delta Pressure": delta_pressure,
            "Movement Observations Used": observations_used,
            "Movement Lookback": lookback,
            "Latest Date": latest["_assessment_date"].date().isoformat(),
            "Prior Date": prior["_assessment_date"].date().isoformat(),
            "Movement Source": source,
        })

    return pd.DataFrame(rows)


def calculate_sector_movement(
    macro_df: pd.DataFrame,
    lookback: int = SECTOR_MOVEMENT_LOOKBACK,
) -> pd.DataFrame:
    """Calculate sector movement without crossing pressure-version boundaries.

    Pressure-v2 history is preferred. Until it contains at least two valid
    observations for a sector, the function falls back to the latest complete
    legacy movement result. The legacy result is selection history only; it is
    not blended with today's Pressure-v2 value.
    """
    current_history = _sector_history_with_current(macro_df)
    movement = _movement_from_history(
        current_history,
        lookback=lookback,
        source=f"Pressure {PRESSURE_VERSION}",
    )
    if movement is not None and not movement.empty:
        return movement

    return _movement_from_history(
        _legacy_sector_history(),
        lookback=lookback,
        source="Legacy Archive Fallback",
    )


def calculate_fundamental_risk(
    macro_df: pd.DataFrame,
    sector_data: dict[str, pd.DataFrame] | None,
    coverage_threshold: float = RISK_COVERAGE_THRESHOLD,
) -> pd.DataFrame:
    """Calculate Biggest Risk as financial-deterioration breadth.

    Each valid company-level signal receives an equal binary flag:
      * FCF margin worsened YoY: current fiscal-year margin - prior margin < 0
      * Net debt / EBITDA worsened YoY: current ratio - prior ratio > 0
      * CapEx / OCF worsened YoY: current ratio - prior ratio > 0

    Sector Risk Score = 100 * adverse flags / valid flags. A sector is
    eligible only when the available signals cover at least the configured
    share of its three-per-company opportunity set.
    """
    if not sector_data or macro_df is None or macro_df.empty:
        return pd.DataFrame()

    signal_contract = {
        "FCF Margin YoY Change": lambda values: values < 0,
        "Net Debt / EBITDA YoY Change": lambda values: values > 0,
        "CapEx / OCF YoY Change": lambda values: values > 0,
    }
    rows = []

    for sector, df in sector_data.items():
        if df is None or df.empty:
            continue

        valid_total = 0
        adverse_total = 0
        component_payload = {}

        for column, is_adverse in signal_contract.items():
            values = _as_numeric(df.get(column, pd.Series(np.nan, index=df.index)))
            valid = values.notna()
            valid_count = int(valid.sum())
            adverse_count = int(is_adverse(values.loc[valid]).sum()) if valid_count else 0

            valid_total += valid_count
            adverse_total += adverse_count
            component_payload[column] = {
                "valid": valid_count,
                "adverse": adverse_count,
                "breadth": (100.0 * adverse_count / valid_count) if valid_count else np.nan,
            }

        possible_signals = int(len(df) * len(signal_contract))
        coverage = (valid_total / possible_signals) if possible_signals else np.nan
        eligible = pd.notna(coverage) and coverage >= coverage_threshold and valid_total > 0
        risk_score = (100.0 * adverse_total / valid_total) if eligible else np.nan

        macro_row = _sector_row(macro_df, sector)
        if macro_row is None:
            continue

        rows.append({
            "Sector": sector,
            "Sector Score": pd.to_numeric(macro_row.get("Sector Score", np.nan), errors="coerce"),
            "Pressure": pd.to_numeric(macro_row.get("Pressure", np.nan), errors="coerce"),
            "Risk Breadth Score": risk_score,
            "Adverse Signals": adverse_total,
            "Valid Signals": valid_total,
            "Possible Signals": possible_signals,
            "Coverage": coverage,
            "Eligible": eligible,
            "FCF Deterioration Breadth": component_payload["FCF Margin YoY Change"]["breadth"],
            "Leverage Deterioration Breadth": component_payload["Net Debt / EBITDA YoY Change"]["breadth"],
            "Reinvestment Deterioration Breadth": component_payload["CapEx / OCF YoY Change"]["breadth"],
        })

    return pd.DataFrame(rows)


def select_current_sector_assessment(
    macro_df: pd.DataFrame,
    sector_data: dict[str, pd.DataFrame] | None = None,
) -> dict[str, Any]:
    if macro_df is None or macro_df.empty:
        return _empty_selection()

    required = ["Sector", "Sector Score", "Pressure"]
    missing = [col for col in required if col not in macro_df.columns]

    if missing:
        return _empty_selection()

    assessment_df = macro_df.copy()
    assessment_df["Sector Score"] = _as_numeric(assessment_df["Sector Score"])
    assessment_df["Pressure"] = _as_numeric(assessment_df["Pressure"])

    usable = assessment_df.dropna(subset=["Sector", "Sector Score", "Pressure"])

    if usable.empty:
        return _empty_selection()

    most_crowded = usable.loc[usable["Pressure"].idxmax()]

    movement_df = calculate_sector_movement(
        macro_df,
        lookback=SECTOR_MOVEMENT_LOOKBACK,
    )

    fastest_mover = None

    if movement_df is not None and not movement_df.empty:
        movement_lookup = movement_df.set_index("Sector")["Abs Sector Movement"]
        movement_usable = usable.copy()
        movement_usable["_Abs Sector Movement"] = (
            movement_usable["Sector"].map(movement_lookup)
        )
        movement_usable = movement_usable.dropna(subset=["_Abs Sector Movement"])

        if not movement_usable.empty:
            fastest_mover = movement_usable.loc[
                movement_usable["_Abs Sector Movement"].idxmax()
            ]

    risk_df = calculate_fundamental_risk(
        macro_df,
        sector_data,
        coverage_threshold=RISK_COVERAGE_THRESHOLD,
    )

    biggest_risk = None

    if risk_df is not None and not risk_df.empty:
        risk_lookup = risk_df.set_index("Sector")["Risk Breadth Score"]
        adverse_lookup = risk_df.set_index("Sector")["Adverse Signals"]
        valid_lookup = risk_df.set_index("Sector")["Valid Signals"]
        risk_usable = usable.copy()
        risk_usable["Risk Breadth Score"] = risk_usable["Sector"].map(risk_lookup)
        risk_usable["Adverse Signals"] = risk_usable["Sector"].map(adverse_lookup)
        risk_usable["Valid Signals"] = risk_usable["Sector"].map(valid_lookup)
        risk_usable = risk_usable.dropna(subset=["Risk Breadth Score"])

        if not risk_usable.empty:
            biggest_risk = risk_usable.loc[
                risk_usable["Risk Breadth Score"].idxmax()
            ]

    return {
        "rows": {
            "Most Crowded": most_crowded,
            "Fastest Mover": fastest_mover,
            "Biggest Risk": biggest_risk,
        },
        "metadata": {
            "assessment_version": ASSESSMENT_VERSION,
            "sector_movement_lookback": SECTOR_MOVEMENT_LOOKBACK,
            "risk_coverage_threshold": RISK_COVERAGE_THRESHOLD,
        },
        "movement": movement_df,
        "risk": risk_df,
    }
