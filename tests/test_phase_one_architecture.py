from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_primary_navigation_uses_four_research_tabs():
    source = (ROOT / "ai_macro.py").read_text()
    assert '["AI MACRO", "FINANCE", "SECTORS", "EVIDENCE"]' in source


def test_sector_detail_is_selected_inside_consolidated_tab():
    source = (ROOT / "helpers" / "render_sectors.py").read_text()
    assert 'st.selectbox(' in source
    assert '"Select sector to evaluate"' in source
    assert 'render_sector_dashboard(' in source
    assert 'render_sector_table(macro_df, use_expander=False)' in source


def test_financial_condition_products_remain_distinct():
    source = (ROOT / "helpers" / "macro_dashboard.py").read_text()
    assert '_render_borrower_financial_condition(' in source
    assert '_render_intermediation_strain(' in source
    assert '_render_financial_conditions_confirmation(' in source
