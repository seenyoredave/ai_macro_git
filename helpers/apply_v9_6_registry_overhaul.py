#!/usr/bin/env python3
"""Destructive cutover for AI Macro v9.6.0 Universal Data Center Registry.

This script performs cleanup only. It does not implement identity logic and it
never creates compatibility aliases. The production identity authority lives in
``loaders/data_center_registry.py``.

Run from the repository root before building the retained universal registry.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

OBSOLETE_PROGRAM_FILES = (
    "loaders/facility_registry_common.py",
    "loaders/facility_sources.py",
    "loaders/facility_identity.py",
    "loaders/campus_registry.py",
    "loaders/facility_registry_loader.py",
    "helpers/campus_identity_hardening_smoke_test.py",
    "helpers/campus_literal_identity_smoke_test.py",
    "helpers/campus_hierarchy_smoke_test.py",
    "helpers/campus_hierarchy_audit.py",
    "helpers/campus_identity_hardening_test.py",
    "helpers/campus_exact_identity_smoke_test.py",
)

DATA_MOVES = (
    (
        "data/facility_registry_seed.csv",
        "data/infrastructure/curated/data_center_primary_evidence.csv",
    ),
    (
        "data/facility_identity_decisions.csv",
        "data/infrastructure/curated/data_center_identity_decisions.csv",
    ),
)

LEGACY_DATA_PATHS = tuple(source for source, _ in DATA_MOVES)
NEW_DATA_PATHS = tuple(destination for _, destination in DATA_MOVES)

FORBIDDEN_CODE_TOKENS = (
    "loaders.facility_registry_common",
    "loaders.facility_sources",
    "loaders.facility_identity",
    "loaders.campus_registry",
    "loaders.facility_registry_loader",
    '"facility_registry"', "'facility_registry'",
    '"campus_registry"', "'campus_registry'",
    '"facility_observations"', "'facility_observations'",
    '"facility_coverage"', "'facility_coverage'",
    '"facility_identity_decisions"', "'facility_identity_decisions'",
    "build_campus_registry",
    "canonicalize_facility_observations",
    "build_facility_observations",
    "load_curated_facility_records",
    "load_gigawatt_facility_records",
    "load_fractracker_facility_records",
    "_assign_canonical_ids",
    "FACILITY_SIZE_METRICS",
    "facility_map_legend_items",
    "data_center_state_detail_map",
    "data_center_state_footprint",
    "data_center_state_published_capacity",
    "data_center_operator_label",
    "force_facility_refresh",
    "allow_facility_live",
    "data/facility_registry_seed.csv",
    "data/facility_identity_decisions.csv",
)

SCAN_ROOTS = (
    "ai_macro.py",
    "analytics",
    "loaders",
    "rendering",
    "water",
    "helpers",
    "developer",
)

EXEMPT = {
    Path("helpers/apply_v9_6_registry_overhaul.py"),
    Path("helpers/data_center_identity_authority_test.py"),
}

DERIVED_REGISTRY_FILES = (
    "data/infrastructure/derived/universal_data_center_entities.csv",
    "data/infrastructure/derived/universal_data_center_observations.csv",
    "data/infrastructure/derived/universal_data_center_membership.csv",
    "data/infrastructure/derived/universal_data_center_unresolved.csv",
    "data/infrastructure/derived/universal_data_center_registry.json",
)

OBSOLETE_DERIVED_FILES = (
    "data/infrastructure/derived/universal_data_center_campuses.csv",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _move_identity_sources() -> list[str]:
    actions: list[str] = []
    for old_relative, new_relative in DATA_MOVES:
        old = ROOT / old_relative
        new = ROOT / new_relative
        if old.exists() and new.exists():
            if _sha256(old) != _sha256(new):
                raise RuntimeError(
                    f"Both legacy and universal registry sources exist with different content: "
                    f"{old_relative} vs {new_relative}"
                )
            old.unlink()
            actions.append(f"removed duplicate legacy source {old_relative}")
            continue
        if old.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
            actions.append(f"moved {old_relative} -> {new_relative}")
    return actions


def _delete_obsolete_program_files() -> list[str]:
    actions: list[str] = []
    for relative in OBSOLETE_PROGRAM_FILES:
        path = ROOT / relative
        if path.exists():
            path.unlink()
            actions.append(f"deleted {relative}")
    for relative in OBSOLETE_DERIVED_FILES:
        path = ROOT / relative
        if path.exists():
            path.unlink()
            actions.append(f"deleted superseded derived table {relative}")
    for directory in (ROOT / "loaders", ROOT / "helpers"):
        cache = directory / "__pycache__"
        if cache.exists():
            shutil.rmtree(cache)
    return actions


def _update_release_manifest_builder() -> list[str]:
    """Move release fingerprints onto the universal-registry source/artifact names."""
    path = ROOT / "helpers" / "build_release_manifest.py"
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace('"loaders/facility_sources.py",', '"loaders/data_center_registry.py",')
    text = text.replace('"data/facility_identity_decisions.csv",', '"data/infrastructure/curated/data_center_identity_decisions.csv",')
    text = text.replace('    "data/infrastructure/derived/universal_data_center_campuses.csv",\n', '')

    registry_source_entry = '    "data/infrastructure/curated/data_center_primary_evidence.csv",\n'
    registry_artifact_entries = "".join(f'    "{relative}",\n' for relative in DERIVED_REGISTRY_FILES)
    marker = '    "data/infrastructure/curated/data_center_identity_decisions.csv",\n'
    if marker in text:
        insert = marker
        if registry_source_entry.strip() not in text:
            insert += registry_source_entry
        for relative in DERIVED_REGISTRY_FILES:
            entry = f'    "{relative}",\n'
            if entry.strip() not in text:
                insert += entry
        text = text.replace(marker, insert, 1)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return ["updated helpers/build_release_manifest.py for universal registry sources/artifacts"]
    return []


def _python_paths() -> list[Path]:
    paths: list[Path] = []
    for item in SCAN_ROOTS:
        path = ROOT / item
        if path.is_file() and path.suffix == ".py":
            paths.append(path)
        elif path.is_dir():
            paths.extend(path.rglob("*.py"))
    return sorted(set(paths))


def _scan_for_ghosts() -> None:
    offenders: list[tuple[str, list[str]]] = []
    for path in _python_paths():
        relative = path.relative_to(ROOT)
        if relative in EXEMPT:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [token for token in FORBIDDEN_CODE_TOKENS if token in text]
        if hits:
            offenders.append((str(relative), hits))
    if offenders:
        lines = ["old data-center identity authority remains:"]
        lines.extend(f"  {path}: {', '.join(hits)}" for path, hits in offenders)
        raise RuntimeError("\n".join(lines))

    for relative in OBSOLETE_PROGRAM_FILES:
        if (ROOT / relative).exists():
            raise RuntimeError(f"obsolete identity module remains: {relative}")
    for relative in LEGACY_DATA_PATHS:
        if (ROOT / relative).exists():
            raise RuntimeError(f"legacy identity source remains: {relative}")


def _compile_python() -> None:
    failures: list[str] = []
    for path in _python_paths():
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc}")
    if failures:
        raise RuntimeError("Python syntax failures:\n  " + "\n  ".join(failures))


def main() -> int:
    required = ROOT / "loaders" / "data_center_registry.py"
    if not required.exists():
        raise FileNotFoundError("loaders/data_center_registry.py must be overwritten before running the cutover")

    actions = []
    actions.extend(_move_identity_sources())
    actions.extend(_delete_obsolete_program_files())
    actions.extend(_update_release_manifest_builder())
    _scan_for_ghosts()
    _compile_python()

    for relative in NEW_DATA_PATHS:
        if not (ROOT / relative).exists():
            print(f"NOTE  optional universal-registry source absent: {relative}")
    for action in actions:
        print(f"CUTOVER  {action}")
    print("PASS  v9.6.0 destructive cutover · legacy identity code/data names removed · Python syntax clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
