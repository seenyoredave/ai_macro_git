"""Borrower Financial Condition engine.

The engine combines standardized company fundamentals with a curated,
human-verifiable commitment ledger. Missing note disclosures remain unknown;
they are never silently converted to zero.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score, weighted_available_score


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMITMENTS_PATH = PROJECT_ROOT / "data" / "capital_commitments.csv"

BORROWER_FINANCIAL_CONDITION_TICKERS = {
    "MSFT", "AMZN", "GOOG", "META", "ORCL",
    "NVDA", "AMD", "IREN", "SMCI", "ANET",
}

BORROWER_FINANCIAL_CONDITION_WEIGHTS = {
    "Cash Flow Strain": 0.30,
    "Debt Capacity Strain": 0.25,
    "Committed Burden": 0.30,
    "Contingent Exposure": 0.15,
}

CASH_FLOW_SUBWEIGHTS = {
    "FCF Margin Strain": 0.60,
    "Reinvestment Burden": 0.40,
}

def borrower_financial_condition_to_signed(value):
    """Map the internal 0-100 adverse-condition score to a centered -100 to +100 scale."""
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip(2.0 * (float(value) - 50.0), -100.0, 100.0))


def normalize_borrower_financial_condition_history(history):
    """Normalize current-version Borrower Financial Condition archive metadata.

    Historical values are rebuilt offline from retained raw inputs. Runtime
    code does not migrate or rescale legacy calculated values.
    """
    if history is None or history.empty or "Borrower Financial Condition" not in history.columns:
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()

    out = history.copy()
    out["Borrower Financial Condition"] = pd.to_numeric(out["Borrower Financial Condition"], errors="coerce")
    if "Borrower Financial Condition Version" in out.columns:
        out["Borrower Financial Condition Version"] = out["Borrower Financial Condition Version"].astype("string")
    else:
        out["Borrower Financial Condition Version"] = pd.Series(pd.NA, index=out.index, dtype="string")
    return out


REQUIRED_LEDGER_COLUMNS = [
    "Ticker",
    "As Of Date",
    "Filing Date",
    "Uncommenced Leases",
    "Purchase or Contractual Commitments",
    "Contingent Exposure",
    "Source URL",
    "Notes",
]


def _normalize_commitment_ledger(df, *, as_of_date=None) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=REQUIRED_LEDGER_COLUMNS)

    missing = [col for col in REQUIRED_LEDGER_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Capital commitment ledger missing columns: {missing}")

    df = df.copy()
    df["Ticker"] = df["Ticker"].astype(str).str.upper().str.strip()
    df["As Of Date"] = pd.to_datetime(df["As Of Date"], errors="coerce")
    df["Filing Date"] = pd.to_datetime(df["Filing Date"], errors="coerce")

    for col in [
        "Uncommenced Leases",
        "Purchase or Contractual Commitments",
        "Contingent Exposure",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if as_of_date is not None:
        cutoff = pd.to_datetime(as_of_date, errors="coerce")
        if pd.isna(cutoff):
            raise ValueError(f"Invalid borrower-financial-condition as_of_date: {as_of_date}")
        df = df.loc[df["Filing Date"].notna() & (df["Filing Date"] <= cutoff)].copy()

    df = df.sort_values(["Ticker", "As Of Date", "Filing Date"], kind="stable")
    return (
        df.groupby("Ticker", as_index=False, dropna=False)
        .tail(1)
        .reset_index(drop=True)
    )


def load_commitment_ledger(path=None, *, as_of_date=None) -> pd.DataFrame:
    ledger_path = Path(path) if path is not None else DEFAULT_COMMITMENTS_PATH

    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        return pd.DataFrame(columns=REQUIRED_LEDGER_COLUMNS)

    return _normalize_commitment_ledger(
        pd.read_csv(ledger_path),
        as_of_date=as_of_date,
    )


def _universe_company_frame(sector_data) -> pd.DataFrame:
    frames = []

    for df in (sector_data or {}).values():
        if df is not None and not df.empty:
            frames.append(df.copy())

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "Ticker" not in combined.columns:
        return pd.DataFrame()

    combined["Ticker"] = combined["Ticker"].astype(str).str.upper().str.strip()
    combined = combined.drop_duplicates(subset=["Ticker"], keep="first")
    return combined[combined["Ticker"].isin(BORROWER_FINANCIAL_CONDITION_TICKERS)].copy()


def _ratio_of_sums(df, numerator, denominator, *, min_companies=2):
    if df is None or df.empty or numerator not in df or denominator not in df:
        return np.nan, 0

    num = pd.to_numeric(df[numerator], errors="coerce")
    den = pd.to_numeric(df[denominator], errors="coerce")
    valid = num.notna() & den.notna() & np.isfinite(num) & np.isfinite(den) & (den > 0)

    valid_count = int(valid.sum())
    if valid_count < min_companies:
        return np.nan, valid_count

    den_sum = float(den.loc[valid].sum())
    if den_sum <= 0:
        return np.nan, valid_count

    return float(num.loc[valid].sum()) / den_sum, valid_count


def _ledger_burden(ledger, cohort, columns, *, min_companies=2):
    """Ratio disclosed obligations to OCF for matching disclosed companies."""
    if ledger is None or ledger.empty or cohort is None or cohort.empty:
        return np.nan, 0, np.nan, []

    working = ledger.copy()
    disclosed_mask = working[list(columns)].notna().any(axis=1)
    working = working.loc[disclosed_mask].copy()

    if working.empty:
        return np.nan, 0, np.nan, []

    working["Obligation"] = working[list(columns)].sum(axis=1, min_count=1)
    working = working.dropna(subset=["Obligation"])

    matching = cohort[cohort["Ticker"].isin(working["Ticker"])].copy()
    if matching.empty:
        return np.nan, 0, np.nan, []

    merged = matching[["Ticker", "Operating Cash Flow"]].merge(
        working[["Ticker", "Obligation"]],
        on="Ticker",
        how="inner",
    )

    obligation = pd.to_numeric(merged["Obligation"], errors="coerce")
    ocf = pd.to_numeric(merged["Operating Cash Flow"], errors="coerce")
    valid = obligation.notna() & ocf.notna() & np.isfinite(obligation) & np.isfinite(ocf) & (ocf > 0)

    valid_count = int(valid.sum())
    if valid_count < min_companies:
        return np.nan, valid_count, np.nan, sorted(merged.loc[valid, "Ticker"].tolist())

    obligation_total = float(obligation.loc[valid].sum())
    ocf_total = float(ocf.loc[valid].sum())
    burden = obligation_total / ocf_total if ocf_total > 0 else np.nan

    return burden, valid_count, obligation_total, sorted(merged.loc[valid, "Ticker"].tolist())


def _debt_capacity_strain(cohort, *, min_companies=2):
    """Score debt capacity without discarding negative-EBITDA companies.

    Branches:
      * positive EBITDA: aggregate net debt / aggregate EBITDA;
      * non-positive EBITDA with positive net debt: aggregate net debt / revenue
        with an impairment floor;
      * non-positive EBITDA with net cash: limited debt-capacity strain, because the
        operating weakness is captured separately by Cash Flow Strain.

    Branch scores are combined by represented revenue; company counts are the
    fallback when revenue weights are unavailable.
    """
    if cohort is None or cohort.empty:
        return {
            "score": np.nan,
            "observations": 0,
            "positive_ebitda_ratio": np.nan,
            "fallback_ratio": np.nan,
            "positive_ebitda_companies": 0,
            "impaired_companies": 0,
            "net_cash_companies": 0,
        }

    frame = cohort.copy()
    for column in ("Net Debt", "EBITDA", "Revenue"):
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")

    usable = frame[
        frame["Net Debt"].notna()
        & frame["EBITDA"].notna()
        & np.isfinite(frame["Net Debt"])
        & np.isfinite(frame["EBITDA"])
    ].copy()
    if len(usable) < min_companies:
        return {
            "score": np.nan,
            "observations": int(len(usable)),
            "positive_ebitda_ratio": np.nan,
            "fallback_ratio": np.nan,
            "positive_ebitda_companies": 0,
            "impaired_companies": 0,
            "net_cash_companies": 0,
        }

    positive = usable[usable["EBITDA"] > 0].copy()
    impaired = usable[
        (usable["EBITDA"] <= 0)
        & (usable["Net Debt"] > 0)
        & usable["Revenue"].notna()
        & np.isfinite(usable["Revenue"])
        & (usable["Revenue"] > 0)
    ].copy()
    net_cash = usable[(usable["EBITDA"] <= 0) & (usable["Net Debt"] <= 0)].copy()

    branch_scores = {}
    branch_exposure = {}

    positive_ratio = np.nan
    if not positive.empty and float(positive["EBITDA"].sum()) > 0:
        positive_ratio = float(positive["Net Debt"].sum()) / float(positive["EBITDA"].sum())
        branch_scores["Positive EBITDA"] = tanh_score(
            positive_ratio, center=1.0, scale=1.5
        )
        branch_exposure["Positive EBITDA"] = float(
            positive.loc[positive["Revenue"].gt(0), "Revenue"].sum()
        )

    fallback_ratio = np.nan
    if not impaired.empty and float(impaired["Revenue"].sum()) > 0:
        fallback_ratio = float(impaired["Net Debt"].sum()) / float(impaired["Revenue"].sum())
        branch_scores["Negative EBITDA / Net Debt"] = max(
            70.0,
            tanh_score(fallback_ratio, center=0.25, scale=0.40),
        )
        branch_exposure["Negative EBITDA / Net Debt"] = float(impaired["Revenue"].sum())

    if not net_cash.empty:
        branch_scores["Negative EBITDA / Net Cash"] = 25.0
        branch_exposure["Negative EBITDA / Net Cash"] = float(
            net_cash.loc[net_cash["Revenue"].gt(0), "Revenue"].sum()
        )

    if not branch_scores:
        score = np.nan
    else:
        weights = {
            name: exposure
            for name, exposure in branch_exposure.items()
            if pd.notna(exposure) and exposure > 0
        }
        if len(weights) != len(branch_scores) or sum(weights.values()) <= 0:
            weights = {
                "Positive EBITDA": len(positive),
                "Negative EBITDA / Net Debt": len(impaired),
                "Negative EBITDA / Net Cash": len(net_cash),
            }
            weights = {
                name: float(weights.get(name, 0))
                for name in branch_scores
                if weights.get(name, 0) > 0
            }

        total_weight = sum(weights.values())
        score = (
            sum(branch_scores[name] * weights[name] for name in weights) / total_weight
            if total_weight > 0
            else np.nan
        )

    return {
        "score": float(np.clip(score, 0, 100)) if pd.notna(score) else np.nan,
        "observations": int(len(usable)),
        "positive_ebitda_ratio": positive_ratio,
        "fallback_ratio": fallback_ratio,
        "positive_ebitda_companies": int(len(positive)),
        "impaired_companies": int(len(impaired)),
        "net_cash_companies": int(len(net_cash)),
        "branch_scores": branch_scores,
    }


def calculate_borrower_financial_condition(
    sector_data,
    commitments_path=None,
    *,
    as_of_date=None,
    commitments_df=None,
) -> dict:
    """Calculate Borrower Financial Condition with a fixed 3-of-4 component rule.

    ``commitments_df`` is used by the audited historical backfill.  Runtime
    callers continue to use the retained current ledger at
    ``commitments_path``.
    """
    ledger = (
        _normalize_commitment_ledger(commitments_df, as_of_date=as_of_date)
        if commitments_df is not None
        else load_commitment_ledger(commitments_path, as_of_date=as_of_date)
    )
    cohort = _universe_company_frame(sector_data)

    fcf_margin, fcf_count = _ratio_of_sums(cohort, "Free Cash Flow", "Revenue")
    reinvestment, reinvestment_count = _ratio_of_sums(
        cohort,
        "CapEx",
        "Operating Cash Flow",
    )
    debt_capacity = _debt_capacity_strain(cohort)

    cash_flow_subscores = {
        "FCF Margin Strain": (
            100.0 - tanh_score(fcf_margin, center=0.10, scale=0.15)
            if pd.notna(fcf_margin)
            else np.nan
        ),
        "Reinvestment Burden": tanh_score(
            reinvestment,
            center=0.35,
            scale=0.50,
        ),
    }
    cash_flow_result = weighted_available_score(
        cash_flow_subscores,
        CASH_FLOW_SUBWEIGHTS,
        min_components=1,
    )

    committed_burden, committed_count, committed_total, committed_tickers = _ledger_burden(
        ledger,
        cohort,
        ["Uncommenced Leases", "Purchase or Contractual Commitments"],
        min_companies=2,
    )
    contingent_burden, contingent_count, contingent_total, contingent_tickers = _ledger_burden(
        ledger,
        cohort,
        ["Contingent Exposure"],
        min_companies=2,
    )

    base_scores = {
        "Cash Flow Strain": cash_flow_result["score"],
        "Debt Capacity Strain": debt_capacity["score"],
        "Committed Burden": tanh_score(committed_burden, center=1.5, scale=2.0),
        "Contingent Exposure": tanh_score(contingent_burden, center=0.10, scale=0.20),
    }

    combined = weighted_available_score(
        base_scores,
        BORROWER_FINANCIAL_CONDITION_WEIGHTS,
        min_components=3,
    )
    signed_scores = {
        name: borrower_financial_condition_to_signed(score)
        for name, score in base_scores.items()
    }
    signed_score = borrower_financial_condition_to_signed(combined["score"])

    cohort_tickers = sorted(cohort["Ticker"].unique().tolist()) if not cohort.empty else []
    ledger_tickers = sorted(ledger["Ticker"].unique().tolist()) if not ledger.empty else []

    components = {
        "Cash Flow Strain": {
            "raw": fcf_margin,
            "secondary_raw": reinvestment,
            "score": signed_scores["Cash Flow Strain"],
            "base_score": base_scores["Cash Flow Strain"],
            "weight": BORROWER_FINANCIAL_CONDITION_WEIGHTS["Cash Flow Strain"],
            "observations": max(fcf_count, reinvestment_count),
            "subcomponents": {
                "FCF Margin Strain": {
                    "raw": fcf_margin,
                    "score": cash_flow_subscores["FCF Margin Strain"],
                    "observations": fcf_count,
                },
                "Reinvestment Burden": {
                    "raw": reinvestment,
                    "score": cash_flow_subscores["Reinvestment Burden"],
                    "observations": reinvestment_count,
                },
            },
        },
        "Debt Capacity Strain": {
            "raw": debt_capacity["positive_ebitda_ratio"],
            "secondary_raw": debt_capacity["fallback_ratio"],
            "score": signed_scores["Debt Capacity Strain"],
            "base_score": base_scores["Debt Capacity Strain"],
            "weight": BORROWER_FINANCIAL_CONDITION_WEIGHTS["Debt Capacity Strain"],
            "observations": debt_capacity["observations"],
            "positive_ebitda_companies": debt_capacity["positive_ebitda_companies"],
            "impaired_companies": debt_capacity["impaired_companies"],
            "net_cash_companies": debt_capacity["net_cash_companies"],
            "branch_scores": debt_capacity.get("branch_scores", {}),
        },
        "Committed Burden": {
            "raw": committed_burden,
            "score": signed_scores["Committed Burden"],
            "base_score": base_scores["Committed Burden"],
            "weight": BORROWER_FINANCIAL_CONDITION_WEIGHTS["Committed Burden"],
            "observations": committed_count,
            "obligation_total": committed_total,
            "tickers": committed_tickers,
        },
        "Contingent Exposure": {
            "raw": contingent_burden,
            "score": signed_scores["Contingent Exposure"],
            "base_score": base_scores["Contingent Exposure"],
            "weight": BORROWER_FINANCIAL_CONDITION_WEIGHTS["Contingent Exposure"],
            "observations": contingent_count,
            "obligation_total": contingent_total,
            "tickers": contingent_tickers,
        },
    }

    ledger_used = ledger[ledger["Ticker"].isin(cohort_tickers)].copy() if not ledger.empty else ledger

    return {
        "score": signed_score,
        "base_score": combined["score"],
        "valid_components": combined["valid_components"],
        "coverage": combined["coverage"],
        "components": components,
        "cohort_tickers": cohort_tickers,
        "target_cohort_size": len(BORROWER_FINANCIAL_CONDITION_TICKERS),
        "ledger_tickers": ledger_tickers,
        "ledger_companies": int(ledger["Ticker"].nunique()) if not ledger.empty else 0,
        "cohort_companies": len(cohort_tickers),
        "commitment_tickers": committed_tickers,
        "contingent_tickers": contingent_tickers,
        "committed_total": committed_total,
        "contingent_total": contingent_total,
        "ledger": ledger_used,
    }
