"""Regression checks for chart breathing room and paired-panel alignment."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from loaders.data_center_inventory_loader import load_data_center_inventory  # noqa: E402
from rendering.charts_common import add_axis_headroom, add_stacked_axis_headroom  # noqa: E402
from rendering.charts_data_center import data_center_stage_profile  # noqa: E402
from rendering.charts_energy import electricity_demand_history  # noqa: E402


def _assert_reference_clearance(figure, *, axis: str, maximum: float, label: str) -> None:
    layout_axis = getattr(figure.layout, axis)
    bounds = list(layout_axis.range or [])
    step = float(layout_axis.dtick or 0)
    if len(bounds) != 2 or step <= 0:
        raise AssertionError(f"{label} is missing an explicit nice-grid range.")
    if bounds[1] <= float(maximum):
        raise AssertionError(f"{label} upper bound does not contain the data.")
    if bounds[1] - float(maximum) < step * 0.45:
        raise AssertionError(f"{label} does not preserve a visible grid interval above the data.")


def main() -> None:
    line = go.Figure(go.Scatter(x=[1, 2, 3], y=[10.0, 14.0, 17.8]))
    add_axis_headroom(line, upper=0.18, lower=0.04)
    _assert_reference_clearance(line, axis="yaxis", maximum=17.8, label="generic line chart")

    stacked = go.Figure()
    stacked.add_bar(x=["A", "B"], y=[40, 65])
    stacked.add_bar(x=["A", "B"], y=[35, 25])
    stacked.update_layout(barmode="stack")
    add_stacked_axis_headroom(stacked, upper=0.18, lower=0.0)
    _assert_reference_clearance(stacked, axis="yaxis", maximum=90.0, label="generic stacked chart")

    retail = pd.read_csv(PROJECT_ROOT / "data" / "energy_retail_market_history.csv")
    demand = electricity_demand_history(retail)
    demand_max = max(float(np.nanmax(trace.y)) for trace in demand.data if len(trace.y))
    _assert_reference_clearance(
        demand,
        axis="yaxis",
        maximum=demand_max,
        label="electricity demand by customer class",
    )

    inventory = load_data_center_inventory()
    stage = data_center_stage_profile(inventory.get("national_stage"))
    site_max = max(float(value) for value in stage.data[0].x)
    capacity_max = max(float(value) for value in stage.data[1].x)
    _assert_reference_clearance(stage, axis="xaxis", maximum=site_max, label="data-center site profile")
    _assert_reference_clearance(stage, axis="xaxis2", maximum=capacity_max, label="data-center capacity profile")

    expected_rules = {
        "rendering/power.py": [
            "power-panel-demand-history",
            "power-panel-large-load-profile",
            "power-panel-gas-pipeline",
            "power-panel-lng",
        ],
        "rendering/finance.py": [
            "finance-panel-realization-ledger",
            "finance-panel-realization-map",
        ],
        "rendering/compute.py": [
            "compute-panel-manufacturing-capacity",
            "compute-panel-capacity-utilization",
            "compute-panel-orders-shipments",
            "compute-panel-backlog-inventory",
            "compute-panel-supply-chain",
            "compute-panel-buildout-geography",
        ],
        "rendering/workforce.py": [
            "workforce-panel-employment-history",
            "workforce-panel-employment-momentum",
        ],
        "rendering/economic_impact.py": [
            "economic-impact-panel-index",
            "economic-impact-panel-current",
        ],
        "rendering/market.py": [
            "market-panel-ownership",
            "market-panel-return-contribution",
            "market-panel-concentration-history",
            "market-panel-participation-history",
            "market-panel-earnings-support",
            "market-panel-speculative-load",
            "market-panel-sector-signal-anatomy",
            "market-panel-sector-structure",
        ],
    }
    for relative_path, keys in expected_rules.items():
        source = (PROJECT_ROOT / relative_path).read_text()
        for key in keys:
            if source.count(f'"{key}"') < 2:
                raise AssertionError(f"{key} is not both keyed and covered by an alignment rule.")

    print(
        "PASS  Platform spacing and alignment · nice-grid headroom verified · "
        f"{sum(len(keys) for keys in expected_rules.values())} paired panels covered"
    )


if __name__ == "__main__":
    main()
