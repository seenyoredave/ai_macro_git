#!/usr/bin/env python3
"""Page-level regression for the v9.6.0 Data Centers geography architecture."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rendering.charts_data_center import data_center_map  # noqa: E402


def main() -> int:
    page = (ROOT / "rendering" / "data_center.py").read_text(encoding="utf-8")
    spatial = (ROOT / "rendering" / "spatial.py").read_text(encoding="utf-8")
    charts = (ROOT / "rendering" / "charts_data_center.py").read_text(encoding="utf-8")

    if "render_spatial_explorer(" not in page:
        raise AssertionError("Data Centers page is not using the shared canonical campus explorer")
    if "go.Choropleth" in charts:
        raise AssertionError("Data Centers page retained the state choropleth geography")
    if 'on_select="rerun"' not in spatial:
        raise AssertionError("Canonical campus map is not interactive")

    fixture = pd.DataFrame([{
        "Campus ID": "campus:test",
        "Campus Name": "Test Campus",
        "Campus Label": "Test Campus — Loudoun County, VA",
        "Operator": "Test Operator",
        "State": "VA",
        "County": "Loudoun County",
        "Latitude": 39.0,
        "Longitude": -77.5,
        "Status": "Operational",
        "Building Count": 2,
        "Identity Confidence": "high",
    }])
    figure = data_center_map(fixture)
    if len(figure.data) != 1 or figure.data[0].type != "scattermap":
        raise AssertionError("Data Centers geography did not render a canonical campus point")
    if str(figure.data[0].customdata[0][0]) != "campus:test":
        raise AssertionError("Data Centers geography lost Campus ID in point selection data")

    print("PASS  Data Centers page · one shared interactive campus explorer · no old choropleth/map stack")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
