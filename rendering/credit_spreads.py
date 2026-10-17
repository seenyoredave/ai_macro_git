from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from loaders.credit_conditions_loader import load_credit_conditions, spread_snapshot
from rendering.charts_common import COLORS, _base_layout
from rendering.components import fmt_number, render_panel_heading, render_statline
from rendering.evidence_gateway import route_to_evidence
from rendering.observation_meta import source_through
from rendering.visual_system import render_plotly_chart


def render_credit_spreads():
    # All modes, including the public Reader, display retained observations.
    data = load_credit_conditions()
    snapshot = spread_snapshot(data)
    with st.container(border=True):
        render_panel_heading("Credit spreads", "ICE BofA via FRED")
        render_statline([
            ("IG OAS", fmt_number(snapshot["IG"]["value"], 0, suffix=" bp"), source_through("ICE BofA / FRED", snapshot["IG"]["date"])),
            ("HY OAS", fmt_number(snapshot["HY"]["value"], 0, suffix=" bp"), source_through("ICE BofA / FRED", snapshot["HY"]["date"])),
            ("HY − IG", fmt_number(snapshot["gap"]["value"], 0, suffix=" bp"), source_through("ICE BofA / FRED", snapshot["gap"]["date"])),
        ], key_prefix="finance-oas")
        if all(snapshot[label]["history"].empty for label in ("IG", "HY")):
            st.caption("Spreads will appear after the next owner or scheduled FRED refresh.")
        else:
            horizon = st.radio("Spread history", ["3M", "1Y", "3Y", "All retained"], index=1, horizontal=True, key="finance-oas-horizon")
            dates = [snapshot[label]["date"] for label in ("IG", "HY") if snapshot[label]["date"] is not None]
            months = {"3M": 3, "1Y": 12, "3Y": 36}.get(horizon)
            cutoff = max(dates) - pd.DateOffset(months=months) if months else None
            figure = go.Figure()
            for label, color in (("IG", COLORS["blue"]), ("HY", COLORS["violet"])):
                frame = snapshot[label]["history"]
                if cutoff is not None:
                    frame = frame[frame["Date"].ge(cutoff)]
                if not frame.empty:
                    figure.add_trace(go.Scatter(x=frame["Date"], y=frame["Value"], name=f"{label} OAS", mode="lines", connectgaps=False,
                                               line={"color": color, "width": 2.4}, hovertemplate="%{x|%Y-%m-%d}<br>%{y:.0f} bp<extra>%{fullData.name}</extra>"))
            figure.update_yaxes(title="Option-adjusted spread (bp)")
            render_plotly_chart(_base_layout(figure, height=300, legend=True), width="stretch", key="finance-oas-history")
        st.caption("Source: ICE Data Indices, LLC, via Federal Reserve Bank of St. Louis. Copyright © ICE Data Indices.")
        st.markdown("[IG series](https://fred.stlouisfed.org/series/BAMLC0A0CM) · [HY series](https://fred.stlouisfed.org/series/BAMLH0A0HYM2)")
        st.button("Inspect spread records", key="finance-spread-evidence", on_click=route_to_evidence,
                  args=("finance", "Credit spread changes"))
