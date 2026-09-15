from __future__ import annotations

# Owner commits may change Python source inside archive/, but retained archive
# state must remain automation-owned. data/ remains fully automation-owned.
OWNER_PROTECTED_PATHS = (
    "data/",
    "archive/",
)

AUTOMATION_PUBLICATION_PATHS = (
    "data/",
    "archive/",
    "openai_artifacts/current.json",
    "openai_artifacts/evaluated.json",
    "openai_artifacts/attempts/",
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
    """Return whether owner commits must leave this retained-state path alone.

    archive/ is mixed-purpose: CSVs and other retained artifacts are automation
    state, while Python modules are normal application source.  Treating the
    whole directory as protected made the standard git-guard workflow silently
    omit source changes such as archive/archive_reader.py.
    """
    normalized = normalize_repository_path(relative)
    if normalized.startswith("data/"):
        return True
    if normalized.startswith("archive/"):
        return not normalized.endswith(".py")
    return False


def is_automation_publication_path(relative: str) -> bool:
    return any(_matches(relative, rule) for rule in AUTOMATION_PUBLICATION_PATHS)


def is_automation_diagnostic_path(relative: str) -> bool:
    return any(_matches(relative, rule) for rule in AUTOMATION_DIAGNOSTIC_PATHS)


def is_automation_allowed_change(relative: str) -> bool:
    return is_automation_publication_path(relative) or is_automation_diagnostic_path(relative)


def automation_stage_paths(mode: str) -> tuple[str, ...]:
    if mode == "publication":
        return AUTOMATION_PUBLICATION_PATHS
    if mode == "ledger":
        return ("automation_artifacts/", "openai_artifacts/attempts/")
    raise ValueError(f"Unknown automation transport mode: {mode}")
