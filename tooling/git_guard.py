"""Local Git information-flow guard for the AI Macro repository."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import subprocess
import sys

from tooling.repository_policy import (
    OWNER_PROTECTED_PATHS,
    is_owner_protected_path,
    normalize_repository_path,
    owner_stage_exclusions,
)

AUTOMATION_LOCK_REF = "refs/tags/ai-macro-automation-refresh-lock"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"


class GuardError(RuntimeError):
    pass


def _run(args: list[str], *, cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise GuardError(detail or f"Command failed: {' '.join(args)}")
    return proc


def repo_root(start: Path | None = None) -> Path:
    cwd = (start or Path.cwd()).resolve()
    proc = _run(["git", "rev-parse", "--show-toplevel"], cwd=cwd)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise GuardError("This command must be run inside the AI Macro Git repository.")
    return Path(proc.stdout.strip()).resolve()


def _current_branch(root: Path) -> str:
    proc = _run(["git", "branch", "--show-current"], cwd=root, check=True)
    return proc.stdout.strip()


def _require_main(root: Path, *, branch: str = DEFAULT_BRANCH) -> None:
    current = _current_branch(root)
    if current != branch:
        raise GuardError(f"Owner publication is restricted to branch `{branch}`; current branch is `{current or 'detached HEAD'}`.")


def automation_lock_active(root: Path, *, remote: str = DEFAULT_REMOTE) -> bool:
    proc = _run(
        ["git", "ls-remote", "--exit-code", "--tags", remote, AUTOMATION_LOCK_REF],
        cwd=root,
    )
    if proc.returncode == 0:
        return True
    if proc.returncode == 2:
        return False
    detail = (proc.stderr or proc.stdout or "").strip()
    raise GuardError(
        "Unable to verify whether the AI Macro automation refresh is active. "
        "The push is blocked rather than guessing."
        + (f" Git reported: {detail}" if detail else "")
    )


def ensure_remote_not_ahead(
    root: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> None:
    fetch = _run(["git", "fetch", "--quiet", remote, branch], cwd=root)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "").strip()
        raise GuardError(
            "Unable to refresh the remote branch before push. The push is blocked."
            + (f" Git reported: {detail}" if detail else "")
        )
    remote_ref = f"{remote}/{branch}"
    relation = _run(["git", "merge-base", "--is-ancestor", remote_ref, "HEAD"], cwd=root)
    if relation.returncode == 0:
        return
    if relation.returncode == 1:
        raise GuardError(
            f"{remote_ref} contains commits that are not in the local branch. "
            f"Run `python -m tooling.git_guard rebase --remote {remote} --branch {branch}` before pushing."
        )
    raise GuardError("Unable to compare the local branch with the remote branch. The push is blocked.")


def _split_z(output: str) -> list[str]:
    return [normalize_repository_path(item) for item in output.split("\0") if item]


def _cached_paths(root: Path) -> list[str]:
    proc = _run(["git", "diff", "--cached", "--name-only", "--no-renames", "-z"], cwd=root, check=True)
    return _split_z(proc.stdout)


def _unstaged_paths(root: Path) -> list[str]:
    proc = _run(["git", "diff", "--name-only", "--no-renames", "-z"], cwd=root, check=True)
    return _split_z(proc.stdout)


def _untracked_paths(root: Path) -> list[str]:
    proc = _run(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=root, check=True)
    return _split_z(proc.stdout)


def _working_paths(root: Path) -> list[str]:
    return sorted(set(_cached_paths(root) + _unstaged_paths(root) + _untracked_paths(root)))


def protected_index_paths(root: Path) -> list[str]:
    return sorted(path for path in _cached_paths(root) if is_owner_protected_path(path))


def ensure_index_preserves_repository_state(root: Path) -> None:
    protected = protected_index_paths(root)
    if not protected:
        return
    detail = "\n  ".join(protected[:12])
    if len(protected) > 12:
        detail += f"\n  +{len(protected) - 12} more"
    raise GuardError(
        "The staged commit contains repository-owned retained state under `data/` or `archive/`. "
        "Those paths may exist or change locally, but owner commits may not publish them upstream."
        + (f"\n  {detail}" if detail else "")
    )


def safe_stage(root: Path) -> tuple[list[str], list[str], list[str]]:
    _require_main(root)
    existing = protected_index_paths(root)
    if existing:
        _run(["git", "reset", "--quiet", "HEAD", "--", *existing], cwd=root, check=True)
    _run(["git", "add", "-A", "--", ".", *owner_stage_exclusions()], cwd=root, check=True)
    ensure_index_preserves_repository_state(root)
    staged = _cached_paths(root)
    protected_local = sorted(path for path in set(_unstaged_paths(root) + _untracked_paths(root)) if is_owner_protected_path(path))
    return staged, protected_local, existing


def protected_paths_in_range(
    root: Path,
    base_ref: str,
    *,
    head_ref: str = "HEAD",
) -> dict[str, list[str]]:
    revs = _run(
        ["git", "rev-list", "--reverse", f"{base_ref}..{head_ref}"],
        cwd=root,
        check=True,
    )
    touched: dict[str, list[str]] = {}
    for commit in [line.strip() for line in revs.stdout.splitlines() if line.strip()]:
        diff = _run(
            ["git", "diff-tree", "--root", "-m", "--no-commit-id", "--name-only", "-r", "-z", commit],
            cwd=root,
            check=True,
        )
        paths = sorted({path for path in _split_z(diff.stdout) if is_owner_protected_path(path)})
        if paths:
            touched[commit] = paths
    return touched


def ensure_outgoing_history_preserves_repository_state(
    root: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> None:
    remote_ref = f"{remote}/{branch}"
    touched = protected_paths_in_range(root, remote_ref)
    if not touched:
        return

    examples: list[str] = []
    for commit, paths in touched.items():
        for path in paths:
            examples.append(f"{commit[:8]} {path}")
            if len(examples) >= 8:
                break
        if len(examples) >= 8:
            break

    detail = "\n  ".join(examples)
    raise GuardError(
        "Outgoing owner commit history touches repository-owned retained state under "
        "`data/` or `archive/`. The push is blocked. Local working copies of those "
        "directories must not be published upstream by owner commits."
        + (f"\n  {detail}" if detail else "")
    )


def _remote_has_path(root: Path, remote_ref: str, relative: str) -> bool:
    proc = _run(["git", "cat-file", "-e", f"{remote_ref}:{relative}"], cwd=root)
    return proc.returncode == 0


def rebase_from_remote(
    root: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> list[str]:
    _require_main(root, branch=branch)
    fetch = _run(["git", "fetch", "--quiet", remote, branch], cwd=root)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout or "").strip()
        raise GuardError("Unable to refresh the remote branch before rebase." + (f" Git reported: {detail}" if detail else ""))

    ensure_outgoing_history_preserves_repository_state(root, remote=remote, branch=branch)

    dirty_owner_paths = sorted(path for path in _working_paths(root) if not is_owner_protected_path(path))
    if dirty_owner_paths:
        detail = "\n  ".join(dirty_owner_paths[:12])
        raise GuardError("Commit or otherwise resolve owner-publishable working changes before rebasing." + (f"\n  {detail}" if detail else ""))

    remote_ref = f"{remote}/{branch}"
    replaced_untracked: list[str] = []
    for relative in _untracked_paths(root):
        if not is_owner_protected_path(relative) or not _remote_has_path(root, remote_ref, relative):
            continue
        path = root / relative
        if path.is_file() or path.is_symlink():
            path.unlink(missing_ok=True)
            replaced_untracked.append(relative)

    _run(
        ["git", "restore", "--source=HEAD", "--staged", "--worktree", "--", *OWNER_PROTECTED_PATHS],
        cwd=root,
        check=True,
    )

    rebase = _run(["git", "rebase", remote_ref], cwd=root)
    if rebase.returncode != 0:
        detail = (rebase.stderr or rebase.stdout or "").strip()
        raise GuardError("Git rebase failed." + (f" Git reported: {detail}" if detail else ""))
    return replaced_untracked


def pre_push_check(
    root: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> None:
    _require_main(root, branch=branch)
    ensure_index_preserves_repository_state(root)
    if automation_lock_active(root, remote=remote):
        raise GuardError(
            "AI Macro automated refresh is currently in progress. Nothing was sent. "
            "Wait for the workflow to complete, then update the local branch before pushing."
        )
    ensure_remote_not_ahead(root, remote=remote, branch=branch)
    ensure_outgoing_history_preserves_repository_state(root, remote=remote, branch=branch)


def install_guard(root: Path) -> tuple[Path, ...]:
    hooks = (root / ".githooks" / "pre-commit", root / ".githooks" / "pre-push")
    missing = [str(path) for path in hooks if not path.exists()]
    if missing:
        raise GuardError("Git guard hook is missing: " + ", ".join(missing))
    for hook in hooks:
        hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _run(["git", "config", "--local", "core.hooksPath", ".githooks"], cwd=root, check=True)
    configured = _run(["git", "config", "--local", "--get", "core.hooksPath"], cwd=root, check=True)
    if configured.stdout.strip() != ".githooks":
        raise GuardError("Git did not retain the expected core.hooksPath setting.")
    return hooks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("stage", help="Stage owner-publishable changes while leaving data/archive unstaged.")
    sub.add_parser("pre-commit", help="Reject staged data/archive changes.")

    rebase = sub.add_parser("rebase", help="Refresh repository-owned state and rebase owner commits onto the remote branch.")
    rebase.add_argument("--remote", default=DEFAULT_REMOTE)
    rebase.add_argument("--branch", default=DEFAULT_BRANCH)

    push = sub.add_parser("pre-push", help="Run branch, index, refresh-lock, remote-ahead, and outgoing-history checks.")
    push.add_argument("--remote", default=DEFAULT_REMOTE)
    push.add_argument("--branch", default=DEFAULT_BRANCH)

    sub.add_parser("install", help="Install the repository's pre-commit and pre-push hooks.")
    sub.add_parser("status", help="Report whether the automation lock is currently active.")

    args = parser.parse_args(argv)
    try:
        root = repo_root()
        if args.command == "stage":
            staged, protected_local, removed_from_index = safe_stage(root)
            print(f"Staged owner-publishable paths: {len(staged)}")
            if removed_from_index:
                print(f"Removed data/archive paths from the index: {len(removed_from_index)}")
            if protected_local:
                print(f"Local data/archive paths left unstaged: {len(protected_local)}")
                for relative in protected_local[:12]:
                    print(f"  {relative}")
                if len(protected_local) > 12:
                    print(f"  +{len(protected_local) - 12} more")
            return 0
        if args.command == "pre-commit":
            ensure_index_preserves_repository_state(root)
            return 0
        if args.command == "rebase":
            replaced = rebase_from_remote(root, remote=args.remote, branch=args.branch)
            if replaced:
                print(f"Replaced local untracked paths now owned by {args.remote}/{args.branch}: {len(replaced)}")
            print(f"Rebased onto {args.remote}/{args.branch}.")
            return 0
        if args.command == "pre-push":
            pre_push_check(root, remote=args.remote, branch=args.branch)
            return 0
        if args.command == "install":
            hooks = install_guard(root)
            print("Installed AI Macro Git guards: " + ", ".join(str(path) for path in hooks))
            return 0
        if args.command == "status":
            active = automation_lock_active(root)
            print("active" if active else "inactive")
            return 0
    except GuardError as exc:
        print(f"Git guard stopped: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
