from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from analytics.development_engine import aggregate_growth_ratio
from analytics.scoring import tanh_score

PROJECT_ROOT = Path(__file__).resolve().parents[1]
YF_HISTORY_PATH = PROJECT_ROOT / "archive" / "yf_history.csv"
INFO_INVESTMENT_HISTORY_PATH = (
    PROJECT_ROOT / "data" / "info_processing_investment_history.csv"
)
TARGET_SECTOR = "ENTERPRISE_AI_SOFTWARE"
MIN_COMPANIES = 5
MIN_DISTINCT_HISTORY = 8

def _fred_payload_value(fred_data, key):
    payload = (fred_data or {}).get(key, np.nan)
    return payload.get("value", np.nan) if isinstance(payload, dict) else payload

def _empirical_or_anchored_score(value, history, *, center, scale):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan, "Unavailable", 0

    history = (
        pd.to_numeric(pd.Series(history, dtype=float), errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    distinct = np.sort(history.round(8).unique())
    if len(distinct) >= MIN_DISTINCT_HISTORY:
        below = float(np.sum(distinct < float(value)))
        equal = float(np.sum(distinct == round(float(value), 8)))
        percentile = 100.0 * (below + 0.5 * equal) / len(distinct)
        return float(np.clip(percentile, 0, 100)), "Empirical Percentile", len(distinct)

    return tanh_score(value, center=center, scale=scale), "Anchored Tanh", len(distinct)

def _company_growth_history(path=YF_HISTORY_PATH, sector=TARGET_SECTOR):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["Date", "CapEx Growth", "Revenue Growth"])

    try:
        frame = pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.DataFrame(columns=["Date", "CapEx Growth", "Revenue Growth"])
    required = {"Date", "Sector", "Ticker", "CapEx", "CapEx Growth", "Revenue", "Revenue Growth"}
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=["Date", "CapEx Growth", "Revenue Growth"])

    frame = frame[frame["Sector"].astype(str) == str(sector)].copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    frame = frame.dropna(subset=["Date", "Ticker"])
    rows = []
    for observation_date, group in frame.groupby("Date", sort=True):
        group = group.drop_duplicates(subset=["Ticker"], keep="last")
        capex_growth, capex_count = aggregate_growth_ratio(
            group, "CapEx", "CapEx Growth", min_companies=MIN_COMPANIES
        )
        revenue_growth, revenue_count = aggregate_growth_ratio(
            group, "Revenue", "Revenue Growth", min_companies=MIN_COMPANIES
        )
        rows.append(
            {
                "Date": observation_date,
                "CapEx Growth": capex_growth,
                "Revenue Growth": revenue_growth,
                "CapEx Companies": capex_count,
                "Revenue Companies": revenue_count,
            }
        )
    return pd.DataFrame(rows)

def _information_investment_growth_history(path=INFO_INVESTMENT_HISTORY_PATH):
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.Series(dtype=float)

    try:
        frame = pd.read_csv(path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError):
        return pd.Series(dtype=float)
    date_column = next(
        (name for name in ("Observation Date", "DATE", "Date") if name in frame.columns),
        None,
    )
    value_column = next(
        (
            name
            for name in ("Info Processing Investment Level", "A679RX1Q020SBEA")
            if name in frame.columns
        ),
        None,
    )
    if date_column is None or value_column is None:
        return pd.Series(dtype=float)

    frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce")
    frame[value_column] = pd.to_numeric(frame[value_column], errors="coerce")
    frame = frame.dropna(subset=[date_column, value_column]).sort_values(date_column)
    if frame.empty:
        return pd.Series(dtype=float)

    series = pd.Series(
        frame[value_column].to_numpy(dtype=float),
        index=pd.DatetimeIndex(frame[date_column]),
    )
    return series.pct_change(4).replace([np.inf, -np.inf], np.nan).dropna()

def calculate_economic_validation_gap(
    sector_data,
    fred_data,
    *,
    sector=TARGET_SECTOR,
    yf_history_path=YF_HISTORY_PATH,
    info_history_path=INFO_INVESTMENT_HISTORY_PATH,
):
    frame = (sector_data or {}).get(sector)
    if frame is None or frame.empty:
        return {"score": np.nan, "components": {}, "valid_components": 0}

    capex_growth, capex_count = aggregate_growth_ratio(
        frame, "CapEx", "CapEx Growth", min_companies=MIN_COMPANIES
    )
    revenue_growth, revenue_count = aggregate_growth_ratio(
        frame, "Revenue", "Revenue Growth", min_companies=MIN_COMPANIES
    )
    macro_growth = pd.to_numeric(
        _fred_payload_value(fred_data, "Info Processing Investment YoY"),
        errors="coerce",
    )

    company_history = _company_growth_history(yf_history_path, sector=sector)
    macro_history = _information_investment_growth_history(info_history_path)

    deployment_score, deployment_method, deployment_history_count = _empirical_or_anchored_score(
        capex_growth,
        company_history.get("CapEx Growth", pd.Series(dtype=float)),
        center=0.10,
        scale=0.35,
    )
    revenue_score, revenue_method, revenue_history_count = _empirical_or_anchored_score(
        revenue_growth,
        company_history.get("Revenue Growth", pd.Series(dtype=float)),
        center=0.08,
        scale=0.25,
    )
    macro_score, macro_method, macro_history_count = _empirical_or_anchored_score(
        macro_growth,
        macro_history,
        center=0.06,
        scale=0.12,
    )

    validation_inputs = [revenue_score, macro_score]
    valid_validation = [value for value in validation_inputs if pd.notna(value)]
    validation_score = (
        float(np.mean(valid_validation)) if len(valid_validation) == 2 else np.nan
    )
    score = (
        float(np.clip(deployment_score - validation_score, -100, 100))
        if pd.notna(deployment_score) and pd.notna(validation_score)
        else np.nan
    )

    return {
        "score": score,
        "deployment_score": deployment_score,
        "validation_score": validation_score,
        "valid_components": int(
            sum(pd.notna(value) for value in (deployment_score, revenue_score, macro_score))
        ),
        "components": {
            "Capital Deployment": {
                "raw": capex_growth,
                "score": deployment_score,
                "observations": capex_count,
                "normalization": deployment_method,
                "history_observations": deployment_history_count,
            },
            "Revenue Validation": {
                "raw": revenue_growth,
                "score": revenue_score,
                "observations": revenue_count,
                "normalization": revenue_method,
                "history_observations": revenue_history_count,
            },
            "Macro Investment Validation": {
                "raw": macro_growth,
                "score": macro_score,
                "observations": 1 if pd.notna(macro_growth) else 0,
                "normalization": macro_method,
                "history_observations": macro_history_count,
            },
        },
    }
