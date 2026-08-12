"""Fail-closed Git transport for the automation publication transaction.

The refresh runner mutates only the Actions working tree. This module verifies
that origin/main has not moved since the workflow started before committing or
pushing those mutations. A user push that slips through the very small lock
startup race therefore wins: automation stops rather than publishing state
computed from an older source revision.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from automation.ledger import STATUS_PATH, write_status


class TransportError(RuntimeError):
    pass


def _run(args: list[str], *, root: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(args, cwd=root, text=True, capture_output=True, check=False)
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise TransportError(detail or f"Command failed: {' '.join(args)}")
    return proc


def _load_status() -> dict[str, Any]:
    if not STATUS_PATH.exists():
        return {}
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _record_transport_failure(message: str, *, result: str) -> None:
    status = _load_status()
    phases = dict(status.get("phases") or {})
    phases["git_transport"] = {
        "status": "failed",
        "reason": result,
        "message": message,
        "at_utc": datetime.now(timezone.utc).isoformat(),
    }
    status["phases"] = phases
    status["runner_result"] = str(status.get("result") or "")
    status["result"] = result
    status["publish_ready"] = False
    status.setdefault("errors", []).append(message)
    write_status(status)


def _remote_head(root: Path, *, remote: str, branch: str) -> str:
    _run(["git", "fetch", "--quiet", remote, branch], root=root, check=True)
    return _run(["git", "rev-parse", f"{remote}/{branch}"], root=root, check=True).stdout.strip()


def _verify_base_unchanged(root: Path, *, remote: str, branch: str, base_sha: str) -> None:
    remote_sha = _remote_head(root, remote=remote, branch=branch)
    if remote_sha != base_sha:
        changed = _run(
            ["git", "diff", "--name-only", f"{base_sha}..{remote}/{branch}"],
            root=root,
        ).stdout.splitlines()
        detail = ", ".join(changed[:12])
        if len(changed) > 12:
            detail += f", +{len(changed) - 12} more"
        raise TransportError(
            "origin/main changed after this automation run started. "
            "Automation will not overwrite or merge a moving publication branch."
            + (f" Remote changes: {detail}" if detail else "")
        )


def _stage(root: Path, mode: str) -> None:
    if mode == "publication":
        paths = ["data/", "archive/", "openai_artifacts/current.json", "automation_artifacts/"]
    elif mode == "ledger":
        paths = ["automation_artifacts/"]
    else:
        raise TransportError(f"Unknown transport mode: {mode}")
    _run(["git", "add", "--", *paths], root=root, check=True)


def publish(mode: str, *, remote: str = "origin", branch: str = "main") -> int:
    root = Path(__file__).resolve().parents[1]
    base_sha = str(os.getenv("GITHUB_SHA", "") or "").strip()
    if not base_sha:
        raise TransportError("GITHUB_SHA is unavailable; refusing an unanchored automation push.")

    _run(["git", "config", "user.name", "ai-macro-automation"], root=root, check=True)
    _run(["git", "config", "user.email", "ai-macro-automation@users.noreply.github.com"], root=root, check=True)

    try:
        _verify_base_unchanged(root, remote=remote, branch=branch, base_sha=base_sha)
    except TransportError as exc:
        _record_transport_failure(str(exc), result="remote_advanced_before_publication")
        raise

    _stage(root, mode)
    if _run(["git", "diff", "--cached", "--quiet"], root=root).returncode == 0:
        return 0

    message = (
        "automation: publish validated AI Macro refresh"
        if mode == "publication"
        else "automation: record AI Macro run"
    )
    _run(["git", "commit", "-m", message], root=root, check=True)

    # Re-check after commit to close the gap between the first comparison and
    # the network push. A final non-fast-forward race is still rejected by Git.
    try:
        _verify_base_unchanged(root, remote=remote, branch=branch, base_sha=base_sha)
    except TransportError as exc:
        _record_transport_failure(str(exc), result="remote_advanced_before_push")
        raise

    push = _run(["git", "push", remote, f"HEAD:{branch}"], root=root)
    if push.returncode != 0:
        detail = (push.stderr or push.stdout or "").strip()
        message = "Git rejected the automation publication push; no force push was attempted."
        if detail:
            message += f" Git reported: {detail}"
        _record_transport_failure(message, result="git_push_rejected")
        raise TransportError(message)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("publication", "ledger"))
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    args = parser.parse_args(argv)
    try:
        return publish(args.mode, remote=args.remote, branch=args.branch)
    except TransportError as exc:
        print(f"Automation Git transport stopped: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
