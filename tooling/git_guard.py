"""Local Git push guard for the semi-automated publication repository."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat
import subprocess
import sys

AUTOMATION_LOCK_REF = "refs/tags/ai-macro-automation-refresh-lock"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"
ONLINE_OWNED_PREFIXES = ("data/", "archive/")


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
            "Run the AI Macro desktop reconciliation before pushing so newer online state is preserved."
        )
    raise GuardError("Unable to compare the local branch with the remote branch. The push is blocked.")


def _normalize_path(value: str) -> str:
    return str(value or "").replace("\\", "/").lstrip("./")


def is_online_owned_path(relative: str) -> bool:
    normalized = _normalize_path(relative)
    return any(normalized.startswith(prefix) for prefix in ONLINE_OWNED_PREFIXES)


def online_owned_paths_in_range(
    root: Path,
    base_ref: str,
    *,
    head_ref: str = "HEAD",
) -> dict[str, list[str]]:
    """Return protected paths touched by each commit in ``base_ref..head_ref``."""

    revs = _run(
        ["git", "rev-list", "--reverse", f"{base_ref}..{head_ref}"],
        cwd=root,
        check=True,
    )
    touched: dict[str, list[str]] = {}
    for commit in [line.strip() for line in revs.stdout.splitlines() if line.strip()]:
        diff = _run(
            [
                "git",
                "diff-tree",
                "--root",
                "-m",
                "--no-commit-id",
                "--name-only",
                "-r",
                commit,
                "--",
                "data",
                "archive",
            ],
            cwd=root,
            check=True,
        )
        paths = sorted(
            {
                _normalize_path(line)
                for line in diff.stdout.splitlines()
                if is_online_owned_path(line)
            }
        )
        if paths:
            touched[commit] = paths
    return touched


def ensure_outgoing_history_preserves_online_state(
    root: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> None:
    remote_ref = f"{remote}/{branch}"
    touched = online_owned_paths_in_range(root, remote_ref)
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
        "Outgoing desktop commit history touches GitHub-owned retained state under "
        "`data/` or `archive/`. The push is blocked. Those directories may only "
        "flow from GitHub to the desktop during reconciliation."
        + (f"\n  {detail}" if detail else "")
    )


def pre_push_check(
    root: Path,
    *,
    remote: str = DEFAULT_REMOTE,
    branch: str = DEFAULT_BRANCH,
) -> None:
    if automation_lock_active(root, remote=remote):
        raise GuardError(
            "AI Macro automated refresh is currently in progress. Nothing was sent. "
            "Wait for the workflow to complete, then run desktop reconciliation again before pushing."
        )
    ensure_remote_not_ahead(root, remote=remote, branch=branch)
    ensure_outgoing_history_preserves_online_state(root, remote=remote, branch=branch)


def install_guard(root: Path) -> Path:
    hook = root / ".githooks" / "pre-push"
    if not hook.exists():
        raise GuardError(f"Push guard is missing: {hook}")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    _run(["git", "config", "--local", "core.hooksPath", ".githooks"], cwd=root, check=True)
    configured = _run(["git", "config", "--local", "--get", "core.hooksPath"], cwd=root, check=True)
    if configured.stdout.strip() != ".githooks":
        raise GuardError("Git did not retain the expected core.hooksPath setting.")
    return hook


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    push = sub.add_parser("pre-push", help="Run refresh-lock, remote-ahead, and retained-state checks.")
    push.add_argument("--remote", default=DEFAULT_REMOTE)
    push.add_argument("--branch", default=DEFAULT_BRANCH)

    sub.add_parser("install", help="Install .githooks as this repository's local hook path.")
    sub.add_parser("status", help="Report whether the automation lock is currently active.")

    args = parser.parse_args(argv)
    try:
        root = repo_root()
        if args.command == "pre-push":
            pre_push_check(root, remote=args.remote, branch=args.branch)
            return 0
        if args.command == "install":
            hook = install_guard(root)
            print(f"Installed AI Macro pre-push guard: {hook}")
            return 0
        if args.command == "status":
            active = automation_lock_active(root)
            print("active" if active else "inactive")
            return 0
    except GuardError as exc:
        print(f"Push blocked: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
