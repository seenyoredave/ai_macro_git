#!/usr/bin/env python3
"""Water county-map interaction and state-outline contract for v9.6.0."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rendering.charts_water import water_county_drought_map  # noqa: E402
from rendering.map_geometry import map_view  # noqa: E402


def _has_bounds(fig) -> bool:
    bounds = fig.layout.map.bounds
    return any(getattr(bounds, field, None) is not None for field in ("west", "east", "south", "north"))


def main() -> int:
    drought = pd.DataFrame([
        {
            "FIPS": "41059", "Snapshot Date": "2026-08-12",
            "D1+ Area Percent": 10.0, "D2+ Area Percent": 5.0,
            "D3+ Area Percent": 0.0, "D4 Area Percent": 0.0,
        },
    ])
    campuses = pd.DataFrame([
        {
            "Campus ID": "campus:or-1", "Campus Label": "AWS Umatilla — Umatilla County, OR",
            "Operator": "Amazon Web Services", "State": "OR", "County": "Umatilla County",
            "Status": "Operational", "Latitude": 45.80, "Longitude": -119.36,
            "Published Capacity Estimate MW": 120.0, "FIPS": "41059",
            "County D2+ Area Percent": 5.0, "PWS Service Area Overlap": True,
            "Direct Water Evidence": False,
        },
    ])

    national = water_county_drought_map(drought, campuses, height=570)
    if not national.data or national.data[0].type != "choroplethmap":
        raise AssertionError("Water national county geography must use the shared MapLibre surface")
    if str(national.layout.map.style) != "carto-darkmatter":
        raise AssertionError("Water national map lost the shared tile basemap")
    if len(national.layout.map.layers) != 1:
        raise AssertionError("Water national map lost the national state-boundary context layer")
    if _has_bounds(national):
        raise AssertionError("Water national map still imposes geographic pan/zoom bounds")

    national_view = map_view(None, height=570)
    if "bounds" in national_view:
        raise AssertionError("Water national map still inherits geographic interaction bounds")
    if float(national_view["zoom"]) < 3.0:
        raise AssertionError("Water national map opens too far out for a US research view")
    if national_view.get("uirevision") != "ai-macro-map-camera:US":
        raise AssertionError("Water national camera is not geography-scoped")

    state = water_county_drought_map(drought, campuses, state="OR", height=610)
    trace_types = [trace.type for trace in state.data]
    if trace_types != ["choroplethmap", "scattermap"]:
        raise AssertionError(f"Water state view has unexpected map layers: {trace_types}")
    if len(state.layout.map.layers) < 2:
        raise AssertionError("Water state view is missing the emphasized state outline")
    if _has_bounds(state):
        raise AssertionError("Water state map still imposes geographic pan/zoom bounds")
    state_view = map_view("OR", height=610)
    if "bounds" in state_view:
        raise AssertionError("Water state camera must not publish interaction bounds")
    if state_view.get("uirevision") != "ai-macro-map-camera:OR":
        raise AssertionError("Water state camera does not reset when geography changes")
    custom = state.data[1].customdata
    if custom is None or str(custom[0][0]) != "campus:or-1":
        raise AssertionError("Water campus markers lost canonical Campus IDs")

    water_source = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    visual = (ROOT / "rendering" / "visual_system.py").read_text(encoding="utf-8")
    if 'merged["scrollZoom"] = True' not in visual:
        raise AssertionError("Shared map renderer does not enable wheel/two-finger zoom")
    if "scrollZoom" in water_source:
        raise AssertionError("Water map still carries a conflicting local scroll-zoom setting")

    print(
        "PASS  water map viewport · US opening camera · unrestricted pan · wheel/pinch zoom · "
        "visible selected-state outline · canonical campus points"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
