"""Deterministic contract checks for the legacy canonical-history bootstrap."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.canonical_history_bootstrap import (  # noqa: E402
    LEGACY_PUBLICATION_SOURCE,
    discover_legacy_snapshot_candidates,
    plan_canonical_history_bootstrap,
)


DOMAINS = (
    "market",
    "finance",
    "compute",
    "data_center",
    "connectivity",
    "power",
    "grid_storage",
    "water",
    "adoption",
    "workforce",
    "economic_impact",
)


def _payload(seed: float, *, legacy_adoption: bool = True) -> str:
    payload = {}
    for index, domain in enumerate(DOMAINS):
        key = "adaptation" if domain == "adoption" and legacy_adoption else domain
        payload[key] = {"metric": seed + index, "missing_metric": None}
    return json.dumps(payload, sort_keys=True)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        archive = root / "archive" / "macro_history.csv"
        archive.parent.mkdir(parents=True, exist_ok=True)
        nan_payload = _payload(1.0).replace("null", "NaN", 1)
        frame = pd.DataFrame([
            {"Date": "2026-08-01", "Macro Snapshot Context": ""},
            {"Date": "2026-08-07", "Macro Snapshot Context": nan_payload},
            {"Date": "2026-08-14", "Macro Snapshot Context": _payload(2.0)},
            # Same-state duplicate is harmless and collapses.
            {"Date": "2026-08-14", "Macro Snapshot Context": _payload(2.0)},
            # Incomplete states must never be promoted.
            {
                "Date": "2026-08-20",
                "Macro Snapshot Context": json.dumps({"market": {"metric": 1}}),
            },
        ])
        frame.to_csv(archive, index=False)

        discovered = discover_legacy_snapshot_candidates(
            root=root,
            domain_order=DOMAINS,
        )
        candidates = discovered["candidates"]
        assert [item.observation_date for item in candidates] == ["2026-08-07", "2026-08-14"]
        assert "adoption" in candidates[0].domain_metrics
        assert "adaptation" not in candidates[0].domain_metrics
        assert discovered["invalid"], "Incomplete legacy state should be rejected"

        history = pd.DataFrame([
            {
                "snapshot_id": "legacy-existing",
                "observation_date": "2026-08-07",
                "publication_source": LEGACY_PUBLICATION_SOURCE,
            },
            {
                "snapshot_id": "native-head",
                "observation_date": "2026-09-15",
                "publication_source": "automation_refresh",
            },
        ])
        plan = plan_canonical_history_bootstrap(
            root=root,
            domain_order=DOMAINS,
            canonical_history=history,
        )
        assert plan["native_canonical_era_start"] == "2026-09-15"
        assert plan["eligible_dates"] == ["2026-08-14"]
        assert any(
            item["observation_date"] == "2026-08-07"
            and item["reason"] == "canonical_date_already_exists"
            for item in plan["skipped"]
        )

        # Once a legacy date is written, it must not redefine the start of the
        # native canonical era and block later legacy candidates on a rerun.
        history = pd.concat([
            history,
            pd.DataFrame([{
                "snapshot_id": "legacy-0814",
                "observation_date": "2026-08-14",
                "publication_source": LEGACY_PUBLICATION_SOURCE,
            }]),
        ], ignore_index=True)
        rerun = plan_canonical_history_bootstrap(
            root=root,
            domain_order=DOMAINS,
            canonical_history=history,
        )
        assert rerun["native_canonical_era_start"] == "2026-09-15"
        assert rerun["eligible_dates"] == []

        # A complete retained state dated after native canonical history begins
        # must not be interleaved with the true canonical era.
        later = pd.concat([
            frame,
            pd.DataFrame([{
                "Date": "2026-09-16",
                "Macro Snapshot Context": _payload(3.0),
            }]),
        ], ignore_index=True)
        later.to_csv(archive, index=False)
        guarded = plan_canonical_history_bootstrap(
            root=root,
            domain_order=DOMAINS,
            canonical_history=history,
        )
        assert any(
            item["observation_date"] == "2026-09-16"
            and item["reason"] == "at_or_after_native_canonical_era"
            for item in guarded["skipped"]
        )

    print("canonical history bootstrap smoke test: PASS")


if __name__ == "__main__":
    main()
