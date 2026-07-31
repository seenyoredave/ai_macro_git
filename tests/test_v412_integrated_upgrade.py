from pathlib import Path
import ast
import sys
import types

import numpy as np
import pandas as pd

from analytics.macro_interpretation import build_macro_interpretation
from loaders.facility_registry_loader import (
    build_facility_registry,
    load_curated_facility_records,
    normalize_im3_locations,
    registry_coverage,
)
_old_streamlit = sys.modules.get("streamlit")
if _old_streamlit is None:
    _streamlit = types.ModuleType("streamlit")
    _streamlit.cache_data = lambda *args, **kwargs: (lambda function: function)
    sys.modules["streamlit"] = _streamlit
from loaders import water_context_loader as water_loader
if _old_streamlit is None:
    sys.modules.pop("streamlit", None)

from research_overlay.visuals import (
    adaptation_history,
    adaptation_sector_bars,
    data_center_map,
    water_availability_context_map,
)


ROOT = Path(__file__).resolve().parents[1]


def test_im3_registry_normalization_preserves_unknown_capacity_and_water():
    im3 = pd.DataFrame(
        [
            {
                "Facility": "Observed site",
                "Operator": "Example",
                "State": "VA",
                "County": "Loudoun",
                "Latitude": 39.0,
                "Longitude": -77.5,
                "Square Feet": 100_000,
            }
        ]
    )
    registry = normalize_im3_locations(im3)
    row = registry.iloc[0]

    assert row["Evidence Grade"] == "C"
    assert row["Status"] == "Observed footprint"
    assert row["Square Feet"] == 100_000
    for field in (
        "Planned Data Center Capacity MW",
        "Contracted Utility Capacity MW",
        "Energized Capacity MW",
        "Annual Electricity Consumption MWh",
        "Water Withdrawal Gallons/Year",
        "Water Consumption Gallons/Year",
        "Site WUE L/kWh",
    ):
        assert pd.isna(row[field])


def test_curated_panhandle_records_use_field_specific_capacity_contracts():
    curated = load_curated_facility_records().set_index("Facility ID")

    assert {
        "verified:project-caprock",
        "verified:google-armstrong",
        "verified:project-matador",
    }.issubset(curated.index)
    assert curated.loc["verified:project-caprock", "Planned Data Center Capacity MW"] == 540
    assert curated.loc["verified:project-matador", "Planned Onsite Generation MW"] == 17_000
    assert pd.isna(curated.loc["verified:project-matador", "Planned Data Center Capacity MW"])
    assert curated["Water Withdrawal Gallons/Year"].isna().all()
    assert curated["Water Consumption Gallons/Year"].isna().all()
    assert curated["Evidence Grade"].eq("B").all()


def test_registry_coverage_counts_evidence_without_inventing_values():
    registry = build_facility_registry(pd.DataFrame())
    coverage = registry_coverage(registry)

    assert coverage["records"] == 3
    assert coverage["verified_project_records"] == 3
    assert coverage["fields"]["Planned Data Center Capacity MW"]["records"] == 1
    assert coverage["fields"]["Planned Onsite Generation MW"]["records"] == 1
    assert coverage["fields"]["Water Withdrawal Gallons/Year"]["records"] == 0


def test_facility_map_retains_records_missing_selected_metric():
    facilities = pd.DataFrame(
        [
            {
                "Facility": "Known",
                "Latitude": 35.0,
                "Longitude": -101.0,
                "State": "TX",
                "Planned Data Center Capacity MW": 540,
            },
            {
                "Facility": "Unknown",
                "Latitude": 35.2,
                "Longitude": -101.2,
                "State": "TX",
                "Planned Data Center Capacity MW": np.nan,
            },
        ]
    )
    figure = data_center_map(facilities, size_by="Planned data-center capacity")

    assert [trace.name for trace in figure.data] == ["Metric available", "Metric unavailable"]
    assert len(figure.data[0].lat) == 1
    assert len(figure.data[1].lat) == 1


def test_nwdc_parser_accepts_documented_location_keyed_response():
    payload = {
        "data": {
            "huc12_id": {
                "010203040501": [{"year_month": "2020-09", "sui_frac": 0.2}],
                "010203040502": [{"water_year": 2020, "sui": 0.6}],
            }
        }
    }
    parsed = water_loader._parse_nwdc_payload(payload)

    assert parsed["HUC12"].tolist() == ["010203040501", "010203040502"]
    assert parsed["Observation Year"].tolist() == [2020, 2020]
    assert np.allclose(parsed["SUI"], [0.2, 0.6])


def test_state_water_fetch_aggregates_huc12_values_to_huc8(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "huc12_id": {
                        "010203040501": [{"water_year": 2020, "sui_frac": 0.2}],
                        "010203040502": [{"water_year": 2020, "sui_frac": 0.6}],
                        "010203050101": [{"water_year": 2020, "sui_frac": 0.8}],
                    }
                }
            }

    monkeypatch.setattr(water_loader.requests, "get", lambda *args, **kwargs: Response())
    result = water_loader._fetch_state_sui("TX").set_index("HUC8")

    assert result.loc["01020304", "Median SUI"] == 0.4
    assert result.loc["01020304", "P75 SUI"] == 0.5
    assert result.loc["01020304", "HUC12 Count"] == 2
    assert result.loc["01020305", "SUI Band"] == "Very high"


def test_huc8_geometry_normalizes_case_for_plotly_feature_ids(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {
                            "HUC8": 1020304,
                            "NAME": "Example watershed",
                            "STATES": "TX",
                            "AREASQKM": 123.0,
                        },
                        "geometry": {"type": "Polygon", "coordinates": []},
                    }
                ],
            }

    monkeypatch.setattr(water_loader.requests, "get", lambda *args, **kwargs: Response())
    result = water_loader._fetch_state_huc8_geojson("TX")
    properties = result["features"][0]["properties"]

    assert properties["huc8"] == "01020304"
    assert properties["name"] == "Example watershed"
    assert properties["states"] == "TX"


def test_water_map_is_physical_context_with_facility_overlay():
    water = pd.DataFrame(
        [{"HUC8": "01020304", "Median SUI": 0.6, "P75 SUI": 0.7, "HUC12 Count": 3, "Watershed": "Example"}]
    )
    geometry = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"huc8": "01020304"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-102, 34], [-100, 34], [-100, 36], [-102, 36], [-102, 34]]],
                },
            }
        ],
    }
    facilities = pd.DataFrame([{"Facility": "Site", "Latitude": 35.0, "Longitude": -101.0, "State": "TX"}])
    figure = water_availability_context_map(water, geometry, facilities)

    assert figure.data[0].type == "choropleth"
    assert figure.data[0].featureidkey == "properties.huc8"
    assert figure.data[1].name == "Facility records"


def test_adaptation_charts_use_95_percent_intervals_from_standard_errors():
    national = pd.DataFrame(
        [
            {
                "Date": "2026-07-30",
                "Current AI Use": 20.0,
                "Expected AI Use": 25.0,
                "Current AI Use SE": 0.5,
                "Expected AI Use SE": 0.75,
            }
        ]
    )
    sectors = pd.DataFrame(
        [
            {
                "Sector": "Information",
                "Sector Code": "51",
                "Current AI Use": 40.0,
                "Expected AI Use": 45.0,
                "Current AI Use SE": 1.0,
                "Expected AI Use SE": 1.5,
            }
        ]
    )

    history_figure = adaptation_history(national)
    sector_figure = adaptation_sector_bars(sectors)

    assert np.allclose(history_figure.data[0].error_y.array, [0.98])
    assert np.allclose(history_figure.data[1].error_y.array, [1.47])
    assert np.allclose(sector_figure.data[0].error_x.array, [1.96])
    assert np.allclose(sector_figure.data[1].error_x.array, [2.94])


def _snapshot_regime(capacity_gap):
    return {
        "AI Equity Index": 50,
        "AI Development Intensity": 60,
        "Economic Validation Gap": 0,
        "Speculation Gap": 0,
        "Power Stress Index": 0,
        "Power Capacity Gap": capacity_gap,
        "Borrower Strain": 0,
        "Lender Strain": 0,
        "Concentration HHI": 20,
        "Deployment Funding Mix": {
            "current": {
                "internal_funding_coverage": 1.2,
                "cash_reserve_coverage_years": 1.2,
                "debt_financing_pulse": 0,
                "forward_commitment_load": 1.0,
            },
            "series": {},
        },
    }


def test_snapshot_requires_power_corroboration_before_buildout_becomes_pressure():
    infrastructure = {
        "series": {"Data Center Construction": {"yoy_growth": 0.5, "date": "2026-06-01"}}
    }
    adaptation = {
        "current_use": 21.5,
        "expected_use": 24.3,
        "expected_adoption_gap": 2.8,
        "annual_change": 2.0,
        "snapshot_date": "2026-07-30",
    }

    uncorroborated = build_macro_interpretation(
        regime_metrics=_snapshot_regime(10),
        macro_history=pd.DataFrame(),
        infrastructure_data=infrastructure,
        adaptation_data=adaptation,
    )
    corroborated = build_macro_interpretation(
        regime_metrics=_snapshot_regime(30),
        macro_history=pd.DataFrame(),
        infrastructure_data=infrastructure,
        adaptation_data=adaptation,
    )

    assert uncorroborated["domains"]["infrastructure"]["pressure_severity"] == 0
    assert corroborated["domains"]["infrastructure"]["pressure_severity"] >= 2
    assert corroborated["snapshot_context"]["adaptation"]["current_use"] == 21.5
    assert corroborated["snapshot_context"]["coverage"]["supplemental_available"] == 2


def test_market_universe_label_is_computed_not_static_text():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    tree = ast.parse(source)
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_market_universe_label"
    )
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "renderers.py", "exec"), namespace)
    label = namespace["_market_universe_label"]
    frame = pd.DataFrame({"Sector": ["A", "B"], "Ticker": ["AAA", "BBB"]})

    assert label(
        {
            "loaded_sectors": 12,
            "configured_sectors": 12,
            "loaded_tickers": 166,
            "configured_tickers": 168,
        },
        frame,
    ) == "12 sectors / 166 of 168 tickers loaded"
