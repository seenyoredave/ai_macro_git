"""AI Development Intensity (ADI) engine.

ADI measures observable physical and capital buildout. It does not claim to
measure broad productivity, social adoption, or an accounting-pure AI segment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score, weighted_available_score


ADI_WEIGHTS = {
    "Capital Deployment": 0.25,
    "Data Center Construction": 0.25,
    "Compute Supply Realization": 0.25,
    "Power Footprint": 0.25,
}

CAPITAL_DEPLOYMENT_SUBWEIGHTS = {
    "Aggregate CapEx Growth": 0.60,
    "CapEx / Operating Cash Flow": 0.40,
}

CONSTRUCTION_SUBWEIGHTS = {
    "Data Center Construction Growth": 0.70,
    "Data Center Share of Private Nonresidential": 0.30,
}

SUPPLY_SUBWEIGHTS = {
    "Aggregate Revenue Growth": 0.70,
    "Revenue Growth Breadth": 0.30,
}

CAPITAL_DEPLOYMENT_SECTORS = {
    "CLOUD_HYPERSCALERS",
    "DATA_CENTER_INFRASTRUCTURE",
    "POWER_GRID",
}

COMPUTE_SUPPLY_SECTORS = {
    "COMPUTE",
    "SEMICAP_EQUIPMENT",
    "DATA_AI_INFRASTRUCTURE",
    "DATA_CENTER_INFRASTRUCTURE",
}


def _unique_company_frame(sector_data, sectors):
    frames = []

    for sector in sectors:
        df = (sector_data or {}).get(sector)
        if df is None or df.empty:
            continue
        frames.append(df.copy())

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)

    if "Ticker" in combined.columns:
        combined["Ticker"] = combined["Ticker"].astype(str).str.upper().str.strip()
        combined = combined.drop_duplicates(subset=["Ticker"], keep="first")

    return combined


def aggregate_growth_ratio(df, value_col, growth_col, min_companies=3):
    """Reconstruct prior aggregate value and calculate ratio-of-sums growth."""
    if df is None or df.empty or value_col not in df or growth_col not in df:
        return np.nan, 0

    current = pd.to_numeric(df[value_col], errors="coerce")
    growth = pd.to_numeric(df[growth_col], errors="coerce")
    valid = (
        current.notna()
        & growth.notna()
        & np.isfinite(current)
        & np.isfinite(growth)
        & (current > 0)
        & (growth > -0.95)
    )

    valid_count = int(valid.sum())
    if valid_count < min_companies:
        return np.nan, valid_count

    current_sum = float(current.loc[valid].sum())
    prior_sum = float((current.loc[valid] / (1.0 + growth.loc[valid])).sum())

    if prior_sum <= 0:
        return np.nan, valid_count

    return (current_sum / prior_sum) - 1.0, valid_count


def aggregate_ratio(df, numerator, denominator, min_companies=3):
    if df is None or df.empty or numerator not in df or denominator not in df:
        return np.nan, 0

    num = pd.to_numeric(df[numerator], errors="coerce")
    den = pd.to_numeric(df[denominator], errors="coerce")
    valid = (
        num.notna()
        & den.notna()
        & np.isfinite(num)
        & np.isfinite(den)
        & (num >= 0)
        & (den > 0)
    )

    valid_count = int(valid.sum())
    if valid_count < min_companies:
        return np.nan, valid_count

    denominator_sum = float(den.loc[valid].sum())
    if denominator_sum <= 0:
        return np.nan, valid_count

    return float(num.loc[valid].sum()) / denominator_sum, valid_count


def growth_breadth(df, growth_col, min_companies=3):
    if df is None or df.empty or growth_col not in df:
        return np.nan, 0

    growth = (
        pd.to_numeric(df[growth_col], errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )

    if len(growth) < min_companies:
        return np.nan, int(len(growth))

    return float((growth > 0).mean()), int(len(growth))


def _subindex(scores, weights, min_components=1):
    return weighted_available_score(
        scores,
        weights,
        min_components=min_components,
    )


def calculate_ai_development_intensity(
    sector_data,
    construction_data=None,
    power_result=None,
) -> dict:
    """Calculate ADI using a fixed 3-of-4 top-level coverage rule."""
    capital_df = _unique_company_frame(sector_data, CAPITAL_DEPLOYMENT_SECTORS)
    supply_df = _unique_company_frame(sector_data, COMPUTE_SUPPLY_SECTORS)

    capex_growth, capex_growth_count = aggregate_growth_ratio(
        capital_df,
        "CapEx",
        "CapEx Growth",
    )
    capex_intensity, capex_intensity_count = aggregate_ratio(
        capital_df,
        "CapEx",
        "Operating Cash Flow",
    )

    capital_subscores = {
        "Aggregate CapEx Growth": tanh_score(capex_growth, center=0.10, scale=0.35),
        "CapEx / Operating Cash Flow": tanh_score(capex_intensity, center=0.35, scale=0.50),
    }
    capital_result = _subindex(
        capital_subscores,
        CAPITAL_DEPLOYMENT_SUBWEIGHTS,
        min_components=1,
    )

    construction_data = construction_data or {}
    construction_growth = pd.to_numeric(
        construction_data.get("yoy_growth", np.nan),
        errors="coerce",
    )
    construction_share = pd.to_numeric(
        construction_data.get("share_private_nonresidential", np.nan),
        errors="coerce",
    )

    construction_subscores = {
        "Data Center Construction Growth": tanh_score(
            construction_growth,
            center=0.05,
            scale=0.25,
        ),
        "Data Center Share of Private Nonresidential": tanh_score(
            construction_share,
            center=0.07,
            scale=0.06,
        ),
    }
    construction_result = _subindex(
        construction_subscores,
        CONSTRUCTION_SUBWEIGHTS,
        min_components=1,
    )

    supply_growth, supply_growth_count = aggregate_growth_ratio(
        supply_df,
        "Revenue",
        "Revenue Growth",
    )
    supply_breadth, supply_breadth_count = growth_breadth(
        supply_df,
        "Revenue Growth",
    )

    supply_subscores = {
        "Aggregate Revenue Growth": tanh_score(supply_growth, center=0.05, scale=0.20),
        "Revenue Growth Breadth": tanh_score(supply_breadth, center=0.50, scale=0.35),
    }
    supply_result = _subindex(
        supply_subscores,
        SUPPLY_SUBWEIGHTS,
        min_components=1,
    )

    power_score = pd.to_numeric(
        (power_result or {}).get("footprint_score", np.nan),
        errors="coerce",
    )

    scores = {
        "Capital Deployment": capital_result["score"],
        "Data Center Construction": construction_result["score"],
        "Compute Supply Realization": supply_result["score"],
        "Power Footprint": power_score,
    }

    combined = weighted_available_score(
        scores,
        ADI_WEIGHTS,
        min_components=3,
    )

    return {
        "score": combined["score"],
        "valid_components": combined["valid_components"],
        "coverage": combined["coverage"],
        "components": {
            "Capital Deployment": {
                "raw": capex_growth,
                "secondary_raw": capex_intensity,
                "score": scores["Capital Deployment"],
                "weight": ADI_WEIGHTS["Capital Deployment"],
                "observations": max(capex_growth_count, capex_intensity_count),
                "subcomponents": {
                    "Aggregate CapEx Growth": {
                        "raw": capex_growth,
                        "score": capital_subscores["Aggregate CapEx Growth"],
                        "observations": capex_growth_count,
                    },
                    "CapEx / Operating Cash Flow": {
                        "raw": capex_intensity,
                        "score": capital_subscores["CapEx / Operating Cash Flow"],
                        "observations": capex_intensity_count,
                    },
                },
            },
            "Data Center Construction": {
                "raw": construction_growth,
                "secondary_raw": construction_share,
                "score": scores["Data Center Construction"],
                "weight": ADI_WEIGHTS["Data Center Construction"],
                "observations": 1 if pd.notna(construction_growth) or pd.notna(construction_share) else 0,
                "date": construction_data.get("date"),
                "source": construction_data.get("source"),
                "subcomponents": {
                    "Data Center Construction Growth": {
                        "raw": construction_growth,
                        "score": construction_subscores["Data Center Construction Growth"],
                    },
                    "Data Center Share of Private Nonresidential": {
                        "raw": construction_share,
                        "score": construction_subscores[
                            "Data Center Share of Private Nonresidential"
                        ],
                    },
                },
            },
            "Compute Supply Realization": {
                "raw": supply_growth,
                "secondary_raw": supply_breadth,
                "score": scores["Compute Supply Realization"],
                "weight": ADI_WEIGHTS["Compute Supply Realization"],
                "observations": max(supply_growth_count, supply_breadth_count),
                "subcomponents": {
                    "Aggregate Revenue Growth": {
                        "raw": supply_growth,
                        "score": supply_subscores["Aggregate Revenue Growth"],
                        "observations": supply_growth_count,
                    },
                    "Revenue Growth Breadth": {
                        "raw": supply_breadth,
                        "score": supply_subscores["Revenue Growth Breadth"],
                        "observations": supply_breadth_count,
                    },
                },
            },
            "Power Footprint": {
                "raw": power_score,
                "score": scores["Power Footprint"],
                "weight": ADI_WEIGHTS["Power Footprint"],
                "observations": (power_result or {}).get(
                    "footprint_valid_components", 0
                ),
                "subcomponents": (power_result or {}).get(
                    "footprint_components", {}
                ),
            },
        },
    }
