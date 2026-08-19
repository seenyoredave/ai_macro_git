from __future__ import annotations

OWNER_PROTECTED_PATHS = (
    "data/",
    "archive/",
)

AUTOMATION_PUBLICATION_PATHS = (
    "data/",
    "archive/",
    "openai_artifacts/current.json",
    "automation_artifacts/",
)

AUTOMATION_DIAGNOSTIC_PATHS = (
    "openai_artifacts/attempts/",
)


def normalize_repository_path(value: str) -> str:
    normalized = str(value or "").replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _matches(relative: str, rule: str) -> bool:
    normalized = normalize_repository_path(relative)
    return normalized.startswith(rule) if rule.endswith("/") else normalized == rule


def is_owner_protected_path(relative: str) -> bool:
    return any(_matches(relative, rule) for rule in OWNER_PROTECTED_PATHS)


def is_automation_publication_path(relative: str) -> bool:
    return any(_matches(relative, rule) for rule in AUTOMATION_PUBLICATION_PATHS)


def is_automation_diagnostic_path(relative: str) -> bool:
    return any(_matches(relative, rule) for rule in AUTOMATION_DIAGNOSTIC_PATHS)


def is_automation_allowed_change(relative: str) -> bool:
    return is_automation_publication_path(relative) or is_automation_diagnostic_path(relative)


def owner_stage_exclusions() -> tuple[str, ...]:
    return tuple(f":(exclude){rule}**" if rule.endswith("/") else f":(exclude){rule}" for rule in OWNER_PROTECTED_PATHS)


def automation_stage_paths(mode: str) -> tuple[str, ...]:
    if mode == "publication":
        return AUTOMATION_PUBLICATION_PATHS
    if mode == "ledger":
        return ("automation_artifacts/",)
    raise ValueError(f"Unknown automation transport mode: {mode}")
