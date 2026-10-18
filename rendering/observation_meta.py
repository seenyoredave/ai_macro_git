"""Compact source and observation date for public readings."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path

import pandas as pd


_ROOT = Path(__file__).resolve().parents[1]
_RETAINED_MANIFEST = _ROOT / "data" / "retained_state_manifest.json"


def source_through(source: str, observed: object, retrieved: object = None) -> str:
    source = str(source or "").strip()
    if not source:
        raise ValueError("An observation label requires a source")
    date = pd.to_datetime(observed, errors="coerce", format="mixed")
    if pd.isna(date):
        date = pd.to_datetime(retrieved, errors="coerce", format="mixed")
    if pd.isna(date):
        return source
    return f"{source} · through {date.strftime('%Y-%m-%d')}"


@lru_cache(maxsize=64)
def _verified_retrieval(relative_path: str, manifest_stamp: int, file_stamp: int, file_size: int):
    del manifest_stamp, file_stamp, file_size
    try:
        entry = json.loads(_RETAINED_MANIFEST.read_text(encoding="utf-8"))["files"][relative_path]
        path = _ROOT / relative_path
        if hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]:
            return entry.get("updated_at_utc")
    except (OSError, KeyError, TypeError, ValueError):
        pass
    return None


def retained_retrieval_date(relative_path: str):
    """Use the retained-file timestamp only while its manifest checksum matches."""
    path = _ROOT / relative_path
    try:
        if path.resolve().is_relative_to((_ROOT / "data").resolve()):
            stat = path.stat()
            return _verified_retrieval(relative_path, _RETAINED_MANIFEST.stat().st_mtime_ns,
                                       stat.st_mtime_ns, stat.st_size)
    except OSError:
        pass
    return None


def latest_observation(frame: object, date_column: str = "Date"):
    """Use observation dates only; retrieval timestamps are not observations."""
    if not isinstance(frame, pd.DataFrame) or frame.empty or date_column not in frame:
        return None
    dates = pd.to_datetime(frame[date_column], errors="coerce", format="mixed")
    return dates.max() if dates.notna().any() else None
