"""Shared static scoring helpers.

The dashboard intentionally uses explicit, reproducible weights. Missing inputs
are omitted only when the caller's minimum-component contract is satisfied;
remaining weights are then renormalized over the valid components.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd


def finite_number(value) -> float:
    """Return a finite float or NaN."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return np.nan

    return number if np.isfinite(number) else np.nan


def tanh_score(value, *, center=0.0, scale=1.0) -> float:
    """Map a raw value to 0-100 with a soft cap and a fixed neutral center."""
    value = finite_number(value)
    center = finite_number(center)
    scale = finite_number(scale)

    if pd.isna(value) or pd.isna(center) or pd.isna(scale) or scale <= 0:
        return np.nan

    return float(np.clip(50.0 + 50.0 * np.tanh((value - center) / scale), 0, 100))


def weighted_available_score(
    scores: Mapping[str, float],
    weights: Mapping[str, float],
    *,
    min_components: int,
) -> dict:
    """Combine valid component scores using fixed weights.

    Data contract:
      - scores are expected on a 0-100 scale;
      - invalid or non-finite values are missing, never zero;
      - at least ``min_components`` must be valid;
      - fixed weights are renormalized across valid components only.
    """
    valid = {}

    for name, raw_score in scores.items():
        score = finite_number(raw_score)
        weight = finite_number(weights.get(name, 0.0))

        if pd.isna(score) or pd.isna(weight) or weight <= 0:
            continue

        valid[name] = {
            "score": float(np.clip(score, 0, 100)),
            "weight": weight,
        }

    if len(valid) < min_components:
        return {
            "score": np.nan,
            "valid_components": len(valid),
            "intended_components": len(scores),
            "coverage": len(valid) / len(scores) if scores else 0.0,
            "normalized_weights": {},
        }

    total_weight = sum(item["weight"] for item in valid.values())

    if total_weight <= 0:
        return {
            "score": np.nan,
            "valid_components": len(valid),
            "intended_components": len(scores),
            "coverage": len(valid) / len(scores) if scores else 0.0,
            "normalized_weights": {},
        }

    normalized_weights = {
        name: item["weight"] / total_weight
        for name, item in valid.items()
    }

    score = sum(
        valid[name]["score"] * normalized_weights[name]
        for name in valid
    )

    return {
        "score": float(np.clip(score, 0, 100)),
        "valid_components": len(valid),
        "intended_components": len(scores),
        "coverage": len(valid) / len(scores) if scores else 0.0,
        "normalized_weights": normalized_weights,
    }
