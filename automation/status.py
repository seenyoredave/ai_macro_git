"""Read-only helpers for the latest committed automation status."""

from __future__ import annotations

import json
from typing import Any

from automation.ledger import STATUS_PATH


def load_automation_status() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {}
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}
