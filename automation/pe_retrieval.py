"""Track verified PE source retrievals in the authorized refresh graph."""
from __future__ import annotations

from datetime import timezone


def record_pe_retrieval(plan, node_id: str, results: list[dict]) -> None:
    """Stamp successful source retrievals, including unchanged data and partial runs.

    Failed providers, skipped refreshes, and retained-file reads cannot advance
    the timestamp. The parent refresh transaction publishes the graph state.
    """
    if any(row.get('status') in {'updated', 'unchanged'} for row in results):
        node = (plan.state.get('nodes') or {}).get(node_id)
        if isinstance(node, dict):
            node['last_retrieval_at_utc'] = plan.now.astimezone(timezone.utc).isoformat()
