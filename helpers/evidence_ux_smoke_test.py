from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "rendering" / "evidence.py"
DASHBOARD = ROOT / "rendering" / "dashboard.py"
THEME = ROOT / "rendering" / "theme.css"
EDITORIAL = ROOT / "docs" / "EDITORIAL_STYLE.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    theme = THEME.read_text(encoding="utf-8")
    editorial = EDITORIAL.read_text(encoding="utf-8")

    # Methodology copy is calm and procedural, not rhetorical.
    require("AI Macro applies a consistent evidence standard across its research." in evidence, "Professional Evidence standards opening is missing.")
    for retired in ("evidence, not allegiance", "No source is owed agreement", "reputation, popularity, ideology"):
        require(retired.casefold() not in evidence.casefold(), f"Retired Evidence rhetoric returned: {retired}")
        require(retired.casefold() not in editorial.casefold(), f"Retired Evidence rhetoric returned to editorial guidance: {retired}")

    # Reader hierarchy: conclusion -> cited facts -> source foundation -> context.
    for phrase in (
        "Trace a Read",
        "Evidence used in the Read",
        "Data foundation",
        "Source foundation",
        "Scope &amp; limits",
        "Recent context",
        "Research standards",
        "Technical records",
        "Open technical records",
    ):
        require(phrase in evidence, f"Evidence Reader hierarchy is missing {phrase!r}.")

    standards_pos = evidence.index('"Research standards"')
    trace_pos = evidence.index('"Trace a Read"')
    technical_pos = evidence.index('"Technical records"')
    require(standards_pos < trace_pos < technical_pos, "Evidence hierarchy must place Research standards directly before Trace a Read and Technical records.")

    require("claim_support" in evidence and "_packet_fact_index" in evidence, "Evidence trace no longer binds published claims to deterministic fact IDs.")
    require("build_evidence_packets(context)" in dashboard, "Evidence tab no longer receives deterministic evidence packets.")
    require("if tabs[12].open" in dashboard, "Evidence packets are no longer scoped to the Evidence tab render path.")

    # The large technical warehouse must not be the default visible surface.
    require('with st.expander("Open technical records", expanded=False):' in evidence, "Technical records are not collapsed by default.")
    require('with st.expander("Read the evidence standards", expanded=False):' in evidence, "Methodology statement should remain available without dominating the page.")
    require("archive/yf_history.csv" not in evidence, "Internal archive path leaked back into the Reader-facing Evidence summary.")

    # Styling contract for a restrained document-like evidence surface.
    for class_name in (
        ".rm-evidence-interpretation",
        ".rm-evidence-fact-grid",
        ".rm-evidence-foundation-card",
        ".rm-evidence-context-grid",
    ):
        require(class_name in theme, f"Evidence visual contract is missing {class_name}.")

    print("PASS  Evidence Reader UX and methodology-copy contract")


if __name__ == "__main__":
    main()
