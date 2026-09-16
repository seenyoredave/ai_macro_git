"""Lock the two human-only platform statements against bot edits."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EVIDENCE_STANDARDS_SHA256 = "f13307fae95db5e75f8efdf6ee61fb2c009674c93bbaaf68724e42207ed9218d"
PURPOSE_STATEMENT_SHA256 = "701f0f3e3d5f182e9f2195dfb09cffa926e022f055b13db53c2681a768b88ea6"


def _sha(value: str) -> str:
    return hashlib.sha256(value.strip().encode("utf-8")).hexdigest()


def _evidence_standards() -> str:
    tree = ast.parse((ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "EVIDENCE_STANDARDS" for target in node.targets):
            continue
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute):
            return str(ast.literal_eval(node.value.func.value)).strip()
        return str(ast.literal_eval(node.value)).strip()
    raise AssertionError("EVIDENCE_STANDARDS is missing")


def _purpose_statement() -> str:
    tree = ast.parse((ROOT / "config" / "metric_definitions.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and key.value == "Purpose Statement":
                return str(ast.literal_eval(value)).strip()
    raise AssertionError("Purpose Statement is missing")


def main() -> None:
    if _sha(_evidence_standards()) != EVIDENCE_STANDARDS_SHA256:
        raise AssertionError("Research standards statement changed")
    if _sha(_purpose_statement()) != PURPOSE_STATEMENT_SHA256:
        raise AssertionError("About this platform statement changed")

    components = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    evidence = (ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")
    bot_rules = (ROOT / "botreadme.md").read_text(encoding="utf-8")

    if 'with st.expander("About this platform", expanded=False):' not in components:
        raise AssertionError("About this platform presentation changed")
    if 'render_platform_purpose(METRIC_DEFINITIONS["Purpose Statement"])' not in app:
        raise AssertionError("About this platform no longer uses the protected Purpose Statement")
    research_section = """render_section(
        "Research standards",
        "Source selection, corroboration, and the boundary between evidence and interpretation.",
        first=True,
    )
    with st.expander("Read the evidence standards", expanded=False):
        st.markdown(EVIDENCE_STANDARDS)"""
    if research_section not in evidence:
        raise AssertionError("Research standards presentation or copy changed")
    if "human-authored and human-only" not in bot_rules:
        raise AssertionError("Human-only statement rule is missing from botreadme.md")

    print("PASS  human-only About this platform and Research standards statements preserved")


if __name__ == "__main__":
    main()
