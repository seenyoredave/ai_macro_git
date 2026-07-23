"""Capital Stress engine.

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

CAPITAL_STRESS_TICKERS = {
    "MSFT", "AMZN", "GOOG", "META", "ORCL",
    "NVDA", "AMD", "IREN", "SMCI", "ANET",
}

CAPITAL_STRESS_WEIGHTS = {
    "Cash Flow Strain": 0.30,
    "Book Leverage": 0.25,
    "Committed Burden": 0.30,
    "Contingent Exposure": 0.15,
}

CASH_FLOW_SUBWEIGHTS = {
    "FCF Margin Strain": 0.60,
    "Reinvestment Burden": 0.40,
}

def capital_stress_to_signed(value):
    """Map the internal 0-100 stress score to a centered -100 to +100 scale."""
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip(2.0 * (float(value) - 50.0), -100.0, 100.0))


def normalize_capital_stress_history(history):
    """Normalize current-version Capital Stress archive metadata.

    Historical values are rebuilt offline from retained raw inputs. Runtime
    code does not migrate or rescale legacy calculated values.
    """
    if history is None or history.empty or "Capital Stress" not in history.columns:
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()

    out = history.copy()
    out["Capital Stress"] = pd.to_numeric(out["Capital Stress"], errors="coerce")
    if "Capital Stress Version" in out.columns:
        out["Capital Stress Version"] = out["Capital Stress Version"].astype("string")
    else:
        out["Capital Stress Version"] = pd.Series(pd.NA, index=out.index, dtype="string")
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


def load_commitment_ledger(path=None, *, as_of_date=None) -> pd.DataFrame:
    ledger_path = Path(path) if path is not None else DEFAULT_COMMITMENTS_PATH

    if not ledger_path.exists() or ledger_path.stat().st_size == 0:
        return pd.DataFrame(columns=REQUIRED_LEDGER_COLUMNS)

    df = pd.read_csv(ledger_path)
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
            raise ValueError(f"Invalid capital-stress as_of_date: {as_of_date}")
        df = df.loc[df["Filing Date"].notna() & (df["Filing Date"] <= cutoff)].copy()

    df = df.sort_values(["Ticker", "As Of Date", "Filing Date"], kind="stable")
    return (
        df.groupby("Ticker", as_index=False, dropna=False)
        .tail(1)
        .reset_index(drop=True)
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
    return combined[combined["Ticker"].isin(CAPITAL_STRESS_TICKERS)].copy()


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


def calculate_capital_stress(
    sector_data,
    commitments_path=None,
    *,
    as_of_date=None,
) -> dict:
    """Calculate Capital Stress with a fixed 3-of-4 component rule."""
    ledger = load_commitment_ledger(
        commitments_path,
        as_of_date=as_of_date,
    )
    cohort = _universe_company_frame(sector_data)

    fcf_margin, fcf_count = _ratio_of_sums(cohort, "Free Cash Flow", "Revenue")
    reinvestment, reinvestment_count = _ratio_of_sums(
        cohort,
        "CapEx",
        "Operating Cash Flow",
    )
    book_leverage, leverage_count = _ratio_of_sums(cohort, "Net Debt", "EBITDA")

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
        "Book Leverage": tanh_score(book_leverage, center=1.0, scale=1.5),
        "Committed Burden": tanh_score(committed_burden, center=1.5, scale=2.0),
        "Contingent Exposure": tanh_score(contingent_burden, center=0.10, scale=0.20),
    }

    combined = weighted_available_score(
        base_scores,
        CAPITAL_STRESS_WEIGHTS,
        min_components=3,
    )
    signed_scores = {
        name: capital_stress_to_signed(score)
        for name, score in base_scores.items()
    }
    signed_score = capital_stress_to_signed(combined["score"])

    cohort_tickers = sorted(cohort["Ticker"].unique().tolist()) if not cohort.empty else []
    ledger_tickers = sorted(ledger["Ticker"].unique().tolist()) if not ledger.empty else []

    components = {
        "Cash Flow Strain": {
            "raw": fcf_margin,
            "secondary_raw": reinvestment,
            "score": signed_scores["Cash Flow Strain"],
            "base_score": base_scores["Cash Flow Strain"],
            "weight": CAPITAL_STRESS_WEIGHTS["Cash Flow Strain"],
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
        "Book Leverage": {
            "raw": book_leverage,
            "score": signed_scores["Book Leverage"],
            "base_score": base_scores["Book Leverage"],
            "weight": CAPITAL_STRESS_WEIGHTS["Book Leverage"],
            "observations": leverage_count,
        },
        "Committed Burden": {
            "raw": committed_burden,
            "score": signed_scores["Committed Burden"],
            "base_score": base_scores["Committed Burden"],
            "weight": CAPITAL_STRESS_WEIGHTS["Committed Burden"],
            "observations": committed_count,
            "obligation_total": committed_total,
            "tickers": committed_tickers,
        },
        "Contingent Exposure": {
            "raw": contingent_burden,
            "score": signed_scores["Contingent Exposure"],
            "base_score": base_scores["Contingent Exposure"],
            "weight": CAPITAL_STRESS_WEIGHTS["Contingent Exposure"],
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
        "target_cohort_size": len(CAPITAL_STRESS_TICKERS),
        "ledger_tickers": ledger_tickers,
        "ledger_companies": int(ledger["Ticker"].nunique()) if not ledger.empty else 0,
        "cohort_companies": len(cohort_tickers),
        "commitment_tickers": committed_tickers,
        "contingent_tickers": contingent_tickers,
        "committed_total": committed_total,
        "contingent_total": contingent_total,
        "ledger": ledger_used,
    }
