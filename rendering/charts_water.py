from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout

def water_withdrawal_components(category_frame, *, height=390):
    frame = category_frame.copy() if isinstance(category_frame, pd.DataFrame) else pd.DataFrame()
    label_map = {
        "public_supply": "Public supply",
        "domestic_self_supply": "Domestic self-supply",
        "industrial_self_supply": "Industrial self-supply",
        "irrigation": "Irrigation",
        "livestock": "Livestock",
        "aquaculture": "Aquaculture",
        "mining": "Mining",
        "thermoelectric_power": "Thermoelectric power",
    }
    components = [
        ("Fresh Groundwater Mgal/d", "Fresh groundwater", COLORS["blue_deep"]),
        ("Fresh Surface Water Mgal/d", "Fresh surface water", COLORS["blue"]),
        ("Saline Groundwater Mgal/d", "Saline groundwater", COLORS["violet_deep"]),
        ("Saline Surface Water Mgal/d", "Saline surface water", COLORS["violet"]),
    ]
    fig = go.Figure()
    if not frame.empty and "Use Category" in frame.columns:
        frame = frame.copy()
        frame["Display"] = frame["Use Category"].map(label_map).fillna(frame["Use Category"])
        frame["Total Withdrawal Mgal/d"] = pd.to_numeric(frame.get("Total Withdrawal Mgal/d"), errors="coerce")
        frame = frame.sort_values("Total Withdrawal Mgal/d", ascending=True, kind="stable")
        for column, label, color in components:
            values = pd.to_numeric(frame.get(column), errors="coerce").fillna(0)
            fig.add_trace(go.Bar(
                x=values / 1000.0,
                y=frame["Display"],
                orientation="h",
                name=label,
                marker_color=color,
                customdata=values,
                hovertemplate=f"%{{y}}<br>{label}: %{{customdata:,.1f}} Mgal/d<extra></extra>",
            ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Billion gallons per day")
    fig.update_yaxes(title="")
    return _base_layout(fig, height=height, legend=True, margin=dict(l=158, r=18, t=30, b=48))

def thermoelectric_water_groups(group_frame, *, metric="Withdrawal", height=340):
    frame = group_frame.copy() if isinstance(group_frame, pd.DataFrame) else pd.DataFrame()
    column = f"{metric} Bgal/day"
    fig = go.Figure()
    if not frame.empty and {"Group", column}.issubset(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=[column]).sort_values(column, ascending=True, kind="stable")
        fig.add_trace(go.Bar(
            x=frame[column],
            y=frame["Group"].astype(str),
            orientation="h",
            marker_color=COLORS["blue"] if metric == "Withdrawal" else COLORS["violet"],
            customdata=np.stack([
                pd.to_numeric(frame.get("Plants"), errors="coerce").fillna(0),
                pd.to_numeric(frame.get("Records"), errors="coerce").fillna(0),
            ], axis=-1),
            hovertemplate=(
                f"%{{y}}<br>{metric}: %{{x:,.3f}} Bgal/day equivalent"
                "<br>Plants: %{customdata[0]:,.0f}<br>Records: %{customdata[1]:,.0f}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Billion gallons per day equivalent")
    fig.update_yaxes(title="")
    return _base_layout(fig, height=height, margin=dict(l=125, r=18, t=18, b=48))
