#!/usr/bin/env python3
"""Water must preserve the universal campus grain without reconstructing identity."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.water_campus import campus_water_dossier, county_water_exposure_profile  # noqa: E402


def main() -> int:
    campuses = pd.DataFrame([
        {
            "Campus ID": "campus:1", "Campus Name": "Campus A", "Campus Label": "Campus A — Umatilla County",
            "State": "OR", "County": "Umatilla County", "FIPS": "41059", "County D2+ Area Percent": 50.0,
        },
        {
            "Campus ID": "campus:2", "Campus Name": "Campus B", "Campus Label": "Campus B — Umatilla County",
            "State": "OR", "County": "Umatilla", "FIPS": "41059", "County D2+ Area Percent": 50.0,
        },
    ])
    dossier = campus_water_dossier(campuses)
    if list(dossier["Campus ID"]) != ["campus:1", "campus:2"]:
        raise AssertionError("Water dossier changed or duplicated Campus IDs")
    county = county_water_exposure_profile(campuses)
    if len(county) != 1 or int(county.iloc[0]["Campuses"]) != 2:
        raise AssertionError("Water county aggregation did not use FIPS-first Campus-ID counts")

    water_source = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    if "from analytics.water_campus import campus_water_dossier, county_water_exposure_profile" not in water_source:
        raise AssertionError("Water renderer is still using legacy facility-grain campus helpers")
    if "campus_display_labels(subset)" not in water_source:
        raise AssertionError("Water selector is not using Campus Labels")

    print("PASS  Water campus contract · one dossier row per Campus ID · FIPS-first county counts · campus labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
