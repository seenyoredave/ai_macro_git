"""Lock owner-authored domain titles/subtitles against unauthorized copy rewrites."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_HEADERS = {
    "market.py": ("Market", "Market value, returns, breadth, valuation, and company fundamentals across the AI equity universe.", "YFinance + SEC EDGAR"),
    "finance.py": ("Finance", "Cash flow, capital spending, debt, commitments, credit conditions, and private-fund returns.", "SEC / company disclosures / CalSTRS / ILPA / FRED / New York Fed / Chicago Fed"),
    "compute.py": ("Compute", "U.S. compute manufacturing, factory capacity, orders, investment, projects, and AI service costs.", None),
    "data_center.py": ("Data Centers", "U.S. data-center campuses, development status, published capacity, operators, and connectivity.", "Universal Data Center Registry"),
    "connectivity.py": ("Connectivity", "Submarine cables, internet exchanges, middle-mile fiber, and links to major data-center markets.", "FCC / Internet Society Pulse / PeeringDB / TeleGeography / NTIA"),
    "power.py": ("Power", "Electricity demand, generation, planned capacity, prices, and natural-gas infrastructure.", "EIA / FRED / facility registry"),
    "grid_storage.py": ("Grid & Storage", "Interconnection queues, reserve margins, battery storage, and grid construction spending.", "Berkeley Lab / NERC / EIA / U.S. Census Bureau"),
    "water.py": ("Water", "Drought, public-water service areas, campus water records, national withdrawals, and water infrastructure.", "USGS / U.S. Drought Monitor / EPA / EIA / U.S. Census Bureau"),
    "adoption.py": ("Adoption", "Personal use, business use, workplace deployment, employee tasks, and paid adoption.", "RPS / U.S. Census BTOS / primary provider disclosures"),
    "workforce.py": ("Workforce", "Employment, hiring, separations, real pay, and task exposure in AI-linked industries.", "U.S. Bureau of Labor Statistics"),
    "economic_impact.py": ("Economic Outcomes", "Productivity, worker compensation, real earnings, investment, output, and labor costs.", "BLS / BEA / FRED / primary company disclosures"),
    "macro.py": ("AI Macro", "Investment, infrastructure, adoption, and U.S. economic data related to AI.", "YFinance / SEC / FRED / Census / EIA"),
    "evidence.py": ("Evidence", "Sources, formulas, coverage rules, and records behind the platform’s published research.", "Sources and methodology"),
}

# Existing section/panel copy that was rewritten during the module pass and must
# remain owner-authored unless the owner explicitly approves a copy change.
PROTECTED_COPY = {
    "market.py": [
        "Market snapshot", "Market concentration and breadth", "Sector valuation and trading", "Sector detail",
        "Current ownership concentration and participation across", "Market-cap concentration, return contribution, and participation across the covered public-equity universe.",
    ],
    "finance.py": [
        "Funding capacity", "Company AI disclosures", "Private-fund cash returns", "Credit conditions",
        "Operating cash flow, cash reserves, debt change, and disclosed commitments relative to capital spending.",
        "Reported AI revenue, backlog, margins, and demand indicators from company disclosures.",
        "Distributions and remaining NAV for technology and AI-adjacent funds in the retained sample.",
        "Corporate-bond distress and Chicago Fed financial-conditions indexes.",
        "Current funding capacity", "Cash flow, cash reserves, debt changes, and future commitments relative to current capital spending",
    ],
    "compute.py": [
        "Manufacturing output", "Factory capacity and demand", "AI hardware supply chain", "U.S. manufacturing projects", "AI revenue and service costs",
        "U.S. output of computers, communications equipment, and semiconductor components.",
    ],
    "data_center.py": [
        "Campus inventory", "Campus geography", "Campus capacity", "Development records", "Connectivity and operators",
        "The campus registry used across Data Centers, Water, Power, Grid & Storage, and Connectivity.",
    ],
    "connectivity.py": [
        "Network overview", "Data centers and network access",
        "U.S.-connected submarine cables, internet exchanges, and federally funded middle-mile fiber.",
        "Published data-center capacity alongside local internet-exchange activity and cable-landing proximity.",
    ],
    "power.py": [
        "Power snapshot", "Electricity demand and large loads", "Generation", "Planned generation", "Electricity prices and fuel infrastructure",
        "Demand growth, reported large loads, planned generation, and electricity prices.",
    ],
    "grid_storage.py": [
        "Interconnection snapshot", "Active queue capacity, project stage, reserve margins, battery duration, and grid construction spending.",
    ],
    "water.py": [
        "County drought", "Campus water profile", "Water disclosure coverage", "National water use", "Campus water records by state",
        "Current U.S. county drought classifications.", "Current county D2+ exposure across tracked campuses.",
    ],
    "adoption.py": [
        "Business integration", "Paid adoption", "Current adoption", "Adoption over time", "AI use by industry",
        "Survey estimates for personal and business AI use.",
    ],
    "workforce.py": [
        "Employment and labor flows", "Employment and real pay", "Labor-market detail",
        "Employment, real pay, job openings, hiring, quits, and layoffs across covered industries.",
        "Employment history, labor flows, earnings, and published estimates of LLM task exposure.",
    ],
    "economic_impact.py": [
        "AI revenue and national outcomes", "Productivity and pay", "Investment, output, and productivity", "Production and labor costs",
        "Provider AI revenue alongside productivity, real compensation, and household earnings.",
        "Nonfarm-business productivity, real compensation, and median real earnings since 2020.",
    ],
}


def _literal(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _tab_header(path: Path) -> tuple[str | None, str | None, str | None]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "render_tab_header":
            values = [_literal(arg) for arg in node.args[:3]]
            while len(values) < 3:
                values.append(None)
            return tuple(values)  # type: ignore[return-value]
    raise AssertionError(f"No render_tab_header call in {path.name}")


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    if 'APP_VERSION = "v3.0.5.' not in app:
        raise AssertionError("Title/subtitle protection must remain active throughout v3.0.5.x")

    for filename, expected in EXPECTED_HEADERS.items():
        path = ROOT / "rendering" / filename
        actual = _tab_header(path)
        if actual != expected:
            raise AssertionError(f"{filename} domain title/subtitle changed: {actual!r} != {expected!r}")
        source = path.read_text(encoding="utf-8")
        for text in PROTECTED_COPY.get(filename, []):
            if text not in source:
                raise AssertionError(f"{filename} protected title/subtitle copy changed or disappeared: {text!r}")

    print("PASS  owner-authored domain titles/subtitles preserved")


if __name__ == "__main__":
    main()
