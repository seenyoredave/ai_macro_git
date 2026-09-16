"""Owner-invoked one-time bootstrap of pre-canonical comparison history."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.canonical_history_bootstrap import bootstrap_legacy_canonical_history  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Import only complete legacy Macro Snapshot Context rows into the "
            "append-only canonical history. Defaults to a dry run."
        )
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Persist eligible historical canonical snapshots. Requires AI_MACRO_MODE=developer.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    report = bootstrap_legacy_canonical_history(write=bool(args.write), root=PROJECT_ROOT)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    if not args.write:
        print("\nDry run only. Re-run with --write after reviewing eligible_dates.")
        return 0
    if report.get("written"):
        # Keep the repository's retained-state and release fingerprints aligned
        # with every successfully created partition, including a partial run
        # that will be completed idempotently on the next invocation.
        from automation.retained_state import refresh_retained_state_manifest
        from helpers.atomic_io import atomic_write_json
        from helpers.build_release_manifest import build_manifest

        refresh_retained_state_manifest(source="canonical_history_bootstrap")
        atomic_write_json(build_manifest(), PROJECT_ROOT / "data" / "release_manifest.json")
        print("\nUpdated retained-state and release manifests.")
    return 2 if report.get("errors") else 0


if __name__ == "__main__":
    raise SystemExit(main())
