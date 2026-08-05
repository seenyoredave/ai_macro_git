from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config.deployment import PROJECT_ROOT, current_context_paths, developer_mode
from helpers.atomic_io import atomic_write_bytes, atomic_write_json, synchronized_path
from loaders.current_context_discovery import refresh_current_context

RETAINED_REGISTRY = PROJECT_ROOT / "data" / "weekly_context_events.csv"


def _read_manifest(path: Path) -> dict:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _seed_public_registry(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    if RETAINED_REGISTRY.exists():
        atomic_write_bytes(RETAINED_REGISTRY.read_bytes(), path)
    else:
        atomic_write_bytes(b"", path)


def refresh_current_context_once_daily(*, as_of=None, force: bool = False) -> dict:
    """Run one discovery pass per Eastern market date; the first caller wins."""
    current = pd.Timestamp(as_of or pd.Timestamp.now()).normalize()
    expected_date = current.date().isoformat()
    paths = current_context_paths()
    paths["base"].mkdir(parents=True, exist_ok=True)

    with synchronized_path(paths["daily_lock"]):
        manifest = _read_manifest(paths["manifest"])
        if not force and manifest.get("as_of") == expected_date:
            return {**manifest, "refresh_status": "already_current", "registry_path": str(paths["registry"])}

        if not developer_mode():
            _seed_public_registry(paths["registry"])

        try:
            manifest = refresh_current_context(
                as_of=current,
                audit_path=paths["audit"],
                manifest_path=paths["manifest"],
                registry_path=paths["registry"],
                merge_registry=True,
            )
            return {**manifest, "refresh_status": "refreshed", "registry_path": str(paths["registry"])}
        except Exception as exc:
            failure = {
                "as_of": expected_date,
                "refresh_status": "failed_retained_fallback",
                "error": f"{type(exc).__name__}: {exc}",
                "registry_path": str(paths["registry"]),
            }
            atomic_write_json(failure, paths["manifest"])
            return failure
