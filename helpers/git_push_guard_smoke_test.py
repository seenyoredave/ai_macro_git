"""Network-free Git contract tests for the local information-flow guard."""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tooling.git_guard import (
    AUTOMATION_LOCK_REF,
    GuardError,
    ensure_index_preserves_repository_state,
    pre_push_check,
    rebase_from_remote,
    safe_stage,
)


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


def seed_repo(base: Path) -> tuple[Path, Path]:
    remote = base / "remote.git"
    must(["git", "init", "--bare", str(remote)], base)
    repo = base / "repo"
    must(["git", "clone", str(remote), str(repo)], base)
    identity(repo)
    must(["git", "checkout", "-b", "main"], repo)
    (repo / "data").mkdir()
    (repo / "archive").mkdir()
    (repo / "src").mkdir()
    (repo / "data" / "state.csv").write_text("remote-1\n")
    (repo / "archive" / "history.csv").write_text("remote-1\n")
    (repo / "src" / "app.py").write_text("VALUE = 1\n")
    must(["git", "add", "-A"], repo)
    must(["git", "commit", "-m", "seed"], repo)
    must(["git", "push", "-u", "origin", "main"], repo)
    return remote, repo


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ai_macro_git_guard_") as tmp:
        base = Path(tmp)
        remote, repo = seed_repo(base)

        (repo / "src" / "app.py").write_text("VALUE = 2\n")
        (repo / "src" / "new.py").write_text("NEW = True\n")
        (repo / "data" / "state.csv").write_text("local-stale\n")
        (repo / "data" / "local_only.csv").write_text("local-only\n")
        (repo / "archive" / "history.csv").write_text("local-stale\n")
        must(["git", "add", "data/state.csv", "data/local_only.csv"], repo)

        staged, protected_local, removed_from_index = safe_stage(repo)
        assert staged == ["src/app.py", "src/new.py"]
        assert removed_from_index == ["data/local_only.csv", "data/state.csv"]
        assert "data/state.csv" in protected_local
        assert "data/local_only.csv" in protected_local
        assert "archive/history.csv" in protected_local
        ensure_index_preserves_repository_state(repo)

        must(["git", "add", "data/state.csv"], repo)
        try:
            ensure_index_preserves_repository_state(repo)
        except GuardError as exc:
            assert "staged commit contains repository-owned retained state" in str(exc)
        else:
            raise AssertionError("Pre-commit index gate accepted protected state.")
        must(["git", "reset", "--quiet", "HEAD", "--", "data/state.csv"], repo)

        must(["git", "commit", "-m", "owner code"], repo)

        other = base / "other"
        must(["git", "clone", str(remote), str(other)], base)
        identity(other)
        must(["git", "checkout", "main"], other)
        (other / "data" / "state.csv").write_text("remote-2\n")
        (other / "data" / "arriving.csv").write_text("remote-arrival\n")
        must(["git", "add", "data"], other)
        must(["git", "commit", "-m", "automation state"], other)
        must(["git", "push", "origin", "main"], other)

        (repo / "data" / "arriving.csv").write_text("local-untracked-copy\n")
        replaced = rebase_from_remote(repo)
        assert replaced == ["data/arriving.csv"]
        assert (repo / "data" / "state.csv").read_text() == "remote-2\n"
        assert (repo / "data" / "arriving.csv").read_text() == "remote-arrival\n"
        assert (repo / "data" / "local_only.csv").read_text() == "local-only\n"
        assert (repo / "src" / "app.py").read_text() == "VALUE = 2\n"

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

        remote_ahead = base / "remote_ahead"
        must(["git", "clone", str(remote), str(remote_ahead)], base)
        identity(remote_ahead)
        must(["git", "checkout", "main"], remote_ahead)
        (remote_ahead / "remote.txt").write_text("new remote code\n")
        must(["git", "add", "remote.txt"], remote_ahead)
        must(["git", "commit", "-m", "remote advance"], remote_ahead)
        must(["git", "push", "origin", "main"], remote_ahead)
        try:
            pre_push_check(repo)
        except GuardError as exc:
            assert "contains commits" in str(exc)
        else:
            raise AssertionError("Remote-ahead state did not block push.")


        renamed = base / "renamed"
        must(["git", "clone", str(remote), str(renamed)], base)
        identity(renamed)
        must(["git", "checkout", "main"], renamed)
        (renamed / "src" / "moved_state.csv").write_text((renamed / "data" / "state.csv").read_text())
        (renamed / "data" / "state.csv").unlink()
        must(["git", "add", "-A"], renamed)
        try:
            ensure_index_preserves_repository_state(renamed)
        except GuardError as exc:
            assert "data/state.csv" in str(exc)
        else:
            raise AssertionError("Protected deletion disguised as a move escaped the index gate.")

        protected = base / "protected"
        must(["git", "clone", str(remote), str(protected)], base)
        identity(protected)
        must(["git", "checkout", "main"], protected)
        (protected / "data" / "state.csv").write_text("bad owner state\n")
        must(["git", "add", "data/state.csv"], protected)
        must(["git", "commit", "--no-verify", "-m", "bad retained state"], protected)
        (protected / "data" / "state.csv").write_text("remote-2\n")
        (protected / "src" / "app.py").write_text("VALUE = 3\n")
        must(["git", "add", "-A"], protected)
        must(["git", "commit", "--no-verify", "-m", "restore state and change code"], protected)
        try:
            pre_push_check(protected)
        except GuardError as exc:
            assert "repository-owned retained state" in str(exc)
            assert "data/state.csv" in str(exc)
        else:
            raise AssertionError("Protected history escaped by restoring the final data contents.")

    print(
        "PASS  Git information flow · safe stage excludes data/archive · pre-commit blocks protected index · "
        "safe rebase refreshes repository state · active lock blocks · remote-ahead blocks · history scan blocks"
    )


if __name__ == "__main__":
    main()
