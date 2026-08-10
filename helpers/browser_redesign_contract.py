"""Browser checks for the dossier and Economic Outcomes redesign primitives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rendering.layout_contracts import delivery_pathway_stage_html, detail_dossier_html, value_realization_bridge_html  # noqa: E402

VIEWPORTS = (1280, 1600, 1920, 2560, 768)
HEIGHT = 1200


def build_fixture() -> str:
    theme = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    pathway_items = [
        ("Queue scale", "2,600 GW", "active generation and storage requests"),
        ("Project maturity", "18.5%", "executed IA or construction"),
        ("Reliability", "7 areas", "below 5% extreme summer margin"),
        ("Storage duration", "3.8 hours", "weighted operating battery duration"),
        ("Delivery investment", "$142B", "electric-power construction annual rate"),
    ]
    deliverability = "".join(
        delivery_pathway_stage_html(stage, index=index, namespace="grid-storage-proof")
        for index, stage in enumerate(pathway_items, start=1)
    )

    dossier = detail_dossier_html(
        title="Equinix Ashburn DC1",
        subtitle="Equinix · Loudoun County, Virginia",
        badge="Observed footprint",
        headline_facts=[
            ("Published capacity", "Not published", "public campus estimate"),
            ("Current D2+ overlap", "12.4%", "moderate current overlap"),
            ("Evidence grade", "Partial", "facility-level water disclosure"),
        ],
        groups=[
            (
                "Physical exposure",
                [
                    ("D1+ area", "34.8%", "2026-07 drought snapshot"),
                    ("D2+ area", "12.4%", "2026-07 drought snapshot"),
                    ("Cooling system", "Not disclosed", "facility evidence"),
                    ("Water source", "Municipal supply", "operator disclosure"),
                ],
            ),
            (
                "Evidence and disclosure",
                [
                    ("Quantified use", "No", "annual withdrawal or consumption"),
                    ("Withdrawal", "n/a", "published facility record"),
                    ("Consumption", "n/a", "published facility record"),
                    ("Evidence status", "Facility-level source identified", "public record"),
                ],
            ),
        ],
        namespace="water-campus-proof",
    )
    bridge = value_realization_bridge_html(
        commercial_value="$37B Microsoft · $20B+ OpenAI ARR",
        production_value="Productivity +14.1% since 2020",
        distribution_rows=[
            ("Real compensation", "+4.5%"),
            ("Labor share", "-8.4%"),
            ("Median earnings", "-0.9%"),
            ("Group spread", "3.3 pts"),
        ],
        namespace="economic-outcomes-proof",
    )
    fixture_css = """
    * { box-sizing: border-box; }
    html, body { margin:0; min-height:100%; background:#090e1a; color:#e5e7eb; font-family:Arial,sans-serif; }
    main { margin:0 auto; max-width:none; padding:1.5rem clamp(1rem, 3vw, 3rem) 4rem; width:100%; }
    h1 { font-size:1.25rem; margin:0 0 1.25rem; }
    .proof-panel { border:1px solid rgba(148,163,184,.18); border-radius:0; margin-bottom:2rem; padding:1rem; }
    .proof-title { color:#f3f6fb; font-size:.9rem; font-weight:760; margin-bottom:.75rem; }
    .streamlit-fit-probe { width:fit-content; max-width:100%; }
    .proof-native-columns { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:.55rem; width:100%; }
    @media (max-width:1050px) { .proof-native-columns { grid-template-columns:repeat(2,minmax(0,1fr)); } }
    @media (max-width:620px) { .proof-native-columns { grid-template-columns:1fr; } }
    """
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<style>{theme}\n{fixture_css}</style></head><body><main>
<h1>AI Macro redesign contract</h1>
<section class='proof-panel' data-proof='deliverability'><div class='proof-title'>Grid Connection Conditions</div><div class='proof-native-columns'>{deliverability}</div></section>
<section class='proof-panel' data-proof='dossier'><div class='proof-title'>Campus water profile</div>{dossier}</section>
<section class='proof-panel' data-proof='bridge'>{bridge}</section>
</main></body></html>"""


def _measure(page, width: int) -> dict:
    return page.evaluate(
        """(width) => {
        const rect = (el) => { const r=el.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}; };
        const deliverability=document.querySelector('.proof-native-columns');
        const deliverabilityWrapper=deliverability;
        const deliverabilityPanel=document.querySelector('[data-proof=\"deliverability\"]');
        const deliveryStages=[...document.querySelectorAll('.rm-deliverability-stage-card')];
        const dossier=document.querySelector('.rm-dossier');
        const facts=[...document.querySelectorAll('.rm-dossier-fact')];
        const groups=[...document.querySelectorAll('.rm-dossier-group')];
        const rows=[...document.querySelectorAll('.rm-dossier-row')];
        const bridge=document.querySelector('.rm-value-bridge');
        const track=document.querySelector('.rm-value-bridge-track');
        const layers=[...document.querySelectorAll('.rm-value-bridge-layer')];
        const all=[deliverability,dossier,bridge,track,...deliveryStages,...facts,...groups,...rows,...layers].filter(Boolean);
        const insideViewport=all.every(el => { const r=el.getBoundingClientRect(); return r.left >= -1 && r.right <= width + 1; });
        const overflowChecked=[deliverability,dossier,bridge,track,...facts,...groups,...rows].filter(Boolean);
        const noOverflow=overflowChecked.every(el => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1);
        const stageContentFits=deliveryStages.every(stage => { const copy=stage.querySelector('.rm-deliverability-copy'); return !copy || (copy.scrollWidth <= copy.clientWidth + 1 && copy.scrollHeight <= copy.clientHeight + 1); });
        const deliveryRects=deliveryStages.map(rect);
        const groupRects=groups.map(rect);
        const layerRects=layers.map(rect);
        return {
          viewport: width,
          deliverability: rect(deliverability),
          deliverabilityWrapper: rect(deliverabilityWrapper),
          deliverabilityPanel: rect(deliverabilityPanel),
          deliveryRects,
          dossier: rect(dossier),
          bridge: rect(bridge),
          groupRects,
          layerRects,
          facts: facts.map(rect),
          insideViewport,
          noOverflow,
          stageContentFits,
          deliverabilityWide: deliveryRects.length === 5 && deliveryRects.every(stage => Math.abs(stage.y-deliveryRects[0].y) < 2),
          wrapperFills: deliverability.getBoundingClientRect().width >= deliverabilityPanel.getBoundingClientRect().width * .90,
          deliverabilityStacked: deliveryRects.length === 5 && deliveryRects.every(stage => stage.width >= deliverability.getBoundingClientRect().width * .45),
          dossierColumns: groups.length > 1 && Math.abs(groupRects[0].y-groupRects[1].y) < 2,
          bridgeHorizontal: layerRects.length === 3 && layerRects.every(layer => Math.abs(layer.y-layerRects[0].y) < 2),
          bridgeVertical: layerRects.length === 3 && layerRects.every(layer => layer.width >= track.getBoundingClientRect().width * .95),
        };
      }""",
        width,
    )


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'audit'/'redesign_contract')
    args=parser.parse_args()
    output=args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    html=build_fixture(); (output/'redesign_fixture.html').write_text(html, encoding='utf-8')
    from playwright.sync_api import sync_playwright
    reports=[]
    with sync_playwright() as p:
        system_chromium = Path("/usr/bin/chromium")
        launch_kwargs = {"headless": True}
        if system_chromium.exists():
            launch_kwargs.update({
                "executable_path": str(system_chromium),
                "args": ["--no-sandbox", "--disable-dev-shm-usage"],
            })
        browser=p.chromium.launch(**launch_kwargs)
        page=browser.new_page(viewport={'width':VIEWPORTS[0], 'height':HEIGHT})
        for width in VIEWPORTS:
            page.set_viewport_size({'width':width,'height':HEIGHT})
            page.set_content(html, wait_until='load')
            report=_measure(page,width)
            narrow=width<=900
            checks={
                'inside_viewport': report['insideViewport'],
                'no_overflow': report['noOverflow'] and report['stageContentFits'],
                'deliverability_layout': report['deliverabilityStacked'] if width <= 900 else report['deliverabilityWide'],
                'streamlit_wrapper_fill': report['wrapperFills'],
                'dossier_responsive': (not report['dossierColumns']) if narrow else report['dossierColumns'],
                'bridge_layout': report['bridgeVertical'] if width <= 760 else report['bridgeHorizontal'],
            }
            report['checks']=checks; report['passed']=all(checks.values())
            page.screenshot(path=output/f'redesign_contract_{width}px.png', full_page=True)
            reports.append(report)
        browser.close()
    payload={'scope':'pure HTML/CSS deliverability, dossier, and value-bridge primitives', 'passed':all(r['passed'] for r in reports), 'results':reports}
    (output/'redesign_contract_report.json').write_text(json.dumps(payload,indent=2),encoding='utf-8')
    if not payload['passed']:
        failed={r['viewport']:[k for k,v in r['checks'].items() if not v] for r in reports if not r['passed']}
        raise AssertionError(f'Redesign browser contract failed: {failed}')
    print('PASS  browser redesign contract · '+', '.join(f'{w}px' for w in VIEWPORTS))


if __name__=='__main__':
    main()
