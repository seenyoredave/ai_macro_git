"""Refresh retained Finance derivatives from SEC Companyfacts.

The market EDGAR archive and Finance funding cards have different retained
schemas. An explicit EDGAR refresh must advance both, otherwise a subsequent
retained rebuild can show fresh SEC coverage beside stale CapEx/debt cards.

This module deliberately rebuilds only the 10-company borrower fundamentals
cohort and the definition-matched debt observations. It does not alter the
manually reviewed forward-commitment ledger.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.borrower_strain_history import (
    BORROWER_STRAIN_CIKS,
    DEBT_GROUPS,
    FUNDAMENTAL_COLUMNS,
    build_company_snapshot,
    instant_group_fact,
)
from helpers.atomic_io import atomic_write_csv
from loaders.edgar_client import fetch_company_facts

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FUNDAMENTALS_PATH = PROJECT_ROOT / "data" / "borrower_strain_fundamentals_history.csv"
DEBT_OBSERVATIONS_PATH = PROJECT_ROOT / "data" / "debt_financing_observations.csv"

DEBT_COLUMNS = [
    "Ticker", "Period End", "Filing Date", "Debt", "Definition", "Source URL", "Evidence Note"
]


def _read(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path)
    for column in columns:
        if column not in frame.columns:
            frame[column] = np.nan
    return frame


def _debt_definitions(observations: pd.DataFrame) -> dict[str, str]:
    if observations.empty:
        return {}
    frame = observations.copy()
    frame["Period End"] = pd.to_datetime(frame["Period End"], errors="coerce")
    frame["Filing Date"] = pd.to_datetime(frame["Filing Date"], errors="coerce")
    frame = frame.dropna(subset=["Ticker", "Definition"])
    latest = (
        frame.sort_values(["Ticker", "Period End", "Filing Date"], kind="stable")
        .groupby("Ticker", as_index=False, dropna=False)
        .tail(1)
    )
    return {
        str(row["Ticker"]).upper(): str(row["Definition"]).strip()
        for _, row in latest.iterrows()
        if str(row["Definition"]).strip()
    }


def _debt_fact_row(
    *,
    ticker: str,
    fact,
    debt_definition: str,
    source_url: str | None,
) -> dict | None:
    debt = pd.to_numeric(getattr(fact, "value", np.nan), errors="coerce")
    period_end = pd.to_datetime(getattr(fact, "period_end", pd.NaT), errors="coerce")
    filing_date = pd.to_datetime(getattr(fact, "filed", pd.NaT), errors="coerce")
    tags = tuple(str(tag).strip() for tag in (getattr(fact, "tags", ()) or ()) if str(tag).strip())
    if pd.isna(debt) or debt < 0 or pd.isna(period_end) or pd.isna(filing_date) or not tags:
        return None
    tag_text = ";".join(tags)
    return {
        "Ticker": str(ticker).upper(),
        "Period End": period_end.date().isoformat(),
        "Filing Date": filing_date.date().isoformat(),
        "Debt": float(debt),
        "Definition": debt_definition,
        "Source URL": source_url,
        "Evidence Note": f"SEC Companyfacts refresh; matched XBRL definition: {tag_text}",
        "_tags": tag_text,
    }


def _matched_debt_pair(
    *,
    ticker: str,
    companyfacts: dict,
    debt_definition: str,
    current_cutoff: pd.Timestamp,
    prior_cutoff: pd.Timestamp,
    current_capex_period_end=None,
    tolerance_days: int = 62,
) -> tuple[dict | None, dict | None, str | None]:
    """Extract one definition-matched debt pair from the same XBRL group.

    A filer can migrate from one valid debt tag family to another over time.
    Selecting the best group independently at each cutoff can therefore reject
    an otherwise comparable pair.  Instead, try each permitted debt group and
    accept the first group that establishes both current and prior-year debt
    under exactly the same XBRL definition.
    """
    source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{BORROWER_STRAIN_CIKS[ticker]}.json"
    capex_period = pd.to_datetime(current_capex_period_end, errors="coerce")
    tolerance = pd.Timedelta(days=int(tolerance_days))
    rejection_notes: list[str] = []

    for group in DEBT_GROUPS:
        current_fact = instant_group_fact(companyfacts, (group,), current_cutoff)
        prior_fact = instant_group_fact(companyfacts, (group,), prior_cutoff)
        current_row = _debt_fact_row(
            ticker=ticker,
            fact=current_fact,
            debt_definition=debt_definition,
            source_url=source_url,
        )
        prior_row = _debt_fact_row(
            ticker=ticker,
            fact=prior_fact,
            debt_definition=debt_definition,
            source_url=source_url,
        )
        if current_row is None or prior_row is None:
            continue

        current_period = pd.Timestamp(current_row["Period End"])
        prior_period = pd.Timestamp(prior_row["Period End"])
        target_prior = current_period - pd.DateOffset(years=1)
        if abs(prior_period - target_prior) > tolerance:
            rejection_notes.append(
                f"{current_row['_tags']}: prior period {prior_period.date()} is not within "
                f"{tolerance_days} days of {target_prior.date()}"
            )
            continue
        if pd.notna(capex_period) and abs(current_period - capex_period) > tolerance:
            rejection_notes.append(
                f"{current_row['_tags']}: debt period {current_period.date()} is not within "
                f"{tolerance_days} days of CapEx period {capex_period.date()}"
            )
            continue
        return current_row, prior_row, None

    detail = "; ".join(rejection_notes[-3:]) if rejection_notes else "no common complete XBRL debt group"
    return None, None, detail

def _reviewed_debt_pair(
    *,
    ticker: str,
    retained_debt: pd.DataFrame,
    debt_definition: str,
    observation_date: pd.Timestamp,
    current_capex_period_end,
    tolerance_days: int = 62,
) -> tuple[dict | None, dict | None, str | None]:
    """Recover a reviewed retained pair when Companyfacts cannot express it.

    SEC Companyfacts aggregates standard taxonomy facts. Some issuers report the
    economically correct debt definition through a combination that is not
    available as one complete standard-tag family in Companyfacts. In that case
    we may retain a filing-reviewed pair, but only when it preserves the issuer's
    retained definition and is period-aligned with the current CapEx snapshot.
    """
    frame = retained_debt.copy()
    if frame.empty:
        return None, None, "reviewed debt ledger is empty"
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame["Definition"] = frame["Definition"].astype(str).str.strip()
    frame["Period End"] = pd.to_datetime(frame["Period End"], errors="coerce")
    frame["Filing Date"] = pd.to_datetime(frame["Filing Date"], errors="coerce")
    frame["Debt"] = pd.to_numeric(frame["Debt"], errors="coerce")
    cutoff = pd.to_datetime(observation_date, errors="coerce")
    capex_period = pd.to_datetime(current_capex_period_end, errors="coerce")
    tolerance = pd.Timedelta(days=int(tolerance_days))
    frame = frame.loc[
        frame["Ticker"].eq(str(ticker).upper())
        & frame["Definition"].eq(str(debt_definition).strip())
        & frame["Period End"].notna()
        & frame["Debt"].notna()
        & frame["Period End"].le(cutoff)
        & (frame["Filing Date"].isna() | frame["Filing Date"].le(cutoff))
    ].copy()
    if frame.empty or pd.isna(capex_period):
        return None, None, "no reviewed observation is available for the current CapEx period"

    frame["CapEx Distance"] = (frame["Period End"] - capex_period).abs()
    aligned = frame.loc[frame["CapEx Distance"].le(tolerance)].copy()
    if aligned.empty:
        return None, None, f"no reviewed debt period is within {tolerance_days} days of CapEx period {capex_period.date()}"
    current = aligned.sort_values(
        ["CapEx Distance", "Period End", "Filing Date"],
        ascending=[True, False, False],
        kind="stable",
    ).iloc[0]
    target_prior = current["Period End"] - pd.DateOffset(years=1)
    prior = frame.loc[frame["Period End"].lt(current["Period End"])].copy()
    if prior.empty:
        return None, None, "reviewed current debt exists but no same-definition prior observation is available"
    prior["Prior Distance"] = (prior["Period End"] - target_prior).abs()
    prior = prior.sort_values(
        ["Prior Distance", "Period End", "Filing Date"],
        ascending=[True, False, False],
        kind="stable",
    ).iloc[0]
    if prior["Prior Distance"] > tolerance:
        return None, None, (
            f"reviewed prior period {prior['Period End'].date()} is not within {tolerance_days} days "
            f"of {target_prior.date()}"
        )

    def _row(source: pd.Series) -> dict:
        return {
            "Ticker": str(ticker).upper(),
            "Period End": source["Period End"].date().isoformat(),
            "Filing Date": (
                source["Filing Date"].date().isoformat() if pd.notna(source["Filing Date"]) else np.nan
            ),
            "Debt": float(source["Debt"]),
            "Definition": str(debt_definition).strip(),
            "Source URL": source.get("Source URL", np.nan),
            "Evidence Note": source.get("Evidence Note", np.nan),
        }

    return _row(current), _row(prior), None


def _reconcile_snapshot_debt(frame: pd.DataFrame, *, ticker: str, debt_row: dict) -> None:
    """Replace generic Companyfacts debt fields with the matched debt result."""
    mask = frame["Ticker"].astype(str).str.upper().eq(str(ticker).upper())
    if not mask.any():
        return
    debt_value = pd.to_numeric(debt_row.get("Debt"), errors="coerce")
    if pd.isna(debt_value):
        return
    frame.loc[mask, "Total Debt"] = float(debt_value)
    frame.loc[mask, "Debt Period End"] = debt_row.get("Period End")
    frame.loc[mask, "Debt Definition"] = debt_row.get("Definition")
    cash = pd.to_numeric(frame.loc[mask, "Cash"], errors="coerce")
    frame.loc[mask, "Net Debt"] = float(debt_value) - cash


def _reasonable_transition(previous_value, new_value) -> bool:
    previous = pd.to_numeric(previous_value, errors="coerce")
    current = pd.to_numeric(new_value, errors="coerce")
    if pd.isna(current) or current < 0:
        return False
    if pd.isna(previous) or previous <= 0:
        return True
    ratio = float(current) / float(previous)
    # This is a corruption guard, not an economic forecast. A >80% quarterly
    # collapse or >5x jump deserves manual review before replacing a retained
    # definition-matched observation.
    return 0.20 <= ratio <= 5.0


def refresh_borrower_finance_derivatives(*, refresh_token: int, observation_date: str | date | None = None) -> dict:
    observation = pd.Timestamp(observation_date or date.today()).normalize()
    prior_observation = observation - pd.DateOffset(years=1)

    retained_fundamentals = _read(FUNDAMENTALS_PATH, FUNDAMENTAL_COLUMNS)
    retained_debt = _read(DEBT_OBSERVATIONS_PATH, DEBT_COLUMNS)
    definitions = _debt_definitions(retained_debt)

    current_rows: list[dict] = []
    companyfacts_by_ticker: dict[str, dict] = {}
    errors: dict[str, str] = {}

    for ticker, cik in BORROWER_STRAIN_CIKS.items():
        try:
            facts = fetch_company_facts(cik, refresh_token=int(refresh_token))
            companyfacts_by_ticker[ticker] = facts
            current_rows.append(
                build_company_snapshot(ticker, facts, observation, "Current SEC refresh")
            )
        except Exception as exc:
            errors[ticker] = f"{type(exc).__name__}: {exc}"

    if len(current_rows) != len(BORROWER_STRAIN_CIKS):
        return {
            "status": "not_written",
            "fundamental_companies": len(current_rows),
            "debt_companies": 0,
            "errors": errors or {"finance": "Incomplete 10-company SEC finance cohort"},
        }

    current_frame = pd.DataFrame(current_rows)
    for column in FUNDAMENTAL_COLUMNS:
        if column not in current_frame.columns:
            current_frame[column] = np.nan
    current_frame = current_frame[FUNDAMENTAL_COLUMNS]

    fundamentals = retained_fundamentals.copy()
    for column in FUNDAMENTAL_COLUMNS:
        if column not in fundamentals.columns:
            fundamentals[column] = np.nan
    date_text = observation.date().isoformat()
    keep = ~(
        fundamentals["Ticker"].astype(str).str.upper().isin(BORROWER_STRAIN_CIKS)
        & fundamentals["Date"].astype(str).eq(date_text)
    )
    retained_current = fundamentals.loc[keep, FUNDAMENTAL_COLUMNS]
    fundamentals = (
        pd.concat([retained_current, current_frame], ignore_index=True, sort=False)
        if not retained_current.empty
        else current_frame.copy()
    )
    fundamentals = fundamentals.sort_values(["Ticker", "Date"], kind="stable").reset_index(drop=True)

    debt = retained_debt.copy()
    for column in DEBT_COLUMNS:
        if column not in debt.columns:
            debt[column] = np.nan
    debt_updates: list[dict] = []
    reviewed_debt_tickers: list[str] = []
    debt_errors: dict[str, str] = {}

    for ticker, definition in definitions.items():
        facts = companyfacts_by_ticker.get(ticker)
        if facts is None:
            debt_errors[ticker] = "Companyfacts unavailable during Finance derivative refresh"
            continue
        current_snapshot = next(row for row in current_rows if row["Ticker"] == ticker)
        current_debt, prior_debt, match_error = _matched_debt_pair(
            ticker=ticker,
            companyfacts=facts,
            debt_definition=definition,
            current_cutoff=observation,
            prior_cutoff=prior_observation,
            current_capex_period_end=current_snapshot.get("CapEx Period End"),
        )
        used_reviewed_fallback = False
        if current_debt is None or prior_debt is None:
            current_debt, prior_debt, fallback_error = _reviewed_debt_pair(
                ticker=ticker,
                retained_debt=retained_debt,
                debt_definition=definition,
                observation_date=observation,
                current_capex_period_end=current_snapshot.get("CapEx Period End"),
            )
            if current_debt is None or prior_debt is None:
                details = [detail for detail in (match_error, fallback_error) if detail]
                debt_errors[ticker] = (
                    "Current/prior debt facts unavailable under a common standard XBRL definition "
                    "or a filing-reviewed retained pair"
                    + (f": {'; reviewed fallback: '.join(details)}" if details else "")
                )
                continue
            used_reviewed_fallback = True

        ticker_existing = debt.loc[debt["Ticker"].astype(str).str.upper().eq(ticker)].copy()
        if not ticker_existing.empty:
            ticker_existing["Period End"] = pd.to_datetime(ticker_existing["Period End"], errors="coerce")
            ticker_existing["Debt"] = pd.to_numeric(ticker_existing["Debt"], errors="coerce")
            ticker_existing = ticker_existing.sort_values("Period End", kind="stable")
        latest_existing = ticker_existing["Debt"].dropna() if "Debt" in ticker_existing else pd.Series(dtype=float)
        previous_value = latest_existing.iloc[-1] if not latest_existing.empty else np.nan
        if not used_reviewed_fallback and not _reasonable_transition(previous_value, current_debt["Debt"]):
            debt_errors[ticker] = (
                f"Debt transition failed corruption guard: retained={previous_value}, "
                f"refreshed={current_debt['Debt']}"
            )
            continue
        current_debt.pop("_tags", None)
        prior_debt.pop("_tags", None)
        _reconcile_snapshot_debt(current_frame, ticker=ticker, debt_row=current_debt)
        _reconcile_snapshot_debt(fundamentals, ticker=ticker, debt_row=current_debt)
        if used_reviewed_fallback:
            reviewed_debt_tickers.append(ticker)
        else:
            debt_updates.extend([prior_debt, current_debt])

    if debt_updates:
        update_frame = pd.DataFrame(debt_updates, columns=DEBT_COLUMNS)
        combo = pd.concat([debt[DEBT_COLUMNS], update_frame], ignore_index=True, sort=False)
        combo["Period End"] = pd.to_datetime(combo["Period End"], errors="coerce")
        combo["Filing Date"] = pd.to_datetime(combo["Filing Date"], errors="coerce")
        combo["Debt"] = pd.to_numeric(combo["Debt"], errors="coerce")
        combo = (
            combo.dropna(subset=["Ticker", "Period End", "Debt", "Definition"])
            .sort_values(["Ticker", "Period End", "Filing Date"], kind="stable")
            .drop_duplicates(["Ticker", "Period End", "Definition"], keep="last")
            .reset_index(drop=True)
        )
        combo["Period End"] = combo["Period End"].dt.date.astype(str)
        combo["Filing Date"] = combo["Filing Date"].dt.date.astype(str)
    else:
        combo = debt[DEBT_COLUMNS].copy()

    # Commit only after both frames have been fully built in memory.
    atomic_write_csv(fundamentals, FUNDAMENTALS_PATH)
    atomic_write_csv(combo, DEBT_OBSERVATIONS_PATH)

    all_errors = dict(errors)
    all_errors.update({f"debt:{k}": v for k, v in debt_errors.items()})
    updated_debt_tickers = sorted({row["Ticker"] for row in debt_updates})
    reviewed_debt_tickers = sorted(set(reviewed_debt_tickers))
    covered_debt_tickers = sorted(set(updated_debt_tickers) | set(reviewed_debt_tickers))
    unresolved_debt_tickers = sorted(set(definitions) - set(covered_debt_tickers))
    return {
        "status": "written",
        "observation_date": date_text,
        "fundamental_companies": int(current_frame["Ticker"].nunique()),
        "debt_target_companies": len(definitions),
        "debt_companies": len(covered_debt_tickers),
        "debt_updated_tickers": updated_debt_tickers,
        "debt_reviewed_tickers": reviewed_debt_tickers,
        "debt_unresolved_tickers": unresolved_debt_tickers,
        "errors": all_errors,
    }
