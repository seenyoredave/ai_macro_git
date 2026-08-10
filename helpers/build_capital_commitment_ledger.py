#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.capital_commitments import (  # noqa: E402
    DEFAULT_LEDGER_PATH,
    build_current_commitment_ledger,
)


def main() -> None:
    ledger = build_current_commitment_ledger()
    ledger.to_csv(DEFAULT_LEDGER_PATH, index=False, date_format="%Y-%m-%d")
    print(f"Wrote {len(ledger)} current capital-commitment rows to {DEFAULT_LEDGER_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
