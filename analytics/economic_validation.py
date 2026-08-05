from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.development_engine import aggregate_growth_ratio
from analytics.scoring import tanh_score

DOWNSTREAM_SECTORS = (
    "CLOUD_HYPERSCALERS",
    "ENTERPRISE_AI_SOFTWARE",
)
MIN_COMPANIES = 5
VALIDATION_WEIGHTS = {
    "Revenue Validation": 0.65,
    "Cash-Margin Validation": 0.35,
}


def _downstream_frame(sector_data, sectors=DOWNSTREAM_SECTORS) -> pd.DataFrame:
    frames = [
        frame.copy()
        for name in sectors
        for frame in [(sector_data or {}).get(name)]
        if isinstance(frame, pd.DataFrame) and not frame.empty
    ]
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if "Ticker" not in combined:
        return pd.DataFrame()
    combined["Ticker"] = combined["Ticker"].astype(str).str.upper().str.strip()
    return combined.drop_duplicates(subset=["Ticker"], keep="first")


def _revenue_weighted_mean(
    frame: pd.DataFrame,
    value_column: str,
    *,
    min_companies=MIN_COMPANIES,
):
    if frame.empty or value_column not in frame or "Revenue" not in frame:
        return np.nan, 0
    values = pd.to_numeric(frame[value_column], errors="coerce")
    revenue = pd.to_numeric(frame["Revenue"], errors="coerce")
    valid = (
        values.notna()
        & revenue.notna()
        & np.isfinite(values)
        & np.isfinite(revenue)
        & revenue.gt(0)
    )
    count = int(valid.sum())
    if count < min_companies:
        return np.nan, count
    return float(np.average(values.loc[valid], weights=revenue.loc[valid])), count


def _fixed_tanh_score(value, *, center, scale):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value) or not np.isfinite(value):
        return np.nan
    return tanh_score(float(value), center=center, scale=scale)


def calculate_economic_validation_gap(
    sector_data,
    fred_data=None,
    *,
    deployment_result=None,
    sectors=DOWNSTREAM_SECTORS,
    **_unused,
):
    del fred_data
    frame = _downstream_frame(sector_data, sectors=sectors)
    deployment_score = pd.to_numeric(
        (deployment_result or {}).get("score"), errors="coerce"
    )
    if frame.empty or pd.isna(deployment_score):
        return {"score": np.nan, "components": {}, "valid_components": 0}

    revenue_growth, revenue_count = aggregate_growth_ratio(
        frame,
        "Revenue",
        "Revenue Growth",
        min_companies=MIN_COMPANIES,
    )
    cash_margin_change, cash_margin_count = _revenue_weighted_mean(
        frame,
        "FCF Margin YoY Change",
    )

    # Fixed, versioned transforms avoid switching between percentile and
    # anchored regimes as the archive grows.
    revenue_score = _fixed_tanh_score(
        revenue_growth,
        center=0.08,
        scale=0.20,
    )
    cash_margin_score = _fixed_tanh_score(
        cash_margin_change,
        center=0.00,
        scale=0.08,
    )
    validation_inputs = {
        "Revenue Validation": revenue_score,
        "Cash-Margin Validation": cash_margin_score,
    }
    validation_score = (
        float(
            sum(
                validation_inputs[name] * weight
                for name, weight in VALIDATION_WEIGHTS.items()
            )
        )
        if all(pd.notna(value) for value in validation_inputs.values())
        else np.nan
    )
    score = (
        float(np.clip(float(deployment_score) - validation_score, -100, 100))
        if pd.notna(validation_score)
        else np.nan
    )

    return {
        "score": score,
        "deployment_score": float(deployment_score),
        "validation_score": validation_score,
        "valid_components": int(
            sum(
                pd.notna(value)
                for value in (deployment_score, revenue_score, cash_margin_score)
            )
        ),
        "cohort": list(sectors),
        "components": {
            "Observable Deployment": {
                "raw": float(deployment_score),
                "score": float(deployment_score),
                "observations": int((deployment_result or {}).get("valid_components", 0)),
                "normalization": "AI Development Intensity",
                "history_observations": np.nan,
            },
            "Revenue Validation": {
                "raw": revenue_growth,
                "score": revenue_score,
                "weight": VALIDATION_WEIGHTS["Revenue Validation"],
                "observations": revenue_count,
                "normalization": "Fixed tanh: center 8%, scale 20%",
                "history_observations": np.nan,
            },
            "Cash-Margin Validation": {
                "raw": cash_margin_change,
                "score": cash_margin_score,
                "weight": VALIDATION_WEIGHTS["Cash-Margin Validation"],
                "observations": cash_margin_count,
                "normalization": "Fixed tanh: center 0 points, scale 8 points",
                "history_observations": np.nan,
            },
        },
    }
