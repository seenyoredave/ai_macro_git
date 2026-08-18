from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

try:
    import streamlit  # noqa: F401
except ModuleNotFoundError:
    import types
    stub = types.ModuleType("streamlit")
    class _CacheData:
        def __call__(self, *args, **kwargs):
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return args[0]
            return lambda fn: fn
    stub.cache_data = _CacheData()
    sys.modules["streamlit"] = stub

from loaders import infrastructure_loader
from loaders.data_center_registry import build_universal_data_center_registry, load_fractracker_data_center_observations


def check_construction_provenance_transaction() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        construction = root / "infrastructure_construction_history.csv"
        macro = root / "data_center_construction_history.csv"
        manifest = root / "source_manifest.csv"
        pd.DataFrame(
            [
                {
                    "source_id": "census-vip-construction",
                    "derived_artifacts": "data/infrastructure_construction_history.csv",
                    "derived_sha256": "stale",
                    "coverage_period": "old",
                    "retrieval_date": "old",
                }
            ]
        ).to_csv(manifest, index=False)

        original = (
            infrastructure_loader.CONSTRUCTION_HISTORY_PATH,
            infrastructure_loader.DATA_CENTER_CONSTRUCTION_HISTORY_PATH,
            infrastructure_loader.INFRASTRUCTURE_SOURCE_MANIFEST_PATH,
            infrastructure_loader.repository_writes_enabled,
        )
        try:
            infrastructure_loader.CONSTRUCTION_HISTORY_PATH = construction
            infrastructure_loader.DATA_CENTER_CONSTRUCTION_HISTORY_PATH = macro
            infrastructure_loader.INFRASTRUCTURE_SOURCE_MANIFEST_PATH = manifest
            infrastructure_loader.repository_writes_enabled = lambda: True
            frame = pd.DataFrame(
                {
                    "Observation Date": pd.to_datetime(["2026-06-01", "2026-07-01"]),
                    "Data Center Construction": [10.0, 11.0],
                    "Private Nonresidential Construction": [100.0, 101.0],
                    "Computer, Electronic & Electrical Manufacturing Construction": [20.0, 21.0],
                    "Private Manufacturing Construction": [30.0, 31.0],
                    "Electric Power Construction": [40.0, 41.0],
                    "Communication Construction": [50.0, 51.0],
                    "Public Highway and Street Construction": [60.0, 61.0],
                    "Public Transportation Construction": [70.0, 71.0],
                    "Public Water Supply Construction": [80.0, 81.0],
                    "Public Sewage and Waste Disposal Construction": [90.0, 91.0],
                }
            )
            infrastructure_loader._persist_construction_bundle(frame)
        finally:
            (
                infrastructure_loader.CONSTRUCTION_HISTORY_PATH,
                infrastructure_loader.DATA_CENTER_CONSTRUCTION_HISTORY_PATH,
                infrastructure_loader.INFRASTRUCTURE_SOURCE_MANIFEST_PATH,
                infrastructure_loader.repository_writes_enabled,
            ) = original

        actual = sha256(construction.read_bytes()).hexdigest()
        row = pd.read_csv(manifest).iloc[0]
        assert row["derived_sha256"] == actual, "construction refresh left a stale provenance checksum"
        assert row["coverage_period"] == "2026-06-01 through 2026-07-01"


def check_reviewed_same_source_merge() -> None:
    decisions = pd.read_csv(
        PROJECT_ROOT / "data" / "infrastructure" / "curated" / "data_center_identity_decisions.csv",
        dtype=str,
    ).fillna("")
    rows = decisions.loc[decisions["Decision Group"].eq("la-hut8-river-bend")].copy()
    source_ids = set(rows["Source Record ID"].astype(str))
    assert source_ids == {"336", "337"}, "reviewed River Bend decision is not bound to current retained source IDs"

    fractracker = load_fractracker_data_center_observations()
    selected = fractracker.loc[fractracker["Source Record ID"].astype(str).isin(source_ids)].copy()
    assert len(selected) == 2, "reviewed River Bend source observations are missing from retained state"

    payload = build_universal_data_center_registry(
        pd.DataFrame(),
        fractracker_observations=selected,
        gigawatt_observations=pd.DataFrame(),
        curated_observations=pd.DataFrame(),
    )
    assert len(payload["campuses"]) == 1, "reviewed same-source campus merge is not applied by the universal registry"
    assert payload["campuses"]["Campus Name"].astype(str).str.contains("River Bend", case=False, na=False).any()


def main() -> int:
    check_construction_provenance_transaction()
    check_reviewed_same_source_merge()
    print("PASS  integrity-linked retained state · construction provenance transaction · reviewed same-source campus merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
