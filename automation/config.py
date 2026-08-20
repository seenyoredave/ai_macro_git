"""Configuration and hard safety limits for unattended AI Macro runs."""

from __future__ import annotations

from dataclasses import dataclass
import os

AUTOMATION_TIMEZONE = "America/New_York"
AUTOMATION_START_LOCAL = "08:07"
HARD_MAX_PAID_CALLS_PER_RUN = 1
HARD_MAX_PAID_CALLS_PER_DAY = 2
DEFAULT_OPENAI_TIMEOUT_SECONDS = 600.0


def _bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, hard_max: int) -> int:
    try:
        requested = int(str(os.getenv(name, default)))
    except (TypeError, ValueError):
        requested = default
    return max(0, min(requested, hard_max))


def _float(name: str, default: float) -> float:
    try:
        return max(1.0, float(str(os.getenv(name, default))))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class AutomationConfig:
    enabled: bool
    openai_enabled: bool
    auto_publish: bool
    trigger: str
    max_paid_calls_per_run: int
    max_paid_calls_per_day: int
    openai_timeout_seconds: float

    @property
    def is_manual(self) -> bool:
        return self.trigger == "workflow_dispatch"


def load_automation_config() -> AutomationConfig:
    trigger = str(os.getenv("AI_MACRO_TRIGGER", "manual_local") or "manual_local").strip()
    enabled = _bool("AI_MACRO_AUTOMATION_ENABLED", False)
    paid = _bool("OPENAI_AUTOMATION_ENABLED", False)
    publish = _bool("AUTO_PUBLISH", False)

    # A manual GitHub run needs an extra explicit paid/publish opt-in even when
    # the scheduled automation switches are enabled.  Clicking Run workflow is
    # never itself authorization to spend money or publish research.
    if trigger == "workflow_dispatch":
        paid = paid and _bool("AI_MACRO_MANUAL_ALLOW_PAID", False)
        publish = publish and _bool("AI_MACRO_MANUAL_ALLOW_PUBLISH", False)

    return AutomationConfig(
        enabled=enabled,
        openai_enabled=paid,
        auto_publish=publish,
        trigger=trigger,
        max_paid_calls_per_run=_bounded_int(
            "AI_MACRO_MAX_PAID_CALLS_PER_RUN", 1, HARD_MAX_PAID_CALLS_PER_RUN
        ),
        max_paid_calls_per_day=_bounded_int(
            "AI_MACRO_MAX_PAID_CALLS_PER_DAY", 2, HARD_MAX_PAID_CALLS_PER_DAY
        ),
        openai_timeout_seconds=_float(
            "AI_MACRO_OPENAI_TIMEOUT_SECONDS", DEFAULT_OPENAI_TIMEOUT_SECONDS
        ),
    )
