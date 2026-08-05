from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.charts_adaptation import adaptation_history, adaptation_sector_bars
from rendering.common import _render_tab_metric_registry
from rendering.components import fmt_date, fmt_number, render_domain_read, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header

def _adaptation_source_rows(adaptation_data):
    national = (adaptation_data or {}).get("national_history")
    rows = []
    if isinstance(national, pd.DataFrame) and not national.empty:
        latest = national.sort_values("Date").iloc[-1]
        for name, display_name in [
            ("Current AI Use", "Current AI Use"),
            ("Expected AI Use", "Expected AI Use"),
            ("Expected Adoption Gap", "Expected Adoption Gap"),
        ]:
            rows.append({
                "Series": display_name,
                "Reading": fmt_number(latest.get(name), 1, suffix=" percentage points" if name == "Expected Adoption Gap" else "%"),
                "Observation Date": fmt_date(latest.get("Date")),
                "Source": "U.S. Census BTOS",
            })
    return pd.DataFrame(rows)

def _render_adaptation_summary(adaptation_data):
    current = pd.to_numeric((adaptation_data or {}).get("current_use"), errors="coerce")
    expected = pd.to_numeric((adaptation_data or {}).get("expected_use"), errors="coerce")
    expected_gap = pd.to_numeric((adaptation_data or {}).get("expected_adoption_gap"), errors="coerce")
    annual = pd.to_numeric((adaptation_data or {}).get("annual_change"), errors="coerce")
    render_statline(
        [
            ("Current business use", fmt_number(current, 1, suffix="%"), "used AI in any business function"),
            ("Expected use", fmt_number(expected, 1, suffix="%"), "expected within six months"),
            ("Expected adoption gap", fmt_number(expected_gap, 1, signed=True, suffix=" pp"), "expected minus current use"),
            ("12-month change", fmt_number(annual, 1, signed=True, suffix=" pp"), fmt_date((adaptation_data or {}).get("snapshot_date"))),
        ],
        key_prefix="adaptation-summary",
    )

def render_adaptation_tab(adaptation_data, tab_read=None):
    render_tab_header(
        "Adaptation",
        "Business AI use and diffusion across U.S. industries.",
        "U.S. Census BTOS",
    )
    render_line_break()
    _render_tab_metric_registry("adaptation")
    render_domain_read(tab_read, label="Adaptation Read", accent="green")
    render_section("Reach", "Observed business use and expected use within the next six months.")
    _render_adaptation_summary(adaptation_data)
    with st.container(border=True):
        render_panel_heading("AI use trajectory", "Census BTOS / employer businesses / 95% confidence intervals")
        st.plotly_chart(
            adaptation_history((adaptation_data or {}).get("national_history")),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="adaptation-national-history",
        )

    render_section("Breadth", "Current and expected use across major industries.")
    with st.container(border=True):
        render_panel_heading("Sector diffusion", "Latest published observation / 95% confidence intervals")
        st.plotly_chart(
            adaptation_sector_bars((adaptation_data or {}).get("sector_snapshot")),
            width="stretch",
            config={"displayModeBar": True, "responsive": True},
            key="adaptation-sector-breadth",
        )

