from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analytics.dashboard_context import DashboardContext
from analytics.read_evidence import build_water_evidence
from analytics.water_competition import (
    campus_water_dossier,
    county_water_exposure_profile,
    local_context_coverage_profile,
)
from analytics.water_local import local_water_constraint_summary
from rendering.charts_water import water_county_drought_exposure, water_local_context_coverage


def _facilities(material_count: int) -> pd.DataFrame:
    rows = []
    for index in range(10):
        material = index < material_count
        rows.append({
            "Facility ID": f"f-{index}",
            "Facility": f"Campus {index}",
            "Operator": "Example",
            "State": "VA" if index < 5 else "TX",
            "County": "Alpha County" if index < 5 else "Beta County",
            "County D1+ Area Percent": 90.0 if material else 10.0,
            "County D2+ Area Percent": 100.0 if material else 0.0,
            "County D3+ Area Percent": 40.0 if material else 0.0,
            "County D4 Area Percent": 0.0,
            "County Drought Snapshot Date": "2026-08-11",
            "D1+ Area Percent": 5.0,
            "D2+ Area Percent": 5.0,
            "Snapshot Date": "2026-08-11",
            "PWS Service Area Query Resolved": True,
            "PWS Service Area Overlap": index == 8,
            "PWS Match Count": 1 if index == 8 else 0,
            "PWSIDs": "VA123" if index == 8 else "",
            "PWS Names": "Example Water" if index == 8 else "",
            "PWS Boundary Basis": "modeled" if index == 8 else "",
            "PWS Authoritative Boundary Overlap": False,
            "PWS Modeled Boundary Overlap": index == 8,
            "PWS Ambiguous Overlap": False,
            "Direct Water Evidence": index == 9,
            "Water Withdrawal Gallons/Year": 1_000_000 if index == 9 else None,
            "Water Consumption Gallons/Year": None,
            "Published Capacity Estimate MW": None,
            "Planned Data Center Capacity MW": None,
        })
    return pd.DataFrame(rows)


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
        "usgs_2020_top_withdrawals": pd.DataFrame(),
    }


def main() -> None:
    sparse = _facilities(1)
    broad = _facilities(6)

    local = local_water_constraint_summary(broad)
    assert local["county_drought_resolved"] == 10
    assert local["facilities_in_counties_with_25pct_d2"] == 6
    assert abs(local["facilities_in_counties_with_25pct_d2_share"] - 0.6) < 1e-9
    assert local["service_area_query_resolved"] == 10
    assert local["service_area_overlap"] == 1
    assert local["direct_water_evidence"] == 1
    assert local["quantified_withdrawal"] == 1
    assert local["published_capacity_records"] == 0

    coverage = local_context_coverage_profile(_water_payload(broad)["facility_context_summary"])
    values = coverage.set_index("Coverage Layer")["Facilities"].to_dict()
    assert values["Current county drought"] == 10
    assert values["EPA point query resolved"] == 10
    assert values["EPA service-area overlap"] == 1
    assert values["Direct facility water evidence"] == 1

    counties = county_water_exposure_profile(broad)
    assert set(counties["County"]) == {"Alpha County", "Beta County"}
    assert counties.iloc[0]["D2+ Area Percent"] == 100.0

    dossier = campus_water_dossier(broad)
    assert "Local D2+ Area Percent" in dossier.columns
    material_row = dossier.loc[dossier["Facility ID"].eq("f-0")].iloc[0]
    assert material_row["Local D2+ Area Percent"] == 100.0
    assert material_row["Local Drought Geography"] == "county"
    assert not bool(material_row["Direct Water Evidence"])

    sparse_packet = build_water_evidence(DashboardContext(water_data=_water_payload(sparse)))
    broad_packet = build_water_evidence(DashboardContext(water_data=_water_payload(broad)))
    assert broad_packet.importance > sparse_packet.importance
    fact_ids = {fact.id for fact in broad_packet.facts}
    assert "water.facilities_in_counties_with_25pct_d2_share_pct" in fact_ids
    assert "water.pws_service_area_overlap_facilities" in fact_ids
    assert "water.pws_provenance_classified_share_pct" in fact_ids
    assert "water.unclassified_pws_overlap_facilities" in fact_ids
    assert "water.authoritative_pws_overlap_facilities" in fact_ids
    assert "water.modeled_pws_overlap_facilities" in fact_ids
    assert "water.published_capacity_in_counties_with_d2_gw" not in fact_ids


    low_provenance = broad.copy()
    low_provenance.loc[low_provenance.index[:5], "PWS Service Area Overlap"] = True
    low_provenance.loc[low_provenance.index[:5], "PWS Boundary Basis"] = "unclassified"
    low_provenance.loc[low_provenance.index[:5], "PWS Authoritative Boundary Overlap"] = False
    low_provenance.loc[low_provenance.index[:5], "PWS Modeled Boundary Overlap"] = False
    low_packet = build_water_evidence(DashboardContext(water_data=_water_payload(low_provenance)))
    low_ids = {fact.id for fact in low_packet.facts}
    assert "water.unclassified_pws_overlap_facilities" in low_ids
    assert "water.authoritative_pws_overlap_facilities" not in low_ids
    assert "water.modeled_pws_overlap_facilities" not in low_ids

    drought_fig = water_county_drought_exposure(broad)
    coverage_fig = water_local_context_coverage(_water_payload(broad)["facility_context_summary"])
    assert len(drought_fig.data) == 2
    assert len(coverage_fig.data) == 1

    print(
        "PASS  Water v2 presentation · county-first exposure · independent observability layers · "
        "breadth-based Read importance · no low-coverage capacity headline"
    )


if __name__ == "__main__":
    main()
