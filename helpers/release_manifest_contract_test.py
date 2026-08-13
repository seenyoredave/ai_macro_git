"""Focused contract for runtime-safe release-manifest inputs."""

from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from helpers.build_release_manifest import RELEASE_FILES, build_manifest  # noqa: E402


def main() -> None:
    if "AGENTS.md" in RELEASE_FILES:
        raise AssertionError("Agent-maintenance instructions became a runtime release input.")

    manifest = build_manifest()
    files = manifest.get("files") or {}
    if set(files) != set(RELEASE_FILES):
        raise AssertionError("Release manifest does not match the declared runtime inputs.")
    if "ai_macro.py" not in files or "helpers/build_release_manifest.py" not in files:
        raise AssertionError("Release manifest omits its application or builder contract.")

    print(
        "PASS  release manifest · runtime inputs only · "
        f"{len(files)} files · AGENTS.md excluded"
    )


if __name__ == "__main__":
    main()
