from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from loaders.credit_conditions_loader import load_credit_conditions, spread_snapshot
from rendering.charts_common import COLORS, _base_layout
from rendering.components import fmt_number, render_panel_heading
from rendering.finance_layout import render_finance_facts
from rendering.observation_meta import source_through
from rendering.visual_system import render_plotly_chart


def _weekly_momentum(history: pd.DataFrame, *, column: str = "Value") -> str:
    """Compare with the last available reading at least seven days earlier."""
    if history is None or history.empty or column not in history:
        return "Weekly comparison pending"
    frame = history.dropna(subset=["Date", column]).sort_values("Date")
    if len(frame) < 2:
        return "Weekly comparison pending"
    current = frame.iloc[-1]
    prior = frame.loc[frame["Date"].le(current["Date"] - pd.Timedelta(days=7))]
    if prior.empty:
        return "Weekly comparison pending"
    earlier = prior.iloc[-1]
    change = float(current[column] - earlier[column])
    arrow = "↗" if change > 0 else "↘" if change < 0 else "→"
    amount = f"{change:+.0f}" if change else "0"
    compared = pd.Timestamp(earlier["Date"])
    return f"{arrow} {amount} bp since {compared:%b} {compared.day}"


def render_credit_spreads():
    # All modes, including the public Reader, display retained observations.
    data = load_credit_conditions()
    snapshot = spread_snapshot(data)
    with st.container(key="finance-panel-spreads"):
        dates = [snapshot[label]["date"] for label in ("IG", "HY") if snapshot[label]["date"] is not None]
        render_panel_heading("IG and HY option-adjusted spreads", source_through("ICE BofA / FRED", max(dates) if dates else None))
        paired = snapshot["IG"]["history"].merge(snapshot["HY"]["history"], on="Date", suffixes=("_IG", "_HY"))
        paired["Gap"] = paired["Value_HY"] - paired["Value_IG"]
        render_finance_facts([
            ("Investment Grade OAS", fmt_number(snapshot["IG"]["value"], 0, suffix=" bp"), None, _weekly_momentum(snapshot["IG"]["history"])),
            ("High Yield OAS", fmt_number(snapshot["HY"]["value"], 0, suffix=" bp"), None, _weekly_momentum(snapshot["HY"]["history"])),
            ("HY − IG spread", fmt_number(snapshot["gap"]["value"], 0, suffix=" bp"), None, _weekly_momentum(paired, column="Gap")),
        ], columns=3, treatment="lead")
        if all(snapshot[label]["history"].empty for label in ("IG", "HY")):
            st.caption("Spreads will appear after the next owner or scheduled FRED refresh.")
        else:
            horizon = st.radio("Spread history", ["3M", "1Y", "3Y", "All retained"], index=1, horizontal=True, key="finance-oas-horizon")
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
            render_plotly_chart(_base_layout(figure, height=310, legend=True), width="stretch", key="finance-oas-history")
        st.markdown(
            '<div class="rm-finance-attribution">'
            '<div class="rm-finance-attribution-links">'
            '<a href="https://fred.stlouisfed.org/series/BAMLC0A0CM">IG series</a>'
            '<a href="https://fred.stlouisfed.org/series/BAMLH0A0HYM2">HY series</a>'
            '</div>'
            '<div class="rm-finance-attribution-credit">'
            'Source: ICE Data Indices, LLC, via Federal Reserve Bank of St. Louis. '
            'Copyright © ICE Data Indices.'
            '</div></div>',
            unsafe_allow_html=True,
        )
