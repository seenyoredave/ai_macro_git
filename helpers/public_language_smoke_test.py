"""Guard against reintroducing retired chatbot-style public copy."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_COPY_FILES = [
    ROOT / "analytics" / "read_service.py",
    ROOT / "config" / "metric_definitions.py",
    ROOT / "rendering" / "adoption.py",
    ROOT / "rendering" / "compute.py",
    ROOT / "rendering" / "connectivity.py",
    ROOT / "rendering" / "data_center.py",
    ROOT / "rendering" / "economic_impact.py",
    ROOT / "rendering" / "evidence.py",
    ROOT / "rendering" / "finance.py",
    ROOT / "rendering" / "grid_storage.py",
    ROOT / "rendering" / "layout_contracts.py",
    ROOT / "rendering" / "macro.py",
    ROOT / "rendering" / "market.py",
    ROOT / "rendering" / "power.py",
    ROOT / "rendering" / "water.py",
    ROOT / "rendering" / "workforce.py",
]

RETIRED_PHRASES = (
    "Commentary temporarily unavailable.",
    "The analyst has wandered off. The data have not.",
    "No published commentary is available.",
    "Read unavailable",
    "in sequence",
    "before direct BDC panel",
    "retained analytical evidence above",
    "ordered by current county D2+ exposure",
    "How market pricing and funding move through physical delivery and adoption toward measurable economic outcomes.",
    "Current top-level indicators and their recent history.",
    "One campus universe shared by Data Centers, Water, Power, Grid & Storage, and Connectivity.",
    "From AI revenue to economic results",
    "From AI revenue to broader economic gains",
    "Trace the research from published interpretation back to the facts, sources, and boundaries that support it.",
    "Start with the conclusion, then inspect the cited analytical evidence and its source foundation.",
    "Abnormal trading pressure relative to sustained, broad-based equity strength",
    "Trailing repricing relative to the profitable operating-earnings base",
    "Current network footprint",
    "Current labor-market conditions",
)


def main() -> None:
    failures: list[str] = []
    for path in PUBLIC_COPY_FILES:
        text = path.read_text(encoding="utf-8")
        for phrase in RETIRED_PHRASES:
            if phrase in text:
                failures.append(f"{path.relative_to(ROOT)}: {phrase}")
    if failures:
        raise AssertionError("Retired public copy found:\n" + "\n".join(failures))
    print(f"PASS public language guard · {len(PUBLIC_COPY_FILES)} files · {len(RETIRED_PHRASES)} retired phrases absent")


if __name__ == "__main__":
    main()
