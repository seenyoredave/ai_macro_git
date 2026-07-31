from __future__ import annotations

from io import BytesIO
from pathlib import Path
import importlib.util
import sys
import types

import numpy as np
import pandas as pd

from analytics.hhi_engine import adjusted_hhi, sector_basket_concentration
from analytics.macro_interpretation import build_macro_interpretation
from loaders.adaptation_loader import _ensure_expected_adoption_gap


ROOT = Path(__file__).resolve().parents[1]


def _load_energy_loader():
    streamlit = types.ModuleType("streamlit")
    streamlit.cache_data = lambda *args, **kwargs: (
        args[0] if args and callable(args[0]) else lambda function: function
    )
    previous = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(
            "energy_loader_v413_test", ROOT / "loaders" / "energy_loader.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous


def test_adjusted_hhi_is_comparable_across_basket_sizes():
    equal_four = sector_basket_concentration(
        pd.DataFrame({"Market Cap": [100, 100, 100, 100]})
    )
    equal_eight = sector_basket_concentration(
        pd.DataFrame({"Market Cap": [100] * 8})
    )
    concentrated = sector_basket_concentration(
        pd.DataFrame({"Market Cap": [970, 10, 10, 10]})
    )

    assert np.isclose(equal_four["adjusted_hhi"], 0.0)
    assert np.isclose(equal_eight["adjusted_hhi"], 0.0)
    assert concentrated["adjusted_hhi"] > 90
    assert adjusted_hhi(1.0, 4) == 100.0
    assert concentrated["effective_firms"] < 2


def test_sector_concentration_preserves_coverage_and_unknown_state():
    result = sector_basket_concentration(
        pd.DataFrame({"Market Cap": [100, np.nan, 50, 0]})
    )
    assert result["valid_company_count"] == 2
    assert result["total_company_count"] == 4
    assert result["coverage"] == 0.5
    assert pd.isna(result["adjusted_hhi"])


def test_eia_retail_price_parser_returns_commercial_and_industrial_history():
    loader = _load_energy_loader()
    raw = pd.DataFrame(
        [
            ["Electric Power Monthly", None, None, None],
            ["Period", "Residential", "Commercial", "Industrial"],
            ["Year 2025", None, None, None],
            ["May", 16.0, 12.93, 8.29],
            ["Year 2026", None, None, None],
            ["May", 16.8, 13.54, 8.71],
        ]
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        raw.to_excel(writer, index=False, header=False)

    parsed = loader.parse_eia_retail_price_workbook(buffer.getvalue())
    assert set(parsed["Series"]) == {
        "Commercial Electricity Price",
        "Industrial Electricity Price",
    }
    assert len(parsed) == 4
    latest = parsed.sort_values("Date").groupby("Series").tail(1).set_index("Series")
    assert latest.loc["Commercial Electricity Price", "Value"] == 13.54
    assert latest.loc["Industrial Electricity Price", "Value"] == 8.71


def test_bundled_energy_archive_contains_retail_price_contract():
    archive = pd.read_csv(ROOT / "archive" / "energy_history.csv")
    latest = archive.iloc[-1]
    assert latest["Version"] == 1.2
    for name in ("Commercial Electricity Price", "Industrial Electricity Price"):
        assert np.isfinite(float(latest[name]))
        assert latest[f"{name} Date"] == "2026-05-01"
        assert np.isfinite(float(latest[f"{name} Change"]))


def test_expected_adoption_gap_is_recomputed_from_components():
    frame = pd.DataFrame(
        {
            "Current AI Use": [21.5],
            "Expected AI Use": [24.3],
            "Expected Adoption Gap": [np.nan],
        }
    )
    repaired = _ensure_expected_adoption_gap(frame)
    assert np.isclose(repaired.iloc[0]["Expected Adoption Gap"], 2.8)


def test_snapshot_uses_new_categories_and_does_not_repeat_slow_annual_changes():
    regime = {
        "AI Equity Index": 60.0,
        "AI Development Intensity": 75.0,
        "Speculation Gap": -15.0,
        "Economic Validation Gap": -20.0,
        "Power Stress Index": -5.0,
        "Power Capacity Gap": 10.0,
        "Borrower Strain": 0.0,
        "Lender Strain": 0.0,
        "Deployment Funding Mix": {
            "current": {
                "internal_funding_coverage": 1.2,
                "cash_reserve_coverage_years": 1.1,
                "debt_financing_pulse": 0.0,
                "forward_commitment_load": 1.0,
            },
            "series": {},
        },
    }
    infrastructure = {
        "series": {
            "Data Center Construction": {
                "yoy_growth": 0.50,
                "date": "2026-06-01",
                "history": pd.DataFrame(
                    {"Date": pd.to_datetime(["2025-06-01", "2026-06-01"]), "Value": [20.0, 30.0]}
                ),
            }
        }
    }
    adaptation = {
        "current_use": 21.5,
        "expected_use": 24.3,
        "expected_adoption_gap": 2.8,
        "annual_change": np.nan,
        "snapshot_date": "2026-07-30",
        "national_history": pd.DataFrame(
            {
                "Date": pd.to_datetime(["2026-07-16", "2026-07-30"]),
                "Current AI Use": [20.5, 21.5],
            }
        ),
    }
    result = build_macro_interpretation(
        regime_metrics=regime,
        macro_history=pd.DataFrame(),
        infrastructure_data=infrastructure,
        adaptation_data=adaptation,
    )

    assert result["headline"] in {
        "Broad expansion",
        "Expansion continuing",
        "Expansion with emerging constraints",
    }
    assert result["expansion_factors"]
    assert not any("concentration" in item.lower() for item in result["constraint_factors"])
    assert any("business AI use" in item for item in result["changes"])
    assert not any("year over year" in item for item in result["changes"])


def test_snapshot_and_infrastructure_layout_contracts_are_structural():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    snapshot = renderer.split("def _render_macro_interpretation", 1)[1].split(
        "def _render_primary_macro_cards", 1
    )[0]
    assert snapshot.index('"Expansion"') < snapshot.index('"Constraints"')
    assert snapshot.index('"Constraints"') < snapshot.index('"This week"')
    assert "render_statline(" not in snapshot

    infrastructure = renderer.split("def render_infrastructure_tab", 1)[1].split(
        "def _energy_item", 1
    )[0]
    assert infrastructure.index('render_section("Buildout"') < infrastructure.index(
        "_render_infrastructure_construction(infrastructure_data)"
    )
    assert '"AI-linked construction"' not in infrastructure
    assert '"US Infrastructure Expenditure"' in infrastructure


def test_macro_card_chain_ends_with_business_adaptation():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    cards = renderer.split("def _render_primary_macro_cards", 1)[1].split(
        "def _render_gap_measures", 1
    )[0]
    assert '"Business Adaptation"' in cards
    assert '"Concentration HHI"' not in cards

def test_v4132_copy_registry_coverage_and_water_withholding_contracts():
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text(encoding="utf-8")

    assert (
        "market conditions • capital deployment • financing • infrastructure development • "
        "resource utilization • observable economic validation"
    ) in app
    assert "Overview of the AI economy using novel metrics to track the evolution." in renderer
    assert '("compute/electrical",' in renderer
    assert 'render_panel_heading("Data Center Registry", f"metric coverage: {valid:,}/{total:,} facility records")' in renderer
    assert "Selected metric coverage:" not in renderer
    assert 'render_section("Water availability"' not in renderer
    assert "load_water_context" not in app

