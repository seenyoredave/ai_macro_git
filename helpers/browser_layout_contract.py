"""Real-browser verification for the shared layout primitives.

This is intentionally a browser test of the exact shared HTML/CSS contracts,
not a substitute for launching the complete Streamlit application.  It remains
useful in environments where the declared Streamlit runtime is unavailable and
is designed to become the fast first layer beneath full-app Playwright tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rendering.layout_contracts import summary_card_html, summary_row_html, summary_stack_html  # noqa: E402

VIEWPORTS = (1280, 1600, 1920, 2560, 768)
HEIGHT = 1200


def _cards(mode: str, namespace: str) -> str:
    fixtures = [
        ("Largest active pipeline", "Virginia", "143 stage-tracked sites"),
        ("Capacity in drought-exposed regions", "87,450 MW", "published campus capacity"),
        ("Direct evidence coverage", "7.8%", "mapped facilities with direct water evidence"),
        ("Long connectivity disclosure label", "Operator-disclosed campus connectivity", "Text must wrap without clipping or touching the card edge"),
    ]
    return "".join(
        summary_card_html(
            label=label,
            value=value,
            note=note,
            namespace=namespace,
            index=index,
            mode=mode,
        )
        for index, (label, value, note) in enumerate(fixtures)
    )


def build_fixture() -> str:
    theme = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    row_cards = summary_row_html(_split_cards(_cards("row", "full-width-proof")), namespace="full-width-proof")
    rail_cards = summary_stack_html(_split_cards(_cards("rail", "compact-proof")), namespace="compact-proof")
    fixture_css = """
    * { box-sizing: border-box; }
    html, body { margin: 0; min-height: 100%; background: #090e1a; color: #e5e7eb; font-family: Arial, sans-serif; }
    .proof-title { margin: 1.2rem 0 0.35rem; font-size: 1.05rem; }
    .proof-copy { color: #94a3b8; margin-bottom: 0.8rem; }
    [data-testid="stHorizontalBlock"] { display: flex; gap: 1.5rem; width: 100%; }
    [data-testid="stColumn"] { min-width: 0; }
    [data-testid="stVerticalBlock"] { width: 100%; }
    [data-testid="stElementContainer"], [data-testid="stMarkdown"], [data-testid="stMarkdownContainer"] { width: 100%; }
    .compact-row > [data-role="chart-column"] { flex: 2.15 1 0; }
    .compact-row > [data-role="rail-column"] { flex: 0.85 1 0; }
    [data-testid="stVerticalBlockBorderWrapper"] { border: 1px solid rgba(148,163,184,.17); border-radius: 14px; padding: 1rem; width: 100%; }
    [data-testid="stPlotlyChart"] { width: 100%; min-height: 410px; background: linear-gradient(135deg, rgba(96,165,250,.14), rgba(167,139,250,.08)); border: 1px dashed rgba(96,165,250,.42); display: grid; place-items: center; color: #cbd5e1; }
    .chart-grid { width: 88%; height: 70%; background-image: linear-gradient(rgba(148,163,184,.12) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,.12) 1px, transparent 1px); background-size: 10% 20%; position: relative; }
    .chart-grid::after { content: "responsive Plotly surface"; position: absolute; inset: 0; display: grid; place-items: center; }
    .st-key-full-width-layout-data-center-geography, .st-key-compact-layout-water-national-claims { margin-bottom: 2rem; }
    """
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>{theme}\n{fixture_css}</style></head>
<body><main class="block-container">
<h1>Recovery layout contract proof</h1>
<div class="st-key-full-width-layout-data-center-geography" data-proof="full-width">
  <div class="proof-title">Full-width analytical section</div>
  <div class="proof-copy">Metric bubbles above; chart consumes the available content width.</div>
  {row_cards}
  <div data-testid="stVerticalBlockBorderWrapper">
    <div data-testid="stPlotlyChart" data-role="full-chart"><div class="chart-grid"></div></div>
  </div>
</div>
<div class="st-key-compact-layout-water-national-claims" data-proof="compact">
  <div class="proof-title">Compact analytical section</div>
  <div class="proof-copy">Chart left; one vertical metric rail right. On narrow screens, bubbles move above the chart.</div>
  <div data-testid="stHorizontalBlock" class="compact-row">
    <div data-testid="stColumn" data-role="chart-column">
      <div data-testid="stVerticalBlock"><div data-testid="stVerticalBlockBorderWrapper" data-role="compact-panel"><div data-testid="stPlotlyChart" data-role="compact-chart"><div class="chart-grid"></div></div></div></div>
    </div>
    <div data-testid="stColumn" data-role="rail-column"><div data-testid="stVerticalBlock"><div data-testid="stElementContainer"><div data-testid="stMarkdown"><div data-testid="stMarkdownContainer">{rail_cards}</div></div></div></div></div>
  </div>
</div>
</main></body></html>"""


def _split_cards(cards: str) -> list[str]:
    marker = '<article class="rm-summary-card'
    parts = cards.split(marker)
    return [marker + part for part in parts[1:]]


def _measure(page, width: int) -> dict:
    result = page.evaluate(
        """(width) => {
        const rect = (sel) => {
          const el = document.querySelector(sel);
          if (!el) return null;
          const r = el.getBoundingClientRect();
          return {x:r.x,y:r.y,width:r.width,height:r.height,bottom:r.bottom,right:r.right};
        };
        const cards = [...document.querySelectorAll('.rm-summary-card')].map((card) => {
          const r = card.getBoundingClientRect();
          const note = card.querySelector('.rm-summary-note');
          const noteRect = note ? note.getBoundingClientRect() : null;
          const childrenInside = [...card.children].every((child) => {
            const c = child.getBoundingClientRect();
            return c.left >= r.left - 0.5 && c.right <= r.right + 0.5 && c.top >= r.top - 0.5 && c.bottom <= r.bottom + 0.5;
          });
          return {
            id: card.dataset.rmCard,
            mode: card.classList.contains('rm-summary-card--rail') ? 'rail' : 'row',
            scrollHeight: card.scrollHeight,
            clientHeight: card.clientHeight,
            scrollWidth: card.scrollWidth,
            clientWidth: card.clientWidth,
            height: r.height,
            noteBottomGap: noteRect ? r.bottom - noteRect.bottom : null,
            childrenInside
          };
        });
        return {
          viewport: width,
          content: rect('.block-container'),
          fullWrapper: rect('[data-proof="full-width"]'),
          fullChart: rect('[data-role="full-chart"]'),
          summaryRow: rect('[data-rm-summary-row="full-width-proof"]'),
          compactWrapper: rect('[data-proof="compact"]'),
          compactChartColumn: rect('[data-role="chart-column"]'),
          railColumn: rect('[data-role="rail-column"]'),
          compactPanel: rect('[data-role="compact-panel"]'),
          summaryStack: rect('[data-rm-summary-stack="compact-proof"]'),
          compactChart: rect('[data-role="compact-chart"]'),
          cards
        };
      }""",
        width,
    )
    full_ratio = result["fullChart"]["width"] / result["fullWrapper"]["width"]
    compact_total = result["compactChartColumn"]["width"] + result["railColumn"]["width"]
    chart_share = result["compactChartColumn"]["width"] / compact_total
    narrow = width <= 900
    rail_cards = [card for card in result["cards"] if card["mode"] == "rail"]
    rail_heights = [card["height"] for card in rail_cards]
    note_gaps = [card["noteBottomGap"] for card in rail_cards if card["noteBottomGap"] is not None]
    checks = {
        "full_chart_at_least_90pct": full_ratio >= 0.90,
        "no_card_vertical_overflow": all(card["scrollHeight"] <= card["clientHeight"] + 1 for card in result["cards"]),
        "no_card_horizontal_overflow": all(card["scrollWidth"] <= card["clientWidth"] + 1 for card in result["cards"]),
        "card_children_inside": all(card["childrenInside"] for card in result["cards"]),
        "summary_row_fits_wrapper": result["summaryRow"]["width"] <= result["fullWrapper"]["width"] + 1,
        "rail_footnote_bottom_padding": all(gap >= 12 for gap in note_gaps),
    }
    if narrow:
        checks.update(
            {
                "rail_above_chart": result["railColumn"]["y"] < result["compactChartColumn"]["y"],
                "chart_collapses_full_width": result["compactChartColumn"]["width"] >= result["compactWrapper"]["width"] * 0.95,
                "rail_collapses_full_width": result["railColumn"]["width"] >= result["compactWrapper"]["width"] * 0.95,
            }
        )
    else:
        checks.update(
            {
                "chart_wider_than_rail": result["compactChartColumn"]["width"] > result["railColumn"]["width"],
                "chart_share_65_to_75pct": 0.65 <= chart_share <= 0.75,
                "rail_is_right_of_chart": result["railColumn"]["x"] > result["compactChartColumn"]["x"],
                "compact_columns_match_height": abs(result["compactChartColumn"]["height"] - result["railColumn"]["height"]) <= 2,
                "panel_and_stack_match_height": abs(result["compactPanel"]["height"] - result["summaryStack"]["height"]) <= 2,
                "rail_cards_even_height": max(rail_heights) - min(rail_heights) <= 2,
            }
        )
    result["derived"] = {
        "full_chart_ratio": full_ratio,
        "compact_chart_share": chart_share,
        "compact_column_height_delta": abs(result["compactChartColumn"]["height"] - result["railColumn"]["height"]),
        "panel_stack_height_delta": abs(result["compactPanel"]["height"] - result["summaryStack"]["height"]),
        "rail_card_height_range": (max(rail_heights) - min(rail_heights)) if rail_heights else None,
        "minimum_note_bottom_gap": min(note_gaps) if note_gaps else None,
    }
    result["checks"] = checks
    result["passed"] = all(checks.values())
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "audit" / "layout_contract")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixture = output / "layout_contract_fixture.html"
    fixture_html = build_fixture()
    fixture.write_text(fixture_html, encoding="utf-8")

    from playwright.sync_api import sync_playwright

    reports = []
    with sync_playwright() as playwright:
        system_chromium = Path("/usr/bin/chromium")
        launch_kwargs = {"headless": True}
        if system_chromium.exists():
            launch_kwargs.update({
                "executable_path": str(system_chromium),
                "args": ["--no-sandbox", "--disable-dev-shm-usage"],
            })
        browser = playwright.chromium.launch(**launch_kwargs)
        page = browser.new_page(viewport={"width": VIEWPORTS[0], "height": HEIGHT})
        for width in VIEWPORTS:
            page.set_viewport_size({"width": width, "height": HEIGHT})
            page.set_content(fixture_html, wait_until="load")
            page.screenshot(path=output / f"layout_contract_{width}px.png", full_page=True)
            reports.append(_measure(page, width))
        browser.close()

    payload = {
        "scope": "shared HTML/CSS primitives; not full Streamlit application",
        "viewports": list(VIEWPORTS),
        "passed": all(report["passed"] for report in reports),
        "results": reports,
    }
    (output / "layout_contract_report.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not payload["passed"]:
        failed = {
            report["viewport"]: [name for name, ok in report["checks"].items() if not ok]
            for report in reports
            if not report["passed"]
        }
        raise AssertionError(f"Browser layout contract failed: {failed}")
    print("PASS  real-browser shared layout contract · " + ", ".join(f"{width}px" for width in VIEWPORTS))


if __name__ == "__main__":
    main()
