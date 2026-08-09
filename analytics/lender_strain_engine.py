from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score, weighted_available_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANK_PATH = PROJECT_ROOT / "data" / "bank_credit_tightening_history.csv"
DEFAULT_BANK_CAPITAL_PATH = PROJECT_ROOT / "data" / "bank_tier1_capital_history.csv"
DEFAULT_BDC_PATH = PROJECT_ROOT / "data" / "private_credit_bdc_history.csv"
DEFAULT_BUSINESS_DELINQUENCY_PATH = PROJECT_ROOT / "data" / "business_loan_delinquency_history.csv"
DEFAULT_PE_PATH = PROJECT_ROOT / "data" / "private_equity_strain_history.csv"

LENDER_STRAIN_WEIGHTS = {
    "Bank Credit Tightening": 0.30,
    "Bank Capital Strain": 0.30,
    "Private Credit Impairment": 0.20,
    "PE Portfolio Financing Strain": 0.20,
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
MIN_LENDER_COMPONENTS = 4

PE_SUBWEIGHTS = {
    "High-Leverage Portfolio Share": 0.60,
    "PIK Burden": 0.40,
}

BDC_OPTIONAL_METRICS = (
    "Nonaccrual at Fair Value (%)",
    "PIK Income Share (%)",
    "NAV Change (%)",
    "Net Losses / Portfolio (%)",
    "Debt to Equity (x)",
)

def lender_strain_to_signed(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return float(np.clip(2.0 * (float(value) - 50.0), -100.0, 100.0))

def normalize_lender_strain_history(history):
    if (
        history is None
        or history.empty
        or "Lender Strain" not in history.columns
    ):
        return history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()

    out = history.copy()
    out["Lender Strain"] = pd.to_numeric(
        out["Lender Strain"], errors="coerce"
    )
    if "Lender Strain Version" in out.columns:
        out["Lender Strain Version"] = out[
            "Lender Strain Version"
        ].astype("string")
    else:
        out["Lender Strain Version"] = pd.Series(
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

def load_business_loan_delinquency_history(path=None):
    frame = _load_csv(
        path or DEFAULT_BUSINESS_DELINQUENCY_PATH,
        ["Date", "Business Loan Delinquency Rate (%)"],
    )
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame["Business Loan Delinquency Rate (%)"] = pd.to_numeric(
        frame["Business Loan Delinquency Rate (%)"], errors="coerce"
    )
    frame = frame.dropna(
        subset=["Date", "Business Loan Delinquency Rate (%)"]
    )
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
    numeric_columns = ["Portfolio Cost ($mm)", "Nonaccrual at Cost (%)", *BDC_OPTIONAL_METRICS]
    for column in numeric_columns:
        if column not in frame.columns:
            frame[column] = np.nan
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame[
        frame["Ticker"].ne("")
        & frame["Date"].notna()
        & frame["Portfolio Cost ($mm)"].gt(0)
        & frame["Nonaccrual at Cost (%)"].notna()
    ].copy()

    rows = []
    for observation_date, group in frame.groupby("Date", sort=True):
        total_cost = float(group["Portfolio Cost ($mm)"].sum())
        row = {
            "Date": observation_date,
            "Portfolio Cost ($mm)": total_cost,
            "Observations": int(group["Ticker"].nunique()),
            "Cohort": ", ".join(sorted(group["Ticker"].unique())),
        }
        metric_map = {
            "Nonaccrual at Cost (%)": "Weighted Nonaccrual at Cost (%)",
            "Nonaccrual at Fair Value (%)": "Weighted Nonaccrual at Fair Value (%)",
            "PIK Income Share (%)": "Weighted PIK Income Share (%)",
            "NAV Change (%)": "Weighted NAV Change (%)",
            "Net Losses / Portfolio (%)": "Weighted Net Losses / Portfolio (%)",
            "Debt to Equity (x)": "Weighted Debt to Equity (x)",
        }
        metric_coverage = {}
        for source_column, output_column in metric_map.items():
            available = group[source_column].notna()
            covered_cost = float(group.loc[available, "Portfolio Cost ($mm)"].sum())
            if covered_cost > 0:
                row[output_column] = float(
                    (group.loc[available, "Portfolio Cost ($mm)"] * group.loc[available, source_column]).sum()
                    / covered_cost
                )
            else:
                row[output_column] = np.nan
            metric_coverage[source_column] = {
                "observations": int(group.loc[available, "Ticker"].nunique()),
                "portfolio_cost_mm": covered_cost,
                "portfolio_share": covered_cost / total_cost if total_cost > 0 else np.nan,
            }
        urls = sorted({
            str(value).strip()
            for value in group.get("Source URL", pd.Series(dtype=object)).dropna()
            if str(value).strip()
        })
        row["Source URL"] = " | ".join(urls)
        row["Metric Coverage"] = metric_coverage
        rows.append(row)

    columns = [
        "Date", "Weighted Nonaccrual at Cost (%)", "Weighted Nonaccrual at Fair Value (%)",
        "Weighted PIK Income Share (%)", "Weighted NAV Change (%)",
        "Weighted Net Losses / Portfolio (%)", "Weighted Debt to Equity (x)",
        "Portfolio Cost ($mm)", "Observations", "Cohort", "Source URL", "Metric Coverage",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values("Date", kind="stable").reset_index(drop=True)

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
    higher_is_adverse=True,
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
        score = percentile if higher_is_adverse else 100.0 - percentile
        return float(np.clip(score, 0, 100)), "Historical Percentile", len(distinct)

    anchored = tanh_score(value, center=center, scale=scale)
    if not higher_is_adverse and pd.notna(anchored):
        anchored = 100.0 - anchored
    return anchored, "Anchored Tanh", len(distinct)

def _channel_score(base_scores, component_names):
    values = {
        name: pd.to_numeric(base_scores.get(name), errors="coerce")
        for name in component_names
    }
    valid = {
        name: float(value)
        for name, value in values.items()
        if pd.notna(value) and np.isfinite(value)
    }
    if len(valid) != len(component_names):
        return np.nan, {}
    weights = {name: 1.0 / len(component_names) for name in component_names}
    score = sum(valid[name] * weights[name] for name in component_names)
    return float(score), weights

def _row_number(row, column):
    if row is None:
        return np.nan
    return pd.to_numeric(row.get(column), errors="coerce")


def _history_values(frame, column, cutoff):
    if frame is None or frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    eligible = frame
    if pd.notna(cutoff) and "Date" in frame.columns:
        eligible = frame.loc[frame["Date"] <= cutoff]
    return eligible[column]


def _normalized_score(raw, history, column, cutoff, *, higher_is_adverse, center, scale):
    score, method, observations = _historical_or_anchored_score(
        raw,
        _history_values(history, column, cutoff),
        higher_is_adverse=higher_is_adverse,
        center=center,
        scale=scale,
    )
    return score, {
        "method": method,
        "history_observations": observations,
    }


def _score_snapshot(
    bank_row=None,
    bank_capital_row=None,
    bdc_row=None,
    pe_row=None,
    *,
    business_delinquency_row=None,
    bank_history=None,
    bank_capital_history=None,
    bdc_history=None,
    business_delinquency_history=None,
    pe_history=None,
    observation_date=None,
):
    direct_bdc_value = _row_number(bdc_row, "Weighted Nonaccrual at Cost (%)")
    bridge_value = _row_number(
        business_delinquency_row, "Business Loan Delinquency Rate (%)"
    )
    use_direct_bdc = pd.notna(direct_bdc_value) and np.isfinite(direct_bdc_value)
    private_credit_mode = (
        "Direct listed-BDC nonaccrual panel"
        if use_direct_bdc
        else (
            "Federal Reserve business-loan delinquency bridge"
            if pd.notna(bridge_value) and np.isfinite(bridge_value)
            else "Unavailable"
        )
    )
    raw = {
        "bank": _row_number(bank_row, "Tightening Percent"),
        "bank_capital": _row_number(bank_capital_row, "Tier 1 Capital Ratio (%)"),
        "private_credit": direct_bdc_value if use_direct_bdc else bridge_value,
        "pe_high_leverage": _row_number(pe_row, "High-Leverage Portfolio Share (%)"),
        "pe_pik": _row_number(pe_row, "PIK Mean (%)"),
    }
    cutoff = pd.to_datetime(observation_date, errors="coerce")

    bank_score, bank_normalization = _normalized_score(
        raw["bank"],
        bank_history,
        "Tightening Percent",
        cutoff,
        higher_is_adverse=True,
        center=0.0,
        scale=35.0,
    )
    bank_capital_score, bank_capital_normalization = _normalized_score(
        raw["bank_capital"],
        bank_capital_history,
        "Tier 1 Capital Ratio (%)",
        cutoff,
        higher_is_adverse=False,
        center=12.5,
        scale=4.0,
    )
    if use_direct_bdc:
        private_credit_score, private_credit_normalization = _normalized_score(
            raw["private_credit"],
            bdc_history,
            "Weighted Nonaccrual at Cost (%)",
            cutoff,
            higher_is_adverse=True,
            center=2.0,
            scale=2.5,
        )
    else:
        private_credit_score, private_credit_normalization = _normalized_score(
            raw["private_credit"],
            business_delinquency_history,
            "Business Loan Delinquency Rate (%)",
            cutoff,
            higher_is_adverse=True,
            center=1.5,
            scale=1.0,
        )
    private_credit_normalization = {
        **private_credit_normalization,
        "evidence_mode": private_credit_mode,
    }
    pe_high_score, pe_high_normalization = _normalized_score(
        raw["pe_high_leverage"],
        pe_history,
        "High-Leverage Portfolio Share (%)",
        cutoff,
        higher_is_adverse=True,
        center=30.0,
        scale=12.0,
    )
    pe_pik_score, pe_pik_normalization = _normalized_score(
        raw["pe_pik"],
        pe_history,
        "PIK Mean (%)",
        cutoff,
        higher_is_adverse=True,
        center=18.0,
        scale=10.0,
    )

    base_scores = {
        "Bank Credit Tightening": bank_score,
        "Bank Capital Strain": bank_capital_score,
        "Private Credit Impairment": private_credit_score,
    }
    pe_subscores = {
        "High-Leverage Portfolio Share": pe_high_score,
        "PIK Burden": pe_pik_score,
    }
    base_scores["PE Portfolio Financing Strain"] = weighted_available_score(
        pe_subscores,
        PE_SUBWEIGHTS,
        min_components=2,
    )["score"]

    bank_channel, _ = _channel_score(base_scores, BANK_CHANNEL_COMPONENTS)
    nonbank_channel, _ = _channel_score(base_scores, NONBANK_CHANNEL_COMPONENTS)
    valid_components = int(
        sum(pd.notna(score) and np.isfinite(score) for score in base_scores.values())
    )
    combined_score = (
        float(
            sum(
                float(base_scores[name]) * weight
                for name, weight in LENDER_STRAIN_WEIGHTS.items()
            )
        )
        if valid_components >= MIN_LENDER_COMPONENTS
        else np.nan
    )
    normalized_weights = dict(LENDER_STRAIN_WEIGHTS) if pd.notna(combined_score) else {}
    signed_scores = {
        name: lender_strain_to_signed(score)
        for name, score in base_scores.items()
    }

    return {
        "score": lender_strain_to_signed(combined_score),
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
            "Bank Credit Tightening": bank_normalization,
            "Bank Capital Strain": bank_capital_normalization,
            "Private Credit Impairment": private_credit_normalization,
            "High-Leverage Portfolio Share": pe_high_normalization,
            "PIK Burden": pe_pik_normalization,
        },
        "raw": raw,
        "private_credit_mode": private_credit_mode,
    }

def build_lender_strain_history(
    bank_history,
    bank_capital_history,
    bdc_history,
    business_delinquency_history,
    pe_history,
):
    date_series = [
        frame["Date"]
        for frame in (
            bank_history,
            bank_capital_history,
            bdc_history,
            business_delinquency_history,
            pe_history,
        )
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
        business_delinquency_row = _asof_row(
            business_delinquency_history, observation_date
        )
        pe_row = _asof_row(pe_history, observation_date)
        snapshot = _score_snapshot(
            bank_row,
            bank_capital_row,
            bdc_row,
            pe_row,
            business_delinquency_row=business_delinquency_row,
            bank_history=bank_history,
            bank_capital_history=bank_capital_history,
            bdc_history=bdc_history,
            business_delinquency_history=business_delinquency_history,
            pe_history=pe_history,
            observation_date=observation_date,
        )

        if pd.isna(snapshot["score"]):
            continue

        rows.append(
            {
                "Date": pd.Timestamp(observation_date),
                "Lender Strain": snapshot["score"],
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
                "Private Credit Evidence": snapshot.get(
                    "private_credit_mode", "Unavailable"
                ),
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


def _component_payload(
    snapshot,
    name,
    *,
    raw_key,
    row,
    observations,
    source,
    source_url,
    normalization=None,
    secondary_raw_key=None,
    extras=None,
):
    payload = {"raw": snapshot["raw"][raw_key]}
    if secondary_raw_key:
        payload["secondary_raw"] = snapshot["raw"][secondary_raw_key]
    payload.update({
        "score": snapshot["signed_scores"].get(name, np.nan),
        "base_score": snapshot["base_scores"].get(name, np.nan),
        "weight": LENDER_STRAIN_WEIGHTS[name],
        "active_weight": snapshot["normalized_weights"].get(name, np.nan),
        "normalization": (
            snapshot["normalization"].get(name, {})
            if normalization is None
            else normalization
        ),
        "observations": int(observations),
        "as_of": _row_date(row),
        "source": source,
        "source_url": source_url,
    })
    payload.update(extras or {})
    return payload

def calculate_lender_strain(
    fred_data=None,
    *,
    bank_path=None,
    bank_capital_path=None,
    bdc_path=None,
    business_delinquency_path=None,
    pe_path=None,
) -> dict:
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
    business_delinquency_history = load_business_loan_delinquency_history(
        business_delinquency_path
    )
    business_delinquency_history = _with_live_observation(
        business_delinquency_history,
        _fred_observation(
            fred_data,
            "Business Loan Delinquency",
            "Business Loan Delinquency Rate (%)",
            "https://fred.stlouisfed.org/series/DRBLACBS",
        ),
    )
    pe_history = load_pe_financing_history(pe_path)

    history = build_lender_strain_history(
        bank_history,
        bank_capital_history,
        bdc_history,
        business_delinquency_history,
        pe_history,
    )

    latest_date_candidates = [
        frame["Date"].max()
        for frame in (
            bank_history,
            bank_capital_history,
            bdc_history,
            business_delinquency_history,
            pe_history,
        )
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
    business_delinquency_row = (
        _asof_row(business_delinquency_history, latest_date)
        if pd.notna(latest_date)
        else None
    )
    pe_row = _asof_row(pe_history, latest_date) if pd.notna(latest_date) else None
    snapshot = _score_snapshot(
        bank_row,
        bank_capital_row,
        bdc_row,
        pe_row,
        business_delinquency_row=business_delinquency_row,
        bank_history=bank_history,
        bank_capital_history=bank_capital_history,
        bdc_history=bdc_history,
        business_delinquency_history=business_delinquency_history,
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

    bank_url = "https://fred.stlouisfed.org/series/SUBLPDMBSXWBNQ"
    bank_capital_url = "https://fred.stlouisfed.org/series/BOGZ1FL010000016Q"
    components = {
        "Bank Credit Tightening": _component_payload(
            snapshot,
            "Bank Credit Tightening",
            raw_key="bank",
            row=bank_row,
            observations=1 if bank_row is not None else 0,
            source=bank_source,
            source_url=bank_row.get("Source_URL", bank_url) if bank_row is not None else bank_url,
        ),
        "Bank Capital Strain": _component_payload(
            snapshot,
            "Bank Capital Strain",
            raw_key="bank_capital",
            row=bank_capital_row,
            observations=1 if bank_capital_row is not None else 0,
            source=bank_capital_source,
            source_url=(
                bank_capital_row.get("Source_URL", bank_capital_url)
                if bank_capital_row is not None
                else bank_capital_url
            ),
        ),
        "Private Credit Impairment": _component_payload(
            snapshot,
            "Private Credit Impairment",
            raw_key="private_credit",
            row=bdc_row,
            observations=int(bdc_row.get("Observations", 0)) if bdc_row is not None else 0,
            source=bdc_source,
            source_url=bdc_row.get("Source URL", "") if bdc_row is not None else "",
            extras={
                "cohort": bdc_row.get("Cohort", "") if bdc_row is not None else "",
                "portfolio_cost_mm": bdc_row.get("Portfolio Cost ($mm)", np.nan) if bdc_row is not None else np.nan,
                "metric_coverage": bdc_row.get("Metric Coverage", {}) if bdc_row is not None else {},
                "nonaccrual_fair_value": bdc_row.get("Weighted Nonaccrual at Fair Value (%)", np.nan) if bdc_row is not None else np.nan,
                "pik_income_share": bdc_row.get("Weighted PIK Income Share (%)", np.nan) if bdc_row is not None else np.nan,
                "nav_change": bdc_row.get("Weighted NAV Change (%)", np.nan) if bdc_row is not None else np.nan,
                "net_losses_portfolio": bdc_row.get("Weighted Net Losses / Portfolio (%)", np.nan) if bdc_row is not None else np.nan,
                "debt_to_equity": bdc_row.get("Weighted Debt to Equity (x)", np.nan) if bdc_row is not None else np.nan,
                "panel_history": bdc_history.copy(),
                "historical_bridge": business_delinquency_history.copy(),
                "evidence_mode": snapshot.get("private_credit_mode", "Unavailable"),
            },
        ),
        "PE Portfolio Financing Strain": _component_payload(
            snapshot,
            "PE Portfolio Financing Strain",
            raw_key="pe_high_leverage",
            secondary_raw_key="pe_pik",
            row=pe_row,
            observations=1 if pe_row is not None else 0,
            source=pe_source,
            source_url=pe_row.get("Source URL", "") if pe_row is not None else "",
            normalization={
                "High-Leverage Portfolio Share": snapshot["normalization"].get(
                    "High-Leverage Portfolio Share", {}
                ),
                "PIK Burden": snapshot["normalization"].get("PIK Burden", {}),
            },
            extras={
                "reported_assets_bn": (
                    pe_row.get("Reported CPC Gross Assets ($bn)", np.nan)
                    if pe_row is not None
                    else np.nan
                ),
            },
        ),
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
        "history_contract": {
            "display_years": 10,
            "bridge_series": "DRBLACBS",
            "bridge_label": "Federal Reserve business-loan delinquency",
            "direct_panel_start": (
                bdc_history["Date"].min().date().isoformat()
                if not bdc_history.empty
                else None
            ),
        },
    }
