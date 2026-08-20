"""Persistence boundary for paid OpenAI responses and published Reader artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config.deployment import PROJECT_ROOT, repository_writes_enabled
from helpers.atomic_io import atomic_write_json, synchronized_path

READ_ARTIFACT_VERSION = "4.0.0"
OPENAI_ARTIFACT_ROOT = PROJECT_ROOT / "openai_artifacts"
READ_ARTIFACT_PATH = OPENAI_ARTIFACT_ROOT / "current.json"
EVALUATED_STATE_PATH = OPENAI_ARTIFACT_ROOT / "evaluated.json"
READ_ATTEMPT_DIR = OPENAI_ARTIFACT_ROOT / "attempts"


def load_read_artifact(path: Path = READ_ARTIFACT_PATH) -> dict[str, Any]:
    with synchronized_path(path):
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return payload if isinstance(payload, dict) else {}


def load_evaluated_state(path: Path = EVALUATED_STATE_PATH) -> dict[str, Any]:
    """Load the last evidence snapshot that received a completed API response."""
    with synchronized_path(path):
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return payload if isinstance(payload, dict) else {}


def evaluated_state_matches_prompt(
    payload: dict[str, Any],
    current_prompt_versions: dict[str, str],
) -> bool:
    """Return whether an evaluated baseline belongs to the active editorial contract."""
    return bool(
        payload.get("evidence_packets")
        and dict(payload.get("prompt_versions") or {}) == dict(current_prompt_versions or {})
    )



def load_read_attempt(attempt_id: str) -> dict[str, Any]:
    """Load one preserved paid attempt by immutable attempt ID."""
    path = attempt_path(attempt_id)
    with synchronized_path(path):
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return payload if isinstance(payload, dict) else {}
def persist_read_artifact(payload: dict[str, Any], path: Path = READ_ARTIFACT_PATH) -> None:
    """Publish one completed typed model result with its validation diagnostics."""
    if not repository_writes_enabled():
        raise PermissionError("Validated commentary artifacts may be written only by an authorized research writer.")
    artifact = dict(payload)
    artifact["artifact_version"] = READ_ARTIFACT_VERSION
    atomic_write_json(artifact, path)


def persist_evaluated_state(payload: dict[str, Any], path: Path = EVALUATED_STATE_PATH) -> None:
    """Persist the completed-evaluation baseline independently of publication."""
    if not repository_writes_enabled():
        raise PermissionError("Evaluated OpenAI state may be written only by an authorized research writer.")
    state = dict(payload)
    state["artifact_version"] = READ_ARTIFACT_VERSION
    atomic_write_json(state, path)


def new_attempt_id(*, evidence_snapshot_id: str = "") -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot = "".join(ch for ch in str(evidence_snapshot_id) if ch.isalnum())[:8] or "snapshot"
    return f"{stamp}_{snapshot}_{uuid4().hex[:8]}"


def attempt_path(attempt_id: str) -> Path:
    safe = "".join(ch for ch in str(attempt_id) if ch.isalnum() or ch in {"-", "_"})
    if not safe:
        raise ValueError("OpenAI attempt_id must contain a safe filename character.")
    return READ_ATTEMPT_DIR / f"{safe}.json"


def persist_read_attempt(payload: dict[str, Any], *, attempt_id: str | None = None) -> str:
    """Persist an immutable-by-identity paid generation attempt.

    The same attempt file may be atomically enriched as generation moves from
    domain response -> validation -> macro response -> publication.  Its
    identity never changes, so the paid response survives even if later
    validation or publication fails.
    """
    if not repository_writes_enabled():
        raise PermissionError("OpenAI attempt artifacts may be written only by an authorized research writer.")
    resolved_id = str(attempt_id or new_attempt_id(evidence_snapshot_id=str(payload.get("evidence_snapshot_id") or "")))
    artifact = dict(payload)
    artifact["attempt_id"] = resolved_id
    artifact["artifact_version"] = READ_ARTIFACT_VERSION
    artifact["saved_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(artifact, attempt_path(resolved_id))
    return resolved_id
