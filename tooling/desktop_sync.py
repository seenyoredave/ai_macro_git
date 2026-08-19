"""Reconcile the desktop master with the Git staging repository safely.

Authority is directional:

* Program/config/documentation files flow from the desktop master to Git.
* ``data/`` and ``archive/`` are online-owned and flow only from Git to desktop.
* Automation artifacts remain online-owned.
* Paid OpenAI attempts are unioned and the newest validated Read retains the
  existing publication-time selection rule.

The desktop must never publish retained ``data/`` or ``archive/`` state.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from automation.retained_state import sha256_file
from tooling.git_guard import (
    GuardError,
    automation_lock_active,
    ensure_outgoing_history_preserves_online_state,
)

DEFAULT_DESKTOP = Path("/Users/Dave/desktop/vsc/ai_macro")
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"

ONLINE_OWNED_PREFIXES = ("data/", "archive/")

LOCAL_PRESERVE_PREFIXES = (
    ".git/",
    ".venv/",
    "venv/",
    "automation_artifacts/",
)
LOCAL_PRESERVE_EXACT = {
    ".gitignore",
    ".streamlit/secrets.toml",
}
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = {".pyc", ".pyo"}

PRESERVED_AUDIT_HOLDINGS = {"remediation_backup_20260808", "current_context_retrospective"}


class SyncError(RuntimeError):
    pass


def _run(args: list[str], *, cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise SyncError(detail or f"Command failed: {' '.join(args)}")
    return proc


def _git_root() -> Path:
    proc = _run(["git", "rev-parse", "--show-toplevel"], cwd=Path.cwd())
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SyncError("Run this command from inside the AI Macro Git staging repository.")
    return Path(proc.stdout.strip()).resolve()


def _normalize(relative: str) -> str:
    return str(relative or "").replace("\\", "/").lstrip("./")


def _is_online_owned(relative: str) -> bool:
    normalized = _normalize(relative)
    return any(normalized.startswith(prefix) for prefix in ONLINE_OWNED_PREFIXES)


def _is_local_preserved(relative: str) -> bool:
    normalized = _normalize(relative)
    return normalized in LOCAL_PRESERVE_EXACT or any(
        normalized.startswith(prefix) for prefix in LOCAL_PRESERVE_PREFIXES
    )


def _skip_source_path(relative: str, path: Path) -> bool:
    normalized = _normalize(relative)
    if _is_online_owned(normalized):
        return True
    if _is_local_preserved(normalized):
        return True
    if normalized.startswith("openai_artifacts/"):
        return True
    if any(part in SKIP_NAMES for part in Path(normalized).parts):
        return True
    if path.suffix.casefold() in SKIP_SUFFIXES:
        return True
    return False


def _clean_transient_and_audit(root: Path) -> dict[str, int]:
    counts = {"pycache": 0, "bytecode": 0, "ds_store": 0, "audit": 0}
    audit_root = root / "audit"
    if audit_root.exists():
        for member in list(audit_root.iterdir()):
            if member.name in PRESERVED_AUDIT_HOLDINGS:
                continue
            if member.is_dir():
                shutil.rmtree(member)
            else:
                member.unlink(missing_ok=True)
            counts["audit"] += 1

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        relative_parts = current_path.relative_to(root).parts if current_path != root else ()
        if any(part in {".git", ".venv", "venv"} for part in relative_parts):
            dirs[:] = []
            continue
        for name in list(dirs):
            if name == "__pycache__":
                shutil.rmtree(current_path / name, ignore_errors=True)
                dirs.remove(name)
                counts["pycache"] += 1
        for name in files:
            path = current_path / name
            if name == ".DS_Store":
                path.unlink(missing_ok=True)
                counts["ds_store"] += 1
            elif path.suffix.casefold() in {".pyc", ".pyo"}:
                path.unlink(missing_ok=True)
                counts["bytecode"] += 1
    return counts


def _require_clean(root: Path) -> None:
    proc = _run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, check=True)
    meaningful: list[str] = []
    for line in proc.stdout.splitlines():
        relative = line[3:].strip().replace("\\", "/")
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        parts = Path(relative).parts
        if (
            "__pycache__" in parts
            or Path(relative).suffix.casefold() in {".pyc", ".pyo"}
            or Path(relative).name == ".DS_Store"
        ):
            continue
        meaningful.append(line)
    if meaningful:
        raise SyncError(
            "The Git staging repository has uncommitted changes. Commit, discard, "
            "or move them before desktop reconciliation."
        )


def _sync_remote_head(root: Path, *, remote: str, branch: str) -> None:
    _run(["git", "fetch", "--quiet", remote, branch], cwd=root, check=True)
    remote_ref = f"{remote}/{branch}"
    local_sha = _run(["git", "rev-parse", "HEAD"], cwd=root, check=True).stdout.strip()
    remote_sha = _run(["git", "rev-parse", remote_ref], cwd=root, check=True).stdout.strip()
    if local_sha == remote_sha:
        return

    remote_is_ancestor = _run(
        ["git", "merge-base", "--is-ancestor", remote_ref, "HEAD"],
        cwd=root,
    )
    local_is_ancestor = _run(
        ["git", "merge-base", "--is-ancestor", "HEAD", remote_ref],
        cwd=root,
    )
    if local_is_ancestor.returncode == 0:
        _run(["git", "merge", "--ff-only", remote_ref], cwd=root, check=True)
        return
    if remote_is_ancestor.returncode == 0:
        ensure_outgoing_history_preserves_online_state(
            root,
            remote=remote,
            branch=branch,
        )
        return
    raise SyncError(
        "The local Git staging branch and origin/main have diverged. Resolve that "
        "Git history before running desktop reconciliation."
    )


def _tree_files(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() or path.is_symlink()
    }


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _mirror_directory(source: Path, destination: Path) -> dict[str, int]:
    """Make ``destination`` an exact file mirror of ``source``."""

    if not source.exists() or not source.is_dir():
        raise SyncError(f"Online-owned source directory is missing: {source}")

    if destination.exists() and not destination.is_dir():
        _remove_path(destination)
    destination.mkdir(parents=True, exist_ok=True)

    source_files = _tree_files(source)
    destination_files = _tree_files(destination)
    counts = {"copied": 0, "removed": 0, "unchanged": 0}

    for relative, path in sorted(destination_files.items(), reverse=True):
        if relative in source_files:
            continue
        _remove_path(path)
        counts["removed"] += 1

    for relative in source_files:
        target = destination / relative
        if target.exists() and target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
            counts["removed"] += 1

    for relative, source_path in source_files.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)

        if source_path.is_symlink():
            link_target = os.readlink(source_path)
            if target.is_symlink() and os.readlink(target) == link_target:
                counts["unchanged"] += 1
                continue
            _remove_path(target)
            target.symlink_to(link_target)
            counts["copied"] += 1
            continue

        if target.exists() and target.is_file():
            try:
                if sha256_file(source_path) == sha256_file(target):
                    counts["unchanged"] += 1
                    continue
            except OSError:
                pass
        elif target.exists():
            _remove_path(target)

        shutil.copy2(source_path, target)
        counts["copied"] += 1

    if destination.exists():
        for path in sorted(
            [item for item in destination.rglob("*") if item.is_dir()],
            key=lambda item: len(item.parts),
            reverse=True,
        ):
            try:
                path.rmdir()
            except OSError:
                pass

    source_after = _tree_files(source)
    destination_after = _tree_files(destination)
    if set(source_after) != set(destination_after):
        raise SyncError(f"Mirror membership mismatch after syncing {source.name}.")

    for relative, source_path in source_after.items():
        target = destination_after[relative]
        if source_path.is_symlink():
            if not target.is_symlink() or os.readlink(source_path) != os.readlink(target):
                raise SyncError(f"Mirror symlink mismatch: {source.name}/{relative}")
        else:
            if target.is_symlink() or sha256_file(source_path) != sha256_file(target):
                raise SyncError(f"Mirror content mismatch: {source.name}/{relative}")

    return counts


def _protected_regular_hashes(root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for root_name in ("data", "archive"):
        for relative, path in _tree_files(root / root_name).items():
            if path.is_file() and not path.is_symlink():
                hashes[f"{root_name}/{relative}"] = sha256_file(path)
    return hashes


def _reconcile_retained_state(desktop: Path, target: Path) -> dict[str, int]:
    """Mirror online-owned ``data/`` and ``archive/`` from Git to desktop."""

    before = _protected_regular_hashes(target)
    totals = {"copied": 0, "removed": 0, "unchanged": 0}
    for root_name in ("data", "archive"):
        counts = _mirror_directory(target / root_name, desktop / root_name)
        for key in totals:
            totals[key] += counts[key]
    after = _protected_regular_hashes(target)
    if before != after:
        raise SyncError("Git-owned data/archive changed during desktop reconciliation.")
    return totals


def _copy_program_surface(desktop: Path, target: Path) -> dict[str, int]:
    """Mirror the desktop-owned program surface into Git, including deletions."""

    counts = {"copied": 0, "deleted": 0}

    tracked = _run(["git", "ls-files", "-z"], cwd=target, check=True).stdout.split("\0")
    for relative in [item for item in tracked if item]:
        normalized = _normalize(relative)
        target_path = target / normalized
        source_path = desktop / normalized
        if _skip_source_path(normalized, target_path):
            continue
        if source_path.exists() or source_path.is_symlink():
            continue
        if target_path.exists() or target_path.is_symlink():
            _remove_path(target_path)
            counts["deleted"] += 1

    for source in desktop.rglob("*"):
        if not source.is_file() and not source.is_symlink():
            continue
        relative = source.relative_to(desktop).as_posix()
        if _skip_source_path(relative, source):
            continue

        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)

        if source.is_symlink():
            link_target = os.readlink(source)
            if destination.is_symlink() and os.readlink(destination) == link_target:
                continue
            _remove_path(destination)
            destination.symlink_to(link_target)
            counts["copied"] += 1
            continue

        if destination.exists() and destination.is_file():
            try:
                if sha256_file(source) == sha256_file(destination):
                    continue
            except OSError:
                pass
        elif destination.exists():
            _remove_path(destination)

        shutil.copy2(source, destination)
        counts["copied"] += 1

    return counts


def _read_artifact_time(payload: dict[str, Any]) -> datetime | None:
    candidates = [
        ((payload.get("publication") or {}).get("published_at")),
        payload.get("published_at"),
        payload.get("generated_at"),
        payload.get("finished_at"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if not text:
            continue
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _artifact_valid(payload: dict[str, Any]) -> bool:
    return bool(
        payload
        and (payload.get("validation") or {}).get("passed")
        and isinstance(payload.get("reads"), dict)
    )


def _reconcile_openai(desktop: Path, target: Path) -> str:
    source_root = desktop / "openai_artifacts"
    target_root = target / "openai_artifacts"
    target_root.mkdir(parents=True, exist_ok=True)

    source_attempts = source_root / "attempts"
    target_attempts = target_root / "attempts"
    target_attempts.mkdir(parents=True, exist_ok=True)
    if source_attempts.exists():
        for source in source_attempts.glob("*.json"):
            destination = target_attempts / source.name
            if destination.exists():
                if sha256_file(source) != sha256_file(destination):
                    raise SyncError(
                        f"Paid-attempt identity collision with different content: {source.name}"
                    )
                continue
            shutil.copy2(source, destination)

    source_current = source_root / "current.json"
    target_current = target_root / "current.json"
    left = _load_json(source_current)
    right = _load_json(target_current)
    left_valid = _artifact_valid(left)
    right_valid = _artifact_valid(right)
    if left_valid and not right_valid:
        shutil.copy2(source_current, target_current)
        return "desktop"
    if right_valid and not left_valid:
        return "remote"
    if not left_valid and not right_valid:
        return "none"
    if (
        source_current.exists()
        and target_current.exists()
        and sha256_file(source_current) == sha256_file(target_current)
    ):
        return "same"

    lt = _read_artifact_time(left)
    rt = _read_artifact_time(right)
    if lt and rt and lt > rt:
        shutil.copy2(source_current, target_current)
        return "desktop"
    if lt and rt and rt > lt:
        return "remote"
    if lt and not rt:
        shutil.copy2(source_current, target_current)
        return "desktop"
    if rt and not lt:
        return "remote"
    raise SyncError(
        "Validated Read artifacts differ but do not have an unambiguous "
        "publication/generation ordering."
    )


def _python_for(root: Path) -> str:
    candidates = [root / ".venv" / "bin" / "python", root / "venv" / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _restore_release_manifest(root: Path, original: bytes | None) -> None:
    path = root / "data" / "release_manifest.json"
    if original is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(original)


def _rebuild_and_test(root: Path) -> None:
    """Run verification without leaving any ``data/`` or ``archive/`` writes."""

    python = _python_for(root)
    before = _protected_regular_hashes(root)
    release_manifest = root / "data" / "release_manifest.json"
    original_release = release_manifest.read_bytes() if release_manifest.exists() else None

    try:
        build = subprocess.run(
            [python, "helpers/build_release_manifest.py"],
            cwd=root,
            text=True,
        )
        if build.returncode != 0:
            raise SyncError(
                "Post-reconciliation verification failed: helpers/build_release_manifest.py"
            )

        integrity = subprocess.run(
            [python, "helpers/integrity_gate.py"],
            cwd=root,
            text=True,
        )
        if integrity.returncode != 0:
            raise SyncError("Post-reconciliation verification failed: helpers/integrity_gate.py")
    finally:
        _restore_release_manifest(root, original_release)

    commands = [
        [python, "helpers/application_import_smoke_test.py"],
        [python, "helpers/read_architecture_smoke_test.py"],
        [python, "helpers/public_copy_smoke_test.py"],
        [python, "helpers/phase1_value_transmission_smoke_test.py"],
        [python, "helpers/automation_contract_smoke_test.py"],
        [python, "helpers/state_reconciliation_smoke_test.py"],
    ]
    for command in commands:
        proc = subprocess.run(command, cwd=root, text=True)
        if proc.returncode != 0:
            raise SyncError(f"Post-reconciliation verification failed: {' '.join(command[1:])}")

    after = _protected_regular_hashes(root)
    if before != after:
        raise SyncError(
            "Verification modified GitHub-owned data/archive state. "
            "Reconciliation stopped before commit."
        )


def reconcile(
    desktop: Path,
    git_root: Path,
    *,
    remote: str,
    branch: str,
    run_tests: bool = True,
) -> None:
    desktop = desktop.resolve()
    if not (desktop / "ai_macro.py").exists():
        raise SyncError(f"Desktop master is not an AI Macro project: {desktop}")
    if desktop == git_root:
        raise SyncError("Desktop master and Git staging repository must be different directories.")
    if automation_lock_active(git_root, remote=remote):
        raise SyncError(
            "AI Macro automated refresh is currently in progress. Desktop "
            "reconciliation is blocked until it finishes."
        )

    _require_clean(git_root)
    _sync_remote_head(git_root, remote=remote, branch=branch)

    ensure_outgoing_history_preserves_online_state(
        git_root,
        remote=remote,
        branch=branch,
    )

    retained_counts = _reconcile_retained_state(desktop, git_root)
    program_counts = _copy_program_surface(desktop, git_root)
    read_choice = _reconcile_openai(desktop, git_root)
    cleanup = _clean_transient_and_audit(git_root)

    if run_tests:
        _rebuild_and_test(git_root)

    print("Desktop reconciliation complete.")
    print(
        "Program surface from desktop: "
        f"updated {program_counts['copied']} · deleted {program_counts['deleted']}"
    )
    print(
        "Online-owned data/archive mirrored to desktop: "
        f"copied {retained_counts['copied']} · removed local-only {retained_counts['removed']} "
        f"· unchanged {retained_counts['unchanged']}"
    )
    print(f"Validated Read selection: {read_choice}")
    print("Automation ledger: preserved from Git/online state")
    print("Push policy: outgoing desktop commits may not touch data/ or archive/")
    print(
        "Cleanup: "
        f"audit outputs {cleanup['audit']} · pycache {cleanup['pycache']} · "
        f"bytecode {cleanup['bytecode']} · .DS_Store {cleanup['ds_store']}"
    )
    print(
        "Review `git status`, then stage/commit the program changes. "
        "The pre-push guard will re-check the automation lock, remote head, "
        "and protected retained-state history."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, default=DEFAULT_DESKTOP)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip verification gates (not recommended).",
    )
    args = parser.parse_args(argv)
    try:
        root = _git_root()
        reconcile(
            args.desktop,
            root,
            remote=args.remote,
            branch=args.branch,
            run_tests=not args.skip_tests,
        )
        return 0
    except (SyncError, GuardError) as exc:
        print(f"Reconciliation stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
