"""Static regression checks for domain-header rhythm and comparison-line removal."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    components = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    theme = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")

    _check('APP_VERSION = "v3.0.5.' in app, "Header refinement must remain in the v3.0.5 patch line")

    header_start = components.index("def render_tab_header(")
    header_end = components.index("def render_line_break", header_start)
    header_body = components[header_start:header_end]
    _check("render_domain_change_line" not in header_body, "Domain comparison blurb still renders in the header")

    height_start = components.index("def inject_panel_height_rules(")
    height_end = components.index("def render_panel_heading", height_start)
    _check("st.html(" in components[height_start:height_end], "Panel-height CSS still consumes vertical layout space")

    for filename, function_name in (
        ("market.py", "_inject_market_page_theme"),
        ("data_center.py", "_inject_data_center_page_theme"),
        ("connectivity.py", "_inject_connectivity_theme"),
        ("power.py", "_inject_power_page_theme"),
    ):
        source = (ROOT / "rendering" / filename).read_text(encoding="utf-8")
        start = source.index(f"def {function_name}(")
        next_def = source.find("\ndef ", start + 5)
        body = source[start: next_def if next_def >= 0 else len(source)]
        _check("st.html(" in body, f"{filename} page CSS still participates in vertical layout")

    _check('div[class*="st-key-domain-header-"] {' in theme, "Common domain-header wrapper spacing is missing")
    _check("margin-bottom: 1.02rem;" in theme, "Common domain-header bottom rhythm changed")
    _check("gap: 0.34rem;" in theme, "Common title/subtitle row spacing changed")
    _check("margin-bottom: 1.35rem;" in theme, "Domain-navigation to header spacing changed")

    print("PASS  uniform domain-header spacing and quiet comparison presentation")


if __name__ == "__main__":
    main()
