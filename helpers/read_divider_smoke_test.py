from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

READ_RENDERERS = {
    "AI Macro": "rendering/macro.py",
    "Market": "rendering/market.py",
    "Finance": "rendering/finance.py",
    "Compute": "rendering/compute.py",
    "Data Centers": "rendering/data_center.py",
    "Connectivity": "rendering/connectivity.py",
    "Power": "rendering/power.py",
    "Grid & Storage": "rendering/grid_storage.py",
    "Water": "rendering/water.py",
    "Adoption": "rendering/adaptation.py",
    "Workforce": "rendering/workforce.py",
    "Economic Outcomes": "rendering/economic_impact.py",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def section_slice(source: str, title: str, endpoint: str) -> str:
    start = source.index(f'"{title}",')
    stop = source.index(endpoint, start)
    return source[start:stop]


def main() -> None:
    markup = (ROOT / "rendering/read_markup.py").read_text(encoding="utf-8")
    theme = (ROOT / "rendering/theme.css").read_text(encoding="utf-8")

    require(
        markup.count('class="rm-read-section-divider"') == 1,
        "Shared Read markup must contain exactly one post-Read divider.",
    )
    require(".rm-read-section-divider" in theme, "Read divider has no shared visual-system style.")
    require("background: var(--rm-border);" in theme, "Read divider no longer uses the platform border token.")

    for label, relative_path in READ_RENDERERS.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        require(
            "render_domain_read(" in source,
            f"{label} no longer renders through the shared Read component.",
        )

    # Tabs whose first analytical surface is a render_section call must suppress
    # that section's own top border. The universal Read divider is the single line.
    checks = [
        ("rendering/macro.py", "Regime board", "_render_primary_macro_cards"),
        ("rendering/market.py", "Market state", "render_statline"),
        ("rendering/finance.py", "Funding capacity", "_render_funding_section"),
        ("rendering/compute.py", "Manufacturing trajectory", "render_summary_row"),
        ("rendering/data_center.py", "Data-center pulse", "render_statline"),
        ("rendering/connectivity.py", "National transport pulse", "facility_count"),
        ("rendering/power.py", "Power pulse", "render_statline"),
        ("rendering/grid_storage.py", "Grid delivery pathway", "render_deliverability_screen"),
        ("rendering/water.py", "Exposure state", "render_statline"),
        ("rendering/adaptation.py", "Diffusion state", "societal ="),
        ("rendering/workforce.py", "Observed workforce outcomes", "with st.container"),
        ("rendering/economic_impact.py", "Outcomes pulse", "render_summary_row"),
    ]
    for relative_path, title, endpoint in checks:
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        block = section_slice(source, title, endpoint)
        require("first=True" in block, f"{title} retained a duplicate post-Read divider in {relative_path}.")

    print(f"Read-divider contract passed across {len(READ_RENDERERS)} Read-bearing tabs.")


if __name__ == "__main__":
    main()
