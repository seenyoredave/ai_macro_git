"""Regression checks for chart breathing room and paired-panel alignment."""

from __future__ import annotations

from pathlib import Path
import re
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


def _css_rule(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", css, flags=re.MULTILINE)
    if not match:
        raise AssertionError(f"CSS surface is missing: {selector}")
    return match.group(1)


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
        "rendering/compute.py": [
            "compute-panel-capacity-demand-selected",
            "compute-panel-buildout-selected",
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

    theme = (PROJECT_ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    subtitle_rule = theme.split(".rm-subtitle-row", 1)[1].split("}", 1)[0]
    if "max-width: none" not in subtitle_rule or "width: 100%" not in subtitle_rule:
        raise AssertionError("The masthead subtitle/version row still has a fixed-width ceiling.")
    tab_rule = theme.split('div[data-testid="stTabs"] button[role="tab"]', 1)[1].split("}", 1)[0]
    for required in ("flex: 0 0 auto", "min-width: max-content", "white-space: nowrap"):
        if required not in tab_rule:
            raise AssertionError(f"Responsive tabs lost their non-collapsing contract: {required}")

    for token in ("--rm-radius-control: 0px", "--rm-radius-panel: 0px"):
        if token not in theme:
            raise AssertionError(f"Global square-edge visual token regressed: {token}")
    square_surfaces = (
        ".rm-card", ".rm-stat", ".rm-panel", ".rm-definition", ".rm-table-wrap",
        '[data-testid="stDataFrame"]', ".stExpander", ".rm-map-key", ".rm-domain-read",
        ".rm-domain-read-evidence-card", ".rm-summary-row", ".rm-summary-stack",
        ".rm-dossier", ".rm-dossier-badge", ".rm-value-bridge", ".rm-deliverability-screen",
        ".rm-deliverability-stage-card",
    )
    for selector in square_surfaces:
        rule = _css_rule(theme, selector)
        if "border-radius: 0" not in rule:
            raise AssertionError(f"Rounded presentation surface returned: {selector}")

    card_rule = theme.split(".rm-domain-read-evidence-card", 1)[1].split("}", 1)[0]
    for required in ("display: grid", "grid-template-rows: minmax(1.8rem, auto) auto 1fr", "align-content: start", "row-gap: 0.18rem"):
        if required not in card_rule:
            raise AssertionError(f"Read evidence-card spacing lost its shared contract: {required}")
    label_rule = theme.split(".rm-domain-read-evidence-label", 1)[1].split("}", 1)[0]
    if "min-height: 1.8rem" not in label_rule or "align-items: flex-end" not in label_rule:
        raise AssertionError("Read evidence labels no longer reserve consistent title space.")
    for selector in (".rm-domain-read-evidence-value", ".rm-domain-read-evidence-context"):
        rule = theme.split(selector, 1)[1].split("}", 1)[0]
        if "margin-top: 0" not in rule:
            raise AssertionError(f"{selector} regained inconsistent top spacing.")

    print(
        "PASS  Platform spacing and alignment · nice-grid headroom verified · "
        f"{sum(len(keys) for keys in expected_rules.values())} paired panels covered"
    )


if __name__ == "__main__":
    main()
