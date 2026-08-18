"""Focused contracts for Water v2 local constraint evidence."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.spatial_context import attach_water_context
from analytics.water_local import local_water_constraint_summary


def main() -> None:
    facilities = pd.DataFrame(
        [
            {
                "Facility ID": "alpha",
                "Facility": "Alpha Campus",
                "State": "VA",
                "County": "Loudoun County",
                "Latitude": 39.05,
                "Longitude": -77.48,
                "Published Capacity Estimate MW": 500.0,
                "Water Source": "Not disclosed",
                "Cooling System": "Not disclosed",
            },
            {
                "Facility ID": "beta",
                "Facility": "Beta Campus",
                "State": "AZ",
                "County": "Maricopa County",
                "Latitude": 33.45,
                "Longitude": -112.07,
                "Published Capacity Estimate MW": 300.0,
                "Water Source": "Not disclosed",
                "Cooling System": "Not disclosed",
            },
            {
                "Facility ID": "gamma",
                "Facility": "Gamma Campus",
                "State": "TX",
                "County": "Dallas County",
                "Latitude": 32.78,
                "Longitude": -96.80,
                "Published Capacity Estimate MW": 200.0,
                "Water Withdrawal Gallons/Year": 123.0,
            },
        ]
    )
    counties = pd.DataFrame(
        [
            {"State": "VA", "County": "Loudoun", "FIPS": "51107", "Year": 2015, "Total Withdrawal Mgal/d": 100.0},
            {"State": "AZ", "County": "Maricopa", "FIPS": "04013", "Year": 2015, "Total Withdrawal Mgal/d": 200.0},
            {"State": "TX", "County": "Dallas", "FIPS": "48113", "Year": 2015, "Total Withdrawal Mgal/d": 300.0},
        ]
    )
    state_drought = pd.DataFrame(
        [
            {"State": "VA", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 10.0, "D2+ Area Percent": 5.0},
            {"State": "AZ", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 20.0, "D2+ Area Percent": 10.0},
            {"State": "TX", "Snapshot Date": "2026-08-11", "D1+ Area Percent": 15.0, "D2+ Area Percent": 7.0},
        ]
    )
    county_drought = pd.DataFrame(
        [
            {
                "FIPS": "51107",
                "County": "Loudoun",
                "State": "VA",
                "Snapshot Date": "2026-08-11",
                "D0+ Area Percent": 80.0,
                "D1+ Area Percent": 60.0,
                "D2+ Area Percent": 40.0,
                "D3+ Area Percent": 15.0,
                "D4 Area Percent": 0.0,
                "Source": "USDM",
                "Source URL": "https://example.test/usdm",
            },
            {
                "FIPS": "48113",
                "County": "Dallas",
                "State": "TX",
                "Snapshot Date": "2026-08-11",
                "D0+ Area Percent": 30.0,
                "D1+ Area Percent": 20.0,
                "D2+ Area Percent": 5.0,
                "D3+ Area Percent": 0.0,
                "D4 Area Percent": 0.0,
                "Source": "USDM",
                "Source URL": "https://example.test/usdm",
            },
        ]
    )

    # Query keys follow the same stable contract used by the EPA point cache.
    from water.epa_pws import _boundary_basis, _is_community_system, query_key

    # EPA Version 3 combines community and non-community systems.  The parser
    # must keep non-community boundaries out of the CWS overlap evidence while
    # retaining STATE/MODELED compatibility for older community rows.
    assert _is_community_system({"Feature_Type": "Community Water System", "Symbology_Field": "STATE"})
    assert _is_community_system({"Feature_Type": "CWS", "Symbology_Field": "MODELED"})
    assert not _is_community_system({"Feature_Type": "Transient Non-Community Water System", "Symbology_Field": "STATE"})
    assert not _is_community_system({"Feature_Type": "Non-Transient Non-Community Water System", "Symbology_Field": "MODELED"})
    assert _is_community_system({"Feature_Type": "", "Symbology_Field": "STATE"})
    assert _is_community_system({"Feature_Type": "", "Symbology_Field": "", "Model_Method": "State"})
    assert not _is_community_system({
        "Feature_Type": "Transient Non-Community Water System",
        "Symbology_Field": "",
        "Model_Method": "State",
    })

    # EPA's CWS metadata exposes two provenance signals.  Version 3 may require
    # Model_Method when the older Symbology_Field is not populated.
    assert _boundary_basis({"Symbology_Field": "STATE", "Model_Method": ""}) == "authoritative"
    assert _boundary_basis({"Symbology_Field": "MODELED", "Model_Method": ""}) == "modeled"
    assert _boundary_basis({"Symbology_Field": "", "Model_Method": "State"}) == "authoritative"
    assert _boundary_basis({"Symbology_Field": "", "Model_Method": "Random Forest"}) == "modeled"
    assert _boundary_basis({"Symbology_Field": "", "Model_Method": ""}) == "unclassified"

    pws = pd.DataFrame(
        [
            {
                "Query Key": query_key("alpha", 39.05, -77.48),
                "Facility ID": "alpha",
                "PWSID": "VA1111111",
                "PWS Name": "Authoritative Utility",
                "Boundary Basis": "authoritative",
                "Query Status": "matched",
            },
            {
                "Query Key": query_key("alpha", 39.05, -77.48),
                "Facility ID": "alpha",
                "PWSID": "VA2222222",
                "PWS Name": "Modeled Utility",
                "Boundary Basis": "modeled",
                "Query Status": "matched",
            },
            {
                "Query Key": query_key("beta", 33.45, -112.07),
                "Facility ID": "beta",
                "PWSID": "",
                "PWS Name": "",
                "Boundary Basis": "",
                "Query Status": "no_match",
            },
        ]
    )

    infrastructure, water = attach_water_context(
        {"facility_registry": facilities},
        {
            "usgs_counties": counties,
            "usdm_state_drought": state_drought,
            "usdm_county_drought": county_drought,
            "epa_pws_matches": pws,
            "local_context_refresh_requested": False,
        },
    )
    context = water["facility_context"].set_index("Facility ID")

    # County context is new and remains semantically separate from legacy state context.
    assert float(context.loc["alpha", "County D2+ Area Percent"]) == 40.0
    assert float(context.loc["alpha", "D2+ Area Percent"]) == 5.0
    assert pd.isna(context.loc["beta", "County D2+ Area Percent"])
    assert float(context.loc["beta", "D2+ Area Percent"]) == 10.0

    # An EPA polygon hit is overlap only. Multiple overlaps stay visibly ambiguous.
    assert bool(context.loc["alpha", "PWS Service Area Query Resolved"])
    assert bool(context.loc["alpha", "PWS Service Area Overlap"])
    assert int(context.loc["alpha", "PWS Match Count"]) == 2
    assert context.loc["alpha", "PWS Boundary Basis"] == "mixed"
    assert bool(context.loc["alpha", "PWS Authoritative Boundary Overlap"])
    assert bool(context.loc["alpha", "PWS Modeled Boundary Overlap"])
    assert bool(context.loc["alpha", "PWS Ambiguous Overlap"])
    assert bool(context.loc["beta", "PWS Service Area Query Resolved"])
    assert not bool(context.loc["beta", "PWS Service Area Overlap"])

    # Service-area overlap must never inflate direct facility water evidence.
    assert not bool(context.loc["alpha", "Direct Water Evidence"])
    assert not bool(context.loc["beta", "Direct Water Evidence"])
    assert bool(context.loc["gamma", "Direct Water Evidence"])

    summary = local_water_constraint_summary(water["facility_context"])
    assert summary["mapped_facilities"] == 3
    assert summary["county_drought_resolved"] == 2
    assert summary["service_area_query_resolved"] == 2
    assert summary["service_area_overlap"] == 1
    assert summary["authoritative_service_area_overlap"] == 1
    assert summary["ambiguous_service_area_overlap"] == 1
    assert summary["direct_water_evidence"] == 1
    assert summary["quantified_withdrawal"] == 1
    assert summary["quantified_consumption"] == 0
    assert summary["facilities_in_counties_with_25pct_d2"] == 1
    assert abs(summary["published_capacity_in_counties_with_25pct_d2_gw"] - 0.5) < 1e-9
    assert summary["highest_county_d2_location"] == "Loudoun County, VA"
    assert summary["highest_county_d2_area_pct"] == 40.0

    # The infrastructure registry receives the same bounded context used by Water.
    assert infrastructure["facility_registry"].equals(water["facility_context"])

    print(
        "PASS  Water v2 local context · county drought · EPA overlap provenance · "
        "no service inference · no water-use inference"
    )


if __name__ == "__main__":
    main()
