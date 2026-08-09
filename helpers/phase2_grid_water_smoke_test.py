"""Phase 2 retained-data, analytics, rendering, and editorial regression gate."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
import sys
import types

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _Block(AbstractContextManager):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class _FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.secrets = {}
        self.charts: list[str] = []
        self.radios: dict[str, list[str]] = {}

    def cache_data(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def cache_resource(self, *args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda function: function

    def markdown(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def container(self, *args, **kwargs):
        return _Block()

    def expander(self, *args, **kwargs):
        return _Block()

    def popover(self, *args, **kwargs):
        return _Block()

    def columns(self, spec, *args, **kwargs):
        count = int(spec) if isinstance(spec, int) else len(spec)
        return [_Block() for _ in range(count)]

    def radio(self, label, options, *, key=None, **kwargs):
        values = list(options)
        self.radios[str(key or label)] = values
        return values[0]

    def selectbox(self, label, options, **kwargs):
        values = list(options)
        return values[0] if values else None

    def text_input(self, *args, **kwargs):
        return str(kwargs.get("value") or "")

    def plotly_chart(self, figure, *, key=None, **kwargs):
        if key:
            self.charts.append(str(key))
        if len(getattr(figure, "data", ())) == 0:
            raise AssertionError(f"Empty default Phase 2 chart: {key}")
        return None


FAKE_ST = _FakeStreamlit()
sys.modules["streamlit"] = FAKE_ST

from analytics.grid_deliverability import (  # noqa: E402
    queue_outcome_snapshot,
    queue_region_profile,
    reserve_margin_profile,
    storage_duration_profile,
)
from analytics.read_architecture import (  # noqa: E402
    READ_ARCHITECTURE_VERSION,
    build_grid_storage_read,
    build_water_read,
)
from analytics.spatial_context import attach_water_context  # noqa: E402
from analytics.water_competition import campus_water_dossier, state_water_exposure_profile  # noqa: E402
from config.visual_design import signature_tool  # noqa: E402
from loaders.energy_loader import load_energy_data  # noqa: E402
from loaders.infrastructure_loader import load_infrastructure_data  # noqa: E402
from loaders.water_loader import load_water_utilization_data  # noqa: E402
from rendering.grid_storage import render_grid_storage_tab  # noqa: E402
from rendering.water import render_water_tab  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    require(READ_ARCHITECTURE_VERSION == "7.0.0", "Phase 2 Read architecture version drifted.")

    energy = load_energy_data()
    infrastructure = load_infrastructure_data()
    water = load_water_utilization_data()
    infrastructure, water = attach_water_context(infrastructure, water)

    outcome = queue_outcome_snapshot(energy.get("queue_outcomes_summary"))
    require(np.isclose(float(outcome.get("Active Queue GW")), 2060.0), "Berkeley Lab active-queue summary changed.")
    require(np.isclose(float(outcome.get("Historical Operational Share Percent")), 13.0), "Historical queue completion share is missing.")
    require(np.isclose(float(outcome.get("Historical Withdrawn Share Percent")), 75.0), "Historical queue withdrawal share is missing.")
    require(float(outcome.get("Median Request to COD Years")) >= 5.0, "Queue lead-time evidence is missing.")

    regions = queue_region_profile(energy.get("interconnection_queue"))
    require(len(regions) >= 8 and regions["Queue GW"].sum() > 1800, "Regional queue-maturity profile is incomplete.")

    reserves = reserve_margin_profile(energy.get("reliability_reserve_margins"))
    require(len(reserves) == 14, "NERC U.S. assessment-area count changed.")
    lowest = reserves.iloc[0]
    require(str(lowest.get("Assessment Area")) == "NPCC-New England", "Lowest extreme-condition reserve area changed.")
    require(np.isclose(float(lowest.get("Extreme Conditions Margin Percent")), -0.9), "Extreme-condition reserve margin changed.")

    duration, duration_summary = storage_duration_profile(energy.get("operating_generators"))
    require(len(duration) == 4, "Operating storage duration bands are incomplete.")
    require(float(duration_summary.get("power_gw", 0)) > 50, "Operating battery power coverage is incomplete.")
    require(2.0 < float(duration_summary.get("weighted_duration_hours", 0)) < 4.0, "Operating storage duration is implausible.")

    drought = water.get("usdm_state_drought")
    require(isinstance(drought, pd.DataFrame) and len(drought) == 51, "State drought snapshot is incomplete.")
    for column in ["D0+ Area Percent", "D1+ Area Percent", "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent"]:
        values = pd.to_numeric(drought[column], errors="coerce")
        require(values.between(0, 100).all(), f"Drought percentage contract failed: {column}")

    summary = water.get("facility_context_summary", {}) or {}
    require(int(summary.get("drought_context_records", 0)) >= 1900, "Drought context did not attach to the facility registry.")
    state_profile = state_water_exposure_profile(water.get("facility_context"), water.get("usgs_state_categories"))
    require(len(state_profile) >= 45, "State water-exposure profile is incomplete.")
    material = state_profile.loc[pd.to_numeric(state_profile["D2+ Area Percent"], errors="coerce").ge(25)]
    require(len(material) >= 10, "Material drought-overlap states are missing.")
    require(pd.to_numeric(material["Published Capacity MW"], errors="coerce").sum() > 50000, "Published capacity was not joined to drought exposure.")
    dossier = campus_water_dossier(water.get("facility_context"))
    require(len(dossier) >= 1900 and "Exposure Tier" in dossier.columns, "Campus water dossier is incomplete.")

    grid_read = build_grid_storage_read(energy, infrastructure)
    for signal in ["historical_operational_pct", "lowest_extreme_margin_pct", "operating_storage_weighted_duration_hours"]:
        require(pd.notna(pd.to_numeric(grid_read.get("signals", {}).get(signal), errors="coerce")), f"Grid Read signal missing: {signal}")
    water_read = build_water_read(water)
    for signal in ["states_with_25pct_d2_area", "published_capacity_in_25pct_d2_states_gw", "direct_evidence_share_pct"]:
        require(pd.notna(pd.to_numeric(water_read.get("signals", {}).get(signal), errors="coerce")), f"Water Read signal missing: {signal}")

    FAKE_ST.charts.clear()
    render_grid_storage_tab(energy, infrastructure, tab_read=grid_read)
    require(set(FAKE_ST.charts) == {
        "grid-storage-conversion-funnel",
        "grid-storage-queue-age",
        "grid-storage-reserve-margins",
        "grid-storage-storage-duration",
        "grid-storage-construction-history",
    }, f"Grid default chart set changed: {FAKE_ST.charts}")

    FAKE_ST.charts.clear()
    render_water_tab(water, infrastructure, tab_read=water_read)
    require(set(FAKE_ST.charts) == {
        "water-competing-uses-2020",
        "water-drought-exposure",
        "water-evidence-ladder",
    }, f"Water default chart set changed: {FAKE_ST.charts}")

    grid_source = (ROOT / "rendering" / "grid_storage.py").read_text(encoding="utf-8")
    water_source = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    connectivity_source = (ROOT / "rendering" / "connectivity.py").read_text(encoding="utf-8")
    require("render_deliverability_screen(" in grid_source, "Grid Delivery Pathway is missing.")
    require("grid-storage-resilience-pair" in grid_source, "Grid reliability/storage paired view is missing.")
    require("render_compact_chart_rail(" not in grid_source and "render_metric_stack(" not in grid_source, "Grid retained the repeated chart-plus-sidecar factory default.")
    require("water-system-workbench" in water_source, "Water background-context workbench is missing.")
    require('views = ["National water claims"]' in water_source and 'views.append("Wastewater investment")' in water_source, "Water context views are not consolidated.")
    require("render_compact_chart_rail(" not in water_source and "render_metric_stack(" not in water_source, "Water retained the repeated chart-plus-sidecar factory default.")
    require("render_compact_chart_rail(" not in connectivity_source and "render_metric_stack(" not in connectivity_source, "Connectivity retained the repeated chart-plus-sidecar factory default.")
    require(connectivity_source.count("st.expander(") == 1 and "Connectivity data" in connectivity_source, "Connectivity registers are not consolidated into one ledger.")

    require(signature_tool("grid_queue_deliverability").status == "current", "Grid deliverability signature tool is missing.")
    require(signature_tool("water_campus_dossier").status == "current", "Campus water dossier signature tool is missing.")

    print(
        "PASS  Phase 2 grid and water · "
        f"{len(regions)} queue regions · {len(reserves)} reserve areas · "
        f"{len(drought)} drought records · {len(dossier):,} campus dossiers"
    )


if __name__ == "__main__":
    main()
