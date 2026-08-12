"""Focused contracts for newest-wins retained-state reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from automation.retained_state import sha256_file
from tooling.desktop_sync import _reconcile_openai, _reconcile_retained_state


def _write_manifest(root: Path, rows: dict[str, tuple[str, str]]) -> None:
    files = {}
    for relative, (stamp, owner) in rows.items():
        path = root / relative
        files[relative] = {
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "updated_at_utc": stamp,
            "updated_by": owner,
            "run_id": "test",
        }
    path = root / "data" / "retained_state_manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "manifest_version": "1.0",
        "generated_at_utc": "2026-08-11T12:00:00+00:00",
        "source": "test",
        "run_id": "test",
        "files": files,
    }, indent=2), encoding="utf-8")


def _artifact(stamp: str, text: str) -> dict:
    return {
        "status": "validated",
        "generated_at": stamp,
        "publication": {"published_at": stamp},
        "validation": {"passed": True},
        "reads": {"macro": {"headline": text}},
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ai_macro_state_reconcile_") as tmp:
        base = Path(tmp)
        desktop = base / "desktop"
        git = base / "git"
        for root in (desktop, git):
            (root / "data").mkdir(parents=True)
            (root / "archive").mkdir(parents=True)
            (root / "openai_artifacts" / "attempts").mkdir(parents=True)

        # Online is newer for one file; desktop is newer for another.
        (desktop / "data" / "alpha.csv").write_text("value\n1\n", encoding="utf-8")
        (git / "data" / "alpha.csv").write_text("value\n2\n", encoding="utf-8")
        (desktop / "archive" / "beta.csv").write_text("value\n9\n", encoding="utf-8")
        (git / "archive" / "beta.csv").write_text("value\n8\n", encoding="utf-8")
        _write_manifest(desktop, {
            "data/alpha.csv": ("2026-08-11T10:00:00+00:00", "desktop"),
            "archive/beta.csv": ("2026-08-11T12:00:00+00:00", "desktop"),
        })
        _write_manifest(git, {
            "data/alpha.csv": ("2026-08-11T11:00:00+00:00", "automation"),
            "archive/beta.csv": ("2026-08-11T09:00:00+00:00", "automation"),
        })

        counts = _reconcile_retained_state(desktop, git)
        assert (git / "data" / "alpha.csv").read_text() == "value\n2\n"
        assert (git / "archive" / "beta.csv").read_text() == "value\n9\n"
        assert counts["remote"] == 1 and counts["desktop"] == 1

        # Paid attempts are append-only and the newer validated Read wins.
        (desktop / "openai_artifacts" / "attempts" / "desktop.json").write_text('{"attempt":"desktop"}\n')
        (git / "openai_artifacts" / "attempts" / "online.json").write_text('{"attempt":"online"}\n')
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

    print("PASS  retained-state reconciliation · per-file newest wins · attempts union · newest validated Read wins")


if __name__ == "__main__":
    main()
