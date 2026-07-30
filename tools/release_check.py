"""Run the mandatory local release gate for the Streamlit application."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    run([sys.executable, "-m", "compileall", "-q", "."])
    run([sys.executable, "-m", "pytest", "-q"])
    run([sys.executable, "tools/render_smoke.py"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
