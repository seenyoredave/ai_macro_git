"""Focused contracts for online-owned retained-state reconciliation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automation.retained_state import sha256_file
from tooling.desktop_sync import (
    _copy_program_surface,
    _reconcile_openai,
    _reconcile_retained_state,
)
from tooling.git_guard import online_owned_paths_in_range


def _artifact(stamp: str, text: str) -> dict:
    return {
        "status": "validated",
        "generated_at": stamp,
        "publication": {"published_at": stamp},
        "validation": {"passed": True},
        "reads": {"macro": {"headline": text}},
    }


def _git(args: list[str], cwd: Path) -> None:
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise AssertionError((proc.stderr or proc.stdout).strip())


def _tree_hashes(root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for base in ("data", "archive"):
        folder = root / base
        if not folder.exists():
            continue
        for path in folder.rglob("*"):
            if path.is_file():
                result[f"{base}/{path.relative_to(folder).as_posix()}"] = sha256_file(path)
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ai_macro_state_reconcile_") as tmp:
        base = Path(tmp)
        desktop = base / "desktop"
        git = base / "git"
        for root in (desktop, git):
            (root / "data").mkdir(parents=True)
            (root / "archive").mkdir(parents=True)
            (root / "openai_artifacts" / "attempts").mkdir(parents=True)

        # Git is authoritative even when the desktop copy looks "newer".
        (desktop / "data" / "alpha.csv").write_text("value\n999\n", encoding="utf-8")
        (git / "data" / "alpha.csv").write_text("value\n2\n", encoding="utf-8")
        (desktop / "archive" / "beta.csv").write_text("value\n999\n", encoding="utf-8")
        (git / "archive" / "beta.csv").write_text("value\n8\n", encoding="utf-8")

        # Remote-only state must download; desktop-only state must disappear.
        (git / "data" / "remote_only.json").write_text('{"owner":"git"}\n', encoding="utf-8")
        (desktop / "archive" / "desktop_only.csv").write_text("stale\n1\n", encoding="utf-8")

        git_before = _tree_hashes(git)
        counts = _reconcile_retained_state(desktop, git)
        git_after = _tree_hashes(git)

        assert git_before == git_after, "Desktop reconciliation modified Git-owned state"
        assert _tree_hashes(desktop) == git_after, "Desktop data/archive is not an exact Git mirror"
        assert (desktop / "data" / "alpha.csv").read_text() == "value\n2\n"
        assert (desktop / "archive" / "beta.csv").read_text() == "value\n8\n"
        assert (desktop / "data" / "remote_only.json").exists()
        assert not (desktop / "archive" / "desktop_only.csv").exists()
        assert counts["copied"] >= 3
        assert counts["removed"] >= 1

        # Program synchronization must never copy desktop data/archive back into Git.
        repo = base / "program_repo"
        desktop_program = base / "program_desktop"
        repo.mkdir()
        desktop_program.mkdir()
        _git(["git", "init", "-b", "main"], repo)
        _git(["git", "config", "user.email", "test@example.com"], repo)
        _git(["git", "config", "user.name", "AI Macro Test"], repo)
        (repo / "data").mkdir()
        (repo / "archive").mkdir()
        (desktop_program / "data").mkdir()
        (desktop_program / "archive").mkdir()
        (repo / "code.py").write_text("VALUE = 1\n", encoding="utf-8")
        (repo / "data" / "state.csv").write_text("remote\n", encoding="utf-8")
        (repo / "archive" / "history.csv").write_text("remote\n", encoding="utf-8")
        _git(["git", "add", "-A"], repo)
        _git(["git", "commit", "-m", "base"], repo)

        (desktop_program / "code.py").write_text("VALUE = 2\n", encoding="utf-8")
        (desktop_program / "data" / "state.csv").write_text("desktop-stale\n", encoding="utf-8")
        (desktop_program / "archive" / "history.csv").write_text("desktop-stale\n", encoding="utf-8")

        program_counts = _copy_program_surface(desktop_program, repo)
        assert program_counts["copied"] == 1
        assert (repo / "code.py").read_text() == "VALUE = 2\n"
        assert (repo / "data" / "state.csv").read_text() == "remote\n"
        assert (repo / "archive" / "history.csv").read_text() == "remote\n"

        # The push guard must inspect history, not merely the final net diff.
        guard_repo = base / "guard_repo"
        guard_repo.mkdir()
        _git(["git", "init", "-b", "main"], guard_repo)
        _git(["git", "config", "user.email", "test@example.com"], guard_repo)
        _git(["git", "config", "user.name", "AI Macro Test"], guard_repo)
        (guard_repo / "data").mkdir()
        (guard_repo / "data" / "state.csv").write_text("remote\n", encoding="utf-8")
        (guard_repo / "code.py").write_text("VALUE = 1\n", encoding="utf-8")
        _git(["git", "add", "-A"], guard_repo)
        _git(["git", "commit", "-m", "base"], guard_repo)
        _git(["git", "tag", "base"], guard_repo)

        (guard_repo / "data" / "state.csv").write_text("stale-desktop\n", encoding="utf-8")
        _git(["git", "add", "-A"], guard_repo)
        _git(["git", "commit", "-m", "bad retained state"], guard_repo)

        (guard_repo / "data" / "state.csv").write_text("remote\n", encoding="utf-8")
        (guard_repo / "code.py").write_text("VALUE = 2\n", encoding="utf-8")
        _git(["git", "add", "-A"], guard_repo)
        _git(["git", "commit", "-m", "restore data and change code"], guard_repo)

        touched = online_owned_paths_in_range(guard_repo, "base")
        assert touched, "Guard failed to detect protected paths in outgoing history"
        assert any("data/state.csv" in paths for paths in touched.values())

        # Existing OpenAI artifact policy remains unchanged.
        (desktop / "openai_artifacts" / "attempts" / "desktop.json").write_text(
            '{"attempt":"desktop"}\n', encoding="utf-8"
        )
        (git / "openai_artifacts" / "attempts" / "online.json").write_text(
            '{"attempt":"online"}\n', encoding="utf-8"
        )
        (desktop / "openai_artifacts" / "current.json").write_text(
            json.dumps(_artifact("2026-08-11T10:00:00+00:00", "desktop")), encoding="utf-8"
        )
        (git / "openai_artifacts" / "current.json").write_text(
            json.dumps(_artifact("2026-08-11T11:00:00+00:00", "online")), encoding="utf-8"
        )
        choice = _reconcile_openai(desktop, git)
        assert choice == "remote"
        assert (git / "openai_artifacts" / "attempts" / "desktop.json").exists()
        assert (git / "openai_artifacts" / "attempts" / "online.json").exists()
        current = json.loads((git / "openai_artifacts" / "current.json").read_text())
        assert current["reads"]["macro"]["headline"] == "online"

    print(
        "PASS  reconciliation · data/archive online-owned · exact desktop mirror · "
        "program sync excludes retained state · push history guard"
    )


if __name__ == "__main__":
    main()
