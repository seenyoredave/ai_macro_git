import json
from pathlib import Path

import numpy as np
import pandas as pd

from analytics.macro_interpretation import (
    MACRO_INTERPRETATION_VERSION,
    build_macro_interpretation,
)


ROOT = Path(__file__).resolve().parents[1]


def _history():
    return pd.DataFrame(
        {
            "Date": ["2026-07-28", "2026-07-29"],
            "AI Equity Index": [46.7, 45.2],
            "AI Development Intensity": [79.7, 80.3],
            "Economic Validation Gap": [-53.3, -53.3],
            "Power Stress Index": [-4.4, -4.4],
            "Power Capacity Gap": [11.0, 11.9],
            "Borrower Strain": [-0.2, 1.3],
            "Lender Strain": [-2.5, -1.5],
            "Concentration HHI": [21.0, 21.3],
            "Speculation Gap": [-33.0, -35.0],
            "AEI Version": ["3.1", "3.1"],
            "ADI Version": ["1.0", "1.0"],
            "EVG Version": ["2.0", "2.0"],
            "Power Stress Version": ["3.0", "3.0"],
            "Power Capacity Gap Version": ["1.0", "1.0"],
            "Borrower Strain Version": ["3.0", "3.0"],
            "Lender Strain Version": ["3.0", "3.0"],
        }
    )


def _regime():
    funding_history = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2025-12-31", "2026-07-30"]),
            "Value": [2.7, 3.0],
        }
    )
    return {
        "AI Equity Index": 44.0,
        "AI Development Intensity": 80.5,
        "Speculation Gap": -36.5,
        "Economic Validation Gap": -53.0,
        "Power Stress Index": -4.4,
        "Power Capacity Gap": 12.0,
        "Borrower Strain": 3.0,
        "Lender Strain": 0.5,
        "Concentration HHI": 21.5,
        "AEI Version": "3.1",
        "ADI Version": "1.0",
        "EVG Version": "2.0",
        "Power Stress Version": "3.0",
        "Power Capacity Gap Version": "1.0",
        "Borrower Strain Version": "3.0",
        "Lender Strain Version": "3.0",
        "Deployment Funding Mix": {
            "current": {
                "internal_funding_coverage": 1.45,
                "cash_reserve_coverage_years": 1.39,
                "debt_financing_pulse": 0.25,
                "forward_commitment_load": 3.0,
            },
            "series": {
                "forward_commitment_load": funding_history,
            },
        },
    }


def _debt_data():
    dates = pd.to_datetime(
        ["2026-06-26", "2026-07-03", "2026-07-10", "2026-07-17", "2026-07-24"]
    )
    values = {
        "Corporate Bond Market Distress": [0.16, 0.14, 0.17, 0.18, 0.20],
        "Investment-Grade Bond Distress": [0.25, 0.23, 0.30, 0.33, 0.35],
        "High-Yield Bond Distress": [0.08, 0.06, 0.11, 0.11, 0.12],
    }
    return {
        "series": {
            name: {
                "value": series[-1],
                "history": pd.DataFrame({"Date": dates, "Value": series}),
            }
            for name, series in values.items()
        }
    }


def _energy_data():
    return {
        "series": {
            "Natural Gas Price": {"change_pct": -10.0},
            "WTI Crude Oil": {"change_pct": 20.4},
        }
    }


def test_macro_interpretation_is_deterministic_sensitive_and_compact():
    kwargs = dict(
        regime_metrics=_regime(),
        macro_history=_history(),
        debt_markets_data=_debt_data(),
        energy_data=_energy_data(),
        fred_data={},
        nfci_history=pd.DataFrame(),
    )
    first = build_macro_interpretation(**kwargs)
    second = build_macro_interpretation(**kwargs)

    assert first == second
    assert first["version"] == MACRO_INTERPRETATION_VERSION
    assert first["headline"].startswith("Resilient")
    assert 1 <= len(first["pressure_factors"]) <= 3
    assert 1 <= len(first["resilience_factors"]) <= 3
    assert 1 <= len(first["changes"]) <= 3
    assert "Forward commitments" in " ".join(first["pressure_factors"])
    assert "WTI" in " ".join(first["pressure_factors"] + first["changes"])
    assert "cash" in first["summary"].lower() or "financeable" in first["summary"].lower()


def test_macro_interpretation_changes_when_funding_buffer_is_removed():
    regime = _regime()
    regime["Deployment Funding Mix"]["current"].update(
        {
            "internal_funding_coverage": 0.55,
            "cash_reserve_coverage_years": 0.35,
        }
    )
    result = build_macro_interpretation(
        regime_metrics=regime,
        macro_history=_history(),
        debt_markets_data=_debt_data(),
        energy_data=_energy_data(),
        fred_data={},
        nfci_history=pd.DataFrame(),
    )
    assert result["headline"] in {"Funding-constrained", "Broad deterioration"}
    assert any("covers only" in item or "less than one year" in item for item in result["pressure_factors"])


def test_macro_interpretation_archive_fields_are_written_by_macro_archiver():
    source = (ROOT / "archive" / "archive.py").read_text()
    archive_columns = pd.read_csv(ROOT / "archive" / "macro_history.csv", nrows=0).columns
    for field in (
        "Macro State",
        "Macro State Summary",
        "Macro Pressure Factors",
        "Macro Resilience Factors",
        "Macro Change Factors",
        "Macro Interpretation Confidence",
        "Macro Interpretation Version",
        "Macro Domain States",
    ):
        assert f'"{field}"' in source
        assert field in archive_columns
    assert "json.dumps" in source


def test_macro_current_state_is_rendered_before_regime_board():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    macro = source.split("def render_macro_tab", 1)[1].split("def _funding_specs", 1)[0]
    assert macro.index('render_section("Current state")') < macro.index('render_section("Regime board"')
    assert "_render_macro_interpretation(regime_metrics)" in macro
    assert "Partial source coverage" in source


def test_power_capacity_gap_uses_peer_statline_without_sparkline():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    block = source.split("def _render_grid_capacity", 1)[1].split("def _render_ai_energy_demand", 1)[0]
    assert '(\n                "Power Capacity Gap",' in block
    assert 'key_prefix="energy-grid-capacity"' in block
    assert 'key="energy-capacity-gap"' not in block
    assert "metric_card(" not in block
