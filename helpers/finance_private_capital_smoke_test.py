"""Regression checks for the Finance capital-lifecycle redesign."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from analytics.private_capital import build_private_capital_realization
from rendering.charts_common import COLORS
from rendering.charts_finance import private_capital_ledger_chart, private_capital_realization_map


def main() -> None:
    realization = build_private_capital_realization()
    funds = realization.get("funds")
    mature = realization.get("mature_funds")
    metrics = realization.get("metrics", {})
    if funds is None or len(funds) != 51:
        raise AssertionError(f"Expected 51 retained fund records, received {0 if funds is None else len(funds)}.")
    if mature is None or len(mature) != 31:
        raise AssertionError(f"Expected 31 mature fund records, received {0 if mature is None else len(mature)}.")
    if not np.allclose(funds["TVPI"], funds["DPI"] + funds["RVPI"], atol=1e-12, equal_nan=True):
        raise AssertionError("Fund-level TVPI identity failed.")
    if not np.isclose(metrics["tvpi"], metrics["dpi"] + metrics["rvpi"], atol=1e-12):
        raise AssertionError("Pooled TVPI identity failed.")
    if not np.isclose(metrics["dpi"], 1.1842385657863554, atol=1e-12):
        raise AssertionError("Unexpected mature-cohort DPI.")
    if not np.isclose(metrics["rvpi"], 0.974091081680859, atol=1e-12):
        raise AssertionError("Unexpected mature-cohort RVPI.")
    source_pdf = PROJECT_ROOT / "data" / "private_capital" / "calstrs_private_equity_performance_2025-06-30.pdf"
    if not source_pdf.exists() or source_pdf.stat().st_size < 100_000:
        raise AssertionError("Retained CalSTRS source PDF is missing or incomplete.")

    ledger = private_capital_ledger_chart(metrics)
    if len(ledger.data) != 2:
        raise AssertionError("Realization ledger must contain distributed and residual traces.")
    if [trace.marker.color for trace in ledger.data] != [COLORS["violet"], COLORS["blue"]]:
        raise AssertionError("Realization ledger left the cool Finance palette.")
    if ledger.layout.barmode != "stack":
        raise AssertionError("Realization ledger is not stacked.")

    realization_map = private_capital_realization_map(funds)
    names = [trace.name for trace in realization_map.data]
    if names != ["Mature (5y+)", "Developing (3-4y)", "Young (0-2y)"]:
        raise AssertionError(f"Unexpected maturity traces: {names}")
    allowed = {COLORS["violet"], COLORS["blue"], COLORS["slate"]}
    if {trace.marker.color for trace in realization_map.data} != allowed:
        raise AssertionError("Fund map left the cool Finance palette.")

    finance_source = (PROJECT_ROOT / "rendering" / "finance.py").read_text()
    section_positions = [
        finance_source.index('"Capital Funding"'),
        finance_source.index('"Private Capital Realization"'),
        finance_source.index('"Credit Markets"'),
        finance_source.index('"Financial Stress"'),
    ]
    if section_positions != sorted(section_positions):
        raise AssertionError("Finance capital-lifecycle sections are out of order.")
    if 'expanded=False' not in finance_source or 'View fund, vintage, and methodology detail' not in finance_source:
        raise AssertionError("Private-capital detail is not collapsed by default.")

    print(
        "PASS  Finance private-capital realization · "
        f"{len(funds)} funds · {len(mature)} mature · "
        f"DPI {metrics['dpi']:.2f}x · TVPI {metrics['tvpi']:.2f}x"
    )


if __name__ == "__main__":
    main()
