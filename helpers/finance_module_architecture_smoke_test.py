"""Static regression checks for the Finance domain module architecture."""

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
    _check(positions == sorted(positions), "Finance module order changed")


def main() -> None:
    app = (ROOT / "ai_macro.py").read_text(encoding="utf-8")
    _check('APP_VERSION = "v3.0.5.' in app, "Finance architecture must remain in the v3.0.5 patch line")

    source = (ROOT / "rendering" / "finance.py").read_text(encoding="utf-8")
    tab = _body(source, "render_finance_tab")
    _ordered(
        tab,
        [
            "_render_current_state(regime_metrics, debt_markets_data, fred_data, nfci_history)",
            '"Funding capacity"',
            "_render_capital_capacity(regime_metrics)",
            '"Company AI disclosures"',
            "_render_commercial_realization(commercialization_data)",
            '"Private-fund cash returns"',
            "_render_private_capital_realization()",
            '"Credit conditions"',
            "_render_debt_markets(debt_markets_data)",
            "_render_nfci(fred_data, nfci_history)",
            '"Borrower and lender stress"',
            'render_evidence_gateway("finance")',
        ],
    )

    for title in (
        '"Current state"',
        '"Funding capacity"',
        '"Company AI disclosures"',
        '"Private-fund cash returns"',
        '"Credit conditions"',
        '"Borrower and lender stress"',
    ):
        _check(title in source, f"Finance module missing: {title}")

    current = _body(source, "_render_current_state")
    for token in ("capex_total", "forward_commitments_total", "Corporate Bond Market Distress", "nfci_snapshot"):
        _check(token in current, f"Finance Current state missing {token}")

    capacity = _body(source, "_render_capital_capacity")
    _check("funding_history" in capacity, "Finance capital capacity lacks combined funding history")
    _check("finance-capital-capacity" in capacity, "Finance capital-capacity summary is missing")
    _check("finance-capital-totals" in capacity, "Finance capital totals are missing")

    _check("def _render_finance_ledger(" not in source, "Finance retained a local reference ledger")
    _check("arrow_safe_dataframe" not in source, "Finance retained dead local-ledger dataframe plumbing")
    _check("load_commitment_components" not in source, "Finance retained dead commitment-ledger plumbing")
    _check("filtered_ledger" not in source, "Finance retained dead commercialization-ledger plumbing")

    charts = (ROOT / "rendering" / "charts_finance.py").read_text(encoding="utf-8")
    funding_chart = _body(charts, "funding_history")
    _check("legend=True" in funding_chart, "Funding history must identify all four capital-capacity series")
    _check('title="Ratio to current CapEx"' in funding_chart, "Funding history axis contract changed")

    print("PASS  Finance capital-cycle module architecture")


if __name__ == "__main__":
    main()
