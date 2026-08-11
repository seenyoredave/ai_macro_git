"""Assemble one Reader snapshot from validated commentary plus Current Context.

Commentary is generated only from retained analytical evidence and persisted as a
validated artifact. Current Context remains a separate, faster-moving sourced
layer that is attached when the Reader snapshot is assembled. Public sessions never
call OpenAI.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock

from analytics.dashboard_context import DashboardContext
from analytics.read_evidence import EVIDENCE_ARCHITECTURE_VERSION
from analytics.read_service import READ_SERVICE_VERSION, build_platform_reads
from config.deployment import developer_mode

READER_SNAPSHOT_VERSION = "1.0.0"
_SNAPSHOT_LOCK = RLock()
_SNAPSHOT_CACHE: dict[str, dict] = {}


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

    if not developer_mode():
        with _SNAPSHOT_LOCK:
            cached = _SNAPSHOT_CACHE.get(snapshot_id)
            if cached is not None:
                return deepcopy(cached)

    reads, commentary = build_platform_reads(context)
    reads = _decorate_reads(reads, snapshot_id=snapshot_id, retrieved_at=retrieved_at)
    snapshot = {
        "snapshot_id": snapshot_id,
        "retrieved_at": retrieved_at,
        "snapshot_version": READER_SNAPSHOT_VERSION,
        "read_service_version": READ_SERVICE_VERSION,
        "evidence_architecture_version": EVIDENCE_ARCHITECTURE_VERSION,
        "evidence_snapshot_id": commentary.get("evidence_snapshot_id", ""),
        "commentary": {key: value for key, value in commentary.items() if key != "packets"},
        "current_context": current_context,
        "reads": reads,
    }

    if not developer_mode():
        with _SNAPSHOT_LOCK:
            _SNAPSHOT_CACHE.clear()
            _SNAPSHOT_CACHE[snapshot_id] = deepcopy(snapshot)
    return snapshot
