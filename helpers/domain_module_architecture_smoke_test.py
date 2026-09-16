"""Static regression checks for the first canonical domain-module layouts."""

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


def _ordered(body: str, tokens: list[str], label: str) -> None:
    positions = [body.index(token) for token in tokens]
    _check(positions == sorted(positions), f"{label} module order changed")


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    _check('APP_VERSION = "v3.0.5.' in app, "Canonical module architecture must remain in the v3.0.5 patch line")

    power = (ROOT / "rendering" / "power.py").read_text(encoding="utf-8")
    power_tab = _body(power, "render_power_tab")
    _ordered(
        power_tab,
        [
            "_render_power_pulse(context)",
            "_render_demand(context)",
            "_render_supply(context)",
            "_render_buildout(context)",
            "_render_prices(context, power_data)",
            'render_evidence_gateway("power")',
        ],
        "Power",
    )
    for title in (
        '"Power snapshot"',
        '"Electricity demand and large loads"',
        '"Generation"',
        '"Planned generation"',
        '"Electricity prices and fuel infrastructure"',
    ):
        _check(title in power, f"Power module missing: {title}")
    _check("def _render_power_ledger(" not in power, "Power retained a local reference ledger")

    adoption = (ROOT / "rendering" / "adoption.py").read_text(encoding="utf-8")
    adoption_tab = _body(adoption, "render_adoption_tab")
    _ordered(
        adoption_tab,
        [
            'render_section("Current adoption"',
            'render_section("Adoption over time"',
            "_render_business_integration(adoption_data)",
            "_render_worker_integration(adoption_data)",
            "_render_paid_adoption(commercialization_data)",
            'render_section("AI use by industry"',
            'render_evidence_gateway("adoption")',
        ],
        "Adoption",
    )
    _check('"Business integration"' in adoption, "Adoption business-integration module is missing")
    _check('"Paid adoption"' in adoption, "Adoption paid-adoption module is missing")
    _check("def _render_adoption_ledger(" not in adoption, "Adoption retained a local reference ledger")

    workforce = (ROOT / "rendering" / "workforce.py").read_text(encoding="utf-8")
    workforce_tab = _body(workforce, "render_workforce_tab")
    _ordered(
        workforce_tab,
        [
            "_render_current_state(workforce_data)",
            "_render_observed_outcomes(workforce_data)",
            "_render_labor_market_dynamics(workforce_data)",
            "_render_compensation(workforce_data)",
            "_render_exposure_benchmark(workforce_data)",
            'render_evidence_gateway("workforce")',
        ],
        "Workforce",
    )
    dynamics = _body(workforce, "_render_labor_market_dynamics")
    _check("Exposure benchmark" not in dynamics, "Workforce exposure remains mixed with observed labor dynamics")
    _check('"Exposure benchmark"' in workforce, "Workforce exposure module is missing")
    _check("def _render_workforce_ledger(" not in workforce, "Workforce retained a local reference ledger")

    print("PASS  canonical Power, Adoption, and Workforce module architecture")


if __name__ == "__main__":
    main()
