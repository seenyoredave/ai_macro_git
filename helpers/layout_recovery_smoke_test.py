"""Static and pure-markup regression checks for the shared layout contracts."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rendering.layout_contracts import (  # noqa: E402
    delivery_pathway_stage_html,
    detail_dossier_html,
    signal_rail_html,
    summary_card_html,
    summary_row_html,
    summary_stack_html,
    value_realization_bridge_html,
)


def _css_rule(theme: str, selector: str) -> str:
    return theme.split(selector, 1)[1].split("}", 1)[0]


def main() -> None:
    markup = summary_card_html(
        label="Long <label>",
        value="Operator-disclosed campus connectivity",
        note="No clipping & safe wrapping",
        namespace="proof",
        index=0,
        mode="rail",
    )
    for required in ("rm-summary-card--rail", "&lt;LABEL&gt;", "&amp;", 'data-rm-card="proof-0"'):
        if required not in markup:
            raise AssertionError(f"Summary card markup lost required contract: {required}")

    row_markup = summary_row_html([markup], namespace="proof")
    stack_markup = summary_stack_html([markup], namespace="proof")
    if 'class="rm-summary-row rm-summary-row--1"' not in row_markup or 'data-rm-summary-row="proof"' not in row_markup:
        raise AssertionError("Summary row wrapper lost the responsive grid contract.")
    for required in ('class="rm-summary-stack"', 'data-rm-summary-stack="proof"', "--rm-card-count:1"):
        if required not in stack_markup:
            raise AssertionError(f"Summary stack wrapper lost the equal-height rail contract: {required}")

    signal_markup = signal_rail_html(
        [("Highest pressure", "Cybersecurity & AI Trust", "Pressure 75")],
        namespace="market-proof",
    )
    for required in ('class="rm-signal-rail rm-signal-rail--1"', 'data-rm-signal="market-proof-0"', "Pressure 75"):
        if required not in signal_markup:
            raise AssertionError(f"Signal rail markup lost required contract: {required}")

    pathway_stages = [
        delivery_pathway_stage_html(("Queue scale", "2,600 GW", "active requests"), index=1, namespace="grid-proof"),
        delivery_pathway_stage_html(("Project maturity", "18.5%", "advanced stage"), index=2, namespace="grid-proof"),
        delivery_pathway_stage_html(("Reliability", "7 areas", "below 5% extreme margin"), index=3, namespace="grid-proof"),
        delivery_pathway_stage_html(("Storage duration", "3.8 hours", "weighted operating duration"), index=4, namespace="grid-proof"),
        delivery_pathway_stage_html(("Delivery investment", "$142B", "annual construction rate"), index=5, namespace="grid-proof"),
    ]
    pathway_markup = "".join(pathway_stages)
    for required in ('class="rm-deliverability-stage-card"', 'data-rm-delivery-stage="grid-proof-1"', "QUEUE SCALE", "DELIVERY INVESTMENT"):
        if required not in pathway_markup:
            raise AssertionError(f"Grid Delivery Pathway stage markup lost required contract: {required}")

    dossier = detail_dossier_html(
        title="Campus <A>",
        subtitle="Operator & location",
        badge="Observed footprint",
        headline_facts=[("Capacity", "100 MW", "published")],
        groups=[("Physical exposure", [("Cooling", "Not disclosed")])],
        namespace="proof-dossier",
    )
    for required in ("rm-dossier", "Campus &lt;A&gt;", "Operator &amp; location", "Physical exposure"):
        if required not in dossier:
            raise AssertionError(f"Dossier markup lost required contract: {required}")

    bridge = value_realization_bridge_html(
        commercial_value="$37B Microsoft · $20B+ OpenAI ARR",
        production_value="Productivity +14.1% since 2020",
        distribution_rows=[
            ("Real compensation", "+4.5%"),
            ("Labor share", "-8.4%"),
            ("Median earnings", "-0.9%"),
            ("Group spread", "3.3 pts"),
        ],
        namespace="proof-bridge",
    )
    for required in ('class="rm-value-bridge"', 'data-rm-value-bridge="proof-bridge"', "Worker and household distribution"):
        if required not in bridge:
            raise AssertionError(f"Value bridge markup lost required contract: {required}")

    theme = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    # Clipping and bottom-pinning are forbidden in the summary cards themselves;
    # other visual elements may legitimately clip progress bars or panel backgrounds.
    card_rules = "\n".join(
        _css_rule(theme, selector)
        for selector in (".rm-summary-card {", ".rm-summary-card--row {", ".rm-summary-card--rail {")
    )
    for forbidden in ("overflow: hidden", "justify-content: space-between", "margin-top: auto", "height: 100%"):
        if forbidden in card_rules:
            raise AssertionError(f"Summary-card CSS reintroduced clipping/pinning rule: {forbidden}")
    for required in (
        "max-width: none !important",
        "st-key-full-width-layout-",
        "st-key-compact-layout-",
        "order: 2",
        "order: 1",
        "overflow-wrap: anywhere",
        "grid-template-columns: repeat(auto-fit",
        "grid-template-rows: repeat(var(--rm-card-count)",
        "align-items: stretch",
        "padding: 0.78rem 0.9rem 0.88rem",
        ".rm-signal-rail",
        ".rm-dossier-groups",
        ".rm-value-bridge-track",
        ".rm-deliverability-stage-card",
    ):
        if required not in theme:
            raise AssertionError(f"Shared layout CSS is missing: {required}")

    # Streamlit must remain the sole owner of responsive Plotly width. Styling
    # any measured/rendered descendant reintroduces the observed 700 px
    # fallback race, particularly in Firefox and initially hidden tabs.
    for forbidden in (
        '[data-testid="stElementContainer"]:has([data-testid="stPlotlyChart"])',
        '[data-testid="stPlotlyChart"] > [data-testid="stFullScreenFrame"]',
        '[data-testid="stPlotlyChart"] [data-testid="stFullScreenFrame"]',
        '[data-testid="stPlotlyChart"] > div',
        ".js-plotly-plot",
        ".plot-container",
        ".svg-container",
    ):
        if forbidden in theme:
            raise AssertionError(f"CSS reintroduced a competing Plotly width owner: {forbidden}")

    app_source = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    dashboard_source = (ROOT / "rendering" / "dashboard.py").read_text(encoding="utf-8")
    for required in ('key="domain-navigation"', 'on_change="rerun"'):
        if required not in app_source:
            raise AssertionError(f"Tracked domain navigation lost: {required}")
    if dashboard_source.count(".open:") != 13:
        raise AssertionError("Hidden domains must not initialize their Plotly charts.")

    data_center = (ROOT / "rendering" / "data_center.py").read_text(encoding="utf-8")
    if "render_compact_chart_rail(" in data_center or "render_metric_stack(" in data_center:
        raise AssertionError("Data Centers regressed to the repeated chart-plus-sidecar layout.")
    for required in ("full-width-layout-data-center-pipeline-explorer", "full-width-layout-data-center-geography", "data-center-panel-operator-structure"):
        if required not in data_center:
            raise AssertionError(f"Data Centers full-rollout hierarchy lost: {required}")

    workforce = (ROOT / "rendering" / "workforce.py").read_text(encoding="utf-8")
    for required in ("full-width-layout-workforce-outcomes-matrix", "full-width-layout-workforce-channels", 'view = st.radio("Channel"'):
        if required not in workforce:
            raise AssertionError(f"Workforce matrix-first workbench lost: {required}")

    grid = (ROOT / "rendering" / "grid_storage.py").read_text(encoding="utf-8")
    if "render_deliverability_screen(" not in grid or "grid-storage-resilience-pair" not in grid:
        raise AssertionError("Grid proof-set hierarchy lost the delivery pathway or paired resilience view.")
    components = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    for required in ('st.columns(5, gap="small", vertical_alignment="top")', 'key=f"grid-delivery-pathway-{namespace}"'):
        if required not in components:
            raise AssertionError(f"Grid Delivery Pathway lost native Streamlit horizontal geometry: {required}")
    if "render_compact_chart_rail(" in grid or "render_metric_stack(" in grid:
        raise AssertionError("Grid regressed to the repeated chart-plus-sidecar layout.")

    water = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    for required in ("full-width-layout-water-state-exposure", "render_detail_dossier(", "full-width-layout-water-evidence", "water-system-workbench"):
        if required not in water:
            raise AssertionError(f"Water proof-set hierarchy lost: {required}")
    if "render_compact_chart_rail(" in water or "render_metric_stack(" in water:
        raise AssertionError("Water regressed to the repeated chart-plus-sidecar layout.")

    economic = (ROOT / "rendering" / "economic_impact.py").read_text(encoding="utf-8")
    render_block = economic.split("def render_economic_impact_tab", 1)[1]
    for required in (
        "_render_pulse(economic_impact_data, commercialization_data)",
        "economic-outcomes-value-bridge",
        "economic-outcomes-overview-realized",
        "value_realization_bridge_html",
        "economic-impact-distribution",
        "_render_distribution_of_gains(economic_impact_data)",
    ):
        if required not in economic:
            raise AssertionError(f"Economic Outcomes redesign lost: {required}")

    market = (ROOT / "rendering" / "market.py").read_text(encoding="utf-8")
    if "render_signal_rail(_assessment_stats" not in market:
        raise AssertionError("Market cross-sector state regressed from the signal rail.")

    print("PASS  shared layout contracts · native Plotly width ownership · dossier · outcomes bridge")


if __name__ == "__main__":
    main()
