#!/usr/bin/env python3
"""Performance and determinism gate for the source-first v9.6.0 registry."""

from __future__ import annotations

from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders.data_center_registry import OBSERVATION_COLUMNS, build_universal_data_center_registry  # noqa: E402

NATIONAL_COUNT = 2000
DENSE_COUNT = 500
NATIONAL_LIMIT_SECONDS = 8.0
DENSE_LIMIT_SECONDS = 20.0


def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=OBSERVATION_COLUMNS)


def _national_fixture(count: int) -> pd.DataFrame:
    rows = []
    states = ["OR", "VA", "TX", "AZ", "OH"]
    for index in range(count):
        rows.append({
            "State": states[index % len(states)],
            "County": f"Performance County {index}",
            "Operator": f"Performance Operator {index}",
            "Facility": f"Performance Campus {index}",
            "Latitude": 25.0 + (index % 300) * 0.08,
            "Longitude": -124.0 + (index // 300) * 0.08,
            "Type": "campus",
            "Square Feet": 200000.0,
        })
    return pd.DataFrame(rows)


def _dense_fixture(count: int) -> pd.DataFrame:
    rng = np.random.default_rng(960)
    return pd.DataFrame({
        "State": ["VA"] * count,
        "County": ["Loudoun County"] * count,
        "Operator": ["Performance Operator"] * count,
        "Facility": ["Performance Operator"] * count,
        "Latitude": 38.80 + rng.random(count) * 0.50,
        "Longitude": -77.70 + rng.random(count) * 0.50,
        "Type": ["building"] * count,
        "Square Feet": rng.integers(50000, 300000, count),
    })


def _build(frame: pd.DataFrame):
    empty = _empty()
    return build_universal_data_center_registry(
        frame,
        fractracker_observations=empty,
        gigawatt_observations=empty,
        curated_observations=empty,
    )


def _membership_signature(payload: dict) -> list[str]:
    campuses = payload["campuses"]
    return sorted(campuses.get("Member Observation IDs", pd.Series(dtype=str)).astype(str))


def main() -> int:
    national = _national_fixture(NATIONAL_COUNT)
    started = time.perf_counter()
    national_payload = _build(national)
    national_elapsed = time.perf_counter() - started
    if len(national_payload["campuses"]) != NATIONAL_COUNT:
        raise AssertionError("Distributed performance fixture changed campus count")
    if national_elapsed > NATIONAL_LIMIT_SECONDS:
        raise AssertionError(f"Distributed registry build took {national_elapsed:.2f}s; limit {NATIONAL_LIMIT_SECONDS:.1f}s")

    dense = _dense_fixture(DENSE_COUNT)
    started = time.perf_counter()
    dense_payload = _build(dense)
    dense_elapsed = time.perf_counter() - started
    if dense_elapsed > DENSE_LIMIT_SECONDS:
        raise AssertionError(f"Dense-county registry build took {dense_elapsed:.2f}s; limit {DENSE_LIMIT_SECONDS:.1f}s")

    deterministic = dense.head(300).copy()
    deterministic_a = _build(deterministic)
    deterministic_b = _build(deterministic.sample(frac=1.0, random_state=960).reset_index(drop=True))
    if _membership_signature(deterministic_a) != _membership_signature(deterministic_b):
        raise AssertionError("Registry membership depends on source row order")

    print(
        "PASS  v9.6.0 registry performance · "
        f"{NATIONAL_COUNT:,} distributed observations in {national_elapsed:.2f}s · "
        f"{DENSE_COUNT:,} dense-county observations in {dense_elapsed:.2f}s · deterministic membership"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
