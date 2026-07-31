from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_research_overlay_keeps_seven_primary_tabs():
    source = (ROOT / "ai_macro.py").read_text()
    assert '["AI MACRO", "MARKET", "FINANCE", "INFRASTRUCTURE", "ENERGY", "ADAPTATION", "EVIDENCE"]' in source


def test_ai_macro_is_the_only_streamlit_entrypoint():
    assert (ROOT / "ai_macro.py").is_file()
    assert not (ROOT / "ai_macro_research_overlay.py").exists()
    source = (ROOT / "ai_macro.py").read_text()
    assert "Primary Streamlit entry point" in source
    assert "Alternative presentation layer" not in source


def test_research_overlay_retains_existing_products():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    required_products = [
        "AI Equity Index",
        "AI Development Intensity",
        "Power Stress Index",
        "Power Capacity Gap",
        "Sector Basket Concentration",
        "Speculation Gap",
        "Economic Validation Gap",
        "AI–Industrial Growth Gap",
        "Internal Funding Coverage",
        "Cash Reserve Runway",
        "Debt Financing Pulse",
        "Forward Commitment Load",
        "Borrower Strain",
        "Lender Strain",
        "Corporate Bond Market Distress",
        "Investment-Grade Bond Distress",
        "High-Yield Bond Distress",
        "Financial Conditions Confirmation",
        "Trading Pressure",
        "Sector Movement",
        "Risk Breadth",
        "Loss-Making EV Share",
        "Commercial Electricity Price",
        "Industrial Electricity Price",
    ]
    for product in required_products:
        assert product in source


def test_statline_uses_native_streamlit_components():
    source = (ROOT / "research_overlay" / "components.py").read_text()
    statline = source.split("def render_statline", 1)[1].split("def render_panel_heading", 1)[0]
    assert "st.columns" in statline
    assert "st.container(key=key)" in statline
    assert "key_prefix: str" in statline
    assert "inspect.currentframe" not in statline
    assert "caller.f_code.co_filename" not in statline
    assert "hashlib.sha1" not in statline
    assert 'key = f"statline-{namespace}-{index}"' in statline
    assert "rm-statline" not in statline


def test_plotly_overlay_does_not_serialize_empty_titles():
    source = (ROOT / "research_overlay" / "visuals.py").read_text()
    assert "fig.update_layout(title=None)" not in source
    assert 'fig.layout.pop("title", None)' in source


def test_sector_tab_revision_is_structurally_present():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    assert '"Most Concentrated"' in source
    assert '"Most Profitable"' not in source
    assert '"Earnings Support"' in source
    assert '"Speculative Load"' in source
    assert 'with st.expander("Sector matrix", expanded=False)' in source
    assert 'Sector equity conditions, trading pressure, factor structure, and constituent fundamentals.' in source
    assert source.index('render_ticker_controls(selected)') < source.index('with st.expander("Factor and pressure data", expanded=False)')


def test_company_table_places_fundamentals_before_beta_and_weights():
    company_block = (ROOT / "research_overlay" / "tables.py").read_text()
    expected_order = [
        '"1Y Return"',
        '"Market Cap"',
        '"Revenue"',
        '"Revenue Growth"',
        '"CapEx"',
        '"CapEx Growth"',
        '"Beta"',
        '"Basket Tier"',
        '"Basket Weight"',
        '"AI Weight"',
    ]
    positions = [company_block.index(item) for item in expected_order]
    assert positions == sorted(positions)


def test_sector_valuation_separates_profitable_multiple_from_loss_making_ev_share():
    valuation_source = (ROOT / "analytics" / "valuation.py").read_text()
    engine_source = (ROOT / "analytics" / "sector_engine.py").read_text()
    assert "aggregate_profitable_forward_ev_ebit" in valuation_source
    assert "profitable_ev / profitable_ebit" in valuation_source
    assert "loss_making_ev / valid_ev" in valuation_source
    assert "aggregate_profitable_forward_ev_ebit" in engine_source
    assert '"Loss-Making EV Share"' in engine_source


def test_sector_evidence_includes_new_analytical_products():
    source = (ROOT / "config" / "metric_definitions.py").read_text()
    assert '"Earnings Support"' in source
    assert '"Speculative Load"' in source
    assert '"Forward EV/EBIT"' in source
    assert '"Loss-Making EV Share"' in source


def test_all_statline_calls_use_explicit_namespaces():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    assert 'key_prefix="macro-current-divergence-primary"' in source
    assert 'key_prefix="macro-current-divergence-context"' in source
    assert 'key_prefix="finance-funding-cohort-totals"' in source
    assert 'key_prefix=f"finance-condition-' in source
    assert "title.lower().replace(' ', '-')" in source
    assert 'key_prefix="finance-nfci-confirmation"' in source
    assert 'key_prefix="sector-dossier-summary-primary"' in source
    assert 'key_prefix="sector-dossier-summary-structure"' in source
    assert 'key_prefix="sector-cross-state"' in source


def test_finance_tab_cleanup_contract_is_present():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    theme = (ROOT / "research_overlay" / "theme.py").read_text()
    assert 'render_section("Credit Conditions")' in renderer
    assert 'render_section("System confirmation"' not in renderer
    assert '("Source", "Chicago Fed NFCI", "updated Wednesday at 8:30am ET")' in renderer
    assert 'funding_history(history, years=10)' in renderer
    assert 'years=10' in renderer
    assert '.modebar {' not in theme
    assert 'stElementToolbar' not in theme
    assert 'Plot controls are intentionally suppressed' not in theme


def test_finance_plot_boxes_keep_plotly_controls_but_drop_redundant_header_meta():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    finance_block = source.split("def _render_funding_section", 1)[1].split("def _assessment_stats", 1)[0]
    assert 'config={"displayModeBar": True, "responsive": True}' in finance_block
    assert 'render_panel_heading("Funding diagnostics history")' in finance_block
    assert 'render_panel_heading(title)' in finance_block
    assert 'render_panel_heading("Financial Conditions Confirmation")' in finance_block
    assert "velocity {" not in finance_block
    assert "Chicago Fed NFCI · independent confirmation" not in finance_block


def test_nfci_and_anfci_share_one_plot_without_promoting_anfci_to_a_card():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    visuals = (ROOT / "research_overlay" / "visuals.py").read_text()
    assert 'financial_conditions_history(snapshot.get("history"), height=275)' in source
    assert '("ANFCI",' not in source
    assert '("NFCI/ANFCI", paired_value' in source
    assert 'name="NFCI"' in visuals
    assert 'name="ANFCI"' in visuals
    assert '"dash": "dash"' in visuals


def test_ai_macro_cleanup_contract_is_present():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    assert '"Overview of the AI economy using novel metrics to track the evolution."' in source
    assert 'render_section("Gap Measures", "Approximations of divergence from broader economic trends.")' in source
    assert '"Expectations and development"' not in source
    macro_block = source.split("def render_macro_tab", 1)[1].split("def _funding_specs", 1)[0]
    assert 'dual_history(' not in macro_block
    assert 'render_section("Component evidence", "Structural decomposition of top-level AI economy metrics.")' in source
    assert 'chart_col, measures_col = st.columns([1.05, 1.25])' in source
    assert 'state_head_html = (' in source
    assert 'st.markdown(state_head_html, unsafe_allow_html=True)' in source
    assert 'f"""\n            <div class="rm-state-head">' not in source


def test_sector_concentration_is_rehomed_and_propagated():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    hhi_engine = (ROOT / "analytics" / "hhi_engine.py").read_text()
    assert '"Sector Basket Concentration"' in renderer
    assert '"Most Concentrated"' in renderer
    assert '"Basket Concentration"' in renderer
    assert '"**Basket-concentration contributors**"' in renderer
    assert 'sector_hhi_component_breakdown(df, top_n=8)' in renderer
    assert 'def adjusted_hhi' in hhi_engine
    assert 'def sector_basket_concentration' in hhi_engine
    assert 'def sector_hhi_component_breakdown' in hhi_engine


def test_platform_title_replaces_station_title():
    app = (ROOT / "ai_macro.py").read_text()
    assert 'AI Economic Research Platform' in app
    assert 'AI Economic Research Station' not in app


def test_power_capacity_gap_is_the_fourth_macro_gap_without_replacing_power_stress():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    engine = (ROOT / "analytics" / "power_capacity_gap.py").read_text()
    definitions = (ROOT / "config" / "metric_definitions.py").read_text()
    assert '"Power Capacity Gap": _value(regime_metrics, "Power Capacity Gap")' in renderer
    assert '("Power Capacity", fmt_number(gaps["Power Capacity Gap"]' in renderer
    assert '"Power Stress Index"' in renderer
    assert 'DEPLOYMENT_PRESSURE_WEIGHTS' in engine
    assert 'POWER_RESPONSE_WEIGHTS' in engine
    assert 'national response proxy' in definitions


def test_power_capacity_gap_inputs_have_persisted_fallbacks():
    construction = (ROOT / "loaders" / "construction_loader.py").read_text()
    fred = (ROOT / "loaders" / "fred_loader.py").read_text()
    assert "Census Local History" in construction
    assert "_load_local_construction_history" in construction
    assert "_rows_to_fred_payload" in fred
    assert '_rows_to_fred_payload(current_week, "FRED Archive")' in fred


def test_gap_scale_note_is_attached_to_chart_column():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    assert 'render_panel_heading("Current divergence")' in renderer
    assert 'render_panel_heading("", "Centered -100 to +100")' in renderer


def test_developer_tools_header_includes_right_aligned_version_and_divider():
    app = (ROOT / "ai_macro.py").read_text()
    theme = (ROOT / "research_overlay" / "theme.py").read_text()
    assert 'APP_VERSION = "v4.14-dev"' in app
    assert 'class="rm-developer-tools-header"' in app
    assert 'class="rm-developer-tools-version"' in app
    assert 'class="rm-developer-tools-divider"' in app
    assert 'justify-content: space-between' in theme
    assert '.rm-developer-tools-divider' in theme
    assert 'border-top: 1px solid var(--rm-border)' in theme


def test_research_ui_cleanup_is_structurally_present():
    app = (ROOT / "ai_macro.py").read_text()
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()

    assert 'dashboard_source_status' not in app
    assert '("Run",' not in app
    assert '("Status",' not in app
    assert '("Universe",' not in app
    assert '("Build", APP_VERSION)' not in app
    assert 'market_universe_summary = {' in app
    assert 'render_masthead(' in app

    assert '"Top five companies plus the remainder"' not in renderer
    assert '"Deployment pressure:' not in renderer
    assert '"Raw AI HHI:' not in renderer

    assert '("Current", fmt_number(value, 1, signed=True), None)' in renderer
    assert '("Velocity", fmt_number((trend or {}).get("velocity"), 2, signed=True), None)' in renderer
    assert '("Acceleration", fmt_number((trend or {}).get("acceleration"), 2, signed=True), None)' in renderer
    assert 'source_stat,' in renderer

    for tab in ("macro", "finance", "energy", "market"):
        assert f'_render_tab_metric_registry("{tab}")' in renderer
    assert '_render_tab_metric_registry("evidence")' not in renderer




def test_purpose_statement_matches_current_scope():
    definitions = (ROOT / "config" / "metric_definitions.py").read_text()
    assert "AI Macro tracks the development of AI as an economic instrument and its footprint in the US economy." in definitions
    assert "where this growth occurs" in definitions
    assert "adaptation of businesses, workers, and institutions to AI integration" in definitions
    assert "capital committed, capacity built, adoption achieved, and value realized" in definitions
    assert "market enthusiasm" not in definitions
    assert "market corrections" not in definitions

def test_evidence_purpose_and_source_data_are_rendered_cleanly():
    source = (ROOT / "research_overlay" / "renderers.py").read_text()
    evidence = source.split("def render_evidence_tab", 1)[1].split("def render_research_dashboard", 1)[0]
    assert 'render_section("Purpose Statement", first=True)' in evidence
    assert 'render_definition(METRIC_DEFINITIONS["Purpose Statement"])' in evidence
    assert '_render_tab_metric_registry("evidence")' not in evidence
    assert 'render_section("Source Data")' in evidence
    assert 'render_section("Source observations"' not in evidence
    assert '"evidence": [' not in source


def test_deliberate_line_breaks_separate_dashboard_layers():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    components = (ROOT / "research_overlay" / "components.py").read_text()
    assert 'def render_line_break()' in components
    assert 'st.markdown("<br>", unsafe_allow_html=True)' in components

    for tab in ("macro", "finance", "energy", "market"):
        expected = (
            'render_line_break()\n'
            f'    _render_tab_metric_registry("{tab}")'
        )
        assert expected in renderer

    finance = renderer.split("def render_finance_tab", 1)[1].split("def _assessment_stats", 1)[0]
    assert 'render_section("Credit Conditions")\n    render_line_break()' in finance

    evidence = renderer.split("def render_evidence_tab", 1)[1].split("def render_research_dashboard", 1)[0]
    assert evidence.index('render_tab_header(') < evidence.index('render_line_break()')
    assert evidence.index('render_line_break()') < evidence.index('render_section("Purpose Statement", first=True)')
    purpose_end = evidence.index('render_definition(METRIC_DEFINITIONS["Purpose Statement"])')
    second_break = evidence.index('render_line_break()', evidence.index('render_line_break()') + 1)
    assert purpose_end < second_break < evidence.index('render_section("Source Data")')
    assert evidence.index('render_section("Source Data")') < evidence.index('render_macro_data(fred_data)')
    assert 'render_section("Source Data",' not in evidence


def test_first_content_section_after_each_metric_registry_uses_standard_divider():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()

    expected = (
        ('_render_tab_metric_registry("macro")', 'render_section("Regime board", "Current readings with retained histories and source state.")'),
        ('_render_tab_metric_registry("finance")', 'render_section("Funding profile", "Current funding ratios and retained cohort history.")'),
        ('_render_tab_metric_registry("energy")', 'render_section("Energy supply", "Current fuel prices and production momentum.")'),
        ('_render_tab_metric_registry("market")', 'render_section("Cross-sector state", "Current leaders in market behavior.")'),
    )
    for registry_call, section_call in expected:
        registry_index = renderer.index(registry_call)
        section_index = renderer.index(section_call, registry_index)
        between = renderer[registry_index:section_index]
        assert "render_line_break()" not in between
        assert "first=True" not in section_call

    assert '.rm-section {' in (ROOT / "research_overlay" / "theme.py").read_text()
    assert 'border-top: 1px solid var(--rm-border);' in (ROOT / "research_overlay" / "theme.py").read_text()


def test_most_concentrated_card_is_compact_and_has_no_helper_tooltip():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    assessment = renderer.split("def _assessment_stats", 1)[1].split("def _rank_text", 1)[0]
    assert "Adjusted HHI compares each sector basket" not in assessment
    assert "effective firms" not in assessment
    assert "Sector Concentration Company Count" in assessment
    assert 'f"Adjusted HHI {fmt_number' in assessment


def test_data_center_registry_panel_title_is_direct():
    renderer = (ROOT / "research_overlay" / "renderers.py").read_text()
    assert 'render_panel_heading("Data Center Registry"' in renderer
    assert 'render_panel_heading("Evidence-graded data-center registry"' not in renderer
