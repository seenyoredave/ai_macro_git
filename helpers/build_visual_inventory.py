"""Build a source-controlled inventory of user-facing visual surfaces.

The inventory is intentionally static-analysis based.  It records where charts,
selectors, and tables are rendered without importing Streamlit or loading data.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.visual_design import matching_signature_tools, signature_tool

RENDERING = ROOT / "rendering"
OUTPUT = ROOT / "data" / "visual_surface_inventory.csv"

DOMAIN_BY_FILE = {
    "macro.py": "AI Macro",
    "market.py": "Market",
    "finance.py": "Finance",
    "compute.py": "Compute",
    "data_center.py": "Data Centers",
    "connectivity.py": "Connectivity",
    "power.py": "Power",
    "grid_storage.py": "Grid & Storage",
    "water.py": "Water",
    "adoption.py": "Adoption",
    "workforce.py": "Workforce",
    "economic_impact.py": "Economic Outcomes",
    "evidence.py": "Evidence",
    "spatial.py": "Shared / AI Macro",
    "sector.py": "Market",
    "sector_dossier.py": "Market",
    "commercialization.py": "Shared commercialization",
}


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return f"{node.func.value.id}.{node.func.attr}"
    return ""


def _keyword(node: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in node.keywords if item.arg == name), None)


def _source(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:
        return ""


def _literal(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return _source(node).removeprefix("f")
    return ""


def _assigned_chart_keys(tree: ast.AST) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        value = node.value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        if any(isinstance(target, ast.Name) and target.id == "chart_key" for target in targets):
            keys.append((value.value, node.lineno))
    return sorted(set(keys), key=lambda item: (item[1], item[0]))


def _chart_role(key: str, expression: str) -> str:
    token = f"{key} {expression}".casefold()
    if "map" in token or "geo" in token or "treemap" in token:
        return "map"
    if any(word in token for word in ("history", "trajectory", "trend", "rotation")):
        return "trend"
    if any(word in token for word in ("pipeline", "queue", "stage", "development")):
        return "pipeline"
    if any(word in token for word in ("mix", "composition", "contribution", "ownership")):
        return "composition"
    if any(word in token for word in ("mismatch", "gap", "matrix", "validation", "alignment")):
        return "relationship"
    if any(word in token for word in ("coverage", "evidence", "ladder", "disclosure")):
        return "coverage"
    if any(word in token for word in ("ranking", "profile", "momentum", "capacity", "distribution", "largest", "depth")):
        return "ranking"
    return "diagnostic"


SIGNATURE_BY_EXPRESSION = {
    "compute_critical_supply_chain": "critical_supply_chain",
    "data_center_state_pipeline": "data_center_pipeline_explorer",
    "landing_gateway_map": "connectivity_gateway_map",
    "queue_by_region": "grid_queue_deliverability",
}


def _signature_status(key: str, expression: str, source_file: str) -> tuple[str, str]:
    matches = matching_signature_tools(key) if key else ()
    if source_file == "spatial.py" and "key_prefix" in key:
        matches = (signature_tool("national_landscape_map"),)
    if not matches:
        for token, tool_id in SIGNATURE_BY_EXPRESSION.items():
            if token in expression:
                matches = (signature_tool(tool_id),)
                break
    if not matches:
        return "shared", ""
    protected = any(tool.protected for tool in matches)
    return ("protected signature" if protected else "signature"), "; ".join(tool.title for tool in matches)


def build_inventory() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for path in sorted(RENDERING.glob("*.py")):
        domain = DOMAIN_BY_FILE.get(path.name)
        if not domain:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        conditional_chart_keys = _assigned_chart_keys(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node)
            if name == "render_plotly_chart":
                key = _literal(_keyword(node, "key")) or _source(_keyword(node, "key"))
                figure = _source(node.args[0]) if node.args else ""
                if key == "chart_key" and conditional_chart_keys:
                    continue
                role = _literal(_keyword(node, "role")) or _chart_role(key, figure)
                status, signature = _signature_status(key.strip("'\""), figure, path.name)
                rows.append({
                    "Domain": domain,
                    "Surface Type": "Chart",
                    "Analytical Role": role,
                    "Key / Control": key,
                    "Source Expression": figure,
                    "Signature Status": status,
                    "Signature Tool": signature,
                    "Source File": str(path.relative_to(ROOT)),
                    "Line": node.lineno,
                })
            elif name in {"st.selectbox", "st.radio"}:
                label = _source(node.args[0]) if node.args else ""
                key = _literal(_keyword(node, "key")) or _source(_keyword(node, "key"))
                rows.append({
                    "Domain": domain,
                    "Surface Type": "Selector",
                    "Analytical Role": "view control",
                    "Key / Control": key or label,
                    "Source Expression": label,
                    "Signature Status": "shared",
                    "Signature Tool": "",
                    "Source File": str(path.relative_to(ROOT)),
                    "Line": node.lineno,
                })
            elif name == "st.dataframe":
                rows.append({
                    "Domain": domain,
                    "Surface Type": "Interactive table",
                    "Analytical Role": "detail / evidence",
                    "Key / Control": _literal(_keyword(node, "key")) or _source(_keyword(node, "key")),
                    "Source Expression": _source(node.args[0]) if node.args else "",
                    "Signature Status": "shared",
                    "Signature Tool": "",
                    "Source File": str(path.relative_to(ROOT)),
                    "Line": node.lineno,
                })
        for chart_key, line in conditional_chart_keys:
            status, signature = _signature_status(chart_key, "conditional renderer", path.name)
            rows.append({
                "Domain": domain,
                "Surface Type": "Chart",
                "Analytical Role": _chart_role(chart_key, "conditional renderer"),
                "Key / Control": chart_key,
                "Source Expression": "conditional selected view",
                "Signature Status": status,
                "Signature Tool": signature,
                "Source File": str(path.relative_to(ROOT)),
                "Line": line,
            })
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values(["Domain", "Source File", "Line"], kind="stable").reset_index(drop=True)
    return frame


def main() -> int:
    frame = build_inventory()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUTPUT, index=False)
    print(f"Wrote {len(frame):,} visual surfaces to {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
