"""Source-backed contract for the full-platform editorial layout rollout."""
from __future__ import annotations

from pathlib import Path
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    manifest = pd.read_csv(ROOT / "data" / "layout_rollout_manifest.csv")
    require(len(manifest) == 52, f"Layout rollout manifest changed unexpectedly: {len(manifest)} rows")
    require(not manifest["Renderer Key"].duplicated().any(), "Layout rollout keys are not unique.")
    required_modes = {"full_width", "workbench", "paired_view", "summary_row", "ledger", "instrument_board", "structured_pathway", "structured_record"}
    require(required_modes.issubset(set(manifest["Layout Mode"])), "Full rollout manifest lost an approved layout mode.")

    renderer_names = (
        "compute.py", "data_center.py", "connectivity.py", "finance.py", "power.py",
        "grid_storage.py", "water.py", "adaptation.py", "workforce.py", "economic_impact.py",
    )
    sources = {name: (ROOT / "rendering" / name).read_text(encoding="utf-8") for name in renderer_names}

    # The old factory default is not permitted on any redesigned page.
    for renderer in renderer_names:
        source = sources[renderer]
        require("render_compact_chart_rail(" not in source, f"{renderer} retained the repeated compact chart-plus-sidecar layout.")
        require("render_metric_stack(" not in source, f"{renderer} retained repeated vertical metric sidecars.")

    # Every non-proof-set domain now exposes one consolidated bottom data ledger.
    for renderer, label in {
        "finance.py": "Finance data",
        "compute.py": "Compute data",
        "data_center.py": "Data-center project data",
        "connectivity.py": "Connectivity data",
        "power.py": "Power data",
        "adaptation.py": "Adoption data",
        "workforce.py": "Workforce data",
        "economic_impact.py": "Economic-outcomes data",
    }.items():
        source = sources[renderer]
        require(source.count("st.expander(") == 1, f"{renderer} should expose exactly one bottom ledger expander.")
        require(label in source, f"{renderer} lost its consolidated ledger label.")

    require("finance-funding-instrument-board" in sources["finance.py"], "Finance funding instrument board is missing.")
    require("full-width-layout-finance-private-capital" in sources["finance.py"], "Private-capital realization map is not full width.")

    for key in (
        "full-width-layout-compute-manufacturing-hero",
        "full-width-layout-compute-capacity-demand",
        "full-width-layout-compute-critical-supply-chain",
        "full-width-layout-compute-domestic-buildout",
    ):
        require(key in sources["compute.py"], f"Compute lost {key}.")

    for key in (
        "full-width-layout-data-center-pipeline-explorer",
        "full-width-layout-data-center-geography",
        "data-center-panel-connectivity-context",
        "data-center-panel-operator-structure",
    ):
        require(key in sources["data_center.py"], f"Data Centers lost {key}.")

    require("full-width-layout-connectivity-gateway-map" in sources["connectivity.py"], "Connectivity gateway map is not the hero canvas.")
    require("connectivity-ledger-view" in sources["connectivity.py"], "Connectivity registers are not consolidated.")

    for key in (
        "full-width-layout-power-generation-supply",
        "full-width-layout-power-generation-buildout",
        "full-width-layout-power-prices",
    ):
        require(key in sources["power.py"], f"Power lost {key}.")

    require("render_deliverability_screen(" in sources["grid_storage.py"], "Grid connection summary is missing.")
    require("grid-storage-resilience-pair" in sources["grid_storage.py"], "Grid paired reliability/storage view is missing.")
    require("render_detail_dossier(" in sources["water.py"], "Water dossier redesign is missing.")
    require("water-system-workbench" in sources["water.py"], "Water context workbench is missing.")

    require("full-width-layout-adoption-trajectory" in sources["adaptation.py"], "Adoption unified trajectory is missing.")
    require('view = st.radio("Use view", ["People", "Business"]' in sources["adaptation.py"], "Adoption People/Business selector is missing.")

    require("full-width-layout-workforce-outcomes-matrix" in sources["workforce.py"], "Workforce Outcomes Matrix is not the hero.")
    require("full-width-layout-workforce-channels" in sources["workforce.py"], "Workforce channel workbench is missing.")

    economic = sources["economic_impact.py"].split("def render_economic_impact_tab", 1)[1]
    require("_render_pulse(economic_impact_data, commercialization_data)" in economic, "Protected Economic Outcomes bridge/history is not first.")
    require("economic-outcomes-value-bridge" in sources["economic_impact.py"], "Economic Outcomes bridge is missing.")
    require("_render_distribution_of_gains(economic_impact_data)" in economic, "Distribution-of-gains paired view is missing.")

    css = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    components = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    require("v6.10 full-platform editorial rollout: space-efficiency contract" in css, "Space-efficiency CSS contract is missing.")
    require('st.columns(5, gap="small", vertical_alignment="top")' in components, "Grid connection summary is not using five native Streamlit columns.")
    require('grid-delivery-pathway-' in components and '.rm-deliverability-stage-card' in css, "Grid connection summary runtime styling contract is missing.")

    print(f"PASS  full-platform layout rollout · {len(manifest)} classified sections · no repeated chart-sidecar factory default")


if __name__ == "__main__":
    main()
