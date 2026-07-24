"""Credit Intermediation Stress engine.

The metric measures whether the financing system is becoming less able or less
willing to support operating businesses. It deliberately separates borrower
health (Capital Stress) from lender/transmission health.

Public inputs:
  1. Federal Reserve SLOOS business-loan tightening;
  2. aggregate U.S. regulatory Tier 1 capital relative to risk-weighted assets;
  3. asset-weighted non-accruals for a fixed public BDC cohort;
  4. SEC Form PF private-equity portfolio leverage and PIK borrowing.

The public-history ledgers are explicit, reviewable CSVs. Missing inputs remain
missing and the headline requires at least three of the four pillars.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score, weighted_available_score


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANK_PATH = PROJECT_ROOT / "data" / "bank_credit_tightening_history.csv"
DEFAULT_BANK_CAPITAL_PATH = PROJECT_ROOT / "data" / "bank_tier1_capital_history.csv"
DEFAULT_BDC_PATH = PROJECT_ROOT / "data" / "private_credit_bdc_history.csv"
DEFAULT_PE_PATH = PROJECT_ROOT / "data" / "private_equity_stress_history.csv"

INTERMEDIATION_WEIGHTS = {
    "Bank Credit Tightening": 0.25,
    "Bank Capital Strain": 0.25,
    "Private Credit Impairment": 0.25,
    "PE Portfolio Financing Strain": 0.25,
}

BANK_CHANNEL_COMPONENTS = (
    "Bank Credit Tightening",
    "Bank Capital Strain",
)
NONBANK_CHANNEL_COMPONENTS = (
    "Private Credit Impairment",
    "PE Portfolio Financing Strain",
)
MIN_PERCENTILE_OBSERVATIONS = 8

PE_SUBWEIGHTS = {
    "High-Leverage Portfolio Share": 0.60,
    "PIK Burden": 0.40,
}

BDC_COHORT = ("ARCC", "OBDC", "FSK", "GBDC", "CION")


def intermediation_stress_to_signed(value):
    """Map the internal 0-100 stress score to centered -100 to +100."""
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip(2.0 * (float(value) - 50.0), -100.0, 100.0))


def normalize_intermediation_stress_history(history):
    """Normalize archive metadata for the current metric version."""
    if (
        history is None
        or history.empty
        or "Credit Intermediation Stress" not in history.columns
    ):
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()

    out = history.copy()
    out["Credit Intermediation Stress"] = pd.to_numeric(
        out["Credit Intermediation Stress"], errors="coerce"
    )
    if "Credit Intermediation Stress Version" in out.columns:
        out["Credit Intermediation Stress Version"] = out[
            "Credit Intermediation Stress Version"
        ].astype("string")
    else:
        out["Credit Intermediation Stress Version"] = pd.Series(
            pd.NA, index=out.index, dtype="string"
        )
    return out


def _load_csv(path, required_columns):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=required_columns)

    frame = pd.read_csv(path)
    missing = [column for column in required_columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{path.name} missing columns: {missing}")
    return frame.copy()


def load_bank_tightening_history(path=None):
    frame = _load_csv(
        path or DEFAULT_BANK_PATH,
        ["Date", "Tightening Percent"],
    )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Tightening Percent"] = pd.to_numeric(
        frame["Tightening Percent"], errors="coerce"
    )
    frame = frame.dropna(subset=["Date", "Tightening Percent"])
    return (
        frame.sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def load_bank_capital_history(path=None):
    frame = _load_csv(
        path or DEFAULT_BANK_CAPITAL_PATH,
        ["Date", "Tier 1 Capital Ratio (%)"],
    )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Tier 1 Capital Ratio (%)"] = pd.to_numeric(
        frame["Tier 1 Capital Ratio (%)"], errors="coerce"
    )
    frame = frame.dropna(subset=["Date", "Tier 1 Capital Ratio (%)"])
    return (
        frame.sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def load_bdc_impairment_history(path=None):
    frame = _load_csv(
        path or DEFAULT_BDC_PATH,
        ["Date", "Ticker", "Portfolio Cost ($mm)", "Nonaccrual at Cost (%)"],
    )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.strip()
    frame["Portfolio Cost ($mm)"] = pd.to_numeric(
        frame["Portfolio Cost ($mm)"], errors="coerce"
    )
    frame["Nonaccrual at Cost (%)"] = pd.to_numeric(
        frame["Nonaccrual at Cost (%)"], errors="coerce"
    )
    frame = frame[
        frame["Ticker"].isin(BDC_COHORT)
        & frame["Date"].notna()
        & frame["Portfolio Cost ($mm)"].gt(0)
        & frame["Nonaccrual at Cost (%)"].notna()
    ].copy()

    rows = []
    for observation_date, group in frame.groupby("Date", sort=True):
        total_cost = float(group["Portfolio Cost ($mm)"].sum())
        weighted_ratio = (
            float(
                (
                    group["Portfolio Cost ($mm)"]
                    * group["Nonaccrual at Cost (%)"]
                ).sum()
                / total_cost
            )
            if total_cost > 0
            else np.nan
        )
        urls = sorted(
            {
                str(value).strip()
                for value in group.get("Source URL", pd.Series(dtype=object)).dropna()
                if str(value).strip()
            }
        )
        rows.append(
            {
                "Date": observation_date,
                "Weighted Nonaccrual at Cost (%)": weighted_ratio,
                "Portfolio Cost ($mm)": total_cost,
                "Observations": int(group["Ticker"].nunique()),
                "Cohort": ", ".join(sorted(group["Ticker"].unique())),
                "Source URL": " | ".join(urls),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "Date",
                "Weighted Nonaccrual at Cost (%)",
                "Portfolio Cost ($mm)",
                "Observations",
                "Cohort",
                "Source URL",
            ]
        )

    return pd.DataFrame(rows).sort_values("Date", kind="stable").reset_index(drop=True)


def load_pe_financing_history(path=None):
    required = [
        "Date",
        "PIK Mean (%)",
        "D/E Less Than Zero ($bn)",
        "D/E 0-1 ($bn)",
        "D/E 1-2 ($bn)",
        "D/E 2-5 ($bn)",
        "D/E 5+ ($bn)",
    ]
    frame = _load_csv(path or DEFAULT_PE_PATH, required)
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    for column in required[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    leverage_columns = required[2:]
    frame["Reported CPC Gross Assets ($bn)"] = frame[leverage_columns].sum(
        axis=1, min_count=len(leverage_columns)
    )
    frame["High-Leverage CPC Gross Assets ($bn)"] = frame[
        ["D/E Less Than Zero ($bn)", "D/E 2-5 ($bn)", "D/E 5+ ($bn)"]
    ].sum(axis=1, min_count=3)
    frame["High-Leverage Portfolio Share (%)"] = np.where(
        frame["Reported CPC Gross Assets ($bn)"] > 0,
        100.0
        * frame["High-Leverage CPC Gross Assets ($bn)"]
        / frame["Reported CPC Gross Assets ($bn)"],
        np.nan,
    )
    return (
        frame.dropna(
            subset=[
                "Date",
                "PIK Mean (%)",
                "High-Leverage Portfolio Share (%)",
            ]
        )
        .sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _fred_observation(fred_data, payload_name, value_column, source_url):
    payload = (fred_data or {}).get(payload_name, {})
    if isinstance(payload, dict):
        value = pd.to_numeric(payload.get("value", np.nan), errors="coerce")
        date_value = pd.to_datetime(payload.get("date"), errors="coerce")
        source = payload.get("source", "FRED")
    else:
        value = pd.to_numeric(payload, errors="coerce")
        date_value = pd.NaT
        source = "FRED"

    if pd.isna(value) or not np.isfinite(value):
        return None

    return {
        "Date": date_value,
        value_column: float(value),
        "Source": source,
        "Source_URL": source_url,
    }


def _with_live_observation(history, observation):
    if observation is None:
        return history

    out = history.copy()
    observation_date = observation["Date"]
    if pd.isna(observation_date):
        if out.empty:
            return out
        observation_date = out["Date"].max()

    observation["Date"] = pd.Timestamp(observation_date).normalize()
    out = pd.concat([out, pd.DataFrame([observation])], ignore_index=True, sort=False)
    return (
        out.sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def _asof_row(frame, observation_date):
    if frame is None or frame.empty:
        return None
    eligible = frame.loc[frame["Date"] <= observation_date]
    return None if eligible.empty else eligible.iloc[-1]


def _historical_or_anchored_score(
    value,
    history,
    *,
    higher_is_stress=True,
    center,
    scale,
):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan, "Unavailable", 0

    history = (
        pd.to_numeric(pd.Series(history, dtype=float), errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    distinct = np.sort(history.round(8).unique())
    if len(distinct) >= MIN_PERCENTILE_OBSERVATIONS:
        below = float(np.sum(distinct < float(value)))
        equal = float(np.sum(distinct == round(float(value), 8)))
        percentile = 100.0 * (below + 0.5 * equal) / len(distinct)
        score = percentile if higher_is_stress else 100.0 - percentile
        return float(np.clip(score, 0, 100)), "Historical Percentile", len(distinct)

    anchored = tanh_score(value, center=center, scale=scale)
    if not higher_is_stress and pd.notna(anchored):
        anchored = 100.0 - anchored
    return anchored, "Anchored Tanh", len(distinct)


def _channel_score(base_scores, component_names):
    valid = {
        name: float(base_scores[name])
        for name in component_names
        if pd.notna(base_scores.get(name)) and np.isfinite(base_scores.get(name))
    }
    if not valid:
        return np.nan, {}
    weight = 1.0 / len(valid)
    return (
        float(sum(valid.values()) / len(valid)),
        {name: weight for name in valid},
    )


def _score_snapshot(
    bank_row=None,
    bank_capital_row=None,
    bdc_row=None,
    pe_row=None,
    *,
    bank_history=None,
    bank_capital_history=None,
    bdc_history=None,
    pe_history=None,
    observation_date=None,
):
    bank_raw = (
        pd.to_numeric(bank_row.get("Tightening Percent"), errors="coerce")
        if bank_row is not None
        else np.nan
    )
    bank_capital_raw = (
        pd.to_numeric(
            bank_capital_row.get("Tier 1 Capital Ratio (%)"), errors="coerce"
        )
        if bank_capital_row is not None
        else np.nan
    )
    bdc_raw = (
        pd.to_numeric(
            bdc_row.get("Weighted Nonaccrual at Cost (%)"), errors="coerce"
        )
        if bdc_row is not None
        else np.nan
    )
    pe_high_leverage = (
        pd.to_numeric(
            pe_row.get("High-Leverage Portfolio Share (%)"), errors="coerce"
        )
        if pe_row is not None
        else np.nan
    )
    pe_pik = (
        pd.to_numeric(pe_row.get("PIK Mean (%)"), errors="coerce")
        if pe_row is not None
        else np.nan
    )

    cutoff = pd.to_datetime(observation_date, errors="coerce")

    def history_values(frame, column):
        if frame is None or frame.empty or column not in frame.columns:
            return pd.Series(dtype=float)
        eligible = frame
        if pd.notna(cutoff) and "Date" in frame.columns:
            eligible = frame.loc[frame["Date"] <= cutoff]
        return eligible[column]

    bank_score, bank_method, bank_history_count = _historical_or_anchored_score(
        bank_raw,
        history_values(bank_history, "Tightening Percent"),
        higher_is_stress=True,
        center=0.0,
        scale=35.0,
    )
    bank_capital_score, bank_capital_method, bank_capital_history_count = (
        _historical_or_anchored_score(
            bank_capital_raw,
            history_values(bank_capital_history, "Tier 1 Capital Ratio (%)"),
            higher_is_stress=False,
            center=12.5,
            scale=4.0,
        )
    )
    bdc_score, bdc_method, bdc_history_count = _historical_or_anchored_score(
        bdc_raw,
        history_values(bdc_history, "Weighted Nonaccrual at Cost (%)"),
        higher_is_stress=True,
        center=2.0,
        scale=2.5,
    )

    pe_high_score, pe_high_method, pe_high_history_count = _historical_or_anchored_score(
        pe_high_leverage,
        history_values(pe_history, "High-Leverage Portfolio Share (%)"),
        higher_is_stress=True,
        center=30.0,
        scale=12.0,
    )
    pe_pik_score, pe_pik_method, pe_pik_history_count = _historical_or_anchored_score(
        pe_pik,
        history_values(pe_history, "PIK Mean (%)"),
        higher_is_stress=True,
        center=18.0,
        scale=10.0,
    )

    base_scores = {
        "Bank Credit Tightening": bank_score,
        "Bank Capital Strain": bank_capital_score,
        "Private Credit Impairment": bdc_score,
    }

    pe_subscores = {
        "High-Leverage Portfolio Share": pe_high_score,
        "PIK Burden": pe_pik_score,
    }
    pe_combined = weighted_available_score(
        pe_subscores,
        PE_SUBWEIGHTS,
        min_components=2,
    )
    base_scores["PE Portfolio Financing Strain"] = pe_combined["score"]

    bank_channel, bank_channel_weights = _channel_score(
        base_scores, BANK_CHANNEL_COMPONENTS
    )
    nonbank_channel, nonbank_channel_weights = _channel_score(
        base_scores, NONBANK_CHANNEL_COMPONENTS
    )
    valid_components = int(
        sum(pd.notna(score) and np.isfinite(score) for score in base_scores.values())
    )
    channel_complete = pd.notna(bank_channel) and pd.notna(nonbank_channel)
    combined_score = (
        0.5 * bank_channel + 0.5 * nonbank_channel
        if valid_components >= 3 and channel_complete
        else np.nan
    )
    normalized_weights = {
        **{name: 0.5 * weight for name, weight in bank_channel_weights.items()},
        **{name: 0.5 * weight for name, weight in nonbank_channel_weights.items()},
    }
    signed_scores = {
        name: intermediation_stress_to_signed(score)
        for name, score in base_scores.items()
    }

    return {
        "score": intermediation_stress_to_signed(combined_score),
        "base_score": combined_score,
        "valid_components": valid_components,
        "coverage": valid_components / 4.0,
        "signed_scores": signed_scores,
        "base_scores": base_scores,
        "normalized_weights": normalized_weights,
        "bank_channel_score": bank_channel,
        "nonbank_channel_score": nonbank_channel,
        "elevated_pillars": int(
            sum(pd.notna(score) and score > 50 for score in base_scores.values())
        ),
        "pe_subscores": pe_subscores,
        "normalization": {
            "Bank Credit Tightening": {
                "method": bank_method,
                "history_observations": bank_history_count,
            },
            "Bank Capital Strain": {
                "method": bank_capital_method,
                "history_observations": bank_capital_history_count,
            },
            "Private Credit Impairment": {
                "method": bdc_method,
                "history_observations": bdc_history_count,
            },
            "High-Leverage Portfolio Share": {
                "method": pe_high_method,
                "history_observations": pe_high_history_count,
            },
            "PIK Burden": {
                "method": pe_pik_method,
                "history_observations": pe_pik_history_count,
            },
        },
        "raw": {
            "bank": bank_raw,
            "bank_capital": bank_capital_raw,
            "bdc": bdc_raw,
            "pe_high_leverage": pe_high_leverage,
            "pe_pik": pe_pik,
        },
    }


def build_intermediation_stress_history(
    bank_history,
    bank_capital_history,
    bdc_history,
    pe_history,
):
    date_series = [
        frame["Date"]
        for frame in (bank_history, bank_capital_history, bdc_history, pe_history)
        if frame is not None and not frame.empty
    ]
    if not date_series:
        return pd.DataFrame()

    dates = pd.Series(pd.concat(date_series, ignore_index=True).dropna().unique())
    dates = pd.to_datetime(dates, errors="coerce").dropna().sort_values()

    rows = []
    for observation_date in dates:
        bank_row = _asof_row(bank_history, observation_date)
        bank_capital_row = _asof_row(bank_capital_history, observation_date)
        bdc_row = _asof_row(bdc_history, observation_date)
        pe_row = _asof_row(pe_history, observation_date)
        snapshot = _score_snapshot(
            bank_row,
            bank_capital_row,
            bdc_row,
            pe_row,
            bank_history=bank_history,
            bank_capital_history=bank_capital_history,
            bdc_history=bdc_history,
            pe_history=pe_history,
            observation_date=observation_date,
        )

        if pd.isna(snapshot["score"]):
            continue

        rows.append(
            {
                "Date": pd.Timestamp(observation_date),
                "Credit Intermediation Stress": snapshot["score"],
                "Bank Credit Tightening": snapshot["signed_scores"].get(
                    "Bank Credit Tightening", np.nan
                ),
                "Bank Capital Strain": snapshot["signed_scores"].get(
                    "Bank Capital Strain", np.nan
                ),
                "Private Credit Impairment": snapshot["signed_scores"].get(
                    "Private Credit Impairment", np.nan
                ),
                "PE Portfolio Financing Strain": snapshot["signed_scores"].get(
                    "PE Portfolio Financing Strain", np.nan
                ),
                "Valid Components": snapshot["valid_components"],
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("Date", kind="stable").reset_index(drop=True)


def _row_date(row):
    if row is None:
        return None
    value = pd.to_datetime(row.get("Date"), errors="coerce")
    return value.date().isoformat() if pd.notna(value) else None


def calculate_intermediation_stress(
    fred_data=None,
    *,
    bank_path=None,
    bank_capital_path=None,
    bdc_path=None,
    pe_path=None,
) -> dict:
    """Calculate the signed Credit Intermediation Stress metric."""
    bank_history = load_bank_tightening_history(bank_path)
    bank_history = _with_live_observation(
        bank_history,
        _fred_observation(
            fred_data,
            "Business Loan Tightening",
            "Tightening Percent",
            "https://fred.stlouisfed.org/series/SUBLPDMBSXWBNQ",
        ),
    )

    bank_capital_history = load_bank_capital_history(bank_capital_path)
    bank_capital_history = _with_live_observation(
        bank_capital_history,
        _fred_observation(
            fred_data,
            "Bank Tier 1 Capital Ratio",
            "Tier 1 Capital Ratio (%)",
            "https://fred.stlouisfed.org/series/BOGZ1FL010000016Q",
        ),
    )

    bdc_history = load_bdc_impairment_history(bdc_path)
    pe_history = load_pe_financing_history(pe_path)

    history = build_intermediation_stress_history(
        bank_history,
        bank_capital_history,
        bdc_history,
        pe_history,
    )

    latest_date_candidates = [
        frame["Date"].max()
        for frame in (bank_history, bank_capital_history, bdc_history, pe_history)
        if frame is not None and not frame.empty
    ]
    latest_date = max(latest_date_candidates) if latest_date_candidates else pd.NaT

    bank_row = _asof_row(bank_history, latest_date) if pd.notna(latest_date) else None
    bank_capital_row = (
        _asof_row(bank_capital_history, latest_date)
        if pd.notna(latest_date)
        else None
    )
    bdc_row = _asof_row(bdc_history, latest_date) if pd.notna(latest_date) else None
    pe_row = _asof_row(pe_history, latest_date) if pd.notna(latest_date) else None
    snapshot = _score_snapshot(
        bank_row,
        bank_capital_row,
        bdc_row,
        pe_row,
        bank_history=bank_history,
        bank_capital_history=bank_capital_history,
        bdc_history=bdc_history,
        pe_history=pe_history,
        observation_date=latest_date,
    )

    bank_source = "Federal Reserve SLOOS / FRED"
    if bank_row is not None and str(bank_row.get("Source", "")).strip():
        bank_source = str(bank_row.get("Source"))

    bank_capital_source = "Federal Reserve Z.1 / FRED"
    if (
        bank_capital_row is not None
        and str(bank_capital_row.get("Source", "")).strip()
    ):
        bank_capital_source = str(bank_capital_row.get("Source"))

    bdc_source = "Public BDC SEC filings"
    pe_source = (
        str(pe_row.get("Source"))
        if pe_row is not None and str(pe_row.get("Source", "")).strip()
        else "SEC Private Fund Statistics / Form PF"
    )

    components = {
        "Bank Credit Tightening": {
            "raw": snapshot["raw"]["bank"],
            "score": snapshot["signed_scores"].get(
                "Bank Credit Tightening", np.nan
            ),
            "base_score": snapshot["base_scores"].get(
                "Bank Credit Tightening", np.nan
            ),
            "weight": INTERMEDIATION_WEIGHTS["Bank Credit Tightening"],
            "active_weight": snapshot["normalized_weights"].get(
                "Bank Credit Tightening", np.nan
            ),
            "normalization": snapshot["normalization"].get(
                "Bank Credit Tightening", {}
            ),
            "observations": 1 if bank_row is not None else 0,
            "as_of": _row_date(bank_row),
            "source": bank_source,
            "source_url": (
                bank_row.get(
                    "Source_URL",
                    "https://fred.stlouisfed.org/series/SUBLPDMBSXWBNQ",
                )
                if bank_row is not None
                else "https://fred.stlouisfed.org/series/SUBLPDMBSXWBNQ"
            ),
        },
        "Bank Capital Strain": {
            "raw": snapshot["raw"]["bank_capital"],
            "score": snapshot["signed_scores"].get("Bank Capital Strain", np.nan),
            "base_score": snapshot["base_scores"].get(
                "Bank Capital Strain", np.nan
            ),
            "weight": INTERMEDIATION_WEIGHTS["Bank Capital Strain"],
            "active_weight": snapshot["normalized_weights"].get(
                "Bank Capital Strain", np.nan
            ),
            "normalization": snapshot["normalization"].get(
                "Bank Capital Strain", {}
            ),
            "observations": 1 if bank_capital_row is not None else 0,
            "as_of": _row_date(bank_capital_row),
            "source": bank_capital_source,
            "source_url": (
                bank_capital_row.get(
                    "Source_URL",
                    "https://fred.stlouisfed.org/series/BOGZ1FL010000016Q",
                )
                if bank_capital_row is not None
                else "https://fred.stlouisfed.org/series/BOGZ1FL010000016Q"
            ),
        },
        "Private Credit Impairment": {
            "raw": snapshot["raw"]["bdc"],
            "score": snapshot["signed_scores"].get(
                "Private Credit Impairment", np.nan
            ),
            "base_score": snapshot["base_scores"].get(
                "Private Credit Impairment", np.nan
            ),
            "weight": INTERMEDIATION_WEIGHTS["Private Credit Impairment"],
            "active_weight": snapshot["normalized_weights"].get(
                "Private Credit Impairment", np.nan
            ),
            "normalization": snapshot["normalization"].get(
                "Private Credit Impairment", {}
            ),
            "observations": (
                int(bdc_row.get("Observations", 0)) if bdc_row is not None else 0
            ),
            "as_of": _row_date(bdc_row),
            "source": bdc_source,
            "source_url": (
                bdc_row.get("Source URL", "") if bdc_row is not None else ""
            ),
            "cohort": (
                bdc_row.get("Cohort", ", ".join(BDC_COHORT))
                if bdc_row is not None
                else ", ".join(BDC_COHORT)
            ),
            "portfolio_cost_mm": (
                bdc_row.get("Portfolio Cost ($mm)", np.nan)
                if bdc_row is not None
                else np.nan
            ),
        },
        "PE Portfolio Financing Strain": {
            "raw": snapshot["raw"]["pe_high_leverage"],
            "secondary_raw": snapshot["raw"]["pe_pik"],
            "score": snapshot["signed_scores"].get(
                "PE Portfolio Financing Strain", np.nan
            ),
            "base_score": snapshot["base_scores"].get(
                "PE Portfolio Financing Strain", np.nan
            ),
            "weight": INTERMEDIATION_WEIGHTS[
                "PE Portfolio Financing Strain"
            ],
            "active_weight": snapshot["normalized_weights"].get(
                "PE Portfolio Financing Strain", np.nan
            ),
            "normalization": {
                "High-Leverage Portfolio Share": snapshot["normalization"].get(
                    "High-Leverage Portfolio Share", {}
                ),
                "PIK Burden": snapshot["normalization"].get("PIK Burden", {}),
            },
            "observations": 1 if pe_row is not None else 0,
            "as_of": _row_date(pe_row),
            "source": pe_source,
            "source_url": pe_row.get("Source URL", "") if pe_row is not None else "",
            "reported_assets_bn": (
                pe_row.get("Reported CPC Gross Assets ($bn)", np.nan)
                if pe_row is not None
                else np.nan
            ),
        },
    }

    return {
        "score": snapshot["score"],
        "base_score": snapshot["base_score"],
        "valid_components": snapshot["valid_components"],
        "coverage": snapshot["coverage"],
        "bank_channel_score": snapshot.get("bank_channel_score", np.nan),
        "nonbank_channel_score": snapshot.get("nonbank_channel_score", np.nan),
        "elevated_pillars": snapshot.get("elevated_pillars", 0),
        "components": components,
        "history": history,
    }
