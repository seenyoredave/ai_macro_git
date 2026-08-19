"""End-to-end retained-data and rendering regression for Connectivity v6.6.2."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
import sys
import types

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _Block(AbstractContextManager):
    def __init__(self, fake):
        self.fake = fake

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
        self.charts: list[dict] = []
        self.radios: dict[str, list[str]] = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def markdown(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def container(self, *args, **kwargs):
        return _Block(self)

    def expander(self, *args, **kwargs):
        return _Block(self)

    def popover(self, *args, **kwargs):
        return _Block(self)

    def columns(self, spec, *args, **kwargs):
        count = int(spec) if isinstance(spec, int) else len(spec)
        return [_Block(self) for _ in range(count)]

    def selectbox(self, label, options, **kwargs):
        return list(options)[0]

    def radio(self, label, options, *, key=None, **kwargs):
        values = list(options)
        self.radios[str(key or label)] = values
        return values[0]

    def plotly_chart(self, figure, *, key=None, **kwargs):
        self.charts.append({"key": key, "traces": len(getattr(figure, "data", ()))})
        return None


FAKE_ST = _FakeStreamlit()
sys.modules["streamlit"] = FAKE_ST

from analytics.dashboard_context import DashboardContext  # noqa: E402
from analytics.domain_state import with_domain_state  # noqa: E402
from analytics.read_evidence import build_connectivity_evidence  # noqa: E402
from loaders import connectivity_loader  # noqa: E402
from loaders.infrastructure_loader import load_infrastructure_data  # noqa: E402
from rendering.common import TAB_METRIC_REGISTRIES  # noqa: E402
from rendering.connectivity import render_connectivity_tab  # noqa: E402


def _campuses() -> pd.DataFrame:
    payload = load_infrastructure_data()
    campuses = payload.get("data_center_registry")
    if not isinstance(campuses, pd.DataFrame):
        raise AssertionError("Universal Data Center Registry is unavailable")
    if not campuses.empty and campuses["Campus ID"].astype(str).duplicated().any():
        raise AssertionError("Universal Data Center Registry contains duplicate Campus IDs")
    return campuses.copy()

def _assert_retained_contract(data: dict) -> None:
    expected = {
        "cable_catalog_entries": 115,
        "selected_landing_markets": 34,
        "ixp_rows": 168,
        "interconnection_markets": 96,
        "middle_mile_awards": 39,
    }
    coverage = data.get("coverage", {}) or {}
    for key, value in expected.items():
        if int(coverage.get(key, -1)) != value:
            raise AssertionError(f"Connectivity retained count drifted for {key}: {coverage.get(key)}")
    if int(coverage.get("facility_search_floor", 0)) < 250:
        raise AssertionError("PeeringDB retained public-search floor is missing.")
    national = data.get("national_summary", {}) or {}
    if int(national.get("U.S. International Submarine Cable Systems", 0)) != 90:
        raise AssertionError("FCC licensed-system context changed unexpectedly.")
    if int(national.get("Middle-Mile New Fiber Miles", 0)) != 12500:
        raise AssertionError("NTIA middle-mile program total changed unexpectedly.")
    if len(data.get("source_manifest", pd.DataFrame())) != 8:
        raise AssertionError("Connectivity source manifest no longer covers all retained layers.")


def _assert_mismatch_contract(data: dict) -> None:
    state = data.get("state_summary", pd.DataFrame())
    louisiana = state.loc[state.get("State", pd.Series(dtype=str)).astype(str).eq("LA")]
    if len(louisiana) != 1:
        raise AssertionError("Louisiana is absent from the state connectivity screen.")
    row = louisiana.iloc[0]
    if float(row.get("Published Development MW", 0)) < 5000:
        raise AssertionError("Louisiana published buildout was lost from Connectivity.")
    if float(row.get("Reported Memberships", -1)) != 0:
        raise AssertionError("Louisiana no longer retains the zero-membership public-evidence screen.")
    if str(row.get("Capacity-Connectivity Flag")) != "High-capacity mismatch":
        raise AssertionError("Louisiana mismatch flag changed unexpectedly.")


def _assert_fallback_contract(campuses: pd.DataFrame) -> None:
    originals = {
        "_parse_pulse_pages": connectivity_loader._parse_pulse_pages,
        "_parse_telegeography_catalog": connectivity_loader._parse_telegeography_catalog,
        "_fetch_peeringdb_facilities": connectivity_loader._fetch_peeringdb_facilities,
        "_refresh_ntia_summary": connectivity_loader._refresh_ntia_summary,
    }
    try:
        def fail(*args, **kwargs):
            raise RuntimeError("offline fixture")
        for name in originals:
            setattr(connectivity_loader, name, fail)
        fallback = connectivity_loader.load_connectivity_data(campuses, force_refresh=True, refresh_token=999, allow_live=True)
    finally:
        for name, value in originals.items():
            setattr(connectivity_loader, name, value)
    if fallback.get("source_mode") != "retained_fallback":
        raise AssertionError(f"Offline refresh was not honestly labeled: {fallback.get('source_mode')}")
    if int((fallback.get("load_report", {}) or {}).get("fallback_layers", 0)) != 4:
        raise AssertionError("Offline refresh did not report all four retained/fallback layers.")
    _assert_retained_contract(fallback)


def main() -> None:
    campuses = _campuses()
    data = connectivity_loader.load_connectivity_data(campuses)
    _assert_retained_contract(data)
    _assert_mismatch_contract(data)
    _assert_fallback_contract(campuses)

    evidence_context = with_domain_state(
        DashboardContext(
            connectivity_data=data,
            infrastructure_data={"data_center_registry": campuses, "connectivity": data},
        ),
        "connectivity",
    )
    packet = build_connectivity_evidence(evidence_context).to_dict()
    if not packet.get("references"):
        raise AssertionError("Connectivity evidence packet lost its source references.")
    fact_ids = {str(item.get("id") or "").split(".", 1)[-1] for item in packet.get("facts", [])}
    required_facts = {
        "active_ixps",
        "international_submarine_cable_systems",
        "us_connected_cable_catalog_entries",
        "middle_mile_new_fiber_miles",
        "high_capacity_low_public_connectivity_states",
    }
    if not required_facts.issubset(fact_ids):
        raise AssertionError(f"Connectivity evidence lost core transport facts: {sorted(required_facts - fact_ids)}")
    read = {
        "headline": "Connectivity evidence is available for validation.",
        "summary": "The renderer receives commentary separately from deterministic transport evidence.",
        "references": packet.get("references", []),
    }

    FAKE_ST.charts.clear()
    render_connectivity_tab(data, {"connectivity": data}, tab_read=read)
    expected_keys = {
        "connectivity-gateway-map",
        "connectivity-interconnection-markets",
        "connectivity-middle-mile-awards",
        "connectivity-state-mismatch",
    }
    rendered = {item["key"] for item in FAKE_ST.charts}
    if expected_keys != rendered:
        raise AssertionError(f"Connectivity default chart set changed: {sorted(rendered)}")
    if any(item["traces"] == 0 for item in FAKE_ST.charts):
        raise AssertionError(f"A default Connectivity chart is empty: {FAKE_ST.charts}")
    if FAKE_ST.radios.get("connectivity-view-submarine") != ["Submarine cable gateways", "Cable pipeline", "Landing regions"]:
        raise AssertionError("Submarine gateway tool selector is missing or reordered.")
    if FAKE_ST.radios.get("connectivity-compute-transport-view") != ["State comparison", "Campus proximity"]:
        raise AssertionError("Compute-versus-transport selector is missing or reordered.")
    source = (PROJECT_ROOT / "rendering" / "connectivity.py").read_text(encoding="utf-8")
    if "render_compact_chart_rail(" in source or "render_metric_stack(" in source:
        raise AssertionError("Connectivity retained the old chart-plus-vertical-rail factory default.")
    if source.count("st.expander(") != 1 or "Connectivity data" not in source:
        raise AssertionError("Connectivity registers are not consolidated into one bottom ledger.")
    if "connectivity" not in TAB_METRIC_REGISTRIES or len(TAB_METRIC_REGISTRIES["connectivity"]) < 6:
        raise AssertionError("Connectivity Terms registry is incomplete.")

    print(
        "PASS  Connectivity domain · "
        f"{len(data['submarine_cable_systems'])} cables · "
        f"{len(data['cable_landing_markets'])} landing markets · "
        f"{len(data['ixp_snapshot'])} IXPs · "
        f"{len(data['middle_mile_awards'])} middle-mile awards · "
        f"{len(FAKE_ST.charts)} default analytical charts"
    )


if __name__ == "__main__":
    main()
