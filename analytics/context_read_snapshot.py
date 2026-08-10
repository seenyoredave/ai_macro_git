"""Bind one Current Context packet to one completed platform Read set.

Public deployments use immutable retained analytical data plus a shared
15-minute Current Context packet.  The first reader for a packet builds the
complete Read set; subsequent readers in the same process receive that exact
Context + Read pair.  Developer mode deliberately bypasses the pair cache so
local provider refreshes immediately rebuild analytical narratives.
"""

from __future__ import annotations

from copy import deepcopy
from threading import RLock

from analytics.dashboard_context import DashboardContext
from analytics.read_architecture import READ_ARCHITECTURE_VERSION, build_platform_reads
from config.deployment import developer_mode

CONTEXT_READ_PAIR_VERSION = "1.1"
_PAIR_LOCK = RLock()
_PAIR_CACHE: dict[str, dict] = {}


def _decorate_reads(reads: dict, *, snapshot_id: str, retrieved_at: str) -> dict:
    output: dict = {}
    for domain, read in (reads or {}).items():
        item = dict(read or {})
        item["context_snapshot_id"] = snapshot_id
        item["context_snapshot_retrieved_at"] = retrieved_at
        item["context_read_pair_version"] = CONTEXT_READ_PAIR_VERSION
        output[domain] = item
    return output


def build_context_read_pair(context: DashboardContext, *, context_report: dict | None = None) -> dict:
    """Return one exact Current Context + completed Read pair.

    ``snapshot_id`` is the cache boundary.  A public deployment's analytical
    data are immutable for the life of a release, so the shared Context packet
    is sufficient to identify the completed Reader-facing pair.  Developer
    mode never reuses this cache because explicit provider refreshes may change
    retained analytical inputs independently of Current Context.
    """
    report = dict(context_report or {})
    current_context = dict(context.current_context or {})
    snapshot_id = str(
        report.get("context_packet_id")
        or report.get("snapshot_id")
        or current_context.get("snapshot_id")
        or "retained-unknown"
    ).strip()
    retrieved_at = str(
        report.get("retrieved_at")
        or current_context.get("snapshot_retrieved_at")
        or ""
    ).strip()

    if not developer_mode():
        with _PAIR_LOCK:
            cached = _PAIR_CACHE.get(snapshot_id)
            if cached is not None:
                return deepcopy(cached)

    reads = _decorate_reads(
        build_platform_reads(context),
        snapshot_id=snapshot_id,
        retrieved_at=retrieved_at,
    )
    pair = {
        "snapshot_id": snapshot_id,
        "retrieved_at": retrieved_at,
        "pair_version": CONTEXT_READ_PAIR_VERSION,
        "read_architecture_version": READ_ARCHITECTURE_VERSION,
        "current_context": current_context,
        "reads": reads,
    }

    if not developer_mode():
        with _PAIR_LOCK:
            # Keep only the active packet.  The 15-minute Current Context cache
            # advances the snapshot id and naturally invalidates the prior pair.
            _PAIR_CACHE.clear()
            _PAIR_CACHE[snapshot_id] = deepcopy(pair)
    return pair
