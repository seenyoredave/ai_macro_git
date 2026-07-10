"""Current Sector Assessment selection logic.

This module keeps hidden selection methods out of the display layer.
The dashboard cards continue to display only Sector Cycle Score and
Sector Pressure Score; these helpers decide which sectors belong in the
assessment cards.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from archive.archive_reader import load_sector_history


ASSESSMENT_VERSION = "CSA_v2.1"
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

    return snapshot


def _sector_history_with_current(macro_df: pd.DataFrame) -> pd.DataFrame:
    history = load_sector_history()
    current = _current_sector_snapshot(macro_df)

    frames = []

    if history is not None and not history.empty:
        frames.append(history.copy())

    if current is not None and not current.empty:
        frames.append(current.copy())

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)

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

    combined = combined.sort_values(
        ["Sector", "_assessment_date"],
        kind="stable",
    )

    # If today's current snapshot is also already in sector_history.csv, keep the
    # last same-date row for each sector so the in-memory current run wins.
    combined = combined.drop_duplicates(
        subset=["Sector", "_assessment_date"],
        keep="last",
    )

    return combined


def calculate_sector_movement(
    macro_df: pd.DataFrame,
    lookback: int = SECTOR_MOVEMENT_LOOKBACK,
) -> pd.DataFrame:
    """Calculate Sector Movement for each sector over a fixed lookback.

    Sector Movement = ΔSector Cycle Score + ΔSector Pressure Score.
    Selection uses max(abs(Sector Movement)); the signed value is retained only
    for internal audit/debugging, not public card display.
    """
    history = _sector_history_with_current(macro_df)

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
        })

    return pd.DataFrame(rows)


def _valid_weights_for_mask(weights: pd.Series, mask: pd.Series) -> float:
    weights = _as_numeric(weights)
    mask = mask.fillna(False)

    if weights.empty:
        return 0.0

    return float(weights.loc[mask & weights.notna() & (weights > 0)].sum())


def _aggregate_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
    *,
    high_strain_when_denominator_nonpositive: bool = True,
) -> float:
    """Calculate a sector-level ratio-of-sums.

    This intentionally avoids company-count means/medians. The denominator
    supplies organic economic scale: revenue for FCF margin, EBITDA for debt
    burden, and operating cash flow for reinvestment burden.
    """
    numerator = _as_numeric(numerator)
    denominator = _as_numeric(denominator)
    mask = numerator.notna() & denominator.notna()

    if not mask.any():
        return np.nan

    num_sum = float(numerator.loc[mask].sum())
    den_sum = float(denominator.loc[mask].sum())

    if den_sum > 0:
        return num_sum / den_sum

    if high_strain_when_denominator_nonpositive and num_sum > 0:
        return np.inf

    if num_sum <= 0:
        return 0.0

    return np.nan


def _rank_strain(series: pd.Series, *, higher_is_worse: bool) -> pd.Series:
    """Convert sector ratios to 0-100 cross-sector strain ranks.

    This is not a public score. It makes unlike ratios comparable before they
    are averaged into Financial Strain.
    """
    values = pd.to_numeric(series, errors="coerce").replace([-np.inf], np.nan)
    valid = values.dropna()

    if len(valid) < 2:
        return pd.Series(np.nan, index=series.index)

    ranks = values.rank(method="average", ascending=True)
    n = int(values.notna().sum())

    if n <= 1:
        return pd.Series(np.nan, index=series.index)

    scaled = ((ranks - 1) / (n - 1)) * 100

    if not higher_is_worse:
        scaled = 100 - scaled

    return scaled


def calculate_fundamental_risk(
    macro_df: pd.DataFrame,
    sector_data: dict[str, pd.DataFrame] | None,
    coverage_threshold: float = RISK_COVERAGE_THRESHOLD,
) -> pd.DataFrame:
    """Calculate hidden Biggest Risk selection data.

    Risk Selection Score = Financial Strain × Pressure Amplifier.

    Financial Strain is a mean of sector-level percentile strain ranks:
      1. low FCF Margin strain = Free Cash Flow / Revenue
      2. high Debt Burden strain = Net Debt / EBITDA
      3. high Reinvestment Burden strain = CapEx / Operating Cash Flow

    Each sector-level ratio is a ratio-of-sums, not a company-count average.
    That lets the financial denominators supply organic economic weighting
    without inventing bespoke sector weights.
    """
    if not sector_data or macro_df is None or macro_df.empty:
        return pd.DataFrame()

    rows = []

    for sector, df in sector_data.items():
        if df is None or df.empty:
            continue

        working = df.copy()

        if "Effective Basket Weight" in working.columns:
            weights = _as_numeric(working["Effective Basket Weight"])
        elif "Basket Weight" in working.columns:
            weights = _as_numeric(working["Basket Weight"])
        else:
            weights = pd.Series(1.0, index=working.index)

        weights = weights.where(weights > 0, np.nan)
        total_weight = weights.dropna().sum()

        if total_weight <= 0 or pd.isna(total_weight):
            continue

        revenue = _as_numeric(working.get("Revenue", pd.Series(np.nan, index=working.index)))
        capex = _as_numeric(working.get("CapEx", pd.Series(np.nan, index=working.index)))
        operating_cash_flow = _as_numeric(
            working.get("Operating Cash Flow", pd.Series(np.nan, index=working.index))
        )
        free_cash_flow = _as_numeric(
            working.get("Free Cash Flow", pd.Series(np.nan, index=working.index))
        )
        ebitda = _as_numeric(working.get("EBITDA", pd.Series(np.nan, index=working.index)))
        net_debt = _as_numeric(working.get("Net Debt", pd.Series(np.nan, index=working.index)))

        fcf_margin_valid = free_cash_flow.notna() & revenue.notna() & (revenue > 0)
        debt_valid = net_debt.notna() & ebitda.notna()
        reinvestment_valid = capex.notna() & operating_cash_flow.notna()

        fcf_margin_coverage = (
            _valid_weights_for_mask(weights, fcf_margin_valid) / total_weight
            if total_weight > 0 else np.nan
        )
        debt_coverage = (
            _valid_weights_for_mask(weights, debt_valid) / total_weight
            if total_weight > 0 else np.nan
        )
        reinvestment_coverage = (
            _valid_weights_for_mask(weights, reinvestment_valid) / total_weight
            if total_weight > 0 else np.nan
        )

        eligible_pillars = sum(
            coverage >= coverage_threshold
            for coverage in [
                fcf_margin_coverage,
                debt_coverage,
                reinvestment_coverage,
            ]
            if not pd.isna(coverage)
        )

        macro_row = _sector_row(macro_df, sector)

        if macro_row is None:
            continue

        pressure = pd.to_numeric(macro_row.get("Pressure", np.nan), errors="coerce")
        sector_score = pd.to_numeric(macro_row.get("Sector Score", np.nan), errors="coerce")

        rows.append({
            "Sector": sector,
            "Sector Score": sector_score,
            "Pressure": pressure,
            "FCF Margin": _aggregate_ratio(
                free_cash_flow,
                revenue,
                high_strain_when_denominator_nonpositive=False,
            ),
            "Net Debt / EBITDA": _aggregate_ratio(
                net_debt,
                ebitda,
                high_strain_when_denominator_nonpositive=True,
            ),
            "CapEx / Operating Cash Flow": _aggregate_ratio(
                capex,
                operating_cash_flow,
                high_strain_when_denominator_nonpositive=True,
            ),
            "FCF Margin Coverage": fcf_margin_coverage,
            "Debt Coverage": debt_coverage,
            "Reinvestment Coverage": reinvestment_coverage,
            "Eligible Pillars": eligible_pillars,
            "Eligible": eligible_pillars >= 2,
        })

    risk_df = pd.DataFrame(rows)

    if risk_df.empty:
        return risk_df

    risk_df["FCF Margin Strain"] = _rank_strain(
        risk_df["FCF Margin"],
        higher_is_worse=False,
    )
    risk_df["Debt Strain"] = _rank_strain(
        risk_df["Net Debt / EBITDA"],
        higher_is_worse=True,
    )
    risk_df["Reinvestment Strain"] = _rank_strain(
        risk_df["CapEx / Operating Cash Flow"],
        higher_is_worse=True,
    )

    risk_df["Financial Strain"] = risk_df[
        ["FCF Margin Strain", "Debt Strain", "Reinvestment Strain"]
    ].mean(axis=1, skipna=True)

    risk_df["Pressure Amplifier"] = 1 + (_as_numeric(risk_df["Pressure"]) / 100)
    risk_df["Risk Selection Score"] = (
        risk_df["Financial Strain"] * risk_df["Pressure Amplifier"]
    )

    risk_df.loc[~risk_df["Eligible"], "Risk Selection Score"] = np.nan

    return risk_df


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
        risk_lookup = risk_df.set_index("Sector")["Risk Selection Score"]
        risk_usable = usable.copy()
        risk_usable["_Risk Selection Score"] = risk_usable["Sector"].map(risk_lookup)
        risk_usable = risk_usable.dropna(subset=["_Risk Selection Score"])

        if not risk_usable.empty:
            biggest_risk = risk_usable.loc[
                risk_usable["_Risk Selection Score"].idxmax()
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
