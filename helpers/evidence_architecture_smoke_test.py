"""Regression smoke test for domain evidence routing and reference centralization."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.streamlit_runtime_stub import install_streamlit_stub  # noqa: E402

install_streamlit_stub()

import streamlit as st  # noqa: E402
from rendering.evidence_gateway import EVIDENCE_LOOKUP, route_to_evidence  # noqa: E402


EXPECTED_DOMAINS = {
    "market",
    "finance",
    "compute",
    "data_center",
    "connectivity",
    "power",
    "grid_storage",
    "water",
    "adoption",
    "workforce",
    "economic_impact",
}

DOMAIN_FILES = {
    "market": "market.py",
    "finance": "finance.py",
    "compute": "compute.py",
    "data_center": "data_center.py",
    "connectivity": "connectivity.py",
    "power": "power.py",
    "grid_storage": "grid_storage.py",
    "water": "water.py",
    "adoption": "adoption.py",
    "workforce": "workforce.py",
    "economic_impact": "economic_impact.py",
}

LOCAL_LEDGER_CALLS = {
    "market": "_render_market_constituent_ledger(",
    "finance": "_render_finance_ledger(",
    "compute": "_render_compute_ledger(",
    "data_center": "_render_data_center_ledger(",
    "connectivity": "_render_connectivity_ledger(",
    "power": "_render_power_ledger(",
    "adoption": "_render_adoption_ledger(",
    "workforce": "_render_workforce_ledger(",
    "economic_impact": "_render_economic_ledger(",
}


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _render_function_tail(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.index(marker)
    return source[start:]


def main() -> None:
    _check(set(EVIDENCE_LOOKUP) == EXPECTED_DOMAINS, "Evidence domain registry changed")

    st.session_state.clear()
    route_to_evidence("water")
    _check(st.session_state.get("domain-navigation") == "EVIDENCE", "Gateway did not select Evidence tab")
    _check(st.session_state.get("evidence-lookup-domain") == "water", "Gateway did not preserve domain selection")

    for domain, filename in DOMAIN_FILES.items():
        source = (ROOT / "rendering" / filename).read_text(encoding="utf-8")
        _check(
            f'render_evidence_gateway("{domain}")' in source,
            f"{domain} does not render the shared Evidence gateway",
        )

    render_functions = {
        "market": "render_market_tab",
        "finance": "render_finance_tab",
        "compute": "render_compute_tab",
        "data_center": "render_data_center_tab",
        "connectivity": "render_connectivity_tab",
        "power": "render_power_tab",
        "adoption": "render_adoption_tab",
        "workforce": "render_workforce_tab",
        "economic_impact": "render_economic_impact_tab",
    }
    for domain, call in LOCAL_LEDGER_CALLS.items():
        source = (ROOT / "rendering" / DOMAIN_FILES[domain]).read_text(encoding="utf-8")
        tail = _render_function_tail(source, render_functions[domain])
        _check(call not in tail, f"{domain} still renders its local reference ledger")

    grid_source = (ROOT / "rendering" / "grid_storage.py").read_text(encoding="utf-8")
    water_source = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    _check('with st.expander("Grid and storage data"' not in _render_function_tail(grid_source, "render_grid_storage_tab"), "Grid local ledger still renders")
    _check('with st.expander("Water data"' not in _render_function_tail(water_source, "render_water_tab"), "Water local ledger still renders")

    evidence_source = (ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    _check("_render_domain_reference_records(" in evidence_source, "Domain reference routing is missing")
    _check("_render_domain_technical_records(" in evidence_source, "Domain technical routing is missing")
    _check("_evidence_domain_selector()" in evidence_source, "Evidence domain selector is not shared across the inspector")
    _check('st.tabs(' in evidence_source[evidence_source.index("def render_evidence_tab("):], "Evidence inspector tabs are missing")
    _check('domain_filter=selected' in evidence_source, "Change inspection is not pinned to the selected Evidence domain")
    _check('"Record group"' not in evidence_source[evidence_source.index("def render_evidence_tab("):], "Legacy grouped Evidence selector still renders")

    dashboard_source = (ROOT / "rendering" / "dashboard.py").read_text(encoding="utf-8")
    _check("commercialization_data=context.commercialization_data" in dashboard_source, "Evidence is missing commercialization reference data")

    app_source = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    _check('APP_VERSION = "v3.0.5.' in app_source, "Pass 1 architecture must remain in the v3.0.5 patch line")

    print({"status": "PASS", "domains": len(EXPECTED_DOMAINS), "route": "water -> EVIDENCE"})


if __name__ == "__main__":
    main()
