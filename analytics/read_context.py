"""Attach Current Context to published commentary without regenerating prose."""

from __future__ import annotations

from typing import Any


def attach_current_context(read: dict, context: dict | None, *, limit: int = 2) -> dict:
    payload = dict(read or {})
    context_payload = context or {}
    events = [
        dict(item) for item in context_payload.get("events", []) or []
        if isinstance(item, dict)
        and str(item.get("verification_status") or item.get("status") or "").strip().lower() != "no_match"
    ][: max(1, int(limit))]
    event_references = [dict(item) for item in context_payload.get("references", []) or [] if isinstance(item, dict)]
    static_references = [dict(item) for item in payload.get("references", []) or [] if isinstance(item, dict)]
    references: list[dict[str, Any]] = []
    source_keys: dict[tuple[str, str], int] = {}
    for reference in [*event_references, *static_references]:
        label = str(reference.get("source_label") or reference.get("source_name") or "").strip()
        url = str(reference.get("source_url") or "").strip()
        if not label:
            continue
        key = (label, url)
        number = source_keys.get(key)
        if number is None:
            number = len(references) + 1
            source_keys[key] = number
            item = dict(reference)
            item["reference_number"] = number
            references.append(item)
    context_items: list[dict[str, Any]] = []
    for event in events:
        label = str(event.get("source_label") or event.get("source_name") or "").strip()
        url = str(event.get("source_url") or "").strip()
        context_items.append({
            "event_id": str(event.get("event_id") or ""),
            "text": str(event.get("display") or event.get("verified_fact") or "").strip(),
            "reference_number": source_keys.get((label, url)),
            "source_url": url,
            "status": str(event.get("status") or "").strip(),
            "legal_status": str(event.get("legal_status") or "").strip(),
            "resolution_status": str(event.get("resolution_status") or "").strip(),
            "priority": float(event.get("priority", 0) or 0),
        })
    context_items = [item for item in context_items if item["text"]]
    payload["references"] = references
    payload["current_context_items"] = context_items
    payload["recent_context"] = context_items[0]["text"] if context_items else ""
    payload["current_context"] = context_payload
    return payload
