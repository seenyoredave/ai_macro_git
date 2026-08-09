"""Focused regression for the v6.6.2 first-class Connectivity domain."""

from __future__ import annotations

from pathlib import Path
import re
import sys
import types

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function


sys.modules.setdefault("streamlit", _FakeStreamlit())

from analytics.read_architecture import DOMAIN_ORDER, DOMAIN_REFERENCES, build_macro_read  # noqa: E402
from config.metric_definitions import METRIC_DEFINITIONS  # noqa: E402
from loaders import commercialization_loader  # noqa: E402
from loaders.connectivity_loader import (  # noqa: E402
    CONNECTIVITY_PHASE,
    REQUIRED_NATIONAL_FIELDS,
    _campus_connectivity_snapshot,
    _merge_national_refresh,
)
from rendering.charts_infrastructure import _select_connectivity_states  # noqa: E402


def _check(condition, message):
    if not condition:
        raise AssertionError(message)


def check_purpose_beacon() -> None:
    statement = " ".join(METRIC_DEFINITIONS["Purpose Statement"].split())
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    _check(readme.startswith("# AI Macro\n"), "README no longer opens with the project name.")
    _check("Streamlit research platform" in readme, "README no longer identifies the project as a Streamlit research platform.")
    _check("U.S. AI economy" in readme, "README no longer states the project's economic scope.")
    _check("Reader mode" in readme and "Developer mode" in readme, "README no longer states the actual Reader/Developer access model.")
    _check(len(readme.splitlines()) <= 40, "README has grown beyond the brief repository-overview contract.")
    _check("## v" not in readme and "review build" not in readme.casefold(), "README has drifted back into release-note copy.")
    for forbidden in ("contributors", "contributing", "pull request", "pip install", "streamlit run"):
        _check(forbidden not in readme.casefold(), f"README has drifted into contributor/setup language: {forbidden}")
    for phrase in ("what is being built", "who is using and paying for it", "productivity, wages, household income", "costs and constraints"):
        _check(phrase in statement, f"Purpose beacon lost the phrase: {phrase}")


def check_connectivity_selection() -> None:
    state_codes = [chr(65 + (i // 26)) + chr(65 + (i % 26)) for i in range(20)]
    rows = [
        {"State": code, "Reported Memberships": 1000 - i * 20, "Published Development MW": 100 + i, "IXPs": 2, "Published Campuses": 1, "Capacity-Connectivity Flag": "No mismatch flag"}
        for i, code in enumerate(state_codes)
    ]
    rows.append({
        "State": "LA", "Reported Memberships": 0, "Published Development MW": 5000,
        "IXPs": 0, "Published Campuses": 1, "Capacity-Connectivity Flag": "High-capacity mismatch",
    })
    selected = _select_connectivity_states(pd.DataFrame(rows), lens="Mismatch screen", limit=16)
    _check("LA" in set(selected["State"]), "Mismatch screen hid Louisiana's high-capacity/zero-membership case.")
    depth = _select_connectivity_states(pd.DataFrame(rows), lens="Connectivity depth", limit=16)
    _check("LA" not in set(depth["State"]), "Connectivity-depth lens is no longer a pure depth ranking.")


def check_connectivity_refresh_contract() -> None:
    retained = pd.DataFrame([{field: index + 1 for index, field in enumerate(REQUIRED_NATIONAL_FIELDS)}])
    refreshed = retained.copy()
    refreshed.loc[0, "Internet Resilience Score"] = np.nan
    merged, report = _merge_national_refresh(refreshed, retained)
    _check(report["complete"] is False, "Retained national fallback was mislabeled complete.")
    _check("Internet Resilience Score" in report["retained_fields"], "Missing national parser field was not reported as retained fallback.")
    _check(float(merged.iloc[0]["Internet Resilience Score"]) == float(retained.iloc[0]["Internet Resilience Score"]), "Retained fallback value was not preserved.")


def check_campus_screen_boundary() -> None:
    campuses = pd.DataFrame([{
        "Facility": "Louisiana AI Campus", "Operator": "Example", "City": "Richland Parish", "State": "LA",
        "Status": "Proposed", "Published Capacity Estimate MW": 5000.0,
    }])
    states = pd.DataFrame([{
        "State": "LA", "Reported Memberships": 0, "IXPs": 0, "Selected Gateway Markets": 0,
        "Connectivity Presence": "Limited public evidence", "Capacity-Connectivity Flag": "High-capacity mismatch",
    }])
    landings = pd.DataFrame([{
        "Landing Market": "Jacksonville", "State / Territory": "FL",
        "Latitude": 30.3322, "Longitude": -81.6557,
    }])
    screen = _campus_connectivity_snapshot(campuses, states, landings)
    _check(len(screen) == 1, "Campus connectivity screen dropped a capacity-bearing project.")
    _check("no direct campus route" in str(screen.iloc[0]["Screening Boundary"]).casefold(), "Campus screen lost its no-direct-route boundary.")
    _check(CONNECTIVITY_PHASE == "Full public-evidence transport layer", "Connectivity domain scope is not explicit.")


def check_commercialization_parser_contract() -> None:
    manifest = pd.DataFrame([{
        "Provider": "OpenAI", "Source URL": "https://example.test/openai", "Parser Key": "openai_scale", "Status": "active",
    }])
    original = commercialization_loader._text
    try:
        commercialization_loader._text = lambda url: "more than 900 million weekly active users"
        values, errors, reports = commercialization_loader._refresh_values(manifest)
        _check(len(values) == 1, "Partial parser fixture did not retain its one valid metric.")
        _check("openai_scale" in errors, "Partial parser coverage was mislabeled complete.")
        _check(reports["openai_scale"]["status"] == "partial", "Parser report did not identify partial coverage.")

        commercialization_loader._text = lambda url: (
            "more than 900 million weekly active users, more than 50 million consumer subscribers, "
            "and more than 9 million paying business users"
        )
        values, errors, reports = commercialization_loader._refresh_values(manifest)
        _check(len(values) == 3 and not errors, "Complete parser fixture did not satisfy the expected-metric contract.")
        _check(reports["openai_scale"]["status"] == "complete", "Complete parser fixture was not labeled complete.")
    finally:
        commercialization_loader._text = original


def check_macro_reference_alignment() -> None:
    reads = {
        domain: {
            "headline": f"{domain} headline",
            "summary": f"{domain} summary",
            "importance": 20,
            "confidence": "high",
            "signals": {},
            "highlights": [{"score": 20, "kind": domain, "text": f"{domain} highlight"}],
            "references": [dict(item) for item in DOMAIN_REFERENCES.get(domain, ())],
        }
        for domain in DOMAIN_ORDER
    }
    reads["compute"]["signals"].update({"critical_layers_covered": 4, "critical_layers_total": 4})
    reads["data_center"]["signals"].update({"tracked_pipeline_capacity_gw": 287.2})
    reads["connectivity"]["signals"].update({
        "active_ixps": 168,
        "international_submarine_cable_systems": 90,
        "cable_catalog_entries": 115,
        "middle_mile_fiber_miles": 12500,
        "high_capacity_low_public_connectivity_states": 1,
    })
    reads["grid_storage"]["signals"].update({"advanced_share": 25})
    reads["adaptation"]["signals"].update({"consumer_active": 50, "current_use": 12, "implied_subscriber_share_pct": 5.6})
    reads["economic_impact"]["signals"].update({
        "microsoft_ai_arr_b": 37, "openai_arr_b": 20,
        "productivity_growth": 2.0, "real_compensation_growth": 1.0,
        "productivity_real_comp_gap": 7.0, "labor_share_since_2020": -4.0,
        "median_real_earnings_growth": 0.5,
    })
    macro = build_macro_read(reads)
    labels = {str(item.get("source_label") or item.get("source_name") or "") for item in macro.get("references", [])}
    required = {"FracTracker Alliance", "Real-Time Population Survey via FRED", "BLS Labor Productivity and Costs"}
    _check(required.issubset(labels), f"Macro references do not follow the three evidence anchors: {sorted(labels)}")


def check_refresh_ownership() -> None:
    app = (PROJECT_ROOT / "ai_macro.py").read_text(encoding="utf-8")
    infrastructure = (PROJECT_ROOT / "loaders" / "infrastructure_loader.py").read_text(encoding="utf-8")
    _check(
        "or st.session_state.force_edgar_refresh" not in app,
        "EDGAR refresh still leaks into unrelated commercialization web fetches.",
    )
    _check(
        'commercialization_domains = {"compute", "adoption", "economic_outcomes"}' in app
        and "commercialization_refresh = bool(refresh_domains & commercialization_domains)" in app,
        "Commercialization refresh is not owned by explicit domain controls.",
    )
    _check('"connectivity": "Connectivity"' in app, "Connectivity is missing from the domain refresh router.")
    _check("load_connectivity_data(" in app, "Connectivity does not have an independent loader call.")
    _check("(2 if facility_refresh else 0)" in infrastructure, "Data Centers refresh completeness does not retain its two-source boundary.")
    _check("load_connectivity_data" not in infrastructure, "Connectivity refresh is still owned by Data Centers.")


def main() -> None:
    checks = (
        ("Purpose beacon", check_purpose_beacon),
        ("Connectivity mismatch selection", check_connectivity_selection),
        ("Connectivity refresh validation", check_connectivity_refresh_contract),
        ("Campus screening boundary", check_campus_screen_boundary),
        ("Commercialization parser contract", check_commercialization_parser_contract),
        ("Macro reference alignment", check_macro_reference_alignment),
        ("Refresh ownership", check_refresh_ownership),
    )
    for label, function in checks:
        function()
        print(f"PASS  {label}")
    print(f"PASS  {len(checks)} stack-completion fidelity contracts")


if __name__ == "__main__":
    main()
