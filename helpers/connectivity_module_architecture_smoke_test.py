"""Static regression checks for the Connectivity domain module architecture."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _body(source: str, function_name: str) -> str:
    start = source.index(f"def {function_name}(")
    next_def = source.find("\ndef ", start + 5)
    return source[start: next_def if next_def >= 0 else len(source)]


def _ordered(body: str, tokens: list[str]) -> None:
    positions = [body.index(token) for token in tokens]
    _check(positions == sorted(positions), "Connectivity module order changed")


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    _check('APP_VERSION = "v3.0.5.' in app, "Connectivity architecture must remain in the v3.0.5 patch line")

    source = (ROOT / "rendering" / "connectivity.py").read_text(encoding="utf-8")
    tab = _body(source, "render_connectivity_tab")
    _ordered(
        tab,
        [
            "_render_current_state(connectivity)",
            "_render_ai_network_interaction(connectivity)",
            "_render_interconnection(connectivity)",
            "_render_submarine(connectivity)",
            "_render_middle_mile(connectivity)",
            "_render_evidence_coverage(connectivity)",
            'render_evidence_gateway("connectivity")',
        ],
    )

    for title in (
        '"Network overview"',
        '"Data centers and network access"',
        '"Internet exchanges"',
        '"Submarine cable gateways"',
        '"Middle-mile fiber"',
        '"Evidence coverage"',
    ):
        _check(title in source, f"Connectivity module missing: {title}")

    interaction = _body(source, "_render_ai_network_interaction")
    _check("data_center_connectivity_state" in interaction, "Connectivity AI/network state comparison is missing")
    _check("campus_distance_distribution" in interaction, "Connectivity campus-proximity view is missing")

    coverage = _body(source, "_render_evidence_coverage")
    for token in (
        "campuses_screened",
        "campuses_with_landing_proximity",
        "campuses_with_live_facility_proximity",
        "states_with_ixp_evidence",
    ):
        _check(token in coverage, f"Connectivity evidence coverage is missing {token}")

    _check("def _render_connectivity_ledger(" not in source, "Connectivity retained a local reference ledger")
    _check("arrow_safe_dataframe" not in source, "Connectivity retained dead local-ledger dataframe plumbing")

    print("PASS  Connectivity AI/network-first module architecture")


if __name__ == "__main__":
    main()
