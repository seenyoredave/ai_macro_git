"""Protect the deterministic AI Macro transmission board and its UI precedence."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analytics.dashboard_context import DashboardContext
from analytics.transmission import build_macro_transmission
from rendering.layout_contracts import transmission_board_html


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def _context(*, speculation=-40.0, power=20.0, validation=30.0, internal=1.2):
    return DashboardContext(
        regime_metrics={
            "AI Equity Index": 40.0,
            "AI Development Intensity": 80.0,
            "Speculation Gap": speculation,
            "Power Capacity Gap": power,
            "Economic Validation Gap": validation,
            "Deployment Funding Mix": {
                "current": {
                    "internal_funding_coverage": internal,
                    "cash_reserve_coverage_years": 0.8,
                    "forward_commitment_load": 4.0,
                }
            },
        },
        adoption_data={"current_use": 20.0, "expected_use": 25.0},
        economic_impact_data={
            "nonfarm_productivity": {"value": 2.0},
            "nonfarm_output": {"value": 3.0},
        },
        infrastructure_data={
            "data_center_inventory": {
                "open_tracker_summary": {
                    "active_pipeline": 100,
                    "active_pipeline_published_mw": 10000.0,
                }
            }
        },
    )


def main() -> None:
    source = (ROOT / "analytics" / "transmission.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = [name for name in imports if name.startswith(("analytics.read_", "language", "openai"))]
    _check(not forbidden, f"Deterministic transmission state depends on language/OpenAI code: {forbidden}")

    state = build_macro_transmission(_context())
    _check(len(state.stages) == 6, "Transmission board no longer has six causal stages")
    _check(state.stages[0].value == "Buildout leads pricing", "Speculation Gap sign semantics changed")
    _check(state.stages[1].value == "Covered now; duration exposed", "Funding-duration relationship changed")
    _check(state.stages[3].value == "Power response trails deployment", "Power Capacity Gap sign semantics changed")
    _check(state.stages[5].value == "Deployment leads validation", "Economic Validation Gap sign semantics changed")
    _check(
        state.breakpoints == ("Buildout → Deliverability", "Deployment → Economic validation"),
        f"Measured breakpoint set changed: {state.breakpoints}",
    )
    _check(
        state.measurement_gaps == ("Adoption depth → Economic outcomes",),
        "Adoption-depth measurement gap disappeared",
    )

    reverse = build_macro_transmission(_context(speculation=12.0, power=-8.0, validation=-6.0, internal=0.8))
    _check(reverse.stages[0].value == "Pricing leads buildout", "Positive Speculation Gap semantics changed")
    _check(reverse.stages[1].value == "Current CapEx needs external funding", "Funding coverage threshold changed")
    _check(reverse.stages[3].value == "Power response leads deployment", "Negative Power Capacity Gap semantics changed")
    _check(reverse.stages[5].value == "Validation keeps pace with deployment", "Negative Economic Validation Gap semantics changed")
    _check(reverse.breakpoints == ("Funding → Buildout",), f"Reverse-case breakpoints changed: {reverse.breakpoints}")

    html = transmission_board_html(
        headline=state.headline,
        breakpoints=state.breakpoints,
        measurement_gaps=state.measurement_gaps,
        stages=[(stage.label, stage.value, stage.note) for stage in state.stages],
        namespace="macro-test",
    )
    _check(html.count('class="rm-transmission-stage"') == 6, "Transmission HTML does not render six stages")
    _check("Measured breakpoints" in html and "Measurement gap" in html, "Transmission board lost evidence-state metadata")

    macro_source = (ROOT / "rendering" / "macro.py").read_text(encoding="utf-8")
    transmission_position = macro_source.index('render_section(\n        "Economic transmission"')
    read_position = macro_source.index('render_domain_read(tab_read')
    regime_position = macro_source.index('render_section("Regime board"')
    _check(transmission_position < read_position < regime_position, "Macro flagship hierarchy is not deterministic answer → Read → detail")

    print("PASS  AI Macro transmission · six-stage deterministic chain · sign semantics · breakpoints · deterministic answer precedes Read")


if __name__ == "__main__":
    main()
