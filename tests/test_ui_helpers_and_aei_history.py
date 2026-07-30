from pathlib import Path

import pandas as pd

from analytics.macro_dataframe import _build_version_aware_aei_trend
from config.metric_definitions import metric_help


def test_aei_history_starts_on_requested_date_without_revision_marker():
    history = pd.DataFrame(
        {
            "Date": ["2026-06-01", "2026-06-14", "2026-06-20", "2026-07-01"],
            "AI Equity Index": [40.0, 42.0, 44.0, 50.0],
            "AEI Version": ["2.0", "2.0", "2.0", "3.1"],
        }
    )

    trend = _build_version_aware_aei_trend(history, current_value=52.0)

    assert trend["history"]["Date"].min() == pd.Timestamp("2026-06-14")
    assert trend["revision_date"] is None
    assert trend["revision_label"] is None
    assert trend["current"] == 52.0
    assert "AEI 2.0" in trend["history_note"]
    assert "AEI 3.1" in trend["history_note"]


def test_metric_card_and_chart_helpers_are_individually_defined():
    helper_keys = [
        "Speculation Gap",
        "Economic Validation Gap",
        "AI-Industrial Growth Gap",
        "Power Capacity Gap",
        "Most Crowded",
        "Fastest Mover",
        "Biggest Risk",
        "Earnings Support",
        "Speculative Load",
    ]

    for key in helper_keys:
        helper = metric_help(key)
        assert helper != "Definition unavailable."
        assert "How to read it" in helper


def test_section_titles_have_no_helpers_and_chart_subtitles_do():
    dashboard_source = (
        Path(__file__).resolve().parents[1] / "helpers" / "macro_dashboard.py"
    ).read_text()

    assert 'st.subheader("AI Economy Snapshot", help=' not in dashboard_source
    assert 'st.subheader("Gap Scores", help=' not in dashboard_source
    assert 'st.subheader("Current Sector Assessment", help=' not in dashboard_source

    assert (
        'st.subheader("Earnings Support", '
        'help=metric_help("Earnings Support"))'
        in dashboard_source
    )
    assert (
        'st.subheader("Speculative Load", '
        'help=metric_help("Speculative Load"))'
        in dashboard_source
    )


def test_metric_registry_excludes_broad_section_titles():
    root = Path(__file__).resolve().parents[1]
    definitions = (root / "config" / "metric_definitions.py").read_text()
    renderer = (root / "research_overlay" / "renderers.py").read_text()

    for title in (
        "AI Economy Snapshot",
        "Gap Scores",
        "Borrower Financial Condition",
        "Current Sector Assessment",
    ):
        assert f'    "{title}":' not in definitions

    registry_block = renderer.split("TAB_METRIC_REGISTRIES =", 1)[1].split("def _render_tab_metric_registry", 1)[0]
    for title in (
        "AI Economy Snapshot",
        "Gap Scores",
        "Borrower Financial Condition",
        "Current Sector Assessment",
    ):
        assert f'        "{title}",' not in registry_block

    assert '        "Lender Strain",' in registry_block
    assert 'render_section("Credit Conditions")' in renderer
    assert 'title="Borrower Strain"' in renderer
    assert 'title="Lender Strain"' in renderer
