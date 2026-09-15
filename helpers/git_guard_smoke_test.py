from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tooling.git_guard import (
    GuardError,
    ensure_index_preserves_repository_state,
    pre_push_check,
    rebase_from_remote,
    safe_stage,
)
from tooling.repository_policy import is_owner_protected_path


def _run(root: Path, *args: str) -> str:
    proc = subprocess.run(
        list(args),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"Command failed ({proc.returncode}): {' '.join(args)}\n{proc.stderr or proc.stdout}"
        )
    return proc.stdout.strip()


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    cases = {
        "data/current_context.json": True,
        "archive/yf_history.csv": True,
        "archive/nested/state.json": True,
        "archive/archive_reader.py": False,
        "archive/schemas.py": False,
        "loaders/market_loader.py": False,
    }
    for relative, expected in cases.items():
        actual = is_owner_protected_path(relative)
        if actual is not expected:
            raise AssertionError(
                f"Unexpected owner-protection classification for {relative}: {actual}"
            )

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        remote = base / "origin.git"
        root = base / "repo"
        root.mkdir()
        _run(base, "git", "init", "--bare", str(remote))
        _run(root, "git", "init", "-b", "main")
        _run(root, "git", "config", "user.email", "git-guard-test@example.invalid")
        _run(root, "git", "config", "user.name", "AI Macro git-guard test")
        _run(root, "git", "remote", "add", "origin", str(remote))

        _write(root, "app.py", "VALUE = 1\n")
        _write(root, "archive/archive_reader.py", "VALUE = 1\n")
        _write(root, "archive/yf_history.csv", "Date,Value\n2026-09-14,1\n")
        _write(root, "data/state.csv", "Date,Value\n2026-09-14,1\n")
        _run(root, "git", "add", "-A")
        _run(root, "git", "commit", "-m", "base")
        _run(root, "git", "push", "-u", "origin", "main")

        _write(root, "app.py", "VALUE = 2\n")
        _write(root, "archive/archive_reader.py", "VALUE = 2\n")
        _write(root, "archive/new_source.py", "VALUE = 1\n")
        _write(root, "archive/yf_history.csv", "Date,Value\n2026-09-15,2\n")
        _write(root, "archive/new_retained.json", '{"value": 2}\n')
        _write(root, "data/state.csv", "Date,Value\n2026-09-15,2\n")

        staged, protected_local, _ = safe_stage(root)
        expected_staged = {
            "app.py",
            "archive/archive_reader.py",
            "archive/new_source.py",
        }
        if set(staged) != expected_staged:
            raise AssertionError(f"Wrong staged paths: {staged}")

        expected_protected = {
            "archive/yf_history.csv",
            "archive/new_retained.json",
            "data/state.csv",
        }
        if not expected_protected.issubset(set(protected_local)):
            raise AssertionError(
                f"Protected retained state was not left unstaged: {protected_local}"
            )
        ensure_index_preserves_repository_state(root)

        _run(root, "git", "add", "archive/yf_history.csv")
        try:
            ensure_index_preserves_repository_state(root)
        except GuardError:
            pass
        else:
            raise AssertionError("pre-commit guard accepted staged archive retained state")
        _run(root, "git", "reset", "--quiet", "HEAD", "--", "archive/yf_history.csv")

        _run(root, "git", "commit", "-m", "owner source change")
        rebase_from_remote(root)
        pre_push_check(root)
        _run(root, "git", "push", "origin", "main")

        source_on_remote = _run(
            root, "git", "show", "origin/main:archive/archive_reader.py"
        )
        retained_on_remote = _run(
            root, "git", "show", "origin/main:archive/yf_history.csv"
        )
        data_on_remote = _run(root, "git", "show", "origin/main:data/state.csv")
        if source_on_remote != "VALUE = 2":
            raise AssertionError("archive Python source did not survive the guarded push sequence")
        if "2026-09-14,1" not in retained_on_remote or "2026-09-15,2" in retained_on_remote:
            raise AssertionError("archive retained state leaked into the owner push")
        if "2026-09-14,1" not in data_on_remote or "2026-09-15,2" in data_on_remote:
            raise AssertionError("data retained state leaked into the owner push")

    print("PASS  git guard stages archive Python source and excludes retained archive/data state")
    print("PASS  standard stage → commit → rebase → pre-push → push sequence preserves that split")


if __name__ == "__main__":
    main()
