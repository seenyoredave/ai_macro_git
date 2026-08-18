from __future__ import annotations

from functools import lru_cache
import json
from math import atan, exp, log, pi, tan
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
STATE_GEOJSON_PATH = ROOT / "assets" / "geo" / "us_states.geojson"

NATIONAL_CENTER = {"lat": 39.1, "lon": -98.7}
# A national opening camera, not a navigation constraint. At normal desktop
# widths this frames the United States without pulling the Atlantic/Africa into
# the initial viewport; once rendered the user may pan and zoom freely.
NATIONAL_ZOOM = 3.05
MAP_STYLE = "carto-darkmatter"

_STATE_VIEW_OVERRIDES = {
    "AK": {
        "center": {"lat": 64.4, "lon": -152.5},
        "zoom": 3.05,
    },
    "HI": {
        "center": {"lat": 20.7, "lon": -157.3},
        "zoom": 5.35,
    },
}


@lru_cache(maxsize=1)
def state_geojson() -> dict:
    if not STATE_GEOJSON_PATH.exists():
        return {"type": "FeatureCollection", "features": []}
    with STATE_GEOJSON_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("type") != "FeatureCollection":
        return {"type": "FeatureCollection", "features": []}
    return payload


def _feature_state(feature: dict) -> str:
    properties = feature.get("properties") or {}
    return str(properties.get("STUSPS") or feature.get("id") or "").strip().upper()


@lru_cache(maxsize=64)
def state_feature_collection(state: str) -> dict:
    code = str(state or "").strip().upper()
    features = [feature for feature in state_geojson().get("features", []) if _feature_state(feature) == code]
    return {"type": "FeatureCollection", "features": features}


def _coordinate_pairs(value):
    if not isinstance(value, (list, tuple)):
        return
    if len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
        yield float(value[0]), float(value[1])
        return
    for child in value:
        yield from _coordinate_pairs(child)


@lru_cache(maxsize=64)
def state_geometry_bounds(state: str) -> tuple[float, float, float, float] | None:
    code = str(state or "").strip().upper()
    features = state_feature_collection(code).get("features", [])
    coordinates: list[tuple[float, float]] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        coordinates.extend(_coordinate_pairs(geometry.get("coordinates")) or [])
    if not coordinates:
        return None
    lon = np.asarray([point[0] for point in coordinates], dtype=float)
    lat = np.asarray([point[1] for point in coordinates], dtype=float)
    finite = np.isfinite(lon) & np.isfinite(lat)
    if not finite.any():
        return None
    return float(lon[finite].min()), float(lat[finite].min()), float(lon[finite].max()), float(lat[finite].max())


def _mercator_lat_fraction(latitude: float) -> float:
    latitude = min(85.0, max(-85.0, float(latitude)))
    sin_value = np.sin(np.deg2rad(latitude))
    return float((1.0 - np.log((1.0 + sin_value) / (1.0 - sin_value)) / (2.0 * pi)) / 2.0)


def _fit_zoom(west: float, south: float, east: float, north: float, *, width: int, height: int) -> float:
    lon_fraction = max((east - west) / 360.0, 1e-9)
    lat_fraction = max(abs(_mercator_lat_fraction(north) - _mercator_lat_fraction(south)), 1e-9)
    tile = 512.0
    usable_width = max(320.0, float(width) * 0.76)
    usable_height = max(260.0, float(height) * 0.72)
    zoom_x = log(usable_width / tile / lon_fraction, 2)
    zoom_y = log(usable_height / tile / lat_fraction, 2)
    return float(np.clip(min(zoom_x, zoom_y), 3.1, 8.0))



def _view_payload(*, center: dict, zoom: float, geography: str) -> dict:
    # Deliberately omit layout.map.bounds. Plotly documents bounds as the
    # mechanism that prevents panning/zooming outside a geographic box; the
    # research maps instead use a starting camera and otherwise remain free.
    return {
        "style": MAP_STYLE,
        "center": dict(center),
        "zoom": float(zoom),
        "bearing": 0.0,
        "pitch": 0.0,
        # Preserve manual camera changes through reruns within one geography,
        # while a US/state change receives its intended opening camera.
        "uirevision": f"ai-macro-map-camera:{geography or 'US'}",
    }


def map_view(state: str | None, *, height: int = 575, width: int = 1080) -> dict:
    code = str(state or "").strip().upper()
    if not code:
        return _view_payload(center=NATIONAL_CENTER, zoom=NATIONAL_ZOOM, geography="US")

    override = _STATE_VIEW_OVERRIDES.get(code)
    if override:
        return _view_payload(
            center=override["center"],
            zoom=float(override["zoom"]),
            geography=code,
        )

    bounds = state_geometry_bounds(code)
    if bounds is None:
        return _view_payload(center=NATIONAL_CENTER, zoom=NATIONAL_ZOOM, geography="US")

    west, south, east, north = bounds
    center = {"lat": (south + north) / 2.0, "lon": (west + east) / 2.0}
    zoom = _fit_zoom(west, south, east, north, width=width, height=height)
    return _view_payload(center=center, zoom=zoom, geography=code)


def state_boundary_layer(state: str | None = None, *, emphasized: bool = False) -> dict | None:
    code = str(state or "").strip().upper()
    source = state_feature_collection(code) if code else state_geojson()
    if not source.get("features"):
        return None
    layer = {
        "sourcetype": "geojson",
        "source": source,
        "type": "line",
        "color": "rgba(226,232,240,0.92)" if emphasized else "rgba(148,163,184,0.42)",
        "line": {"width": 2.4 if emphasized else 0.8},
        "opacity": 1.0,
    }
    if not emphasized:
        layer["below"] = "traces"
    return layer


def map_layers(state: str | None = None) -> list[dict]:
    layers: list[dict] = []
    national = state_boundary_layer(None, emphasized=False)
    if national:
        layers.append(national)
    if state:
        selected = state_boundary_layer(state, emphasized=True)
        if selected:
            layers.append(selected)
    return layers


__all__ = [
    "MAP_STYLE",
    "map_layers",
    "map_view",
    "state_feature_collection",
    "state_geojson",
    "state_geometry_bounds",
]
