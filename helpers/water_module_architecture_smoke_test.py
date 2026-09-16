"""Static regression checks for the Water domain module architecture."""

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
    _check(positions == sorted(positions), "Water module order changed")


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    _check('APP_VERSION = "v3.0.5.' in app, "Water architecture must remain in the v3.0.5 patch line")

    water = (ROOT / "rendering" / "water.py").read_text(encoding="utf-8")
    tab = _body(water, "render_water_tab")
    _ordered(
        tab,
        [
            "_render_current_state(context)",
            "_render_campus_dossier(context)",
            "_render_local_exposure(context)",
            "_render_system_context_workbench(context, infrastructure_data)",
            "_render_coverage(context)",
            'render_evidence_gateway("water")',
        ],
    )

    for title in (
        '"Current state"',
        '"Water observability"',
        '"Campus water profile"',
        '"County drought"',
        '"National water use"',
        '"Water disclosure coverage"',
    ):
        _check(title in water, f"Water module missing: {title}")

    current = _body(water, "_render_current_state")
    _check("water_local_context_coverage" in current, "Water observability is not part of Current state")

    coverage = _body(water, "_render_coverage")
    _check("water_state_evidence_profile" in coverage, "Water evidence coverage lacks state-level direct-evidence view")
    _check("water_local_context_coverage" not in coverage, "Water observability is duplicated in Evidence coverage")

    exposure = _body(water, "_render_local_exposure")
    _check("first=True" not in exposure, "Geographic exposure incorrectly owns first-module spacing")

    _check("def _render_water_ledger(" not in water, "Water retained a local reference ledger")
    _check("arrow_safe_dataframe" not in water, "Water retained dead local-ledger dataframe plumbing")

    print("PASS  Water observability-first module architecture")


if __name__ == "__main__":
    main()
