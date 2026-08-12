"""Network-free Git contract tests for the local automation push guard."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tooling.git_guard import AUTOMATION_LOCK_REF, GuardError, pre_push_check


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def must(args: list[str], cwd: Path) -> str:
    proc = run(args, cwd)
    if proc.returncode != 0:
        raise AssertionError((proc.stderr or proc.stdout or "").strip())
    return proc.stdout.strip()


def identity(root: Path) -> None:
    must(["git", "config", "user.name", "AI Macro Test"], root)
    must(["git", "config", "user.email", "test@example.invalid"], root)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ai_macro_push_guard_") as tmp:
        base = Path(tmp)
        remote = base / "remote.git"
        must(["git", "init", "--bare", str(remote)], base)
        repo = base / "repo"
        must(["git", "clone", str(remote), str(repo)], base)
        identity(repo)
        must(["git", "checkout", "-b", "main"], repo)
        (repo / "seed.txt").write_text("seed\n")
        must(["git", "add", "seed.txt"], repo)
        must(["git", "commit", "-m", "seed"], repo)
        must(["git", "push", "-u", "origin", "main"], repo)

        pre_push_check(repo)

        must(["git", "tag", "-a", "ai-macro-automation-refresh-lock", "-m", "active"], repo)
        must(["git", "push", "origin", AUTOMATION_LOCK_REF], repo)
        try:
            pre_push_check(repo)
        except GuardError as exc:
            assert "currently in progress" in str(exc)
        else:
            raise AssertionError("Active automation lock did not block push.")
        must(["git", "push", "origin", f":{AUTOMATION_LOCK_REF}"], repo)
        must(["git", "tag", "-d", "ai-macro-automation-refresh-lock"], repo)

        other = base / "other"
        must(["git", "clone", str(remote), str(other)], base)
        identity(other)
        must(["git", "checkout", "main"], other)
        (other / "remote.txt").write_text("new remote state\n")
        must(["git", "add", "remote.txt"], other)
        must(["git", "commit", "-m", "remote advance"], other)
        must(["git", "push", "origin", "main"], other)
        try:
            pre_push_check(repo)
        except GuardError as exc:
            assert "contains commits" in str(exc)
        else:
            raise AssertionError("Remote-ahead state did not block push.")

    print("PASS  local Git push guard · active refresh lock blocks · remote-ahead blocks · no GitHub API dependency")


if __name__ == "__main__":
    main()
