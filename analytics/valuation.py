"""Shared operating-earnings valuation calculations."""

from __future__ import annotations

import numpy as np
import pandas as pd


def aggregate_forward_ebit_yield(
    frame: pd.DataFrame,
    *,
    min_count: int = 5,
    min_coverage: float = 0.60,
    coverage_weight_column: str | None = None,
) -> dict:
    """Return a ratio-of-sums forward EBIT yield and coverage metadata.

    The valuation itself is always ``sum(forward EBIT) / sum(enterprise value)``.
    Coverage is measured by enterprise value unless an explicit portfolio-weight
    column is supplied, as with the benchmark proxy.
    """
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
        & (forward_ebit > 0)
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
    if covered_ev <= 0 or covered_ebit <= 0:
        return result

    yield_value = covered_ebit / covered_ev
    result["yield"] = float(yield_value)
    result["multiple"] = float(1.0 / yield_value)
    return result
