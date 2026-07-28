import numpy as np
import pytest

from analytics.power_capacity_gap import calculate_power_capacity_gap
from analytics.scoring import tanh_score


def _development(construction=80.0, capital=60.0):
    return {
        "components": {
            "Data Center Construction": {"score": construction, "raw": 0.25},
            "Capital Deployment": {"score": capital, "raw": 0.18},
        }
    }


def _fred(output=0.05, capacity=0.04):
    return {
        "Electric Power Output YoY": {"value": output},
        "Electric Power Capacity YoY": {"value": capacity},
    }


def test_power_capacity_gap_compares_physical_deployment_with_measured_response():
    result = calculate_power_capacity_gap(_development(), _fred())

    expected_deployment = 0.60 * 80.0 + 0.40 * 60.0
    output_score = tanh_score(0.05, center=0.01, scale=0.04)
    capacity_score = tanh_score(0.04, center=0.01, scale=0.03)
    expected_response = 0.60 * output_score + 0.40 * capacity_score

    assert result["deployment_pressure_score"] == pytest.approx(expected_deployment)
    assert result["power_response_score"] == pytest.approx(expected_response)
    assert result["score"] == pytest.approx(expected_deployment - expected_response)
    assert result["valid_components"] == 4
    assert result["coverage"] == pytest.approx(1.0)


def test_power_capacity_gap_requires_both_deployment_and_both_response_components():
    missing_deployment = calculate_power_capacity_gap(
        _development(construction=np.nan),
        _fred(),
    )
    missing_response = calculate_power_capacity_gap(
        _development(),
        _fred(capacity=np.nan),
    )

    assert np.isnan(missing_deployment["score"])
    assert np.isnan(missing_response["score"])


def test_power_capacity_gap_preserves_channel_labels_and_raw_inputs():
    result = calculate_power_capacity_gap(_development(), _fred())
    components = result["components"]

    assert components["Data Center Construction"]["channel"] == "Deployment Pressure"
    assert components["Delivered Power Growth"]["channel"] == "Power-System Response"
    assert components["Delivered Power Growth"]["raw"] == pytest.approx(0.05)
    assert components["Installed Capacity Growth"]["raw"] == pytest.approx(0.04)
