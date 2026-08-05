from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "ai_macro_v6_5_1"


def app_mode() -> str:
    """Return the explicit deployment mode; public is the safe default."""
    value = str(os.getenv("AI_MACRO_MODE", "public") or "public").strip().lower()
    return "developer" if value in {"dev", "developer", "local", "admin"} else "public"


def developer_mode() -> bool:
    return app_mode() == "developer"


def repository_writes_enabled() -> bool:
    """Only the desktop/developer workflow may mutate retained repository data."""
    return developer_mode()


def current_context_paths() -> dict[str, Path]:
    """Use retained files locally and an ephemeral shared ledger in public mode."""
    if developer_mode():
        base = PROJECT_ROOT / "data"
    else:
        base = PUBLIC_RUNTIME_ROOT / "current_context"
    return {
        "base": base,
        "registry": base / "weekly_context_events.csv",
        "audit": base / "current_context_candidate_audit.csv",
        "manifest": base / "current_context_refresh_manifest.json",
        "daily_lock": base / ".daily_refresh",
    }
