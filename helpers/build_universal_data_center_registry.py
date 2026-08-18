#!/usr/bin/env python3
"""Build and retain the v9.6.0 Universal Data Center Registry from retained sources."""

from __future__ import annotations

from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders.data_center_registry import (  # noqa: E402
    build_registry_from_retained_sources,
    persist_universal_data_center_registry,
    load_retained_universal_data_center_registry,
)


def main() -> int:
    started = time.perf_counter()
    payload = build_registry_from_retained_sources()
    persist_universal_data_center_registry(payload, force=True)
    elapsed = time.perf_counter() - started

    retained_started = time.perf_counter()
    retained = load_retained_universal_data_center_registry(require_current=True)
    retained_elapsed = time.perf_counter() - retained_started
    if retained is None:
        raise AssertionError("Persisted Universal Data Center Registry failed retained reload verification")

    built_ids = set(payload["campuses"]["Campus ID"].astype(str))
    retained_ids = set(retained["campuses"]["Campus ID"].astype(str))
    if built_ids != retained_ids:
        raise AssertionError("Persisted campus universe changed during serialization")

    built_membership = sorted(
        zip(payload["membership"]["Observation ID"].astype(str), payload["membership"]["Campus ID"].astype(str))
    ) if not payload["membership"].empty else []
    retained_membership = sorted(
        zip(retained["membership"]["Observation ID"].astype(str), retained["membership"]["Campus ID"].astype(str))
    ) if not retained["membership"].empty else []
    if built_membership != retained_membership:
        raise AssertionError("Persisted campus membership changed during serialization")

    summary = dict(payload.get("summary") or {})
    print(
        "PASS  Universal Data Center Registry retained · "
        f"{int(summary.get('campuses', 0) or 0):,} campuses · "
        f"{int(summary.get('facility_entities', 0) or 0):,} facilities · "
        f"{int(summary.get('building_entities', 0) or 0):,} buildings · "
        f"{int(summary.get('unresolved_observations', 0) or 0):,} unresolved observations · "
        f"{elapsed:.2f}s build · {retained_elapsed:.2f}s verified retained reload"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
