"""Targeted regression for v6.5 Water, Grid & Storage, and buildout rotation."""

from __future__ import annotations

from pathlib import Path
import sys
import types

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

from analytics.infrastructure_cycle import current_buildout_momentum  # noqa: E402
from analytics.water_competition import current_top_withdrawal_profile  # noqa: E402
from rendering.charts_infrastructure import infrastructure_leadership_rotation  # noqa: E402
from rendering.charts_water import wastewater_construction_history  # noqa: E402


def main() -> None:
    construction = pd.read_csv(PROJECT_ROOT / "data" / "infrastructure_construction_history.csv")
    construction["Observation Date"] = pd.to_datetime(construction["Observation Date"], errors="coerce", format="mixed")

    required = {
        "Data Center Construction",
        "Computer, Electronic & Electrical Manufacturing Construction",
        "Electric Power Construction",
        "Communication Construction",
        "Public Water Supply Construction",
        "Public Sewage and Waste Disposal Construction",
    }
    missing = required - set(construction.columns)
    if missing:
        raise AssertionError(f"Construction history is missing v6.5 series: {sorted(missing)}")

    momentum = current_buildout_momentum(construction)
    if momentum.empty or momentum.iloc[0]["Series"] != "Data centers":
        raise AssertionError("Data centers are no longer identified as the current buildout leader.")

    rotation = infrastructure_leadership_rotation(construction)
    if len(rotation.data) != 2 or rotation.data[0].type != "heatmap" or rotation.data[1].type != "bar":
        raise AssertionError("Buildout leadership must pair a rotation heatmap with current momentum bars.")
    gutter = float(rotation.layout.xaxis2.domain[0]) - float(rotation.layout.xaxis.domain[1])
    if gutter < 0.08:
        raise AssertionError(f"Buildout leadership current panel lacks breathing room: {gutter:.3f}")

    top = pd.read_csv(PROJECT_ROOT / "data" / "water" / "derived" / "usgs_2020_top_withdrawals.csv")
    profile = current_top_withdrawal_profile(top)
    if profile.empty or profile["Observation Year"].dropna().lt(2020).any():
        raise AssertionError("Current Water competing-use context is not confined to 2020+ evidence.")

    wastewater = construction[["Observation Date", "Public Sewage and Waste Disposal Construction"]].dropna()
    wastewater = wastewater.loc[wastewater["Observation Date"] >= pd.Timestamp("2020-01-01")]
    if wastewater.empty or wastewater["Observation Date"].max() < pd.Timestamp("2026-01-01"):
        raise AssertionError("Wastewater investment chronology is missing or stale.")
    wastewater_fig = wastewater_construction_history(construction)
    if len(wastewater_fig.data) != 1 or wastewater_fig.data[0].type != "scatter":
        raise AssertionError("Water wastewater context must render as one chronological series.")

    app_source = (PROJECT_ROOT / "ai_macro.py").read_text(encoding="utf-8")
    macro_source = (PROJECT_ROOT / "rendering" / "macro.py").read_text(encoding="utf-8")
    water_source = (PROJECT_ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    grid_source = (PROJECT_ROOT / "rendering" / "grid_storage.py").read_text(encoding="utf-8")

    if "macro-buildout-leadership-rotation" not in macro_source:
        raise AssertionError("Buildout Leadership Rotation is not housed in AI Macro.")
    if '"INFRASTRUCTURE"' in app_source:
        raise AssertionError("The retired Infrastructure tab is still exposed.")
    if "2015" in water_source:
        raise AssertionError("Pre-2020 evidence is referenced on the current Water analytical surface.")
    if "Wastewater investment" not in water_source or "wastewater_construction_history" not in water_source:
        raise AssertionError("Wastewater was not integrated into Water.")
    for phrase in ("Current water exposure", "Campus water profile", "Water disclosure coverage", "Other water demand and infrastructure"):
        if phrase not in water_source:
            raise AssertionError(f"Water lost a Phase 2 analytical surface: {phrase}")
    if "height=460" not in water_source:
        raise AssertionError("Water data tables are not explicitly scrollable.")
    if '"State"' not in water_source:
        raise AssertionError("The facility water ledger no longer exposes State for sorting.")

    for phrase in ("Grid connection conditions", "Queue outcomes", "Regional queue conditions", "Reliability and storage", "Operating duration", "Grid and storage data"):
        if phrase not in grid_source:
            raise AssertionError(f"Grid & Storage lost a Phase 2 analytical surface: {phrase}")

    print(
        "PASS  v6.9.1 Water + Grid Phase 2 · rotation rehomed · wastewater current through "
        f"{wastewater['Observation Date'].max():%Y-%m} · {len(momentum)} rotation channels"
    )


if __name__ == "__main__":
    main()
