from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.borrower_strain_engine import (
    BORROWER_STRAIN_TICKERS,
    load_commitment_ledger,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FUNDAMENTALS_HISTORY_PATH = (
    PROJECT_ROOT / "data" / "borrower_strain_fundamentals_history.csv"
)
DEFAULT_COMMITMENTS_HISTORY_PATH = (
    PROJECT_ROOT / "data" / "capital_commitments_history.csv"
)

_HISTORY_COLUMNS = [
    "Date",
    "Internal Funding Coverage",
    "Cash Reserve Coverage",
    "Debt Financing Pulse",
    "Forward Commitment Load",
]

def _read_nonempty_csv(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    return frame if not frame.empty else pd.DataFrame()

def _cohort_frame(sector_data) -> pd.DataFrame:
    frames = [
        frame.copy()
        for frame in (sector_data or {}).values()
        if frame is not None and not frame.empty
    ]
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "Ticker" not in combined.columns:
        return pd.DataFrame()

    combined["Ticker"] = combined["Ticker"].astype(str).str.upper().str.strip()
    combined = combined.drop_duplicates(subset=["Ticker"], keep="first")
    combined = combined[combined["Ticker"].isin(BORROWER_STRAIN_TICKERS)].copy()

    for column in ("Operating Cash Flow", "CapEx", "Cash", "Total Debt"):
        combined[column] = pd.to_numeric(combined.get(column), errors="coerce")
    return combined

def _safe_sum(series) -> float:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return float(values.sum(min_count=1)) if values.notna().any() else np.nan

def _safe_ratio(numerator, denominator) -> float:
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    if (
        pd.isna(numerator)
        or pd.isna(denominator)
        or not np.isfinite(numerator)
        or not np.isfinite(denominator)
        or denominator <= 0
    ):
        return np.nan
    return float(numerator) / float(denominator)

def _ratio_of_sums(frame: pd.DataFrame, numerator: str, denominator: str, *, min_companies=2):
    if frame is None or frame.empty or numerator not in frame or denominator not in frame:
        return np.nan, 0

    num = pd.to_numeric(frame[numerator], errors="coerce")
    den = pd.to_numeric(frame[denominator], errors="coerce")
    valid = num.notna() & den.notna() & np.isfinite(num) & np.isfinite(den) & (den > 0)
    count = int(valid.sum())
    if count < min_companies:
        return np.nan, count

    return _safe_ratio(num.loc[valid].sum(), den.loc[valid].sum()), count

def _normalize_fundamentals(history: pd.DataFrame) -> pd.DataFrame:
    required = {"Date", "Ticker"}
    if history is None or history.empty or not required.issubset(history.columns):
        return pd.DataFrame()

    frame = history.copy()
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame = frame[frame["Ticker"].isin(BORROWER_STRAIN_TICKERS)].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame["Financial Period End"] = pd.to_datetime(
        frame.get("Financial Period End"), errors="coerce", format="mixed"
    )
    frame["Financial Filing Date"] = pd.to_datetime(
        frame.get("Financial Filing Date"), errors="coerce", format="mixed"
    )
    for column in (
        "Operating Cash Flow",
        "CapEx",
        "Cash",
        "Total Debt",
        "OCF Quarters",
        "CapEx Quarters",
    ):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    return frame.dropna(subset=["Date", "Ticker"])

def _latest_fundamentals_snapshot(
    history: pd.DataFrame,
    observation_date=None,
) -> pd.DataFrame:
    frame = _normalize_fundamentals(history)
    if frame.empty:
        return frame

    cutoff = pd.to_datetime(observation_date, errors="coerce")
    if pd.notna(cutoff):
        frame = frame[frame["Date"] <= cutoff].copy()
    if frame.empty:
        return frame

    # One internally coherent SEC observation per company. Period end is the
    # measurement vintage; filing/archive dates only break ties.
    return (
        frame.sort_values(
            ["Ticker", "Financial Period End", "Financial Filing Date", "Date"],
            kind="stable",
            na_position="first",
        )
        .groupby("Ticker", as_index=False, dropna=False)
        .tail(1)
        .reset_index(drop=True)
    )

def _ttm_ratio_of_sums(
    snapshot: pd.DataFrame,
    numerator: str,
    denominator: str = "CapEx",
    *,
    min_companies=2,
):
    if snapshot is None or snapshot.empty:
        return np.nan, 0
    frame = snapshot.copy()
    valid = pd.Series(True, index=frame.index)
    if numerator == "Operating Cash Flow":
        valid &= pd.to_numeric(frame.get("OCF Quarters"), errors="coerce").eq(4)
    if denominator == "CapEx":
        valid &= pd.to_numeric(frame.get("CapEx Quarters"), errors="coerce").eq(4)
    return _ratio_of_sums(
        frame.loc[valid], numerator, denominator, min_companies=min_companies
    )

def _matched_debt_pulse(
    fundamentals_history: pd.DataFrame,
    snapshot: pd.DataFrame,
    *,
    tolerance_days=62,
    min_companies=2,
):
    if snapshot is None or snapshot.empty:
        return np.nan, np.nan, np.nan, np.nan, 0

    history = _normalize_fundamentals(fundamentals_history)
    if history.empty:
        return np.nan, np.nan, np.nan, np.nan, 0
    history = (
        history.dropna(subset=["Financial Period End", "Total Debt"])
        .sort_values(
            ["Ticker", "Financial Period End", "Financial Filing Date", "Date"],
            kind="stable",
        )
        .drop_duplicates(subset=["Ticker", "Financial Period End"], keep="last")
    )

    matched = []
    for _, current in snapshot.iterrows():
        period_end = pd.to_datetime(current.get("Financial Period End"), errors="coerce")
        capex = pd.to_numeric(current.get("CapEx"), errors="coerce")
        debt = pd.to_numeric(current.get("Total Debt"), errors="coerce")
        capex_quarters = pd.to_numeric(current.get("CapEx Quarters"), errors="coerce")
        if (
            pd.isna(period_end)
            or pd.isna(capex)
            or capex <= 0
            or capex_quarters != 4
            or pd.isna(debt)
        ):
            continue
        target = period_end - pd.DateOffset(years=1)
        candidates = history[
            (history["Ticker"] == current["Ticker"])
            & (history["Financial Period End"] < period_end)
        ].copy()
        if candidates.empty:
            continue
        candidates["Distance"] = (candidates["Financial Period End"] - target).abs()
        prior = candidates.sort_values("Distance", kind="stable").iloc[0]
        if prior["Distance"] > pd.Timedelta(days=tolerance_days):
            continue
        matched.append(
            {
                "CapEx": float(capex),
                "Current Debt": float(debt),
                "Prior Debt": float(prior["Total Debt"]),
            }
        )

    matched = pd.DataFrame(matched)
    if len(matched) < min_companies:
        return np.nan, np.nan, np.nan, np.nan, len(matched)
    current_total = _safe_sum(matched["Current Debt"])
    prior_total = _safe_sum(matched["Prior Debt"])
    capex_total = _safe_sum(matched["CapEx"])
    return (
        _safe_ratio(current_total - prior_total, capex_total),
        current_total,
        prior_total,
        capex_total,
        len(matched),
    )

def _aggregate_fundamentals(history: pd.DataFrame) -> pd.DataFrame:
    required = {"Date", "Ticker"}
    if history is None or history.empty or not required.issubset(history.columns):
        return pd.DataFrame(
            columns=["Date", "Operating Cash Flow", "CapEx", "Cash", "Total Debt"]
        )

    frame = history.copy()
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame = frame[frame["Ticker"].isin(BORROWER_STRAIN_TICKERS)].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    for column in ("Operating Cash Flow", "CapEx", "Cash", "Total Debt"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

    return (
        frame.dropna(subset=["Date"])
        .groupby("Date", as_index=False)[
            ["Operating Cash Flow", "CapEx", "Cash", "Total Debt"]
        ]
        .sum(min_count=1)
        .sort_values("Date", kind="stable")
        .reset_index(drop=True)
    )

def _nearest_prior_year_value(
    history: pd.DataFrame,
    as_of_date,
    value_column: str,
    *,
    tolerance_days=62,
):
    if history is None or history.empty or value_column not in history.columns:
        return np.nan

    as_of = pd.to_datetime(as_of_date, errors="coerce")
    if pd.isna(as_of):
        return np.nan

    target = as_of - pd.DateOffset(years=1)
    dates = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    values = pd.to_numeric(history[value_column], errors="coerce")
    candidates = pd.DataFrame({"Date": dates, "Value": values}).dropna()
    candidates = candidates[candidates["Date"] < as_of].copy()
    if candidates.empty:
        return np.nan

    candidates["Distance"] = (candidates["Date"] - target).abs()
    nearest = candidates.sort_values("Distance", kind="stable").iloc[0]
    if nearest["Distance"] > pd.Timedelta(days=tolerance_days):
        return np.nan
    return float(nearest["Value"])

def _debt_financing_pulse_history(fundamentals: pd.DataFrame) -> pd.Series:
    if fundamentals is None or fundamentals.empty:
        return pd.Series(dtype=float)

    pulses = []
    for _, row in fundamentals.iterrows():
        prior_debt = _nearest_prior_year_value(
            fundamentals,
            row["Date"],
            "Total Debt",
        )
        current_debt = pd.to_numeric(row.get("Total Debt"), errors="coerce")
        capex = pd.to_numeric(row.get("CapEx"), errors="coerce")
        pulse = (
            _safe_ratio(current_debt - prior_debt, capex)
            if pd.notna(current_debt) and pd.notna(prior_debt)
            else np.nan
        )
        pulses.append(pulse)
    return pd.Series(pulses, index=fundamentals.index, dtype=float)

def _normalize_commitments(history: pd.DataFrame) -> pd.DataFrame:
    if history is None or history.empty or "Ticker" not in history.columns:
        return pd.DataFrame()

    frame = history.copy()
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame = frame[frame["Ticker"].isin(BORROWER_STRAIN_TICKERS)].copy()

    as_of = pd.to_datetime(frame.get("As Of Date"), errors="coerce", format="mixed")
    filing = pd.to_datetime(frame.get("Filing Date"), errors="coerce", format="mixed")
    frame["As Of Date"] = as_of
    frame["Filing Date"] = filing
    frame["Available Date"] = filing.fillna(as_of)

    for column in ("Uncommenced Leases", "Purchase or Contractual Commitments"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame["Forward Commitments"] = frame[
        ["Uncommenced Leases", "Purchase or Contractual Commitments"]
    ].sum(axis=1, min_count=1)

    return frame.dropna(subset=["Available Date", "Forward Commitments"])

def _forward_commitment_history(
    fundamentals_history: pd.DataFrame,
    commitments_history: pd.DataFrame,
    *,
    min_companies=2,
) -> pd.DataFrame:
    if fundamentals_history is None or fundamentals_history.empty:
        return pd.DataFrame(columns=["Date", "Forward Commitment Load"])

    fundamentals = fundamentals_history.copy()
    if not {"Date", "Ticker", "CapEx"}.issubset(fundamentals.columns):
        return pd.DataFrame(columns=["Date", "Forward Commitment Load"])

    fundamentals["Ticker"] = fundamentals["Ticker"].astype(str).str.upper().str.strip()
    fundamentals = fundamentals[fundamentals["Ticker"].isin(BORROWER_STRAIN_TICKERS)].copy()
    fundamentals["Date"] = pd.to_datetime(
        fundamentals["Date"], errors="coerce", format="mixed"
    )
    fundamentals["CapEx"] = pd.to_numeric(fundamentals["CapEx"], errors="coerce")
    commitments = _normalize_commitments(commitments_history)
    if commitments.empty:
        return pd.DataFrame(columns=["Date", "Forward Commitment Load"])

    rows = []
    for observation_date in sorted(fundamentals["Date"].dropna().unique()):
        observed = fundamentals[fundamentals["Date"] == observation_date][
            ["Ticker", "CapEx"]
        ].copy()
        observed = observed[
            observed["CapEx"].notna()
            & np.isfinite(observed["CapEx"])
            & (observed["CapEx"] > 0)
        ]

        matched = []
        for _, company in observed.iterrows():
            available = commitments[
                (commitments["Ticker"] == company["Ticker"])
                & (commitments["Available Date"] <= observation_date)
            ].sort_values(["Available Date", "As Of Date"], kind="stable")
            if available.empty:
                continue
            latest = available.iloc[-1]
            matched.append(
                {
                    "CapEx": float(company["CapEx"]),
                    "Forward Commitments": float(latest["Forward Commitments"]),
                }
            )

        matched_frame = pd.DataFrame(matched)
        ratio, count = _ratio_of_sums(
            matched_frame,
            "Forward Commitments",
            "CapEx",
            min_companies=min_companies,
        )
        rows.append(
            {
                "Date": pd.Timestamp(observation_date),
                "Forward Commitment Load": ratio,
                "Commitment Companies": count,
            }
        )

    return pd.DataFrame(rows)

def _current_forward_commitment_load(
    cohort: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    min_companies=2,
):
    if cohort is None or cohort.empty or ledger is None or ledger.empty:
        return np.nan, np.nan, 0

    commitments = _normalize_commitments(ledger)
    if commitments.empty:
        return np.nan, np.nan, 0

    latest = (
        commitments.sort_values(["Ticker", "Available Date", "As Of Date"], kind="stable")
        .groupby("Ticker", as_index=False, dropna=False)
        .tail(1)
    )
    merged = cohort[["Ticker", "CapEx"]].merge(
        latest[["Ticker", "Forward Commitments"]],
        on="Ticker",
        how="inner",
    )
    ratio, count = _ratio_of_sums(
        merged,
        "Forward Commitments",
        "CapEx",
        min_companies=min_companies,
    )
    total = _safe_sum(merged.loc[merged["Forward Commitments"].notna(), "Forward Commitments"])
    return ratio, total, count

def _build_history(
    fundamentals_history: pd.DataFrame,
    commitments_history: pd.DataFrame,
) -> pd.DataFrame:
    fundamentals = _normalize_fundamentals(fundamentals_history)
    if fundamentals.empty:
        return pd.DataFrame(columns=_HISTORY_COLUMNS)

    rows = []
    for observation_date in sorted(fundamentals["Date"].dropna().unique()):
        snapshot = _latest_fundamentals_snapshot(
            fundamentals_history, observation_date
        )
        internal, _ = _ttm_ratio_of_sums(snapshot, "Operating Cash Flow")
        cash, _ = _ttm_ratio_of_sums(snapshot, "Cash")
        debt, _, _, _, _ = _matched_debt_pulse(fundamentals_history, snapshot)
        rows.append(
            {
                "Date": pd.Timestamp(observation_date),
                "Internal Funding Coverage": internal,
                "Cash Reserve Coverage": cash,
                "Debt Financing Pulse": debt,
                # The historical ledger changes definition across vintages.
                # Keep the current curated snapshot, but do not chart a false trend.
                "Forward Commitment Load": np.nan,
            }
        )

    history = pd.DataFrame(rows, columns=_HISTORY_COLUMNS)
    history["Date"] = pd.to_datetime(history["Date"], errors="coerce", format="mixed")
    return (
        history[_HISTORY_COLUMNS]
        .dropna(subset=["Date"])
        .sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )

def _series(history: pd.DataFrame, column: str) -> pd.DataFrame:
    if history is None or history.empty or column not in history.columns:
        return pd.DataFrame(columns=["Date", "Value"])
    out = history[["Date", column]].rename(columns={column: "Value"}).copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    return (
        out.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .reset_index(drop=True)
    )

def calculate_deployment_funding_mix(
    sector_data,
    *,
    commitments_df=None,
    fundamentals_history=None,
    commitments_history=None,
) -> dict:
    ledger = load_commitment_ledger() if commitments_df is None else commitments_df.copy()

    fundamentals_history = (
        _read_nonempty_csv(DEFAULT_FUNDAMENTALS_HISTORY_PATH)
        if fundamentals_history is None
        else fundamentals_history.copy()
    )
    commitments_history = (
        _read_nonempty_csv(DEFAULT_COMMITMENTS_HISTORY_PATH)
        if commitments_history is None
        else commitments_history.copy()
    )

    snapshot = _latest_fundamentals_snapshot(fundamentals_history)
    internal_coverage, internal_count = _ttm_ratio_of_sums(
        snapshot, "Operating Cash Flow"
    )
    cash_reserve_coverage, reserve_count = _ttm_ratio_of_sums(snapshot, "Cash")
    debt_financing_pulse, total_debt, prior_debt, debt_capex_total, debt_count = _matched_debt_pulse(
        fundamentals_history, snapshot
    )
    capex_total = _safe_sum(
        snapshot.loc[
            pd.to_numeric(snapshot.get("CapEx Quarters"), errors="coerce").eq(4),
            "CapEx",
        ]
    ) if not snapshot.empty else np.nan

    forward_commitment_load, forward_commitments, commitment_count = (
        _current_forward_commitment_load(snapshot, ledger)
    )

    history = _build_history(fundamentals_history, commitments_history)
    current = {
        "internal_funding_coverage": internal_coverage,
        "cash_reserve_coverage_years": cash_reserve_coverage,
        "debt_financing_pulse": debt_financing_pulse,
        "forward_commitment_load": forward_commitment_load,
        "capex_total": capex_total,
        "total_debt": total_debt,
        "prior_year_total_debt": prior_debt,
        "debt_financing_capex_total": debt_capex_total,
        "forward_commitments_total": forward_commitments,
        "cohort_companies": int(snapshot["Ticker"].nunique()) if not snapshot.empty else 0,
        "internal_funding_companies": internal_count,
        "cash_reserve_companies": reserve_count,
        "debt_financing_companies": debt_count,
        "commitment_companies": commitment_count,
        "history_available": bool(not history.empty),
        "measurement_date": (
            snapshot["Financial Period End"].max().date().isoformat()
            if not snapshot.empty and snapshot["Financial Period End"].notna().any()
            else None
        ),
    }

    current_date = (
        snapshot["Date"].max()
        if not snapshot.empty and snapshot["Date"].notna().any()
        else pd.NaT
    )
    current_row = pd.DataFrame(
        [
            {
                "Date": current_date,
                "Internal Funding Coverage": internal_coverage,
                "Cash Reserve Coverage": cash_reserve_coverage,
                "Debt Financing Pulse": debt_financing_pulse,
                "Forward Commitment Load": forward_commitment_load,
            }
        ]
    )
    history_with_current = pd.concat([history, current_row], ignore_index=True, sort=False)
    history_with_current["Date"] = pd.to_datetime(
        history_with_current["Date"], errors="coerce", format="mixed"
    )
    history_with_current = (
        history_with_current.dropna(subset=["Date"])
        .sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )

    return {
        "current": current,
        "history": history_with_current,
        "series": {
            "internal_funding_coverage": _series(
                history_with_current,
                "Internal Funding Coverage",
            ),
            "cash_reserve_coverage_years": _series(
                history_with_current,
                "Cash Reserve Coverage",
            ),
            "debt_financing_pulse": _series(
                history_with_current,
                "Debt Financing Pulse",
            ),
            "forward_commitment_load": _series(
                history_with_current,
                "Forward Commitment Load",
            ),
        },
    }
