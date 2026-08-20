"""Assemble one Reader snapshot from published commentary plus Current Context.

Commentary is generated only from retained analytical evidence and persisted with
nonblocking diagnostics. Current Context remains a separate, faster-moving sourced
layer that is attached when the Reader snapshot is assembled. Public sessions never
call OpenAI.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock

from analytics.dashboard_context import DashboardContext
from analytics.read_capsules import CAPSULE_ARCHITECTURE_VERSION
from analytics.read_evidence import EVIDENCE_ARCHITECTURE_VERSION
from analytics.read_service import READ_SERVICE_VERSION, build_platform_reads
from analytics.read_store import READ_ARTIFACT_PATH
from config.deployment import developer_mode

READER_SNAPSHOT_VERSION = "1.2.0"
_SNAPSHOT_LOCK = RLock()
_SNAPSHOT_CACHE: dict[str, dict] = {}


def _artifact_cache_token() -> str:
    try:
        stat = READ_ARTIFACT_PATH.stat()
    except OSError:
        return "missing"
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _cached_snapshot_usable(snapshot: dict) -> bool:
    commentary = dict(snapshot.get("commentary") or {})
    if commentary.get("status") not in {"validated", "published_with_warnings"}:
        return True
    # A publishable artifact is last-known-good until a newer artifact replaces
    # it. The 24-hour publication lease is freshness metadata only and must not
    # invalidate an otherwise usable Reader cache after a weekend or failed run.
    return bool(commentary.get("artifact_publishable"))


def _decorate_reads(reads: dict, *, snapshot_id: str, retrieved_at: str) -> dict:
    output: dict = {}
    for domain, read in (reads or {}).items():
        item = dict(read or {})
        item["context_snapshot_id"] = snapshot_id
        item["context_snapshot_retrieved_at"] = retrieved_at
        item["reader_snapshot_version"] = READER_SNAPSHOT_VERSION
        output[domain] = item
    return output


def build_reader_snapshot(context: DashboardContext, *, context_report: dict | None = None) -> dict:
    report = dict(context_report or {})
    current_context = dict(context.current_context or {})
    snapshot_id = str(
        report.get("context_packet_id")
        or report.get("snapshot_id")
        or current_context.get("snapshot_id")
        or "retained-unknown"
    ).strip()
    retrieved_at = str(report.get("retrieved_at") or current_context.get("snapshot_retrieved_at") or "").strip()

    cache_key = f"{snapshot_id}:{_artifact_cache_token()}"
    if not developer_mode():
        with _SNAPSHOT_LOCK:
            cached = _SNAPSHOT_CACHE.get(cache_key)
            if cached is not None and _cached_snapshot_usable(cached):
                return deepcopy(cached)

    reads, commentary = build_platform_reads(context)
    reads = _decorate_reads(reads, snapshot_id=snapshot_id, retrieved_at=retrieved_at)
    snapshot = {
        "snapshot_id": snapshot_id,
        "retrieved_at": retrieved_at,
        "snapshot_version": READER_SNAPSHOT_VERSION,
        "read_service_version": READ_SERVICE_VERSION,
        "evidence_architecture_version": EVIDENCE_ARCHITECTURE_VERSION,
        "capsule_architecture_version": CAPSULE_ARCHITECTURE_VERSION,
        "evidence_snapshot_id": commentary.get("evidence_snapshot_id", ""),
        "commentary": {key: value for key, value in commentary.items() if key != "packets"},
        "current_context": current_context,
        "reads": reads,
    }

    if not developer_mode():
        with _SNAPSHOT_LOCK:
            _SNAPSHOT_CACHE.clear()
            _SNAPSHOT_CACHE[cache_key] = deepcopy(snapshot)
    return snapshot
