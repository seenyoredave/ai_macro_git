from __future__ import annotations

from pathlib import Path

import streamlit as st

_THEME_PATH = Path(__file__).with_name("theme.css")

def inject_research_theme() -> None:
    st.markdown(f"<style>{_THEME_PATH.read_text()}</style>", unsafe_allow_html=True)
