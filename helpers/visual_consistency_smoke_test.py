"""Guard the bounded v3.0.5.9 visual-calibration contract."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    theme = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    evidence = (ROOT / "rendering" / "evidence.py").read_text(encoding="utf-8")

    if 'APP_VERSION = "v3.0.5.9"' not in app:
        raise AssertionError("visual-calibration package version mismatch")

    required_theme = (
        "/* v3.0.5.9 visual consistency calibration. */",
        ".rm-section.first.compact",
        ".rm-summary-card--row .rm-summary-label",
        ".rm-summary-card--row .rm-summary-note",
        'div[class*="st-key-evidence-inspector"] [data-baseweb="tab-list"]',
        'div[class*="st-key-evidence-inspector"] .rm-table td',
        '.rm-summary-row .rm-summary-card--row:last-child:nth-child(odd)',
    )
    for token in required_theme:
        if token not in theme:
            raise AssertionError(f"missing visual consistency rule: {token}")

    if 'with st.container(key="evidence-inspector"):' not in evidence:
        raise AssertionError("Evidence inspector must keep its scoped visual shell")

    # Do not let a visual pass mutate the two human-only statements. The
    # dedicated statement smoke test verifies exact hashes; these anchors make
    # this pass fail loudly if either surface disappears from its renderer.
    if 'EVIDENCE_STANDARDS = """' not in evidence:
        raise AssertionError("Research standards statement anchor missing")
    components = (ROOT / "rendering" / "components.py").read_text(encoding="utf-8")
    if "def render_platform_purpose(statement: str)" not in components:
        raise AssertionError("About this platform statement renderer missing")

    print("PASS  visual rhythm, stat alignment, and scoped Evidence density")


if __name__ == "__main__":
    main()
