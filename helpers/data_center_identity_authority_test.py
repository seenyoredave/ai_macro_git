#!/usr/bin/env python3
"""Stop-the-line authority test for the v9.6.2 Universal Data Center Registry."""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN = (
    "loaders.facility_registry_common",
    "loaders.facility_sources",
    "loaders.facility_identity",
    "loaders.campus_registry",
    "loaders.facility_registry_loader",
    '"facility_registry"', "'facility_registry'",
    '"campus_registry"', "'campus_registry'",
    '"facility_observations"', "'facility_observations'",
    '"facility_coverage"', "'facility_coverage'",
    '"facility_identity_decisions"', "'facility_identity_decisions'",
    "build_campus_registry",
    "normalize_facility_observations",
    "build_facility_observations",
    "load_curated_facility_records",
    "load_gigawatt_facility_records",
    "load_fractracker_facility_records",
    "_assign_registry_ids",
    "FACILITY_SIZE_METRICS",
    "facility_map_legend_items",
    "data_center_state_detail_map",
    "data_center_state_footprint",
    "data_center_state_published_capacity",
    "data_center_operator_label",
    "force_facility_refresh",
    "allow_facility_live",
    "data/facility_registry_seed.csv",
    "data/facility_identity_decisions.csv",
    "helpers/apply_v9_6_registry_overhaul.py",
)

EXEMPT = {
    Path("helpers/data_center_identity_authority_test.py"),
}

OBSOLETE = (
    "loaders/facility_registry_common.py",
    "loaders/facility_sources.py",
    "loaders/facility_identity.py",
    "loaders/campus_registry.py",
    "loaders/facility_registry_loader.py",
    "data/facility_registry_seed.csv",
    "data/facility_identity_decisions.csv",
)

IDENTITY_FUNCTIONS = (
    "build_universal_data_center_registry",
    "_resolve_clusters",
    "_cluster_unassigned_buildings",
    "_cluster_unassigned_facilities",
    "_assign_campus_labels",
)


def _python_paths() -> list[Path]:
    paths = [ROOT / "ai_macro.py"]
    for directory in ("analytics", "automation", "config", "loaders", "rendering", "water", "helpers", "developer", "tooling"):
        base = ROOT / directory
        if base.exists():
            paths.extend(base.rglob("*.py"))
    return [path for path in sorted(set(paths)) if path.exists()]


def main() -> int:
    offenders: list[tuple[str, list[str]]] = []
    function_owners: dict[str, list[str]] = {name: [] for name in IDENTITY_FUNCTIONS}

    for path in _python_paths():
        relative = path.relative_to(ROOT)
        text = path.read_text(encoding="utf-8", errors="replace")
        if relative not in EXEMPT:
            hits = [token for token in FORBIDDEN if token in text]
            if hits:
                offenders.append((str(relative), hits))
        for name in IDENTITY_FUNCTIONS:
            if re.search(rf"(?m)^def\s+{re.escape(name)}\s*\(", text):
                function_owners[name].append(str(relative))

    if offenders:
        for path, hits in offenders:
            print(f"FAIL  {path}: {', '.join(hits)}")
        return 1

    obsolete = [relative for relative in OBSOLETE if (ROOT / relative).exists()]
    if obsolete:
        for relative in obsolete:
            print(f"FAIL  obsolete identity artifact still exists: {relative}")
        return 2

    registry_path = ROOT / "loaders" / "data_center_registry.py"
    if not registry_path.exists():
        print("FAIL  loaders/data_center_registry.py is missing")
        return 3
    registry_source = registry_path.read_text(encoding="utf-8")
    if 'REGISTRY_VERSION = "9.6.2"' not in registry_source:
        print("FAIL  Universal Data Center Registry version is not 9.6.2")
        return 4

    for name, owners in function_owners.items():
        if owners != ["loaders/data_center_registry.py"]:
            print(f"FAIL  identity function {name} owners: {owners}")
            return 5

    required_registry_rules = (
        '"Observation Level"].eq("campus")',
        'record["level"] == "building"',
        '_distinct_physical_building_count',
        'return [], list(indexes)',
        'A lone building',
    )
    missing = [token for token in required_registry_rules if token not in registry_source]
    if missing:
        print(f"FAIL  source-grain identity rules are incomplete: {missing}")
        return 6

    charts = (ROOT / "rendering" / "charts_data_center.py").read_text(encoding="utf-8")
    spatial = (ROOT / "rendering" / "spatial.py").read_text(encoding="utf-8")
    data_center = (ROOT / "rendering" / "data_center.py").read_text(encoding="utf-8")
    visual = (ROOT / "rendering" / "visual_system.py").read_text(encoding="utf-8")
    map_geometry = (ROOT / "rendering" / "map_geometry.py").read_text(encoding="utf-8")
    if "go.Choropleth" in charts:
        print("FAIL  Data Center geography still contains a state choropleth substitute")
        return 7
    if "data_center_map(" not in spatial or "render_spatial_explorer(" not in data_center:
        print("FAIL  Data Center and shared spatial surfaces do not share the campus map")
        return 8
    if 'on_select="rerun"' not in spatial or "selection_points(" not in spatial:
        print("FAIL  shared campus map is not wired for point selection")
        return 9
    if "def selection_points(" not in visual or "on_select" not in visual:
        print("FAIL  map interaction plumbing is duplicated outside the shared visual system")
        return 10
    if "def map_view(" not in map_geometry or "def map_layers(" not in map_geometry:
        print("FAIL  Data Centers and Water do not share one map viewport/boundary authority")
        return 10
    if "map_view(" not in charts or "map_layers(" not in charts:
        print("FAIL  Data Center geography bypasses the shared map viewport authority")
        return 10

    water_renderer = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    if "from analytics.water_campus import campus_water_dossier, county_water_exposure_profile" not in water_renderer:
        print("FAIL  Water still routes campus identity through legacy facility-grain helpers")
        return 11

    infrastructure = (ROOT / "loaders" / "infrastructure_loader.py").read_text(encoding="utf-8")
    if "load_retained_universal_data_center_registry(require_current=True)" not in infrastructure:
        print("FAIL  normal startup does not consume the retained universal registry")
        return 12
    retained_pos = infrastructure.find("load_retained_universal_data_center_registry(require_current=True)")
    source_load_pos = infrastructure.find("load_fractracker_data_center_observations(", retained_pos)
    if retained_pos < 0 or source_load_pos < retained_pos:
        print("FAIL  raw identity sources are loaded before retained registry resolution")
        return 13

    print(
        "PASS  one data-center identity authority · source grain enforced · "
        "one campus map · retained registry is runtime authority · no legacy code/data names"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
