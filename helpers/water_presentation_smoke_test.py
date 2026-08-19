#!/usr/bin/env python3
"""Water presentation contract for the v9.6 universal-campus architecture."""

from __future__ import annotations

from pathlib import Path
import ast
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.water_campus import campus_water_dossier, county_water_exposure_profile
from analytics.water_competition import local_context_coverage_profile
from analytics.water_local import local_water_constraint_summary
from rendering.charts_water import water_county_drought_map


def _campuses(material_count: int) -> pd.DataFrame:
    points = [
        ("campus:al-1", "01001", "AL", "Autauga", 32.54, -86.64),
        ("campus:al-2", "01001", "AL", "Autauga", 32.56, -86.61),
        ("campus:al-3", "01003", "AL", "Baldwin", 30.66, -87.75),
        ("campus:al-4", "01003", "AL", "Baldwin", 30.70, -87.80),
        ("campus:al-5", "01005", "AL", "Barbour", 31.87, -85.39),
        ("campus:tx-1", "48029", "TX", "Bexar", 29.42, -98.49),
        ("campus:tx-2", "48029", "TX", "Bexar", 29.47, -98.43),
        ("campus:tx-3", "48453", "TX", "Travis", 30.27, -97.74),
        ("campus:tx-4", "48453", "TX", "Travis", 30.31, -97.71),
        ("campus:tx-5", "48201", "TX", "Harris", 29.76, -95.37),
    ]
    rows = []
    for index, (campus_id, fips, state, county, lat, lon) in enumerate(points):
        material = index < material_count
        label = f"Example Campus {index + 1} — {county}, {state}"
        rows.append({
            "Campus ID": campus_id,
            "Campus Name": f"Example Campus {index + 1}",
            "Campus Label": label,
            "Operator": "Example",
            "State": state,
            "County": county,
            "FIPS": fips,
            "Latitude": lat,
            "Longitude": lon,
            "County D1+ Area Percent": 90.0 if material else 10.0,
            "County D2+ Area Percent": 70.0 if material else 0.0,
            "County D3+ Area Percent": 40.0 if material else 0.0,
            "County D4 Area Percent": 0.0,
            "County Drought Snapshot Date": "2026-08-11",
            "D1+ Area Percent": 5.0,
            "D2+ Area Percent": 5.0,
            "Snapshot Date": "2026-08-11",
            "PWS Service Area Query Resolved": True,
            "PWS Service Area Overlap": index == 8,
            "PWS Match Count": 1 if index == 8 else 0,
            "PWSIDs": "TX123" if index == 8 else "",
            "PWS Names": "Example Water" if index == 8 else "",
            "PWS Boundary Basis": "modeled" if index == 8 else "",
            "PWS Authoritative Boundary Overlap": False,
            "PWS Modeled Boundary Overlap": index == 8,
            "PWS Ambiguous Overlap": False,
            "Direct Water Evidence": index == 9,
            "Water Withdrawal Gallons/Year": 1_000_000 if index == 9 else None,
            "Water Consumption Gallons/Year": None,
            "Published Capacity Estimate MW": 1200 if index == 0 else None,
            "Planned Data Center Capacity MW": None,
            "Status": "Proposed",
        })
    return pd.DataFrame(rows)


def _county_drought() -> pd.DataFrame:
    return pd.DataFrame([
        {"FIPS": "01001", "County": "Autauga", "State": "AL", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 90.0, "D2+ Area Percent": 70.0, "D3+ Area Percent": 40.0, "D4 Area Percent": 0.0},
        {"FIPS": "01003", "County": "Baldwin", "State": "AL", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 20.0, "D2+ Area Percent": 10.0, "D3+ Area Percent": 0.0, "D4 Area Percent": 0.0},
        {"FIPS": "01005", "County": "Barbour", "State": "AL", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 0.0, "D2+ Area Percent": 0.0, "D3+ Area Percent": 0.0, "D4 Area Percent": 0.0},
        {"FIPS": "48029", "County": "Bexar", "State": "TX", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 75.0, "D2+ Area Percent": 50.0, "D3+ Area Percent": 20.0, "D4 Area Percent": 0.0},
        {"FIPS": "48453", "County": "Travis", "State": "TX", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 30.0, "D2+ Area Percent": 15.0, "D3+ Area Percent": 0.0, "D4 Area Percent": 0.0},
        {"FIPS": "48201", "County": "Harris", "State": "TX", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 0.0, "D2+ Area Percent": 0.0, "D3+ Area Percent": 0.0, "D4 Area Percent": 0.0},
    ])


def main() -> int:
    obsolete_phase2 = ROOT / "helpers" / "phase2_grid_water_smoke_test.py"
    if obsolete_phase2.exists():
        raise AssertionError("Obsolete facility-grain Phase 2 Water smoke test still exists")

    broad = _campuses(6)

    local = local_water_constraint_summary(broad)
    assert local["campuses"] == 10
    assert local["campuses_with_county_drought_data"] == 10
    assert local["campuses_in_counties_with_25pct_d2"] == 6
    assert abs(local["campuses_in_counties_with_25pct_d2_share"] - 0.6) < 1e-9

    coverage = local_context_coverage_profile({
        "campuses": 10,
        "county_drought_context_records": 10,
        "pws_service_area_query_resolved_records": 10,
        "pws_service_area_overlap_records": 1,
        "direct_water_evidence_records": 1,
        "quantified_withdrawal_records": 1,
        "quantified_consumption_records": 0,
    })
    values = coverage.set_index("Coverage Layer")["Campuses"].to_dict()
    assert values["Current county drought"] == 10
    assert values["EPA service-area overlap"] == 1

    counties = county_water_exposure_profile(broad)
    assert set(counties["State"]) == {"AL", "TX"}
    assert counties["FIPS"].nunique() == 6

    dossier = campus_water_dossier(broad)
    assert len(dossier) == 10
    assert dossier["Campus ID"].nunique() == 10
    assert "Local D2+ Area Percent" in dossier.columns

    national = water_county_drought_map(_county_drought(), broad)
    assert national.data and national.data[0].type == "choroplethmap"
    assert "01001" in set(national.data[0].locations)
    assert not any(getattr(national.layout.map.bounds, field, None) is not None for field in ("west", "east", "south", "north"))

    texas = water_county_drought_map(_county_drought(), broad, state="TX")
    assert [trace.type for trace in texas.data] == ["choroplethmap", "scattermap"]
    assert all(str(location).startswith("48") for location in texas.data[0].locations)
    assert len(texas.data[1].lat) == 5

    water_source = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    parsed = ast.parse(water_source)
    helper_nodes = [
        node for node in parsed.body
        if isinstance(node, ast.FunctionDef) and node.name in {"_state_exposure_order", "_campus_priority_frame"}
    ]
    helper_ns = {"pd": pd}
    exec(compile(ast.Module(body=helper_nodes, type_ignores=[]), "rendering/water.py", "exec"), helper_ns)
    ranked_states = helper_ns["_state_exposure_order"](dossier)
    assert ranked_states[0] == "AL", ranked_states
    tx_priority = helper_ns["_campus_priority_frame"](dossier.loc[dossier["State"].eq("TX")])
    assert float(tx_priority.iloc[0]["Local D2+ Area Percent"]) >= float(tx_priority.iloc[-1]["Local D2+ Area Percent"])

    required_copy = [
        "National county drought map",
        "Select a county to open its state.",
        "rm-water-profile-v3",
        "Local conditions",
        "Service area",
        "Campus water",
        "Water data coverage",
    ]
    for phrase in required_copy:
        assert phrase in water_source, phrase

    forbidden_copy = [
        "not a claim",
        "does not establish",
        "not data-center use",
        "without estimating",
        "geographic context only",
    ]
    lowered = water_source.casefold()
    for phrase in forbidden_copy:
        assert phrase.casefold() not in lowered, phrase

    assert 'st.session_state["water-dossier-state"] = state' in water_source
    assert 'campus_key = f"water-dossier-campus-{state}"' in water_source
    render_tab = water_source[water_source.index("def render_water_tab"):]
    assert render_tab.index("_render_local_exposure(context)") < render_tab.index("_render_campus_dossier(context)")
    assert render_tab.index("_render_campus_dossier(context)") < render_tab.index("_render_system_context_workbench(context, infrastructure_data)")
    assert render_tab.index("_render_system_context_workbench(context, infrastructure_data)") < render_tab.index("_render_coverage(context)")

    chart_source = (ROOT / "rendering" / "charts_water.py").read_text(encoding="utf-8")
    assert "go.Choroplethmap(" in chart_source
    assert "go.Scattermap(" in chart_source
    assert "map_view(" in chart_source
    assert "map_layers(" in chart_source

    print(
        "PASS  Water presentation · campus grain · FIPS-first drought · "
        "MapLibre drilldown · campus dossier continuity"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
