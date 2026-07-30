"""AI buildout financing diagnostics.

The module exposes four auditable ratios rather than another composite score:
internal funding coverage, cash reserve coverage, debt financing pulse, and
forward commitment load.
"""

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
    fundamentals = _aggregate_fundamentals(fundamentals_history)
    if fundamentals.empty:
        return pd.DataFrame(columns=_HISTORY_COLUMNS)

    history = fundamentals.copy()
    history["Internal Funding Coverage"] = [
        _safe_ratio(ocf, capex)
        for ocf, capex in zip(history["Operating Cash Flow"], history["CapEx"])
    ]
    history["Cash Reserve Coverage"] = [
        _safe_ratio(cash, capex)
        for cash, capex in zip(history["Cash"], history["CapEx"])
    ]
    history["Debt Financing Pulse"] = _debt_financing_pulse_history(history)

    commitment_history = _forward_commitment_history(
        fundamentals_history,
        commitments_history,
    )
    if not commitment_history.empty:
        history = history.merge(
            commitment_history[["Date", "Forward Commitment Load"]],
            on="Date",
            how="left",
        )
    else:
        history["Forward Commitment Load"] = np.nan

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
    """Calculate current funding diagnostics and retained point-in-time history."""
    cohort = _cohort_frame(sector_data)
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

    internal_coverage, internal_count = _ratio_of_sums(
        cohort,
        "Operating Cash Flow",
        "CapEx",
    )
    cash_reserve_coverage, reserve_count = _ratio_of_sums(
        cohort,
        "Cash",
        "CapEx",
    )

    capex_total = _safe_sum(cohort.get("CapEx", pd.Series(dtype=float)))
    total_debt = _safe_sum(cohort.get("Total Debt", pd.Series(dtype=float)))
    aggregated_history = _aggregate_fundamentals(fundamentals_history)
    prior_debt = _nearest_prior_year_value(
        aggregated_history,
        pd.Timestamp.today().normalize(),
        "Total Debt",
    )
    debt_financing_pulse = (
        _safe_ratio(total_debt - prior_debt, capex_total)
        if pd.notna(total_debt) and pd.notna(prior_debt)
        else np.nan
    )

    forward_commitment_load, forward_commitments, commitment_count = (
        _current_forward_commitment_load(cohort, ledger)
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
        "forward_commitments_total": forward_commitments,
        "cohort_companies": int(cohort["Ticker"].nunique()) if not cohort.empty else 0,
        "internal_funding_companies": internal_count,
        "cash_reserve_companies": reserve_count,
        "commitment_companies": commitment_count,
        "history_available": bool(not history.empty),
    }

    current_row = pd.DataFrame(
        [
            {
                "Date": pd.Timestamp.today().normalize(),
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
