from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDERING = ROOT / "rendering"

PUBLIC_CALLS = {
    "caption",
    "info",
    "warning",
    "write",
    "markdown",
    "render_section",
    "render_panel_heading",
    "render_tab_header",
    "render_statline",
    "metric_card",
}

BANNED_PUBLIC_PHRASES = {
    "rps directly measures",
    "coverage now separates",
    "it still does not observe",
    "missing disclosure is never inferred",
    "the platform does not",
    "the platform uses",
    "manual connectivity refresh",
    "latest refresh report",
    "connectivity refresh report",
    "source mode",
    "coverage contract",
    "retained archive",
    "active retained sources",
    "configured universe",
    "parser version",
    "ingestion status",
    "reading " + "rule",
    "important " + "boundary",
    "does " + "not claim",
    "neither " + "measure",
    "measures public " + "cable-system",
    "coverage and " + "limitations",
    "whether technology and " + "ai-adjacent",
    "historical panels begin with the earliest date",
    "source universes and separate totals",
    "a compact site-economics cross-signal",
    "detailed evidence in connectivity",
}

# These phrases are appropriate in Terms or Evidence, but never in a domain
# Read, graphic, heading, footer, sidebar, or presentation control.
BANNED_PRESENTATION_COMMENTARY = {
    "what it cannot prove",
    "what this cannot prove",
    "cannot prove",
    "does not prove",
    "not evidence that",
    "causal attribution",
    "causal claim",
    "evidence strength",
    "attribution boundary",
    "important boundary",
    "methodology detail",
    "counterweight",
    "source register",
    "evidence ledger",
}

SENTENCE_START_WHETHER = re.compile(r"(?:^|[.!?]\s+)whether\b", re.IGNORECASE)

READ_RENDERERS = [
    "macro.py",
    "market.py",
    "finance.py",
    "compute.py",
    "data_center.py",
    "connectivity.py",
    "power.py",
    "grid_storage.py",
    "water.py",
    "adaptation.py",
    "workforce.py",
    "economic_impact.py",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return ""


def literal_text(node: ast.AST) -> str:
    values: list[str] = []
    for item in ast.walk(node):
        if isinstance(item, ast.Constant) and isinstance(item.value, str):
            values.append(item.value)
    return " ".join(values).lower()


def public_literal_strings(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def main() -> None:
    violations: list[str] = []
    for path in sorted(RENDERING.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or call_name(node) not in PUBLIC_CALLS:
                continue
            text = literal_text(node)
            for phrase in BANNED_PUBLIC_PHRASES:
                if phrase in text:
                    violations.append(f"{path.name}:{node.lineno}: {phrase}")

    for path in [ROOT / "config" / "metric_definitions.py", ROOT / "analytics" / "read_architecture.py"]:
        for lineno, text in public_literal_strings(path):
            lowered = text.lower()
            for phrase in BANNED_PUBLIC_PHRASES:
                if phrase in lowered:
                    violations.append(f"{path.relative_to(ROOT)}:{lineno}: {phrase}")
            if SENTENCE_START_WHETHER.search(text.strip()):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: sentence starts with Whether")

    presentation_paths = [RENDERING / filename for filename in READ_RENDERERS] + [
        RENDERING / "read_markup.py",
        RENDERING / "layout_contracts.py",
        ROOT / "analytics" / "read_architecture.py",
        ROOT / "config" / "visual_design.py",
    ]
    for path in presentation_paths:
        for lineno, text in public_literal_strings(path):
            lowered = text.casefold()
            for phrase in BANNED_PRESENTATION_COMMENTARY:
                if phrase in lowered:
                    violations.append(f"{path.relative_to(ROOT)}:{lineno}: {phrase}")

    for path in sorted(RENDERING.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or call_name(node) not in PUBLIC_CALLS:
                continue
            text = " ".join(
                item.value for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            )
            if SENTENCE_START_WHETHER.search(text.strip()):
                violations.append(f"{path.name}:{node.lineno}: sentence starts with Whether")

    require(not violations, "Developer-facing public copy found:\n" + "\n".join(sorted(set(violations))))

    for filename in READ_RENDERERS:
        source = (RENDERING / filename).read_text(encoding="utf-8")
        marker = "render_domain_read("
        require(marker in source, f"{filename} no longer uses the shared Read component.")
        after = source.split(marker, 1)[1]
        next_section = after.find("render_section(")
        if next_section >= 0:
            pre_section = after[:next_section]
            require("st.caption(" not in pre_section, f"{filename} places a free-floating note beneath the Read.")

    adoption = (RENDERING / "adaptation.py").read_text(encoding="utf-8")
    workforce = (RENDERING / "workforce.py").read_text(encoding="utf-8")
    require("RPS directly measures" not in adoption, "Adoption developer note returned.")
    require("Coverage now separates" not in workforce, "Workforce developer note returned.")

    data_center = (RENDERING / "data_center.py").read_text(encoding="utf-8")
    terms = (ROOT / "config" / "metric_definitions.py").read_text(encoding="utf-8")
    impact = (RENDERING / "economic_impact.py").read_text(encoding="utf-8")
    impact_layout = (RENDERING / "layout_contracts.py").read_text(encoding="utf-8")
    require("rm-data-center-source-note" not in data_center, "Data-center methodology footer returned to the presentation.")
    require("### Campus-identity methodology" in terms, "Data-center deduplication methodology is missing from Terms.")
    for phrase in ("Evidence strength", "Causal label", "what it cannot prove"):
        require(phrase.casefold() not in (impact + impact_layout).casefold(), f"Economic Outcomes construct commentary returned: {phrase}")

    print(f"Public-copy contract passed across {len(READ_RENDERERS)} Read-bearing tabs.")


if __name__ == "__main__":
    main()
