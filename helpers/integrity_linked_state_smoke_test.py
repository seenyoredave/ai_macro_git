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
from loaders.facility_registry_loader import build_campus_registry, load_fractracker_facility_records
from loaders.facility_identity import _assign_canonical_ids


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
    decisions = pd.read_csv(PROJECT_ROOT / "data" / "facility_identity_decisions.csv", dtype=str).fillna("")
    rows = decisions.loc[decisions["Decision Group"].eq("pa-tecfusions-keystone-connect")]
    source_ids = set(rows["Source Record ID"].astype(str))
    assert len(source_ids) == 2
    fractracker = load_fractracker_facility_records()

    # When the historical reviewed IDs are still present, prove the decision
    # ledger directly merges same-source records before generic spatial logic.
    selected = fractracker.loc[fractracker["Source Record ID"].astype(str).isin(source_ids)].copy()
    if len(selected) == 2:
        assigned = _assign_canonical_ids(selected)
        assert assigned["Canonical Facility ID"].nunique() == 1, (
            "reviewed same-source campus merge is not being applied by the production matcher"
        )

    # Upstream edits may change a content-derived Source Record ID.  Find the
    # reviewed campus semantically and verify the current production campus
    # matcher still resolves it once.
    tecfusions = fractracker.loc[
        fractracker["Facility"].astype(str).str.contains("Keystone Connect", case=False, na=False)
        & fractracker["State"].astype(str).eq("PA")
    ].copy()
    assert len(tecfusions) >= 2, "reviewed TECfusions campus fixture is missing from retained state"

    # Prove the semantic review survives the exact failure mode seen in live
    # operation: content-derived upstream IDs churn and therefore no longer
    # match the historical decision ledger.
    shifted = tecfusions.head(2).copy()
    shifted.loc[:, "Source Record ID"] = [
        "fractracker-source:synthetic-id-shift-a",
        "fractracker-source:synthetic-id-shift-b",
    ]
    assigned = _assign_canonical_ids(shifted)
    assert assigned["Canonical Facility ID"].nunique() == 1, (
        "reviewed TECfusions semantic alias did not survive changed upstream Source Record IDs"
    )

    campuses = build_campus_registry(tecfusions)
    matches = campuses["Facility"].astype(str).str.contains("Keystone Connect", case=False, na=False)
    assert int(matches.sum()) == 1, "reviewed TECfusions alias did not survive current upstream record identities"


def main() -> int:
    check_construction_provenance_transaction()
    check_reviewed_same_source_merge()
    print("PASS  integrity-linked retained state · construction provenance transaction · reviewed same-source campus merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
