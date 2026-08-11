from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RUNTIME_ROOT = Path(tempfile.gettempdir()) / "ai_macro"


def app_mode() -> str:
    """Return the explicit runtime mode; public is the safe default."""
    value = str(os.getenv("AI_MACRO_MODE", "public") or "public").strip().lower()
    if value in {"dev", "developer", "local", "admin"}:
        return "developer"
    if value in {"automation", "worker", "scheduled"}:
        return "automation"
    return "public"


def developer_mode() -> bool:
    return app_mode() == "developer"


def automation_mode() -> bool:
    return app_mode() == "automation"


def repository_writes_enabled() -> bool:
    """Only explicit owner/developer or automation-worker runtimes may mutate retained state."""
    return app_mode() in {"developer", "automation"}


def current_context_paths() -> dict[str, Path]:
    """Return the single retained Current Context publication paths.

    Public Reader processes are readers only.  Developer and automation-worker
    processes are the only runtimes allowed to refresh these retained files.
    """
    base = PROJECT_ROOT / "data"
    return {
        "base": base,
        "registry": base / "weekly_context_events.csv",
        "audit": base / "current_context_candidate_audit.csv",
        "manifest": base / "current_context_refresh_manifest.json",
        "daily_lock": base / ".daily_refresh",
    }
