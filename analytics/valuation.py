from __future__ import annotations

import numpy as np
import pandas as pd

SECTOR_VALUATION_VERSION = "2.0"

def aggregate_forward_ebit_yield(
    frame: pd.DataFrame,
    *,
    min_count: int = 5,
    min_coverage: float = 0.60,
    coverage_weight_column: str | None = None,
) -> dict:
    result = {
        "yield": np.nan,
        "multiple": np.nan,
        "company_count": 0,
        "coverage": 0.0,
    }
    if frame is None or frame.empty:
        return result

    forward_ebit = pd.to_numeric(frame.get("Forward EBIT"), errors="coerce")
    enterprise_value = pd.to_numeric(frame.get("Enterprise Value"), errors="coerce")
    positive_ev = enterprise_value.notna() & np.isfinite(enterprise_value) & (enterprise_value > 0)
    valid = (
        positive_ev
        & forward_ebit.notna()
        & np.isfinite(forward_ebit)
    )
    count = int(valid.sum())

    if coverage_weight_column and coverage_weight_column in frame.columns:
        weights = pd.to_numeric(frame[coverage_weight_column], errors="coerce")
        eligible_weights = weights.where(positive_ev & weights.gt(0))
        total_weight = float(eligible_weights.sum(skipna=True))
        covered_weight = float(weights.where(valid & weights.gt(0)).sum(skipna=True))
        coverage = covered_weight / total_weight if total_weight > 0 else 0.0
    else:
        total_ev = float(enterprise_value.loc[positive_ev].sum())
        covered_ev = float(enterprise_value.loc[valid].sum())
        coverage = covered_ev / total_ev if total_ev > 0 else 0.0

    result.update({"company_count": count, "coverage": float(coverage)})

    if count < int(min_count) or coverage < float(min_coverage):
        return result

    covered_ev = float(enterprise_value.loc[valid].sum())
    covered_ebit = float(forward_ebit.loc[valid].sum())
    if covered_ev <= 0:
        return result

    yield_value = covered_ebit / covered_ev
    result["yield"] = float(yield_value)
    if yield_value > 0:
        result["multiple"] = float(1.0 / yield_value)
    return result

def aggregate_profitable_forward_ev_ebit(
    frame: pd.DataFrame,
    *,
    min_valid_count: int = 5,
    min_profitable_count: int = 3,
    min_coverage: float = 0.60,
) -> dict:
    result = {
        "multiple": np.nan,
        "valid_company_count": 0,
        "profitable_company_count": 0,
        "loss_making_company_count": 0,
        "data_coverage": 0.0,
        "profitable_ev_share": np.nan,
        "loss_making_ev_share": np.nan,
        "profitable_enterprise_value": np.nan,
        "profitable_forward_ebit": np.nan,
        "loss_making_enterprise_value": np.nan,
    }
    if frame is None or frame.empty:
        return result

    enterprise_value = pd.to_numeric(frame.get("Enterprise Value"), errors="coerce")
    forward_ebit = pd.to_numeric(frame.get("Forward EBIT"), errors="coerce")

    eligible = (
        enterprise_value.notna()
        & np.isfinite(enterprise_value)
        & enterprise_value.gt(0)
    )
    valid = (
        eligible
        & forward_ebit.notna()
        & np.isfinite(forward_ebit)
    )
    profitable = valid & forward_ebit.gt(0)
    loss_making = valid & forward_ebit.le(0)

    total_eligible_ev = float(enterprise_value.loc[eligible].sum())
    valid_ev = float(enterprise_value.loc[valid].sum())
    data_coverage = valid_ev / total_eligible_ev if total_eligible_ev > 0 else 0.0

    profitable_ev = float(enterprise_value.loc[profitable].sum())
    profitable_ebit = float(forward_ebit.loc[profitable].sum())
    loss_making_ev = float(enterprise_value.loc[loss_making].sum())

    profitable_share = profitable_ev / valid_ev if valid_ev > 0 else np.nan
    loss_share = loss_making_ev / valid_ev if valid_ev > 0 else np.nan

    result.update(
        {
            "valid_company_count": int(valid.sum()),
            "profitable_company_count": int(profitable.sum()),
            "loss_making_company_count": int(loss_making.sum()),
            "data_coverage": float(data_coverage),
            "profitable_ev_share": float(profitable_share) if pd.notna(profitable_share) else np.nan,
            "loss_making_ev_share": float(loss_share) if pd.notna(loss_share) else np.nan,
            "profitable_enterprise_value": profitable_ev,
            "profitable_forward_ebit": profitable_ebit,
            "loss_making_enterprise_value": loss_making_ev,
        }
    )

    if (
        int(valid.sum()) < int(min_valid_count)
        or int(profitable.sum()) < int(min_profitable_count)
        or data_coverage < float(min_coverage)
        or profitable_ev <= 0
        or profitable_ebit <= 0
    ):
        return result

    result["multiple"] = float(profitable_ev / profitable_ebit)
    return result
