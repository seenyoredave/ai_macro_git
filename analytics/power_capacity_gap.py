"""Power Capacity Gap engine.

The metric compares observable AI deployment pressure with a national proxy for
power-system response. It is deliberately distinct from Power Stress: the gap
asks whether deployment is moving faster than measured power delivery and
capacity expansion, while Power Stress asks how strained the system appears
relative to reference conditions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.scoring import tanh_score, weighted_available_score


POWER_CAPACITY_GAP_VERSION = "1.0"

DEPLOYMENT_PRESSURE_WEIGHTS = {
    "Data Center Construction": 0.60,
    "Capital Deployment": 0.40,
}

POWER_RESPONSE_WEIGHTS = {
    "Delivered Power Growth": 0.60,
    "Installed Capacity Growth": 0.40,
}


def _fred_value(fred_data, name):
    payload = (fred_data or {}).get(name, np.nan)
    value = payload.get("value", np.nan) if isinstance(payload, dict) else payload
    return pd.to_numeric(value, errors="coerce")


def calculate_power_capacity_gap(development_result, fred_data) -> dict:
    """Return deployment pressure minus measured national power response.

    Deployment pressure uses the two ADI pillars most directly associated with
    physical power demand: data-center construction and capital deployment.

    Power-system response blends actual electric-power output growth with
    installed capacity growth. Requiring both components reduces reliance on
    nameplate additions alone, although the result remains a national proxy and
    does not measure regional transmission, interconnection, or firm capacity.
    """
    development_components = (
        (development_result or {}).get("components", {}) or {}
    )
    deployment_scores = {
        name: pd.to_numeric(
            (development_components.get(name, {}) or {}).get("score", np.nan),
            errors="coerce",
        )
        for name in DEPLOYMENT_PRESSURE_WEIGHTS
    }
    deployment = weighted_available_score(
        deployment_scores,
        DEPLOYMENT_PRESSURE_WEIGHTS,
        min_components=2,
    )

    output_yoy = _fred_value(fred_data, "Electric Power Output YoY")
    capacity_yoy = _fred_value(fred_data, "Electric Power Capacity YoY")
    response_scores = {
        "Delivered Power Growth": tanh_score(
            output_yoy,
            center=0.01,
            scale=0.04,
        ),
        "Installed Capacity Growth": tanh_score(
            capacity_yoy,
            center=0.01,
            scale=0.03,
        ),
    }
    response = weighted_available_score(
        response_scores,
        POWER_RESPONSE_WEIGHTS,
        min_components=2,
    )

    deployment_score = pd.to_numeric(deployment.get("score"), errors="coerce")
    response_score = pd.to_numeric(response.get("score"), errors="coerce")
    gap = (
        float(np.clip(deployment_score - response_score, -100.0, 100.0))
        if pd.notna(deployment_score) and pd.notna(response_score)
        else np.nan
    )

    return {
        "score": gap,
        "deployment_pressure_score": deployment_score,
        "power_response_score": response_score,
        "valid_components": int(
            deployment.get("valid_components", 0)
            + response.get("valid_components", 0)
        ),
        "coverage": float(
            (
                deployment.get("valid_components", 0)
                + response.get("valid_components", 0)
            )
            / 4.0
        ),
        "components": {
            "Data Center Construction": {
                "raw": (
                    development_components.get("Data Center Construction", {}) or {}
                ).get("raw", np.nan),
                "score": deployment_scores["Data Center Construction"],
                "weight": DEPLOYMENT_PRESSURE_WEIGHTS["Data Center Construction"],
                "channel": "Deployment Pressure",
            },
            "Capital Deployment": {
                "raw": (
                    development_components.get("Capital Deployment", {}) or {}
                ).get("raw", np.nan),
                "score": deployment_scores["Capital Deployment"],
                "weight": DEPLOYMENT_PRESSURE_WEIGHTS["Capital Deployment"],
                "channel": "Deployment Pressure",
            },
            "Delivered Power Growth": {
                "raw": output_yoy,
                "score": response_scores["Delivered Power Growth"],
                "weight": POWER_RESPONSE_WEIGHTS["Delivered Power Growth"],
                "channel": "Power-System Response",
            },
            "Installed Capacity Growth": {
                "raw": capacity_yoy,
                "score": response_scores["Installed Capacity Growth"],
                "weight": POWER_RESPONSE_WEIGHTS["Installed Capacity Growth"],
                "channel": "Power-System Response",
            },
        },
    }
