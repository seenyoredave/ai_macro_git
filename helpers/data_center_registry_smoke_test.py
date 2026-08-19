#!/usr/bin/env python3
"""Focused source-semantic regression for the v9.6.2 Universal Data Center Registry."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders.data_center_registry import (  # noqa: E402
    OBSERVATION_COLUMNS,
    REGISTRY_VERSION,
    assert_campus_foreign_keys,
    build_universal_data_center_registry,
)


def _umatilla_im3() -> pd.DataFrame:
    rows = [
        (216430.0, 45.920636947215385, -119.23183081222601),
        (211240.0, 45.9206470959813, -119.22998114824706),
        (225421.0, 45.92059673606088, -119.22880463543319),
        (217375.0, 45.920560017544766, -119.2270042542689),
        (16064.0, 45.9195152860519, -119.22609033029622),
        (216777.0, 45.79777488423153, -119.3619587184748),
        (216903.0, 45.79916503597342, -119.36665800187097),
        (215405.0, 45.799021058242246, -119.36173272208137),
        (13837.0, 45.799686801299124, -119.35844453141172),
        (13867.0, 45.797739077942104, -119.35891962466793),
        (218698.0, 45.88251751383444, -119.34165178350064),
        (218723.0, 45.8795325502289, -119.3416356310324),
        (218708.0, 45.88252485310848, -119.33969006466042),
        (211502.0, 45.80963736512278, -119.2686151324205),
        (212806.0, 45.808273441247415, -119.26861305294734),
    ]
    return pd.DataFrame([
        {
            "State": "OR", "County": "Umatilla County",
            "Operator": "Amazon Web Services", "Facility": "Amazon Web Services",
            "Square Feet": sqft, "Latitude": lat, "Longitude": lon, "Type": "building",
        }
        for sqft, lat, lon in rows
    ])


def _gigawatt_pdx80() -> pd.DataFrame:
    # This reproduces the retained Gigawatt source condition: the OSM record is
    # named, but country=XX/region omission leaves U.S. jurisdiction blank until
    # it is reconciled against co-located IM3 geometry.
    return pd.DataFrame([{
        "Observation ID": "gigawatt:osm-way-706776322",
        "Source Record ID": "osm-way-706776322",
        "Source": "Gigawatt Map retained export",
        "Source Class": "Observed footprint",
        "Observation Level": "building",
        "Name": "Amazon PDX80",
        "Operator": "amazon",
        "State": "",
        "County": "",
        "Latitude": 45.79780877762864,
        "Longitude": -119.36661621790076,
        "Published Capacity Estimate MW": 10.79,
        "Status": "Observed footprint",
        "Evidence Grade": "D",
    }])


def _weak_county_records() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Observation ID": f"weak-umatilla-{number}",
            "Source Record ID": f"weak-source-{number}",
            "Source": "weak project fixture",
            "Source Class": "Open project tracker",
            "Observation Level": "campus",
            "Name": "Umatilla County",
            "State": "OR",
            "County": "Umatilla County",
            "Latitude": lat,
            "Longitude": lon,
        }
        for number, (lat, lon) in enumerate([
            (45.92060, -119.22880),
            (45.88252, -119.34165),
            (45.70000, -119.50000),
        ], start=1)
    ])




def _cross_state_same_name() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Observation ID": "cielo-fl",
            "Source Record ID": "cielo-fl",
            "Source": "primary fixture",
            "Source Class": "Primary project evidence",
            "Observation Level": "campus",
            "Name": "Cielo Digital Infrastructure",
            "City": "Haines City",
            "State": "FL",
            "County": "Polk",
            "Latitude": 28.17875,
            "Longitude": -81.6457,
            "Status": "Proposed",
            "Evidence Grade": "A",
        },
        {
            "Observation ID": "cielo-ia",
            "Source Record ID": "cielo-ia",
            "Source": "primary fixture",
            "Source Class": "Primary project evidence",
            "Observation Level": "campus",
            "Name": "Cielo Digital Infrastructure",
            "City": "Des Moines",
            "State": "IA",
            "County": "Polk",
            "Latitude": 41.57011,
            "Longitude": -93.5839,
            "Status": "Proposed",
            "Evidence Grade": "A",
        },
    ])

def main() -> int:
    empty = pd.DataFrame(columns=OBSERVATION_COLUMNS)
    payload = build_universal_data_center_registry(
        _umatilla_im3(),
        gigawatt_observations=_gigawatt_pdx80(),
        fractracker_observations=_weak_county_records(),
        curated_observations=empty,
    )
    campuses = payload["campuses"]
    entities = payload["entities"]

    if REGISTRY_VERSION != "9.6.2":
        raise AssertionError("Registry version changed")
    if len(campuses) != 4:
        raise AssertionError(campuses[["Campus Name", "Campus Label", "Building Count"]].to_string(index=False))
    if not campuses["Campus ID"].is_unique or not campuses["Campus Label"].is_unique:
        raise AssertionError("Campus IDs or labels are not unique")
    if "Amazon PDX80 — Umatilla County, OR" not in set(campuses["Campus Label"].astype(str)):
        raise AssertionError("Named PDX80 evidence did not name its inferred campus")
    generic_labels = sorted(label for label in campuses["Campus Label"].astype(str) if label.startswith("Amazon Web Services"))
    if generic_labels != [
        "Amazon Web Services — Umatilla County, OR — Campus 1",
        "Amazon Web Services — Umatilla County, OR — Campus 2",
        "Amazon Web Services — Umatilla County, OR — Campus 3",
    ]:
        raise AssertionError(f"Unexpected Umatilla campus labels: {generic_labels}")
    if any(label.startswith("Umatilla County") for label in campuses["Campus Label"].astype(str)):
        raise AssertionError("County-only source records manufactured a campus")
    if int(entities["Entity Level"].eq("building").sum()) != 16:
        raise AssertionError("Building observations were promoted, deleted, or double-counted")

    pdx = payload["observations"].loc[payload["observations"]["Source Record ID"].eq("osm-way-706776322")]
    if len(pdx) != 1 or pdx.iloc[0]["State"] != "OR" or pdx.iloc[0]["County"] != "Umatilla County":
        raise AssertionError("PDX80 U.S. jurisdiction was not reconciled from IM3 geometry")

    cross_state = build_universal_data_center_registry(
        pd.DataFrame(),
        gigawatt_observations=empty,
        fractracker_observations=empty,
        curated_observations=_cross_state_same_name(),
    )["campuses"]
    cross_state_labels = set(cross_state["Campus Label"].astype(str))
    expected_cross_state = {
        "Cielo Digital Infrastructure — Haines City, FL",
        "Cielo Digital Infrastructure — Des Moines, IA",
    }
    if cross_state_labels != expected_cross_state:
        raise AssertionError(f"Cross-state campus labels are ambiguous: {sorted(cross_state_labels)}")

    full = campuses[["Campus ID"]].copy()
    assert_campus_foreign_keys(campuses, full, domain="water", allow_subset=False)
    assert_campus_foreign_keys(campuses, full.iloc[:2], domain="connectivity", allow_subset=True)

    single_building = pd.DataFrame([{
        "State": "TX",
        "County": "Example County",
        "Operator": "Example Operator",
        "Facility": "Example Building",
        "Latitude": 32.80,
        "Longitude": -96.80,
        "Type": "building",
        "Square Feet": 200000.0,
    }])
    building_payload = build_universal_data_center_registry(
        single_building,
        gigawatt_observations=empty,
        fractracker_observations=empty,
        curated_observations=empty,
    )
    if len(building_payload["campuses"]) != 0 or len(building_payload["unresolved_observations"]) != 1:
        raise AssertionError("A lone building observation manufactured a campus")

    point_only = pd.DataFrame([{
        "State": "DC",
        "County": "District of Columbia",
        "Operator": "Example Operator",
        "Facility": "Example Point Data Center",
        "Latitude": 38.90,
        "Longitude": -77.03,
        "Type": "point",
    }])
    point_payload = build_universal_data_center_registry(
        point_only,
        gigawatt_observations=empty,
        fractracker_observations=empty,
        curated_observations=empty,
    )
    if len(point_payload["campuses"]) != 0 or len(point_payload["unresolved_observations"]) != 1:
        raise AssertionError("An uncorroborated source point manufactured a campus")

    print(
        "PASS  v9.6.2 source-first registry · 15 retained IM3 AWS buildings + PDX80 → "
        "4 Umatilla campuses · cross-state labels expose jurisdiction · county-only records create zero campuses · building grain preserved · lone buildings and point-only records remain unresolved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
