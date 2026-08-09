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
DEFAULT_DEBT_OBSERVATIONS_PATH = (
    PROJECT_ROOT / "data" / "debt_financing_observations.csv"
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
    for column in ("OCF Period End", "CapEx Period End", "Debt Period End", "Cash Period End"):
        values = (
            frame[column]
            if column in frame.columns
            else pd.Series(pd.NaT, index=frame.index, dtype="datetime64[ns]")
        )
        frame[column] = pd.to_datetime(values, errors="coerce", format="mixed")
    # Legacy retained snapshots predate component-level period columns.  Flow
    # and cash ratios may use the row's reconciled filing period as a bounded
    # fallback; debt does not, because its definition is the contract at issue.
    for column in ("OCF Period End", "CapEx Period End", "Cash Period End"):
        frame[column] = frame[column].fillna(frame["Financial Period End"])
    for column in ("Debt Definition", "Cash Definition"):
        frame[column] = frame.get(column, pd.Series(index=frame.index, dtype="string")).astype("string")
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
    period_columns = {
        "Operating Cash Flow": "OCF Period End",
        "CapEx": "CapEx Period End",
        "Cash": "Cash Period End",
    }
    numerator_period = period_columns.get(numerator)
    denominator_period = period_columns.get(denominator)
    if numerator_period and denominator_period:
        distance = (frame[numerator_period] - frame[denominator_period]).abs()
        valid &= distance.le(pd.Timedelta(days=62))
    return _ratio_of_sums(
        frame.loc[valid], numerator, denominator, min_companies=min_companies
    )

def _matched_debt_pulse(
    fundamentals_history: pd.DataFrame,
    snapshot: pd.DataFrame,
    *,
    debt_observations: pd.DataFrame | None = None,
    tolerance_days=62,
    min_companies=2,
):
    if snapshot is None or snapshot.empty:
        return np.nan, np.nan, np.nan, np.nan, 0

    history = _normalize_fundamentals(fundamentals_history)
    observations = _normalize_debt_observations(debt_observations)
    if history.empty and observations.empty:
        return np.nan, np.nan, np.nan, np.nan, 0
    if observations.empty:
        history = (
            history.dropna(subset=["Debt Period End", "Total Debt"])
            .rename(
                columns={
                    "Debt Period End": "Period End",
                    "Total Debt": "Debt",
                    "Debt Definition": "Definition",
                    "Financial Filing Date": "Filing Date",
                }
            )
            .sort_values(
                ["Ticker", "Period End", "Filing Date", "Date"],
                kind="stable",
            )
            .drop_duplicates(subset=["Ticker", "Period End"], keep="last")
        )
        observations = history[
            ["Ticker", "Period End", "Filing Date", "Debt", "Definition"]
        ].copy()

    matched = []
    for _, current in snapshot.iterrows():
        observation_date = pd.to_datetime(current.get("Date"), errors="coerce")
        capex_period_end = pd.to_datetime(current.get("CapEx Period End"), errors="coerce")
        capex = pd.to_numeric(current.get("CapEx"), errors="coerce")
        capex_quarters = pd.to_numeric(current.get("CapEx Quarters"), errors="coerce")
        if (
            pd.isna(observation_date)
            or pd.isna(capex_period_end)
            or pd.isna(capex)
            or capex <= 0
            or capex_quarters != 4
        ):
            continue

        company_observations = observations[
            (observations["Ticker"] == current["Ticker"])
            & (observations["Period End"] <= observation_date)
            & (
                observations["Filing Date"].isna()
                | (observations["Filing Date"] <= observation_date)
            )
        ].copy()
        if company_observations.empty:
            continue
        current_debt = company_observations.sort_values(
            ["Period End", "Filing Date"], kind="stable"
        ).iloc[-1]
        period_end = current_debt["Period End"]
        debt = current_debt["Debt"]
        debt_definition = str(current_debt["Definition"]).strip()
        if (
            pd.isna(period_end)
            or abs(period_end - capex_period_end) > pd.Timedelta(days=tolerance_days)
            or pd.isna(debt)
            or not debt_definition
        ):
            continue
        target = period_end - pd.DateOffset(years=1)
        candidates = company_observations[
            (company_observations["Period End"] < period_end)
            & (company_observations["Definition"] == debt_definition)
        ].copy()
        if candidates.empty:
            continue
        candidates["Distance"] = (candidates["Period End"] - target).abs()
        prior = candidates.sort_values("Distance", kind="stable").iloc[0]
        if prior["Distance"] > pd.Timedelta(days=tolerance_days):
            continue
        matched.append(
            {
                "CapEx": float(capex),
                "Current Debt": float(debt),
                "Prior Debt": float(prior["Debt"]),
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

def _normalize_debt_observations(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = ["Ticker", "Period End", "Filing Date", "Debt", "Definition"]
    if frame is None or frame.empty or not set(columns).issubset(frame.columns):
        return pd.DataFrame(columns=columns)
    out = frame.copy()
    out["Ticker"] = out["Ticker"].astype(str).str.upper().str.strip()
    out = out[out["Ticker"].isin(BORROWER_STRAIN_TICKERS)].copy()
    out["Period End"] = pd.to_datetime(out["Period End"], errors="coerce", format="mixed")
    out["Filing Date"] = pd.to_datetime(out["Filing Date"], errors="coerce", format="mixed")
    out["Debt"] = pd.to_numeric(out["Debt"], errors="coerce")
    out["Definition"] = out["Definition"].astype("string").str.strip()
    return (
        out.dropna(subset=["Ticker", "Period End", "Debt", "Definition"])
        .sort_values(["Ticker", "Period End", "Filing Date"], kind="stable")
        .drop_duplicates(["Ticker", "Period End", "Definition"], keep="last")
        .reset_index(drop=True)
    )

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
    fundamentals = _normalize_fundamentals(fundamentals_history)
    if fundamentals.empty or not {"Date", "Ticker", "CapEx"}.issubset(fundamentals.columns):
        return pd.DataFrame(columns=["Date", "Forward Commitment Load"])

    commitments = _normalize_commitments(commitments_history)
    if commitments.empty:
        return pd.DataFrame(columns=["Date", "Forward Commitment Load"])

    rows = []
    for observation_date in sorted(fundamentals["Date"].dropna().unique()):
        observed = fundamentals[fundamentals["Date"] == observation_date][
            ["Ticker", "CapEx", "CapEx Quarters"]
        ].copy()
        observed = observed[
            observed["CapEx"].notna()
            & np.isfinite(observed["CapEx"])
            & (observed["CapEx"] > 0)
            & observed["CapEx Quarters"].eq(4)
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
    eligible = cohort.loc[
        pd.to_numeric(cohort.get("CapEx Quarters"), errors="coerce").eq(4),
        ["Ticker", "CapEx"],
    ]
    merged = eligible.merge(
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
    debt_observations: pd.DataFrame | None = None,
    current_commitments: pd.DataFrame | None = None,
) -> pd.DataFrame:
    fundamentals = _normalize_fundamentals(fundamentals_history)
    if fundamentals.empty:
        return pd.DataFrame(columns=_HISTORY_COLUMNS)

    commitment_frames = [
        frame for frame in (commitments_history, current_commitments)
        if isinstance(frame, pd.DataFrame) and not frame.empty
    ]
    combined_commitments = (
        pd.concat(commitment_frames, ignore_index=True, sort=False)
        if commitment_frames
        else pd.DataFrame()
    )
    commitment_history = _forward_commitment_history(
        fundamentals_history,
        combined_commitments,
    )
    commitment_lookup = (
        commitment_history.set_index("Date")["Forward Commitment Load"]
        if not commitment_history.empty
        else pd.Series(dtype=float)
    )

    rows = []
    for observation_date in sorted(fundamentals["Date"].dropna().unique()):
        snapshot = _latest_fundamentals_snapshot(
            fundamentals_history, observation_date
        )
        internal, _ = _ttm_ratio_of_sums(snapshot, "Operating Cash Flow")
        cash, _ = _ttm_ratio_of_sums(snapshot, "Cash")
        debt, _, _, _, _ = _matched_debt_pulse(
            fundamentals_history,
            snapshot,
            debt_observations=debt_observations,
        )
        rows.append(
            {
                "Date": pd.Timestamp(observation_date),
                "Internal Funding Coverage": internal,
                "Cash Reserve Coverage": cash,
                "Debt Financing Pulse": debt,
                "Forward Commitment Load": commitment_lookup.get(
                    pd.Timestamp(observation_date), np.nan
                ),
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
    debt_observations=None,
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
    debt_observations = (
        _read_nonempty_csv(DEFAULT_DEBT_OBSERVATIONS_PATH)
        if debt_observations is None
        else debt_observations.copy()
    )

    snapshot = _latest_fundamentals_snapshot(fundamentals_history)
    internal_coverage, internal_count = _ttm_ratio_of_sums(
        snapshot, "Operating Cash Flow"
    )
    cash_reserve_coverage, reserve_count = _ttm_ratio_of_sums(snapshot, "Cash")
    debt_financing_pulse, total_debt, prior_debt, debt_capex_total, debt_count = _matched_debt_pulse(
        fundamentals_history,
        snapshot,
        debt_observations=debt_observations,
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

    history = _build_history(
        fundamentals_history,
        commitments_history,
        debt_observations=debt_observations,
        current_commitments=ledger,
    )
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
    # The SEC financial snapshot and the commitments ledger do not necessarily
    # become available on the same day. Update the three filing-period metrics
    # on the retained observation date, then date the commitment endpoint to the
    # filing that actually made the latest ledger value observable.
    history_with_current = history.copy()
    financial_values = {
        "Internal Funding Coverage": internal_coverage,
        "Cash Reserve Coverage": cash_reserve_coverage,
        "Debt Financing Pulse": debt_financing_pulse,
    }
    if pd.notna(current_date):
        current_mask = pd.to_datetime(
            history_with_current.get("Date"), errors="coerce", format="mixed"
        ).eq(current_date)
        if current_mask.any():
            for column, value in financial_values.items():
                history_with_current.loc[current_mask, column] = value
        else:
            history_with_current = pd.concat(
                [history_with_current, pd.DataFrame([{"Date": current_date, **financial_values}])],
                ignore_index=True,
                sort=False,
            )

    normalized_current_commitments = _normalize_commitments(ledger)
    commitment_current_date = (
        normalized_current_commitments["Available Date"].max()
        if not normalized_current_commitments.empty
        else current_date
    )
    if pd.notna(commitment_current_date):
        commitment_mask = pd.to_datetime(
            history_with_current.get("Date"), errors="coerce", format="mixed"
        ).eq(commitment_current_date)
        if commitment_mask.any():
            history_with_current.loc[
                commitment_mask, "Forward Commitment Load"
            ] = forward_commitment_load
        else:
            history_with_current = pd.concat(
                [
                    history_with_current,
                    pd.DataFrame(
                        [
                            {
                                "Date": commitment_current_date,
                                "Forward Commitment Load": forward_commitment_load,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
                sort=False,
            )

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
