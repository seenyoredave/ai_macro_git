"""Reconcile the desktop master into the Git staging repository safely.

Code/config follows the desktop master. Mutable retained research state follows a
per-file newest-wins ledger. Automation artifacts remain online-owned, paid
attempts are unioned, and the currently published validated Read is selected by
its own publication/generation timestamp.
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
import tempfile
from typing import Any

from automation.retained_state import (
    build_retained_state_manifest,
    choose_newer_entry,
    is_retained_state_path,
    load_retained_state_manifest,
    merged_manifest,
    refresh_retained_state_manifest,
    sha256_file,
    write_manifest,
)
from tooling.git_guard import GuardError, automation_lock_active

DEFAULT_DESKTOP = Path("/Users/Dave/desktop/vsc/ai_macro")
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"

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


def _clean_transient_and_audit(root: Path) -> dict[str, int]:
    counts = {"pycache": 0, "bytecode": 0, "ds_store": 0, "audit": 0}
    audit_root = root / "audit"
    if audit_root.exists():
        for child in list(audit_root.iterdir()):
            if child.name in PRESERVED_AUDIT_HOLDINGS:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink(missing_ok=True)
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


def _require_clean(root: Path) -> None:
    proc = _run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, check=True)
    meaningful: list[str] = []
    for line in proc.stdout.splitlines():
        relative = line[3:].strip().replace("\\", "/")
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        parts = Path(relative).parts
        if "__pycache__" in parts or Path(relative).suffix.casefold() in {".pyc", ".pyo"} or Path(relative).name == ".DS_Store":
            continue
        meaningful.append(line)
    if meaningful:
        raise SyncError(
            "The Git staging repository has uncommitted changes. Commit, discard, or move them before desktop reconciliation."
        )


def _sync_remote_head(root: Path, *, remote: str, branch: str) -> None:
    _run(["git", "fetch", "--quiet", remote, branch], cwd=root, check=True)
    remote_ref = f"{remote}/{branch}"
    local_sha = _run(["git", "rev-parse", "HEAD"], cwd=root, check=True).stdout.strip()
    remote_sha = _run(["git", "rev-parse", remote_ref], cwd=root, check=True).stdout.strip()
    if local_sha == remote_sha:
        return
    remote_is_ancestor = _run(["git", "merge-base", "--is-ancestor", remote_ref, "HEAD"], cwd=root)
    local_is_ancestor = _run(["git", "merge-base", "--is-ancestor", "HEAD", remote_ref], cwd=root)
    if local_is_ancestor.returncode == 0:
        _run(["git", "merge", "--ff-only", remote_ref], cwd=root, check=True)
        return
    if remote_is_ancestor.returncode == 0:
        # Local commits are already ahead of origin. Preserve them and reconcile
        # the desktop onto the current local staging state.
        return
    raise SyncError(
        "The local Git staging branch and origin/main have diverged. Resolve that Git history before running desktop reconciliation."
    )


def _is_local_preserved(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lstrip("./")
    return normalized in LOCAL_PRESERVE_EXACT or any(normalized.startswith(prefix) for prefix in LOCAL_PRESERVE_PREFIXES)


def _skip_source_path(relative: str, path: Path) -> bool:
    normalized = relative.replace("\\", "/").lstrip("./")
    if _is_local_preserved(normalized):
        return True
    if normalized.startswith("openai_artifacts/"):
        return True
    if normalized.startswith("data/") and is_retained_state_path(normalized):
        return True
    if is_retained_state_path(normalized):
        return True
    if any(part in SKIP_NAMES for part in Path(normalized).parts):
        return True
    if path.suffix.casefold() in SKIP_SUFFIXES:
        return True
    return False


def _copy_program_surface(desktop: Path, target: Path) -> int:
    copied = 0
    for source in desktop.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(desktop).as_posix()
        if _skip_source_path(relative, source):
            continue
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and sha256_file(source) == sha256_file(destination):
            continue
        shutil.copy2(source, destination)
        copied += 1
    return copied


def _git_path_time(root: Path, relative: str) -> datetime:
    proc = _run(["git", "log", "-1", "--format=%cI", "--", relative], cwd=root)
    text = proc.stdout.strip()
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    path = root / relative
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)


def _remote_state_manifest(root: Path) -> dict[str, Any]:
    from automation.retained_state import iter_retained_state_files

    existing = load_retained_state_manifest(root)
    actual = {path.relative_to(root).as_posix(): path for path in iter_retained_state_files(root)}
    if existing:
        # Validate both membership and hashes. If a file changed or appeared
        # without advancing the ledger, use that path's Git commit time as the
        # conservative repair timestamp. Removed files naturally fall out when
        # the manifest is rebuilt.
        prior_files = dict(existing.get("files") or {})
        bootstrap: dict[str, datetime] = {}
        needs_rebuild = set(actual) != set(prior_files)
        for relative, path in actual.items():
            entry = dict(prior_files.get(relative) or {})
            if not entry or sha256_file(path) != entry.get("sha256"):
                bootstrap[relative] = _git_path_time(root, relative)
                needs_rebuild = True
        if not needs_rebuild:
            return existing
        return build_retained_state_manifest(
            root=root,
            source="git_repair",
            previous=existing,
            bootstrap_times=bootstrap,
        )

    bootstrap: dict[str, datetime] = {}
    for relative in actual:
        bootstrap[relative] = _git_path_time(root, relative)
    return build_retained_state_manifest(
        root=root,
        source="git_bootstrap",
        previous={},
        bootstrap_times=bootstrap,
    )


def _reconcile_retained_state(desktop: Path, target: Path) -> dict[str, int]:
    # A reconciled desktop normally already has a ledger. This scan also catches any
    # owner edits that changed retained content outside the normal refresh path.
    desktop_manifest = refresh_retained_state_manifest(root=desktop, source="desktop_sync_scan")
    remote_manifest = _remote_state_manifest(target)
    desktop_entries = dict(desktop_manifest.get("files") or {})
    remote_entries = dict(remote_manifest.get("files") or {})
    selected: dict[str, dict[str, Any]] = {}
    counts = {"desktop": 0, "remote": 0, "same": 0}

    for relative in sorted(set(desktop_entries) | set(remote_entries)):
        left = desktop_entries.get(relative)
        right = remote_entries.get(relative)
        decision = choose_newer_entry(relative, left, right)
        desktop_path = desktop / relative
        target_path = target / relative

        if decision == "left":
            if not desktop_path.exists():
                raise SyncError(f"Desktop ledger references a missing retained file: {relative}")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(desktop_path, target_path)
            selected[relative] = dict(left or {})
            counts["desktop"] += 1
        elif decision == "right":
            if not target_path.exists():
                raise SyncError(f"Git ledger references a missing retained file: {relative}")
            selected[relative] = dict(right or {})
            counts["remote"] += 1
        else:
            entry = dict(left or right or {})
            if not target_path.exists() and desktop_path.exists():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(desktop_path, target_path)
            selected[relative] = entry
            counts["same"] += 1

    write_manifest(
        target,
        merged_manifest(selected_entries=selected, source="desktop_git_reconciliation"),
    )
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
    return bool(payload and (payload.get("validation") or {}).get("passed") and isinstance(payload.get("reads"), dict))


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
                    raise SyncError(f"Paid-attempt identity collision with different content: {source.name}")
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
    if source_current.exists() and target_current.exists() and sha256_file(source_current) == sha256_file(target_current):
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
    raise SyncError("Validated Read artifacts differ but do not have an unambiguous publication/generation ordering.")


def _python_for(root: Path) -> str:
    candidates = [root / ".venv" / "bin" / "python", root / "venv" / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _rebuild_and_test(root: Path) -> None:
    python = _python_for(root)
    commands = [
        [python, "helpers/build_release_manifest.py"],
        [python, "helpers/integrity_gate.py"],
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


def reconcile(desktop: Path, git_root: Path, *, remote: str, branch: str, run_tests: bool = True) -> None:
    desktop = desktop.resolve()
    if not (desktop / "ai_macro.py").exists():
        raise SyncError(f"Desktop master is not an AI Macro project: {desktop}")
    if desktop == git_root:
        raise SyncError("Desktop master and Git staging repository must be different directories.")
    if automation_lock_active(git_root, remote=remote):
        raise SyncError(
            "AI Macro automated refresh is currently in progress. Desktop reconciliation is blocked until it finishes."
        )

    _require_clean(git_root)
    _sync_remote_head(git_root, remote=remote, branch=branch)

    copied = _copy_program_surface(desktop, git_root)
    state_counts = _reconcile_retained_state(desktop, git_root)
    read_choice = _reconcile_openai(desktop, git_root)
    cleanup = _clean_transient_and_audit(git_root)

    # automation_artifacts/ is intentionally never copied from desktop. The
    # freshly fetched Git state remains authoritative for the online ledger.
    if run_tests:
        _rebuild_and_test(git_root)

    print("Desktop reconciliation complete.")
    print(f"Program files updated from desktop: {copied}")
    print(
        "Retained state: "
        f"desktop newer {state_counts['desktop']} · online newer {state_counts['remote']} · unchanged {state_counts['same']}"
    )
    print(f"Validated Read selection: {read_choice}")
    print("Automation ledger: preserved from Git/online state")
    print(
        "Cleanup: "
        f"audit outputs {cleanup['audit']} · pycache {cleanup['pycache']} · "
        f"bytecode {cleanup['bytecode']} · .DS_Store {cleanup['ds_store']}"
    )
    print("Review `git status`, then commit and push normally. The pre-push guard will re-check the automation lock and remote head.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", type=Path, default=DEFAULT_DESKTOP)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--skip-tests", action="store_true", help="Skip verification gates (not recommended).")
    args = parser.parse_args(argv)
    try:
        root = _git_root()
        reconcile(args.desktop, root, remote=args.remote, branch=args.branch, run_tests=not args.skip_tests)
        return 0
    except (SyncError, GuardError) as exc:
        print(f"Reconciliation stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
