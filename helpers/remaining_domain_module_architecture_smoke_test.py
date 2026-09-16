"""Static regression checks for the remaining canonical domain-module layouts."""

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
    _check('APP_VERSION = "v3.0.5.8"' in app, "Title/subtitle protection must remain active in v3.0.5.8")

    market = (ROOT / "rendering" / "market.py").read_text(encoding="utf-8")
    market_tab = _body(market, "render_market_tab")
    _ordered(
        market_tab,
        [
            "_render_market_ledger_summary(market_ledger",
            "_render_market_structure(market_ledger)",
            'render_section("Sector valuation and trading"',
            '"Sector detail"',
            "_render_market_history(market_ledger)",
            'render_evidence_gateway("market")',
        ],
        "Market",
    )
    for title in ('"Market snapshot"', '"Market concentration and breadth"', '"Sector valuation and trading"', '"Sector detail"', '"Historical development"'):
        _check(title in market, f"Market module missing: {title}")
    _check("Shiller CAPE" in market, "Market broader-market valuation context is missing")
    _check("def _render_market_constituent_ledger(" not in market, "Market retained a local reference ledger")

    compute = (ROOT / "rendering" / "compute.py").read_text(encoding="utf-8")
    compute_tab = _body(compute, "render_compute_tab")
    _ordered(
        compute_tab,
        [
            "_render_current_state(infrastructure_data)",
            "_render_capacity_and_demand(infrastructure_data)",
            "_render_critical_supply_chain(infrastructure_data)",
            "_render_domestic_buildout(infrastructure_data)",
            "_render_serving_economics(commercialization_data)",
            "_render_manufacturing_output(infrastructure_data)",
            'render_evidence_gateway("compute")',
        ],
        "Compute",
    )
    for title in ('"Current state"', '"Factory capacity and demand"', '"AI hardware supply chain"', '"U.S. manufacturing projects"', '"AI revenue and service costs"', '"Manufacturing output"'):
        _check(title in compute, f"Compute module missing: {title}")
    _check("def _render_compute_ledger(" not in compute, "Compute retained a local reference ledger")
    _check("arrow_safe_dataframe" not in compute, "Compute retained local-ledger dataframe plumbing")

    data_center = (ROOT / "rendering" / "data_center.py").read_text(encoding="utf-8")
    dc_tab = _body(data_center, "render_data_center_tab")
    _ordered(
        dc_tab,
        [
            "_render_pulse(campuses, infrastructure_data)",
            "_render_development_profile(inventory)",
            "_render_scale(campuses)",
            "_render_geography(campuses, infrastructure_data)",
            "_render_connectivity_operator_structure(connectivity, campuses)",
            "_render_evidence_coverage(campuses)",
            'render_evidence_gateway("data_center")',
        ],
        "Data Centers",
    )
    for title in ('"Campus inventory"', '"Development records"', '"Campus capacity"', '"Campus geography"', '"Connectivity and operators"', '"Evidence coverage"'):
        _check(title in data_center, f"Data Centers module missing: {title}")
    coverage = _body(data_center, "_render_evidence_coverage")
    for token in ('"Capacity coverage"', '"Mapped coverage"', '"Source coverage"', '"Higher-grade evidence"'):
        _check(token in coverage, f"Data Centers evidence coverage missing {token}")
    _check("def _render_data_center_ledger(" not in data_center, "Data Centers retained a local registry ledger")

    grid = (ROOT / "rendering" / "grid_storage.py").read_text(encoding="utf-8")
    grid_tab = _body(grid, "render_grid_storage_tab")
    _ordered(
        grid_tab,
        [
            "_render_deliverability_screen(context)",
            "_render_ai_grid_deliverability(context)",
            "_render_queue_conversion(context)",
            "_render_reliability_storage(context)",
            "_render_queue_regions(context)",
            "_render_investment(context)",
            'render_evidence_gateway("grid_storage")',
        ],
        "Grid & Storage",
    )
    for title in ('"Interconnection snapshot"', '"Data-center load and grid deliverability"', '"Queue outcomes"', '"Reliability and storage"', '"Regional interconnection queues"', '"Grid construction spending"'):
        _check(title in grid, f"Grid & Storage module missing: {title}")
    ai_grid = _body(grid, "_render_ai_grid_deliverability")
    _check("data_center_capacity_by_state" in ai_grid, "Grid AI interface lacks data-center geography")
    _check("queue_age_by_region" in ai_grid, "Grid AI interface lacks interconnection maturity")
    regional = _body(grid, "_render_queue_regions")
    _check('["Technology", "Region"]' in regional, "Grid regional module duplicates AI-interface queue-age view")
    charts = (ROOT / "rendering" / "charts_grid_storage.py").read_text(encoding="utf-8")
    _check("def data_center_capacity_by_state(" in charts, "Grid data-center capacity chart is missing")

    economic = (ROOT / "rendering" / "economic_impact.py").read_text(encoding="utf-8")
    economic_tab = _body(economic, "render_economic_impact_tab")
    _ordered(
        economic_tab,
        [
            "_render_current_state(economic_impact_data, commercialization_data)",
            "_render_commercial_signal(commercialization_data)",
            "_render_macro_validation(economic_impact_data)",
            "_render_distribution_of_gains(economic_impact_data)",
            '"Investment, output, and productivity"',
            '"Production and labor costs"',
            'render_evidence_gateway("economic_impact")',
        ],
        "Economic Outcomes",
    )
    for title in ('"AI revenue and national outcomes"', '"AI commercial signal"', '"Macro validation"', '"Productivity and pay"', '"Investment, output, and productivity"', '"Production and labor costs"'):
        _check(title in economic, f"Economic Outcomes module missing: {title}")
    _check("def _render_economic_ledger(" not in economic, "Economic Outcomes retained a local reference ledger")
    _check("arrow_safe_dataframe" not in economic, "Economic Outcomes retained local-ledger dataframe plumbing")

    contract = (ROOT / "rendering" / "layout_contracts.py").read_text(encoding="utf-8")
    _check("AI commercialization and macro outcomes" in contract, "Economic Outcomes current-state framing is missing")
    _check("Parallel readings" in contract, "Economic Outcomes parallel-reading framing is missing")
    css = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    bridge_css = css[css.index(".rm-value-bridge {"): css.index("/* v6.10 presentation proof set")]
    _check("::after" not in bridge_css, "Economic Outcomes bridge still uses directional arrows")

    print("PASS  Market, Compute, Data Centers, Grid & Storage, and Economic Outcomes module architecture")


if __name__ == "__main__":
    main()
