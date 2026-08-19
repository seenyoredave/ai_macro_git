#!/usr/bin/env python3
"""Cross-domain Campus-ID integration contract for v9.6.2."""

from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.spatial_context import attach_water_context  # noqa: E402
from loaders.data_center_registry import (  # noqa: E402
    assert_campus_foreign_keys,
    load_retained_universal_data_center_registry,
)
from loaders.water_loader import load_water_utilization_data  # noqa: E402


def main() -> int:
    payload = load_retained_universal_data_center_registry(require_current=True)
    if payload is None:
        raise AssertionError(
            "Retained Universal Data Center Registry is absent or stale; "
            "run helpers/build_universal_data_center_registry.py first"
        )
    campuses = payload["campuses"]
    if campuses.empty:
        raise AssertionError("Retained Universal Data Center Registry has no campuses")

    infrastructure = {
        "data_center_registry": campuses,
        "data_center_entities": payload["entities"],
        "data_center_observations": payload["observations"],
        "data_center_membership": payload["membership"],
        "data_center_unresolved_observations": payload["unresolved_observations"],
        "data_center_registry_summary": payload["summary"],
    }
    water = load_water_utilization_data(force_refresh=False, allow_live=False)
    enriched_infrastructure, water = attach_water_context(infrastructure, water)
    water_campuses = water.get("campus_context")
    if not isinstance(water_campuses, pd.DataFrame):
        raise AssertionError("Water did not return a campus-grain context")
    assert_campus_foreign_keys(campuses, water_campuses[["Campus ID"]], domain="water", allow_subset=False)

    central_after = enriched_infrastructure.get("data_center_registry")
    if not isinstance(central_after, pd.DataFrame):
        raise AssertionError("Water enrichment removed the central registry")
    if list(central_after["Campus ID"].astype(str)) != list(campuses["Campus ID"].astype(str)):
        raise AssertionError("Water enrichment mutated the Campus-ID set")

    registry_ids = set(campuses["Campus ID"].astype(str))
    water_ids = set(water_campuses["Campus ID"].astype(str))
    if registry_ids != water_ids:
        raise AssertionError(
            f"Cross-domain universe drift: registry={len(registry_ids):,}, water={len(water_ids):,}"
        )

    for relative, required in (
        ("rendering/power.py", 'get("data_center_registry")'),
        ("rendering/spatial.py", 'get("data_center_registry")'),
        ("rendering/evidence.py", 'get("data_center_registry")'),
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        if required not in text:
            raise AssertionError(f"{relative} does not consume the universal registry directly")

    print(
        "PASS  cross-domain registry integration · "
        f"{len(registry_ids):,} Campus IDs identical in Data Centers and Water · "
        "Power/Spatial/Evidence wired to the same registry"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
