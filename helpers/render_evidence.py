import streamlit as st

from config.metric_definitions import METRIC_DEFINITIONS
from helpers.macro_dashboard import render_edgar_data, render_macro_data


def render_evidence_dashboard(fred_data=None, sector_data=None):
    """Render methodology, definitions, and source-data evidence."""
    st.title("Evidence")
    st.caption("Purpose • metric definitions • source data")
    st.markdown("---")

    st.subheader("Purpose Statement")
    st.write(METRIC_DEFINITIONS["Purpose Statement"])
    st.markdown("---")

    st.subheader("Metric Definitions")
    definition_names = [
        name for name in METRIC_DEFINITIONS
        if name != "Purpose Statement"
    ]
    selected_definition = st.selectbox(
        "Select metric or analytical product",
        definition_names,
        key="evidence_metric_definition",
    )
    st.markdown(METRIC_DEFINITIONS[selected_definition])
    st.markdown("---")

    st.subheader("Source Data")
    render_macro_data(fred_data)
    render_edgar_data(sector_data)
