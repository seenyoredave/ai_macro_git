"""Headless automation orchestration must rebuild from retained state without writes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["AI_MACRO_MODE"] = "automation"

# Provider packages are runtime requirements, but this contract exercises only
# retained mode. Lightweight import shims keep the test usable in source-audit
# environments where optional network clients are intentionally absent.
try:
    import yfinance  # noqa: F401
except ModuleNotFoundError:
    sys.modules["yfinance"] = types.ModuleType("yfinance")
try:
    import fredapi  # noqa: F401
except ModuleNotFoundError:
    module = types.ModuleType("fredapi")
    module.Fred = type("Fred", (), {})
    sys.modules["fredapi"] = module

from helpers.streamlit_runtime_stub import install_streamlit_stub
install_streamlit_stub()

from analytics.read_evidence import build_evidence_packets
from automation.research_refresh import refresh_research_state


def _tree_hash() -> str:
    digest = hashlib.sha256()
    for base in (ROOT / "data", ROOT / "archive"):
        for path in sorted(item for item in base.rglob("*") if item.is_file()):
            digest.update(str(path.relative_to(ROOT)).encode("utf-8"))
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main() -> None:
    before = _tree_hash()
    bundle = refresh_research_state(as_of="2026-08-10", live=False)
    after = _tree_hash()
    if before != after:
        raise AssertionError("Retained headless automation build mutated retained research files.")
    if bundle.snapshot_write_report.get("reason") != "retained_read_mode":
        raise AssertionError(f"Retained automation build did not stay in read mode: {bundle.snapshot_write_report}")
    if (bundle.reports.get("current_context") or {}).get("source_mode") != "retained":
        raise AssertionError("Headless retained build did not use retained Current Context.")
    packets = build_evidence_packets(bundle.context)
    if len(packets) != 11:
        raise AssertionError(f"Headless automation build did not produce 11 evidence domains: {len(packets)}")
    print("PASS  headless retained automation build · 11 evidence domains · zero retained-file changes")


if __name__ == "__main__":
    main()
