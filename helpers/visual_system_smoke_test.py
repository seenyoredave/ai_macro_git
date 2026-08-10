"""Regression test for the v6.7 Phase 0 visual-system contract."""
from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.visual_design import DOMAIN_VISUAL_PROFILES, domain_profile, protected_signature_tools, validate_visual_contract



def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    errors = validate_visual_contract()
    require(not errors, "Visual contract errors: " + "; ".join(errors))

    protected = {tool.tool_id: tool for tool in protected_signature_tools()}
    require("buildout_leadership_rotation" in protected, "Buildout Leadership Rotation lost protected status.")
    require("national_landscape_map" in protected, "National Landscape Map lost protected status.")

    macro_source = (ROOT / "rendering" / "macro.py").read_text(encoding="utf-8")
    spatial_source = (ROOT / "rendering" / "spatial.py").read_text(encoding="utf-8")
    require("macro-buildout-leadership-rotation" in macro_source, "Buildout Leadership Rotation renderer is missing.")
    require('key=f"{key_prefix}-map"' in spatial_source, "National landscape map renderer is missing.")
    require('key_prefix="macro-national-landscape"' in macro_source, "AI Macro no longer owns the national landscape map.")
    require(
        'render_panel_heading("Buildout leadership rotation"' not in macro_source,
        "AI Macro restored the redundant Buildout Leadership Rotation inner title.",
    )
    require(
        'render_panel_heading("Buildout and outcome gaps"' not in macro_source,
        "AI Macro restored the redundant Buildout and Outcome Gaps inner title.",
    )

    direct_plotly = []
    for path in (ROOT / "rendering").glob("*.py"):
        if path.name == "visual_system.py":
            continue
        if "st.plotly_chart(" in path.read_text(encoding="utf-8"):
            direct_plotly.append(path.name)
    require(not direct_plotly, f"Charts bypass the shared renderer: {direct_plotly}")

    connectivity_charts = (ROOT / "rendering" / "charts_connectivity.py").read_text(encoding="utf-8")
    require("_base_layout" in connectivity_charts, "Connectivity still carries an independent chart shell.")

    chart_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    fake_streamlit = types.SimpleNamespace(
        markdown=lambda *args, **kwargs: None,
        plotly_chart=lambda *args, **kwargs: chart_calls.append((args, kwargs)),
    )
    sys.modules.setdefault("streamlit", fake_streamlit)
    from rendering.visual_system import apply_platform_chart_contract, render_plotly_chart

    representative_figures = [
        go.Figure(go.Bar(x=["A", "B"], y=[1, 2])),
        go.Figure(go.Scattergeo(lat=[21.3], lon=[-157.8], mode="markers")),
        go.Figure(go.Treemap(labels=["A", "B"], parents=["", "A"], values=[2, 1])),
        go.Figure(go.Heatmap(z=[[1, 2], [3, 4]])),
    ]
    for index, figure in enumerate(representative_figures):
        normalized = apply_platform_chart_contract(figure, key=f"visual-contract-{index}")
        require(normalized.layout.uirevision == f"ai-macro:visual-contract-{index}", "Chart state contract was not applied.")
        require(normalized.layout.font.family.startswith("Inter"), "Shared chart typography was not applied.")

    retained_geometry = go.Figure(go.Scatter(x=[1, 2], y=[1, 2])).update_layout(width=901, autosize=False)
    normalized_geometry = apply_platform_chart_contract(retained_geometry, key="geometry-owner-proof")
    require(normalized_geometry.layout.width == 901, "Shared renderer unexpectedly rewrote Plotly width.")
    require(normalized_geometry.layout.autosize is False, "Shared renderer unexpectedly rewrote Plotly autosize.")
    render_plotly_chart(go.Figure(go.Scatter(x=[1, 2], y=[1, 2])), key="stretch-owner-proof")
    require(bool(chart_calls), "Shared renderer did not issue a Streamlit chart call.")
    require(chart_calls[-1][1].get("width") == "stretch", "Streamlit lost sole ownership of responsive chart width.")

    components = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    require("rm-tabkicker" in components and "domain_profile(title)" in components, "Domain stage headers are not shared.")
    require("profile = domain_profile(domain)" in components, "Read accents do not inherit the shared domain palette.")

    expected_accents = {
        "macro": "blue",
        "market": "violet",
        "finance": "violet",
        "compute": "blue",
        "data_centers": "blue",
        "connectivity": "blue",
        "power": "amber",
        "grid_storage": "amber",
        "water": "amber",
        "adoption": "green",
        "workforce": "green",
        "economic_outcomes": "green",
        "evidence": "slate",
    }
    for slug, accent in expected_accents.items():
        profile = domain_profile(slug)
        require(profile is not None and profile.accent == accent, f"{slug} lost its {accent} family accent.")

    renderer_domains = {
        "macro.py": "macro",
        "market.py": "market",
        "finance.py": "finance",
        "compute.py": "compute",
        "data_center.py": "data_centers",
        "connectivity.py": "connectivity",
        "power.py": "power",
        "grid_storage.py": "grid_storage",
        "water.py": "water",
        "adaptation.py": "adoption",
        "workforce.py": "workforce",
        "economic_impact.py": "economic_outcomes",
    }
    for filename, slug in renderer_domains.items():
        source = (ROOT / "rendering" / filename).read_text(encoding="utf-8")
        read_line = next(line for line in source.splitlines() if "render_domain_read(" in line)
        require(f'domain="{slug}"' in read_line, f"{filename} does not bind its Read to the {slug} domain palette.")
        require("accent=" not in read_line, f"{filename} hard-codes a Read accent outside the shared domain palette.")

    css = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    for token in ("--rm-space-1", "--rm-radius-panel", ".rm-tabkicker", ".rm-visually-hidden"):
        require(token in css, f"Missing visual-system CSS token: {token}")
    require("--rm-radius-panel: 0px" in css, "Platform panels regained rounded corners.")
    require("--rm-radius-control: 0px" in css, "Platform controls regained rounded corners.")

    subprocess.run([sys.executable, str(ROOT / "helpers" / "build_visual_inventory.py")], check=True, cwd=ROOT)
    inventory = pd.read_csv(ROOT / "data" / "visual_surface_inventory.csv")
    require(not inventory.empty, "Visual inventory is empty.")
    domains = set(inventory["Domain"].dropna().astype(str))
    expected = {profile.title for profile in DOMAIN_VISUAL_PROFILES}
    require(expected.issubset(domains), f"Visual inventory is missing domains: {sorted(expected - domains)}")
    require((inventory["Surface Type"] == "Chart").sum() >= 45, "Chart inventory unexpectedly contracted.")

    print(
        "PASS  v6.7 visual system · "
        f"{len(DOMAIN_VISUAL_PROFILES)} domain profiles · "
        f"{len(inventory)} inventoried surfaces · "
        "2 protected AI Macro signature tools"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
