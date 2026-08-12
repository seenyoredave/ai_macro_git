"""Durable freshness ledger for mutable retained research state.

The application has two independent writers: the desktop developer workspace and
GitHub automation.  Git commit time and filesystem mtime are not reliable enough
for deciding which retained dataset is newer after ZIP extraction or directory
copies.  This module records a per-file timestamp only when the file's content
hash actually changes.

The ledger itself is retained state.  It does not authorize provider access and
never performs network I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from config.deployment import PROJECT_ROOT
from helpers.atomic_io import atomic_write_json

STATE_MANIFEST_VERSION = "1.0"
STATE_MANIFEST_PATH = PROJECT_ROOT / "data" / "retained_state_manifest.json"

# release_manifest fingerprints the final application/data tree and is rebuilt
# after reconciliation; it must not participate in newest-wins state selection.
_STATE_EXACT_EXCLUDES = {
    "data/release_manifest.json",
    "data/retained_state_manifest.json",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_retained_state_path(relative: str) -> bool:
    normalized = str(relative).replace("\\", "/").lstrip("./")
    if normalized in _STATE_EXACT_EXCLUDES:
        return False
    if normalized.startswith("data/"):
        return True
    if normalized.startswith("archive/") and Path(normalized).suffix.casefold() in {
        ".csv", ".json", ".gz", ".xlsx", ".xls", ".pdf", ".png"
    }:
        return True
    return False


def iter_retained_state_files(root: Path = PROJECT_ROOT) -> list[Path]:
    files: list[Path] = []
    data_root = root / "data"
    if data_root.exists():
        for path in data_root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if is_retained_state_path(relative):
                    files.append(path)
    archive_root = root / "archive"
    if archive_root.exists():
        for path in archive_root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(root).as_posix()
                if is_retained_state_path(relative):
                    files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def load_retained_state_manifest(root: Path = PROJECT_ROOT) -> dict[str, Any]:
    path = root / "data" / "retained_state_manifest.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict) or payload.get("manifest_version") != STATE_MANIFEST_VERSION:
        return {}
    return payload


def _fallback_mtime(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return utc_now()


def build_retained_state_manifest(
    *,
    root: Path = PROJECT_ROOT,
    source: str,
    run_id: str = "",
    now: datetime | None = None,
    previous: dict[str, Any] | None = None,
    bootstrap_times: dict[str, datetime] | None = None,
) -> dict[str, Any]:
    """Hash retained files and advance freshness only when content changed."""

    moment = (now or utc_now()).astimezone(timezone.utc)
    prior = dict(previous if previous is not None else load_retained_state_manifest(root))
    prior_files = dict(prior.get("files") or {})
    bootstrap = dict(bootstrap_times or {})
    files: dict[str, dict[str, Any]] = {}

    for path in iter_retained_state_files(root):
        relative = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        size = int(path.stat().st_size)
        old = dict(prior_files.get(relative) or {})
        if old.get("sha256") == digest and _parse_time(old.get("updated_at_utc")):
            updated_at = str(old["updated_at_utc"])
            updated_by = str(old.get("updated_by") or "unknown")
            updated_run_id = str(old.get("run_id") or "")
        else:
            baseline = bootstrap.get(relative)
            if baseline is None and not old:
                baseline = _fallback_mtime(path)
            changed_at = baseline or moment
            updated_at = _iso(changed_at)
            updated_by = str(source or "unknown")
            updated_run_id = str(run_id or "")
        files[relative] = {
            "sha256": digest,
            "bytes": size,
            "updated_at_utc": updated_at,
            "updated_by": updated_by,
            "run_id": updated_run_id,
        }

    return {
        "manifest_version": STATE_MANIFEST_VERSION,
        "generated_at_utc": _iso(moment),
        "source": str(source or "unknown"),
        "run_id": str(run_id or ""),
        "files": files,
    }


def refresh_retained_state_manifest(
    *,
    root: Path = PROJECT_ROOT,
    source: str,
    run_id: str = "",
    now: datetime | None = None,
    bootstrap_times: dict[str, datetime] | None = None,
) -> dict[str, Any]:
    manifest = build_retained_state_manifest(
        root=root,
        source=source,
        run_id=run_id,
        now=now,
        bootstrap_times=bootstrap_times,
    )
    output = root / "data" / "retained_state_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest, output)
    return manifest


def entry_time(entry: dict[str, Any] | None) -> datetime | None:
    return _parse_time((entry or {}).get("updated_at_utc"))


def choose_newer_entry(
    relative: str,
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> str:
    """Return ``left``, ``right`` or ``same`` for one retained-state path.

    Equal timestamps with unequal hashes are intentionally an error: silently
    choosing one would violate the newest-wins contract.
    """

    a = dict(left or {})
    b = dict(right or {})
    if not a and not b:
        return "same"
    if a and not b:
        return "left"
    if b and not a:
        return "right"
    if a.get("sha256") == b.get("sha256"):
        return "same"
    at = entry_time(a)
    bt = entry_time(b)
    if at and bt:
        if at > bt:
            return "left"
        if bt > at:
            return "right"
    elif at:
        return "left"
    elif bt:
        return "right"
    raise RuntimeError(
        f"Retained-state conflict for {relative}: different content has no unambiguous freshness ordering."
    )


def merged_manifest(
    *,
    selected_entries: dict[str, dict[str, Any]],
    source: str,
    run_id: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    return {
        "manifest_version": STATE_MANIFEST_VERSION,
        "generated_at_utc": _iso((now or utc_now()).astimezone(timezone.utc)),
        "source": str(source or "reconciliation"),
        "run_id": str(run_id or ""),
        "files": dict(sorted(selected_entries.items())),
    }


def write_manifest(root: Path, manifest: dict[str, Any]) -> None:
    output = root / "data" / "retained_state_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(manifest, output)
