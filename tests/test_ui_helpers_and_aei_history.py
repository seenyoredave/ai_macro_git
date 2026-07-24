from pathlib import Path

import pandas as pd

from analytics.macro_dataframe import _build_version_aware_aei_trend
from config.metric_definitions import metric_help


def test_aei_history_starts_on_requested_date_without_revision_marker():
    history = pd.DataFrame(
        {
            "Date": ["2026-06-01", "2026-06-14", "2026-06-20", "2026-07-01"],
            "AI Equity Index": [40.0, 42.0, 44.0, 50.0],
            "AEI Version": ["2.0", "2.0", "2.0", "3.0"],
        }
    )

    trend = _build_version_aware_aei_trend(history, current_value=52.0)

    assert trend["history"]["Date"].min() == pd.Timestamp("2026-06-14")
    assert trend["revision_date"] is None
    assert trend["revision_label"] is None
    assert trend["current"] == 52.0
    assert "AEI 2.0" in trend["history_note"]
    assert "AEI 3.0" in trend["history_note"]


def test_metric_card_and_chart_helpers_are_individually_defined():
    helper_keys = [
        "Speculation Gap",
        "Economic Validation Gap",
        "AI-Industrial Growth Gap",
        "Most Crowded",
        "Fastest Mover",
        "Biggest Risk",
        "AI Sector Positioning Map",
        "AI Sector Rotation Matrix",
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
        'st.subheader("AI Sector Positioning Map", '
        'help=metric_help("AI Sector Positioning Map"))'
        in dashboard_source
    )
    assert (
        'st.subheader("AI Sector Rotation Matrix", '
        'help=metric_help("AI Sector Rotation Matrix"))'
        in dashboard_source
    )
