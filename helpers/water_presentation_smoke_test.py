from __future__ import annotations

from pathlib import Path
import ast
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.water_competition import (
    campus_water_dossier,
    county_water_exposure_profile,
    local_context_coverage_profile,
)
from analytics.water_local import local_water_constraint_summary
from rendering.charts_water import water_county_drought_map, water_local_context_coverage


def _facilities(material_count: int) -> pd.DataFrame:
    rows = []
    points = [
        ("01001", "AL", "Autauga", 32.54, -86.64),
        ("01001", "AL", "Autauga", 32.56, -86.61),
        ("01003", "AL", "Baldwin", 30.66, -87.75),
        ("01003", "AL", "Baldwin", 30.70, -87.80),
        ("01005", "AL", "Barbour", 31.87, -85.39),
        ("48029", "TX", "Bexar", 29.42, -98.49),
        ("48029", "TX", "Bexar", 29.47, -98.43),
        ("48453", "TX", "Travis", 30.27, -97.74),
        ("48453", "TX", "Travis", 30.31, -97.71),
        ("48201", "TX", "Harris", 29.76, -95.37),
    ]
    for index, (fips, state, county, lat, lon) in enumerate(points):
        material = index < material_count
        rows.append({
            "Facility ID": f"f-{index}",
            "Facility": f"Campus {index}",
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


def _water_payload(frame: pd.DataFrame) -> dict:
    summary = {
        "facilities": len(frame),
        "county_drought_context_records": int(frame["County D2+ Area Percent"].notna().sum()),
        "pws_service_area_query_resolved_records": int(frame["PWS Service Area Query Resolved"].sum()),
        "pws_service_area_overlap_records": int(frame["PWS Service Area Overlap"].sum()),
        "direct_water_evidence_records": int(frame["Direct Water Evidence"].sum()),
        "quantified_withdrawal_records": int(frame["Water Withdrawal Gallons/Year"].notna().sum()),
        "quantified_consumption_records": 0,
    }
    return {
        "facility_context": frame,
        "facility_context_summary": summary,
        "summary": {},
        "usdm_county_drought": _county_drought(),
        "usgs_2020_top_withdrawals": pd.DataFrame(),
    }


def main() -> None:
    broad = _facilities(6)

    local = local_water_constraint_summary(broad)
    assert local["county_drought_resolved"] == 10
    assert local["facilities_in_counties_with_25pct_d2"] == 6
    assert abs(local["facilities_in_counties_with_25pct_d2_share"] - 0.6) < 1e-9

    coverage = local_context_coverage_profile(_water_payload(broad)["facility_context_summary"])
    values = coverage.set_index("Coverage Layer")["Facilities"].to_dict()
    assert values["Current county drought"] == 10
    assert values["EPA service-area overlap"] == 1

    counties = county_water_exposure_profile(broad)
    assert set(counties["State"]) == {"AL", "TX"}
    dossier = campus_water_dossier(broad)
    assert "Local D2+ Area Percent" in dossier.columns


    national = water_county_drought_map(_county_drought(), broad)
    assert len(national.data) == 1
    assert national.data[0].type == "choropleth"
    assert "01001" in set(national.data[0].locations)

    alabama = water_county_drought_map(_county_drought(), broad, state="AL")
    assert alabama.data[0].type == "choropleth"
    assert all(str(location).startswith("01") for location in alabama.data[0].locations)
    assert any(trace.type == "scattergeo" for trace in alabama.data[1:])

    geometry_path = ROOT / "assets" / "geo" / "us_counties.geojson"
    assert geometry_path.exists()
    assert geometry_path.stat().st_size > 500_000
    manifest_source = (ROOT / "helpers" / "build_release_manifest.py").read_text(encoding="utf-8")
    assert "assets/geo/us_counties.geojson" in manifest_source

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
    assert float(tx_priority.iloc[0]["Local D2+ Area Percent"]) >= float(tx_priority.iloc[-1]["Local D2+ Area Percent"]), tx_priority[["Facility", "Local D2+ Area Percent"]]
    required_copy = [
        "National county drought map",
        "Select a county to open its state.",
        "rm-water-profile-v3",
        "Local conditions",
        "Service area",
        "Facility water",
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
    assert 'key=f"water-dossier-campus-{state}"' in water_source
    render_tab = water_source[water_source.index("def render_water_tab"): ]
    assert render_tab.index("_render_local_exposure(context)") < render_tab.index("_render_campus_dossier(context)")
    assert render_tab.index("_render_campus_dossier(context)") < render_tab.index("_render_system_context_workbench(context, infrastructure_data)")
    assert render_tab.index("_render_system_context_workbench(context, infrastructure_data)") < render_tab.index("_render_coverage(context)")

    chart_source = (ROOT / "rendering" / "charts_water.py").read_text(encoding="utf-8")
    assert "go.Choropleth(" in chart_source
    assert "fitbounds=\"locations\"" in chart_source
    assert "go.Scattergeo(" in chart_source

    print(
        "PASS  Water sequence v4 · map-to-campus state continuity · exposure-first defaults · national context before data coverage"
    )


if __name__ == "__main__":
    main()
