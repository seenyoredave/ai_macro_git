from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loaders.data_center_inventory_loader import build_data_center_national_database

if __name__ == "__main__":
    frame = build_data_center_national_database()
    print(f"Wrote {len(frame):,} data-center evidence rows")
