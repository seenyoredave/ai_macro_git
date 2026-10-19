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
    _check('APP_VERSION = "v3.0.8.5"' in app, "PE retrieval-date correction must use v3.0.8.4")

    source = (ROOT / "rendering" / "finance.py").read_text(encoding="utf-8")
    tab = _body(source, "render_finance_tab")
    _ordered(
        tab,
        [
            '"Funding capacity"',
            "_render_capital_capacity(regime_metrics)",
            '"Company AI disclosures"',
            "_render_commercial_realization(commercialization_data)",
            '"Private equity"',
            "_render_pe_conditions(pe_conditions)",
            '"Credit conditions"',
            'credit_view = st.radio(',
            '"Borrower and lender stress"',
            'render_evidence_gateway(',
        ],
    )

    for title in (
        '"Funding capacity"',
        '"Company AI disclosures"',
        '"Private equity"',
        '"Credit conditions"',
        '"Borrower and lender stress"',
    ):
        _check(title in source, f"Finance module missing: {title}")

    capacity = _body(source, "_render_capital_capacity")
    _check("funding_history" in capacity, "Finance capital capacity lacks combined funding history")
    for token in ("capex_total", "forward_commitments_total", "_funding_capacity_stats"):
        _check(token in capacity, f"Finance funding exhibit lost {token}")
    _check('columns=4, treatment="lead"' in capacity, "Funding debt totals must share the headline row")
    _check('treatment="funding"' in capacity and 'st.columns([1.85, 1]' in capacity, "Funding constituents must sit beside the chart")
    funding_stats = _body(source, "_funding_capacity_stats")
    _check('current.get("total_debt")' in capacity and 'current.get("prior_year_total_debt")' in capacity, "Debt totals are missing from headline row")
    _ordered(funding_stats, ['"Internal cash flow / CapEx"', '"Cash reserve coverage"', '"Debt change / CapEx"', '"Future commitments / CapEx"'])
    _check("_render_current_state" not in source, "Finance repeats readings in a second current-state strip")

    credit = tab[tab.index('credit_view = st.radio('):tab.index('"Borrower and lender stress"')]
    for call in ('render_credit_spreads()', '_render_debt_markets(debt_markets_data)', '_render_nfci(fred_data, nfci_history)'):
        _check(call in credit, f"Finance credit view lost {call}")
    _check('key="finance-credit-view"' in credit, "Credit view selection does not persist")
    cmdi = _body(source, "_render_debt_markets")
    _check('rm-finance-cmdi-card' in cmdi and 'rm-card-label' in cmdi and 'rm-card-context' in cmdi, "CMDI cards lost their readings")
    _check('source_through("New York Fed CMDI", latest_observation' in cmdi and 'rm-card-meta' not in cmdi, "CMDI source date must appear only in the heading")
    _check('rm-rail' not in cmdi and 'sparkline' not in cmdi and 'metric_card(' not in cmdi, "CMDI cards still render individual mini charts")
    for section in ("_render_capital_capacity", "_render_nfci"):
        body = _body(source, section)
        _check("render_finance_facts" in body, f"{section} lacks its readings")
    _ordered(cmdi, ["render_panel_heading(", "rm-finance-cmdi", "render_plotly_chart("])
    _check('height=310' in cmdi, "CMDI chart footprint changed")
    nfci = _body(source, "_render_nfci")
    _ordered(nfci, ["render_panel_heading(", "render_finance_facts([", "render_plotly_chart("])
    _check('height=310' in nfci and 'treatment="lead"' in nfci, "Financial conditions chart footprint changed")
    _ordered(nfci, ['("NFCI",', '("ANFCI",', '("3-month change",'])
    _check('columns=3, treatment="lead"' in nfci and '"Chicago Fed / FRED"' in nfci, "NFCI and ANFCI require distinct readings with a shared source date")
    _check('treatment="lead"' in capacity, "Funding exhibit lacks headline totals")
    _check('render_finance_section("Funding capacity"' in tab and 'render_finance_section("Borrower and lender stress"' in tab, "Finance hierarchy is missing")
    _check('"Private equity", "Cash in • cash out • ROI"' in tab
           and 'sources=pe_sources' in tab and 'retrieved = last_pe_retrieval_date()' in tab,
           "Compact PE section must use the recorded retrieval date")
    _check('10.19.2026' not in tab and 'pe_sources += f" • through {retrieved}"' in tab,
           "PE source attribution must not contain a static date")

    # Exercise the actual shared helper call, not just the Finance caller's text.
    # This catches packaging omissions where Finance passes sources= but an
    # older finance_layout.py is still installed.
    import sys
    from unittest.mock import patch
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from helpers.streamlit_runtime_stub import install_streamlit_stub

    install_streamlit_stub()
    from rendering import finance_layout

    with patch.object(finance_layout.st, "markdown", create=True) as output:
        finance_layout.render_finance_section(
            "Private equity", "Cash in • cash out • ROI",
            sources="GF Data/ACG • KPMG • Cambridge Associates",
        )
    _check(output.call_count == 1, "Sourced Finance header must render exactly once")
    sourced_html = output.call_args.args[0]
    _check('rm-finance-section--sourced' in sourced_html
           and 'rm-finance-section-sources' in sourced_html
           and 'GF Data/ACG • KPMG • Cambridge Associates' in sourced_html,
           "Sourced Finance header must place provider attribution at upper-right")
    with patch.object(finance_layout.st, "markdown", create=True) as output:
        finance_layout.render_finance_section("Funding capacity", "Operating funding")
    _check('rm-finance-section--sourced' not in output.call_args.args[0],
           "Other Finance sections must retain their existing header")
    _check('finance-section-pe-conditions' in tab and 'finance-panel-pe-conditions' in source,
           "The PE replacement must use standard bordered sections and finance panels")
    pe = _body(source, "_render_pe_conditions")
    _check('build_pe_conditions_markup(context)' in pe and 'st.markdown(markup, unsafe_allow_html=True)' in pe,
           "PE section lost its compact conditions presentation")
    _check('finance-panel-pe-conditions' in pe and 'st.container(' in pe,
           "PE presentation must stay inside its existing Finance panel")
    pe_layout = (ROOT / "rendering" / "pe_conditions_layout.py").read_text(encoding="utf-8")
    for token in ('rm-pe-journey', 'Valuations', 'Selling companies', 'Cash to investors', 'Investor returns'):
        _check(token in pe_layout, f"PE reading lost {token}")
    _check('OpenAI(' not in pe_layout and 'urlopen' not in pe_layout,
           "PE presentation must not refresh sources or call editorial AI")
    for forbidden in ('finance-section-pe-market', 'finance-section-private',
                      '_render_private_capital_realization(', '_render_pe_market_context('):
        _check(forbidden not in tab and forbidden not in source,
               f"Old PE section was retained: {forbidden}")
    _check('treatment="strain"' in _body(source, "_render_financial_condition_summary"), "Strain readings lost their three reading treatment")
    detail = _body(source, "_render_financial_condition_detail")
    _ordered(detail, ['render_panel_heading(', 'key="finance-view-stress-detail"', 'render_plotly_chart('])
    _check('st.session_state.get("finance-view-stress-detail", "Borrower")' in tab, "Stress selection must follow the chart toggle")
    _check('None, context' in _body(source, "_render_financial_condition_summary"), "Strain readings repeat the source footer")
    _check('source_through("ICE BofA / FRED"' in (ROOT / "rendering" / "credit_spreads.py").read_text(encoding="utf-8"), "Spread source date is missing from heading")
    _check('render_evidence_gateway("finance")' in tab, "Finance must use the shared Evidence gateway")
    _check('"Inspect spread records"' not in source and '"Inspect lender records"' not in source, "Reference record actions remain on Finance")
    _check("finance-lender-evidence" not in source, "Lender record button remains in the chart")
    for key in ("funding", "disclosures", "pe-conditions", "credit", "stress"):
        _check(f'with st.container(border=True, key="finance-section-{key}"):' in tab, f"Finance {key} section lacks its border")
    spreads = (ROOT / "rendering" / "credit_spreads.py").read_text(encoding="utf-8")
    _check('columns=3, treatment="lead"' in spreads and "border=True" not in spreads, "Credit spreads lost its lead readings")
    _check('height=310' in spreads, "Spread chart differs from the credit-view footprint")
    _ordered(spreads, ['render_panel_heading(', 'render_finance_facts([', 'render_plotly_chart('])
    _check('None)' in spreads, "Spread readings repeat the source footer")
    _check('rm-finance-attribution-links' in spreads and 'rm-finance-attribution-credit' in spreads, "Spread attribution is not on one line")
    _check('finance-spread-evidence' not in spreads, "Spread record button remains beside the chart")

    theme = (ROOT / "rendering" / "theme.css").read_text(encoding="utf-8")
    _check('.rm-finance-facts::before' in theme and '.rm-finance-cmdi {' in theme, "Finance data rows lack a continuous purple rule")
    _check('border-top: 3px solid #a78bfa !important;' not in theme[theme.index('div[class*="st-key-finance-section-"]'):theme.index('.rm-finance-section-copy h2')], "Finance sections still have purple top borders")
    markup = (ROOT / "rendering" / "read_markup.py").read_text(encoding="utf-8")
    _check("text-align: justify;" in theme and "text-align-last: left;" in theme, "Read paragraph alignment changed")
    _check(".rm-finance-facts--lead" in theme and ".rm-finance-section" in theme, "Finance editorial hierarchy lacks layout rules")
    _check(".rm-finance-facts--private" in theme and "min-height: 430px" in theme, "Private-fund stack height differs from chart")
    _check('grid-template-columns: repeat(3, minmax(0, 1fr));' in theme and '.rm-finance-facts--strain' in theme, "Stress readings must be horizontal")
    finance_theme = theme[theme.index('/* Finance keeps one detail chart'):theme.index('.rm-evidence-gateway {', theme.index('/* Finance keeps one detail chart'))]
    _check('border-top: 3px solid #a78bfa' in finance_theme and 'border-top: 2px solid rgba(96, 165, 250' not in finance_theme, "Finance boxes must use a purple top rule")
    _check(".rm-finance-section-number" not in theme, "Finance section numbers remain")
    _check('.rm-pe-journey {' in theme and 'grid-template-columns: repeat(2, minmax(0, 1fr));' in theme,
           "PE layout lost its two-by-two equal-width cards")
    _check('@media (max-width: 850px)' in theme and '.rm-pe-journey {grid-template-columns: 1fr;}' in theme,
           "PE cards must stack without overflow on narrow screens")
    _check('html.escape(paragraph)' in markup, "Read output lost text escaping")

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
