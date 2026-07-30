"""Shared operating-earnings valuation calculations."""

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
    """Return a ratio-of-sums forward EBIT yield and coverage metadata.

    The earnings yield is ``sum(forward EBIT) / sum(enterprise value)`` across
    companies with positive enterprise value and a finite forward-EBIT estimate.
    Negative forward EBIT remains economically informative for the yield and is
    therefore retained. The reciprocal multiple is reported only when the
    aggregate yield is positive; otherwise EV/EBIT is not meaningful (NM).

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


def aggregate_signed_forward_ev_ebit(
    frame: pd.DataFrame,
    *,
    min_count: int = 5,
    min_coverage: float = 0.60,
) -> dict:
    """Aggregate signed forward EV/EBIT values for diagnostic analysis.

    This function is not used by the current sector valuation product;
    near-zero EBIT denominators make the signed weighted average unstable.

    Each company multiple is ``enterprise value / forward EBIT``. Negative
    forward EBIT therefore produces a negative multiple, which subtracts from
    positive-company contributions in the sector aggregate. Companies are not
    dropped merely because EBIT is negative.

    Effective Basket Weight is preferred, followed by Basket Weight; equal
    weights are used only when neither field exists. Coverage is the share of
    eligible weight represented by finite, nonzero-EBIT observations.
    """
    result = {
        "multiple": np.nan,
        "company_count": 0,
        "coverage": 0.0,
        "positive_contribution": 0.0,
        "negative_contribution": 0.0,
        "weight_column": "Equal Weight",
    }
    if frame is None or frame.empty:
        return result

    enterprise_value = pd.to_numeric(frame.get("Enterprise Value"), errors="coerce")
    forward_ebit = pd.to_numeric(frame.get("Forward EBIT"), errors="coerce")
    valid_base = (
        enterprise_value.notna()
        & np.isfinite(enterprise_value)
        & enterprise_value.gt(0)
        & forward_ebit.notna()
        & np.isfinite(forward_ebit)
        & forward_ebit.abs().gt(1e-9)
    )

    weight_column = next(
        (
            name
            for name in ("Effective Basket Weight", "Basket Weight")
            if name in frame.columns
        ),
        None,
    )
    if weight_column is None:
        weights = pd.Series(1.0, index=frame.index, dtype=float)
        eligible_weight = pd.Series(True, index=frame.index)
    else:
        weights = pd.to_numeric(frame[weight_column], errors="coerce")
        eligible_weight = weights.notna() & np.isfinite(weights) & weights.gt(0)
        result["weight_column"] = weight_column

    eligible = (
        enterprise_value.notna()
        & np.isfinite(enterprise_value)
        & enterprise_value.gt(0)
        & eligible_weight
    )
    valid = valid_base & eligible_weight
    count = int(valid.sum())
    total_weight = float(weights.loc[eligible].sum())
    covered_weight = float(weights.loc[valid].sum())
    coverage = covered_weight / total_weight if total_weight > 0 else 0.0
    result.update({"company_count": count, "coverage": float(coverage)})

    if count < int(min_count) or coverage < float(min_coverage) or covered_weight <= 0:
        return result

    multiples = enterprise_value.loc[valid] / forward_ebit.loc[valid]
    normalized_weights = weights.loc[valid] / covered_weight
    contributions = normalized_weights * multiples
    result["positive_contribution"] = float(contributions.where(contributions > 0, 0.0).sum())
    result["negative_contribution"] = float(contributions.where(contributions < 0, 0.0).sum())
    result["multiple"] = float(contributions.sum())
    return result


def aggregate_profitable_forward_ev_ebit(
    frame: pd.DataFrame,
    *,
    min_valid_count: int = 5,
    min_profitable_count: int = 3,
    min_coverage: float = 0.60,
) -> dict:
    """Return profitable-cohort EV/EBIT and loss-making enterprise-value share.

    The displayed multiple is a ratio of sums across companies with positive
    forward EBIT::

        sum(enterprise value) / sum(forward EBIT)

    Loss-making companies are not folded into that denominator. Their economic
    significance is retained separately as the share of valid sector enterprise
    value represented by companies with non-positive forward EBIT.

    Data coverage is the share of positive enterprise value with a finite
    forward-EBIT estimate. The multiple requires at least ``min_valid_count``
    valid observations, ``min_profitable_count`` profitable observations, and
    ``min_coverage`` enterprise-value data coverage.
    """
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
