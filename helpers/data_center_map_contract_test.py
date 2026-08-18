#!/usr/bin/env python3
"""Interactive-map contract for the v9.6.0 universal campus geography."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rendering.charts_data_center import data_center_map  # noqa: E402
from rendering.map_geometry import map_layers, map_view, state_feature_collection  # noqa: E402


def _fixture() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Campus ID": "campus:or-1", "Campus Name": "AWS Umatilla", "Campus Label": "AWS Umatilla — Umatilla County, OR",
            "Operator": "Amazon Web Services", "State": "OR", "County": "Umatilla County", "Status": "Operational",
            "Latitude": 45.80, "Longitude": -119.36, "Building Count": 6, "Published Capacity Estimate MW": 120.0,
            "Identity Confidence": "high",
        },
        {
            "Campus ID": "campus:va-1", "Campus Name": "Example Virginia", "Campus Label": "Example Virginia — Loudoun County, VA",
            "Operator": "Example Operator", "State": "VA", "County": "Loudoun County", "Status": "Under construction",
            "Latitude": 39.01, "Longitude": -77.48, "Building Count": 3, "Published Capacity Estimate MW": 80.0,
            "Identity Confidence": "medium",
        },
        {
            "Campus ID": "campus:tx-1", "Campus Name": "Example Texas", "Campus Label": "Example Texas — Dallas County, TX",
            "Operator": "Example Operator", "State": "TX", "County": "Dallas County", "Status": "Proposed",
            "Latitude": 32.80, "Longitude": -96.80, "Building Count": 2, "Published Capacity Estimate MW": 50.0,
            "Identity Confidence": "high",
        },
    ])


def _campus_ids(fig) -> set[str]:
    ids: set[str] = set()
    for trace in fig.data:
        custom = getattr(trace, "customdata", None)
        if custom is None:
            continue
        for row in custom:
            if len(row):
                ids.add(str(row[0]))
    return ids


def _has_bounds(fig) -> bool:
    bounds = fig.layout.map.bounds
    return any(getattr(bounds, field, None) is not None for field in ("west", "east", "south", "north"))


def main() -> int:
    campuses = _fixture()
    national = data_center_map(campuses, size_by="Published capacity estimate", selected_campus_id="campus:or-1")
    if not national.data or any(trace.type != "scattermap" for trace in national.data):
        raise AssertionError("Canonical campus geography must render selectable MapLibre campus points")
    if _campus_ids(national) != set(campuses["Campus ID"]):
        raise AssertionError("Map customdata lost canonical Campus IDs")
    if str(national.layout.map.style) != "carto-darkmatter":
        raise AssertionError("Campus geography lost its professional tile basemap")
    if _has_bounds(national):
        raise AssertionError("National map still imposes geographic pan/zoom bounds")
    if str(national.layout.dragmode) != "pan":
        raise AssertionError("Campus map is not configured as a free pan surface")

    national_view = map_view(None, height=560)
    if abs(float(national_view["center"]["lon"]) + 98.7) > 0.5 or abs(float(national_view["center"]["lat"]) - 39.1) > 0.5:
        raise AssertionError("National map camera is not centered on the United States")
    if float(national_view["zoom"]) < 3.0:
        raise AssertionError("National map opens too far out for a US research view")
    if "bounds" in national_view:
        raise AssertionError("Shared map camera must not publish interaction bounds")
    if national_view.get("uirevision") != "ai-macro-map-camera:US":
        raise AssertionError("National map camera revision is not geography-scoped")

    state = data_center_map(campuses, state="OR")
    if _campus_ids(state) != {"campus:or-1"}:
        raise AssertionError("State drilldown did not restrict the canonical campus population")
    if len(state.layout.map.layers) < 2:
        raise AssertionError("State drilldown is missing the emphasized state boundary layer")
    if _has_bounds(state):
        raise AssertionError("State drilldown still imposes geographic pan/zoom bounds")
    state_view = map_view("OR", height=560)
    if not (3.0 < float(state_view["zoom"]) < 8.5):
        raise AssertionError("State drilldown did not receive a local opening zoom")
    if "bounds" in state_view:
        raise AssertionError("State drilldown must remain free to pan beyond the selected state")
    if state_view.get("uirevision") != "ai-macro-map-camera:OR":
        raise AssertionError("State map camera revision does not reset on geography change")
    if not state_feature_collection("OR").get("features"):
        raise AssertionError("Oregon outline geometry is unavailable")
    if len(map_layers("OR")) != 2:
        raise AssertionError("State map must contain national context plus selected-state outline")

    spatial = (ROOT / "rendering" / "spatial.py").read_text(encoding="utf-8")
    visual = (ROOT / "rendering" / "visual_system.py").read_text(encoding="utf-8")
    if 'on_select="rerun"' not in spatial or 'selection_mode="points"' not in spatial:
        raise AssertionError("Campus map click selection is not wired through Streamlit")
    if "def selection_points(" not in visual:
        raise AssertionError("Map selection event parsing is not centralized")
    if 'if role == "map":' not in visual or 'merged["scrollZoom"] = True' not in visual:
        raise AssertionError("Map wheel/two-finger zoom is not centralized in the shared renderer")
    if "scrollZoom" in spatial:
        raise AssertionError("Spatial map still carries a redundant local zoom configuration")

    print(
        "PASS  campus map contract · US opening camera · unrestricted two-axis pan · "
        "wheel/pinch zoom · geography-scoped camera reset · canonical Campus IDs · emphasized state outline"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
