from __future__ import annotations

from io import BytesIO
import importlib.util
import sys
import types
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


class _CacheData:
    def __call__(self, *args, **kwargs):
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return lambda function: function


def _load_module(relative_path: str, name: str):
    streamlit = types.ModuleType("streamlit")
    streamlit.cache_data = _CacheData()
    old_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = streamlit
    try:
        spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module
    finally:
        if old_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = old_streamlit


def _construction_workbook(sheet: str, frame: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, sheet_name=sheet, startrow=3, index=False)
    return buffer.getvalue()


def _btos_workbook(estimates: pd.DataFrame, errors: pd.DataFrame) -> bytes:
    dates = pd.DataFrame(
        {
            "Smpdt": [202515, 202615],
            "Publication Date": [pd.Timestamp("2025-07-31"), pd.Timestamp("2026-07-30")],
        }
    )
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        estimates.to_excel(writer, sheet_name="Response Estimates", index=False)
        errors.to_excel(writer, sheet_name="Response Standard Errors", index=False)
        dates.to_excel(writer, sheet_name="Collection and Reference Dates", index=False)
    return buffer.getvalue()


def test_infrastructure_workbook_parsers_preserve_series_contract():
    loader = _load_module("loaders/infrastructure_loader.py", "infrastructure_loader_test")
    private = pd.DataFrame(
        {
            "Date": ["Jun-25", "Jun-26p"],
            "Data center": [25000, 32000],
            "Nonresidential": [750000, 800000],
            "Computer/ electronic/ electrical": [110000, 125000],
            "Manufacturing": [210000, 230000],
            "Communication": [26000, 28000],
        }
    )
    public = pd.DataFrame(
        {
            "Date": ["Jun-25", "Jun-26p"],
            "Public Highway and street": [125000, 132000],
            "Public Transportation": [58000, 61000],
            "Public Water supply": [34000, 37000],
        }
    )

    private_out = loader.parse_private_infrastructure_workbook(
        _construction_workbook("Private SA", private)
    )
    public_out = loader.parse_public_infrastructure_workbook(
        _construction_workbook("Public SA", public)
    )

    assert private_out.iloc[-1]["Data Center Construction"] == 32000
    assert private_out.iloc[-1]["Computer, Electronic & Electrical Manufacturing Construction"] == 125000
    assert public_out.iloc[-1]["Public Highway and Street Construction"] == 132000
    assert private_out.iloc[-1]["Observation Date"] == pd.Timestamp("2026-06-01")


def test_data_center_geojson_parser_keeps_location_provenance_fields():
    loader = _load_module("loaders/infrastructure_loader.py", "infrastructure_geojson_test")
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "state_abb": "VA",
                    "county": "Loudoun County",
                    "operator": "Example Operator",
                    "name": "Example Facility",
                    "sqft": 150000,
                    "type": "point",
                },
                "geometry": {"type": "Point", "coordinates": [-77.5, 39.0]},
            },
            {
                "type": "Feature",
                "properties": {"state_abb": "TX"},
                "geometry": {"type": "Polygon", "coordinates": []},
            },
        ],
    }

    frame = loader.parse_data_center_geojson(payload)

    assert len(frame) == 1
    assert frame.iloc[0]["State"] == "VA"
    assert frame.iloc[0]["Operator"] == "Example Operator"
    assert frame.iloc[0]["Square Feet"] == 150000
    assert frame.iloc[0]["Longitude"] == -77.5


def test_btos_parsers_keep_current_expected_and_sampling_error_separate():
    loader = _load_module("loaders/adaptation_loader.py", "adaptation_loader_test")
    national_estimates = pd.DataFrame(
        {
            "Question ID": [7, 24],
            "Answer": ["Yes", "Yes"],
            "202515": ["18.0%", "21.0%"],
            "202615": ["21.5%", "24.3%"],
        }
    )
    national_errors = pd.DataFrame(
        {
            "Question ID": [7, 24],
            "Answer": ["Yes", "Yes"],
            "202515": ["0.4%", "0.5%"],
            "202615": ["0.4%", "0.5%"],
        }
    )
    national = loader.parse_btos_national_workbook(
        _btos_workbook(national_estimates, national_errors)
    )

    assert national.iloc[-1]["Current AI Use"] == 21.5
    assert national.iloc[-1]["Expected AI Use"] == 24.3
    assert round(float(national.iloc[-1]["Expected Adoption Gap"]), 1) == 2.8
    assert national.iloc[-1]["Current AI Use SE"] == 0.4

    sector_estimates = pd.DataFrame(
        {
            "Sector": ["51", "51", "54", "54"],
            "Question ID": [7, 24, 7, 24],
            "Answer": ["Yes", "Yes", "Yes", "Yes"],
            "202515": ["38.0%", "41.0%", "37.0%", "40.0%"],
            "202615": ["41.9%", "45.0%", "40.0%", "43.0%"],
        }
    )
    sector_errors = sector_estimates.copy()
    sector_errors[["202515", "202615"]] = "0.8%"
    sector = loader.parse_btos_sector_workbook(
        _btos_workbook(sector_estimates, sector_errors)
    )

    information = sector.loc[sector["Sector Code"] == "51"].iloc[0]
    assert information["Sector"] == "Information"
    assert information["Current AI Use"] == 41.9
    assert information["Expected AI Use"] == 45.0


def test_seeded_development_data_is_current_and_explicitly_descriptive():
    national = pd.read_csv(ROOT / "data" / "adaptation_national_history.csv")
    sectors = pd.read_csv(ROOT / "data" / "adaptation_sector_snapshot.csv")
    construction = pd.read_csv(ROOT / "data" / "infrastructure_construction_history.csv")
    definitions = (ROOT / "config" / "metric_definitions.py").read_text()

    assert not national.empty
    assert national.iloc[-1]["Date"] == "2026-07-30"
    assert national.iloc[-1]["Current AI Use"] == 21.5
    assert national.iloc[-1]["Expected AI Use"] == 24.3
    assert not sectors.empty
    assert pd.to_numeric(sectors["Current AI Use"], errors="coerce").max() >= 40.0
    assert not construction.empty
    assert "Data Center Construction" in construction.columns
    assert "Computer, Electronic & Electrical Manufacturing Construction" in construction.columns
    assert "do not measure facility size, construction stage" in definitions
    assert "does not measure intensity of use, productivity" in definitions


def test_infrastructure_and_adaptation_visuals_render_expected_layers():
    visuals = _load_module("research_overlay/visuals.py", "infrastructure_adaptation_visuals_test")
    locations = pd.DataFrame(
        {
            "Latitude": [39.0],
            "Longitude": [-77.5],
            "Facility": ["Example Facility"],
            "Operator": ["Example Operator"],
            "County": ["Loudoun County"],
            "State": ["VA"],
            "Square Feet": [150000],
        }
    )
    map_figure = visuals.data_center_map(locations)
    assert len(map_figure.data) == 1
    assert map_figure.data[0].type == "scattergeo"

    history = pd.DataFrame(
        {
            "Observation Date": pd.to_datetime(["2025-06-01", "2026-06-01"]),
            "Data Center Construction": [25000.0, 32000.0],
            "Computer, Electronic & Electrical Manufacturing Construction": [110000.0, 125000.0],
        }
    )
    buildout_figure = visuals.infrastructure_construction_history(history)
    assert {trace.name for trace in buildout_figure.data} == {
        "Data centers",
        "Computer, electronic & electrical manufacturing",
    }

    adaptation = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2025-07-31", "2026-07-30"]),
            "Current AI Use": [18.0, 21.5],
            "Expected AI Use": [21.0, 24.3],
        }
    )
    adaptation_figure = visuals.adaptation_history(adaptation)
    assert {trace.name for trace in adaptation_figure.data} == {
        "Current use",
        "Expected use within six months",
    }


def test_new_tabs_preserve_the_infrastructure_energy_boundary():
    app = (ROOT / "ai_macro.py").read_text()
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    definitions = (ROOT / "config" / "metric_definitions.py").read_text()

    assert '["AI MACRO", "MARKET", "FINANCE", "INFRASTRUCTURE", "ENERGY", "ADAPTATION", "EVIDENCE"]' in app
    assert 'render_tab_header(\n        "Infrastructure"' in renderer
    assert 'render_tab_header(\n        "Adaptation"' in renderer
    assert '"US Infrastructure Expenditure",' in renderer
    assert "National-level communication, transport, and public water-supply construction expenditures" in renderer
    assert "Infrastructure records what is being built; Energy records whether the power system can sustain it." not in renderer
    assert '"Evidence-Graded Facility Registry"' in definitions
    assert '"Water Availability Context"' not in definitions
    assert 'render_section("Water availability"' not in renderer
    assert '_render_water_availability_context' not in renderer
    assert '"Current Business AI Use"' in definitions
