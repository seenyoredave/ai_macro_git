"""Regression smoke test for domain evidence routing and reference centralization."""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from helpers.streamlit_runtime_stub import install_streamlit_stub  # noqa: E402

install_streamlit_stub()

import streamlit as st  # noqa: E402
from rendering.evidence_gateway import EVIDENCE_LOOKUP, route_to_evidence  # noqa: E402
from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.domain_state import DomainState  # noqa: E402
from analytics import read_service  # noqa: E402
from rendering.observation_meta import latest_observation, source_through  # noqa: E402
from rendering.snapshot_status import market_snapshot_label  # noqa: E402
import pandas as pd  # noqa: E402


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
    _check(st.session_state.get("evidence-layer") == "Reference records", "Gateway did not open reference records")
    route_to_evidence("finance", "Credit spread changes")
    _check(st.session_state.get("evidence-finance-reference-view") == "Credit spread changes", "Gateway did not select the linked Finance dataset")
    partial = DashboardContext(domain_states={"finance": DomainState(metrics={}, importance=0)})
    with patch.object(read_service, "build_evidence_packets", side_effect=AssertionError("Partial canonical state reached packet builder")):
        reads, status = read_service.build_platform_reads(partial)
    _check(set(reads) == EXPECTED_DOMAINS | {"macro"}, "Partial canonical state lost retained Reads")
    _check(status["canonical_state_status"] == "incomplete", "Partial canonical state diagnostic missing")
    _check(source_through("FRED", "2026-07-01") == "FRED · through 2026-07-01", "Public observation label drifted")
    _check(source_through("New York Fed", None) == "New York Fed", "Missing dates must not be invented")
    _check(source_through("YFinance", None, "2026-10-17") == "YFinance · through 2026-10-17", "Retrieval fallback was lost")
    sample = pd.DataFrame({"Date": ["2026-07-01", "2026-10-07"], "Retrieved At": ["2026-10-17"] * 2})
    _check(source_through("FRED", latest_observation(sample)) == "FRED · through 2026-10-07", "Retrieval time displaced observation date")
    market = pd.DataFrame({"Market Data Date": ["2026-08-07", "2026-08-05", "2026-08-07"]})
    _check(market_snapshot_label(market) == "YFinance · through 2026-08-07 · 1 retained from 2026-08-05", "Market freshness label drifted")

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
    _check('key="evidence-layer", on_change="rerun"' in evidence_source, "Evidence layer cannot be selected by linked routes")
    _check('"Finance reference dataset", FINANCE_REFERENCE_DATASETS' in evidence_source, "Finance records are not in a compact selector")
    finance_source = (ROOT / "rendering" / "finance.py").read_text(encoding="utf-8")
    _check('live_sources="FRED + SEC"' in finance_source, "Lender public source label changed")
    _check("ObservationMeta" not in finance_source, "Verbose observation metadata returned to Finance")
    _check('domain_filter=selected' in evidence_source, "Change inspection is not pinned to the selected Evidence domain")
    _check('"Record group"' not in evidence_source[evidence_source.index("def render_evidence_tab("):], "Legacy grouped Evidence selector still renders")

    dashboard_source = (ROOT / "rendering" / "dashboard.py").read_text(encoding="utf-8")
    _check("commercialization_data=context.commercialization_data" in dashboard_source, "Evidence is missing commercialization reference data")

    app_source = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    _check('APP_VERSION = "v3.0.6.' in app_source, "Evidence architecture must remain in the v3.0.6 line")

    print({"status": "PASS", "domains": len(EXPECTED_DOMAINS), "route": "finance -> credit spread records"})


if __name__ == "__main__":
    main()
