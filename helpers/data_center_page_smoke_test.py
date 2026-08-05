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
        self.radio_options[str(key or label)] = values
        return values[0]

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
from rendering.charts_data_center import data_center_stage_profile  # noqa: E402
from rendering.data_center import (  # noqa: E402
    _active_footprint,
    _campus_capacity,
    _render_development_profile,
    _render_geography,
    _render_project_structure,
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
    if len(active) != 42:
        raise AssertionError(f"Unexpected canonical active-campus count: {len(active)}")
    if not 0.80 < capacity.notna().mean() < 0.90:
        raise AssertionError("Canonical capacity coverage is outside the retained range.")

    FAKE_ST.charts.clear()
    FAKE_ST.radio_options.clear()
    _render_pulse(inventory)
    _render_development_profile(inventory)
    _render_geography(inventory)
    _render_project_structure(campuses)

    visible = [item for item in FAKE_ST.charts if not item["hidden"]]
    hidden = [item for item in FAKE_ST.charts if item["hidden"]]
    if len(visible) != 3:
        raise AssertionError(f"Expected three default-visible charts, found {len(visible)}: {visible}")
    if hidden:
        raise AssertionError(f"Project detail should use tables, not hidden charts: {hidden}")
    if any(item["traces"] == 0 for item in visible):
        raise AssertionError(f"A default-visible Data Center chart is empty: {visible}")

    if FAKE_ST.radio_options.get("data-center-view-geography") != [
        "Leading state pipelines", "National map", "Regional balance"
    ]:
        raise AssertionError("Data Center geography selector changed unexpectedly.")
    if FAKE_ST.radio_options.get("data-center-view-project-structure") != [
        "Capacity bands", "Largest campuses", "Active operators"
    ]:
        raise AssertionError("Data Center project selector changed unexpectedly.")

    profile = data_center_stage_profile(inventory.get("national_stage"), height=455)
    if len(profile.data) != 2:
        raise AssertionError("Stage profile must retain paired site and published-capacity views.")
    if profile.layout.xaxis.title.text != "Sites" or "Published capacity" not in profile.layout.xaxis2.title.text:
        raise AssertionError("Stage profile axes no longer distinguish counts from capacity.")

    print(
        "PASS  Data Center calm-hierarchy smoke test · "
        f"{len(visible)} visible charts · {len(active)} canonical active campuses · "
        f"{tracker.get('active_pipeline')} stage-tracked pipeline sites"
    )


if __name__ == "__main__":
    main()
