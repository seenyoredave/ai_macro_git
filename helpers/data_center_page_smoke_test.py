"""Targeted regression test for the simplified Data Center page hierarchy."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
import sys
import types

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


class _Block(AbstractContextManager):
    def __init__(self, fake, *, expander: bool = False):
        self.fake = fake
        self.expander = expander

    def __enter__(self):
        if self.expander:
            self.fake.expander_depth += 1
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self.expander:
            self.fake.expander_depth -= 1
        return False


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.expander_depth = 0
        self.charts: list[dict] = []
        self.radio_options: dict[str, list[str]] = {}
        self.radio_returns: dict[str, str] = {}
        self.session_state = {}

    def markdown(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def columns(self, spec, *args, **kwargs):
        count = int(spec) if isinstance(spec, int) else len(spec)
        return [_Block(self) for _ in range(count)]

    def container(self, *args, **kwargs):
        return _Block(self)

    def expander(self, *args, **kwargs):
        return _Block(self, expander=True)

    def radio(self, label, options, *, key=None, **kwargs):
        values = list(options)
        radio_key = str(key or label)
        self.radio_options[radio_key] = values
        return self.radio_returns.get(radio_key, values[0])

    def plotly_chart(self, figure, *, key=None, **kwargs):
        self.charts.append({
            "key": key,
            "hidden": self.expander_depth > 0,
            "traces": len(getattr(figure, "data", ())),
        })
        return None


FAKE_ST = _FakeStreamlit()
sys.modules["streamlit"] = FAKE_ST

from loaders.data_center_inventory_loader import load_data_center_inventory  # noqa: E402
from loaders.facility_registry_loader import (  # noqa: E402
    build_campus_registry,
    canonicalize_facility_observations,
    load_curated_facility_records,
    load_gigawatt_facility_records,
)
from rendering.charts_data_center import (  # noqa: E402
    data_center_stage_profile,
    data_center_state_published_capacity,
)
from rendering.data_center import (  # noqa: E402
    _active_footprint,
    _campus_capacity,
    _render_development_profile,
    _render_connectivity_operator_structure,
    _render_geography,
    _render_pulse,
)


def _campuses() -> pd.DataFrame:
    records = pd.concat(
        [load_curated_facility_records(), load_gigawatt_facility_records()],
        ignore_index=True,
        sort=False,
    )
    registry = canonicalize_facility_observations(records)
    return build_campus_registry(registry)


def main() -> None:
    inventory = load_data_center_inventory()
    campuses = _campuses()
    broad = inventory.get("broad_summary", {}) or {}
    tracker = inventory.get("open_tracker_summary", {}) or {}

    if int(broad.get("operating", 0)) != 3068:
        raise AssertionError("Broad operating footprint changed unexpectedly.")
    if int(broad.get("development", 0)) != 1556:
        raise AssertionError("Broad development footprint changed unexpectedly.")
    if int(tracker.get("active_pipeline", 0)) != 894:
        raise AssertionError("Stage-tracked active pipeline changed unexpectedly.")
    if not np.isclose(float(tracker.get("active_pipeline_published_mw", 0)) / 1000.0, 287.155, atol=1e-6):
        raise AssertionError("Published pipeline capacity changed unexpectedly.")

    active = _active_footprint(campuses)
    capacity = _campus_capacity(active)
    if len(active) != 41:
        raise AssertionError(f"Unexpected canonical active-campus count: {len(active)}")
    if not 0.80 < capacity.notna().mean() < 0.90:
        raise AssertionError("Canonical capacity coverage is outside the retained range.")

    connectivity_probe = {
        "state_summary": pd.DataFrame([
            {"State": "LA", "Reported Memberships": 0, "Published Development MW": 5545.0, "IXPs": 0, "Published Campuses": 1, "Capacity-Connectivity Flag": "High-capacity mismatch"},
            {"State": "VA", "Reported Memberships": 580, "Published Development MW": 11068.0, "IXPs": 8, "Published Campuses": 5, "Capacity-Connectivity Flag": "No mismatch flag"},
        ]),
        "national_summary": {"Active IXPs": 168, "U.S.-Connected Cable Catalog Entries": 115, "Middle-Mile New Fiber Miles": 12500},
        "coverage": {"mismatch_states": 1},
    }
    FAKE_ST.charts.clear()
    FAKE_ST.radio_options.clear()
    _render_pulse(inventory)
    _render_development_profile(inventory)
    _render_geography(inventory, campuses)
    _render_connectivity_operator_structure(connectivity_probe, campuses)

    visible = [item for item in FAKE_ST.charts if not item["hidden"]]
    hidden = [item for item in FAKE_ST.charts if item["hidden"]]
    if len(visible) != 4:
        raise AssertionError(f"Expected four default-visible charts, found {len(visible)}: {visible}")
    if hidden:
        raise AssertionError(f"Data Center project detail should use tables, not hidden charts: {hidden}")
    if any(item["traces"] == 0 for item in visible):
        raise AssertionError(f"A default-visible Data Center chart is empty: {visible}")
    if FAKE_ST.radio_options.get("data-center-view-pipeline-explorer") != ["Lifecycle stage", "Leading state pipelines"]:
        raise AssertionError("Data Center pipeline explorer selector changed unexpectedly.")
    if FAKE_ST.radio_options.get("data-center-view-geography") != ["National map", "Published capacity", "Regional balance"]:
        raise AssertionError("Data Center geography selector changed unexpectedly.")
    connectivity_charts = [item for item in FAKE_ST.charts if item["key"] == "data-center-connectivity-context-chart"]
    if len(connectivity_charts) != 1 or connectivity_charts[0]["traces"] != 2:
        raise AssertionError(f"Data Center connectivity structure did not render: {connectivity_charts}")

    profile = data_center_stage_profile(inventory.get("national_stage"), height=455)
    if len(profile.data) != 2:
        raise AssertionError("Stage profile must retain paired site and published-capacity views.")
    if profile.layout.xaxis.title.text != "Sites" or "Published capacity" not in profile.layout.xaxis2.title.text:
        raise AssertionError("Stage profile axes no longer distinguish counts from capacity.")

    capacity_by_state = data_center_state_published_capacity(campuses, height=500)
    if len(capacity_by_state.data) != 3:
        raise AssertionError("Published-capacity state view must retain the three active development stages.")
    if capacity_by_state.layout.xaxis.title.text != "Published capacity estimate (GW)":
        raise AssertionError("Published-capacity state view lost its explicit unit and estimate label.")
    if not any(float(np.nansum(trace.x)) > 0 for trace in capacity_by_state.data):
        raise AssertionError("Published-capacity state view is empty on retained campus data.")

    ranking_probe = pd.DataFrame(
        [
            {"State": "AA", "Status": "Proposed", "Published Capacity Estimate MW": 1000.0},
            {"State": "BB", "Status": "Under construction", "Published Capacity Estimate MW": 2000.0},
            {"State": "BB", "Status": "Expanding", "Published Capacity Estimate MW": 500.0},
            {"State": "CC", "Status": "Announced", "Published Capacity Estimate MW": 300.0},
        ]
    )
    ranked = data_center_state_published_capacity(ranking_probe, top_n=2, height=500)
    if list(ranked.data[0].y) != ["AA", "BB"]:
        raise AssertionError("Published-capacity state view is not ranked by total disclosed capacity.")

    print(
        "PASS  Data Center calm-hierarchy smoke test · "
        f"{len(visible)} visible charts · {len(active)} canonical active campuses · "
        f"{tracker.get('active_pipeline')} stage-tracked pipeline sites"
    )


if __name__ == "__main__":
    main()
