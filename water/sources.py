from __future__ import annotations

from pathlib import Path

import pandas as pd

from water.ledger import sha256_file
from water.schema import SOURCE_MANIFEST_COLUMNS

def load_source_manifest(path: str | Path, project_root: str | Path | None = None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=SOURCE_MANIFEST_COLUMNS)
    frame = pd.read_csv(path, dtype=str).fillna("")
    for column in SOURCE_MANIFEST_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    root = Path(project_root) if project_root is not None else path.resolve().parents[2]
    health = []
    for _, row in frame.iterrows():
        raw_path = str(row.get("raw_path") or "").strip()
        expected = str(row.get("raw_sha256") or "").strip().lower()
        if not raw_path:
            health.append(str(row.get("source_health") or "identified"))
            continue
        local = root / raw_path
        if not local.exists():
            health.append("missing_retained_raw")
        elif expected and sha256_file(local).lower() != expected:
            health.append("checksum_mismatch")
        else:
            health.append("retained_and_validated")
    frame["source_health"] = health
    return frame[SOURCE_MANIFEST_COLUMNS]
