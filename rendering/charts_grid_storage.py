from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom


def grid_construction_history(history: pd.DataFrame | None, *, height: int = 410):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", "Electric Power Construction"])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        clean["Electric Power Construction"] = pd.to_numeric(clean.get("Electric Power Construction"), errors="coerce")
        clean = clean.loc[clean["Observation Date"] >= pd.Timestamp("2020-01-01")].dropna(subset=["Observation Date", "Electric Power Construction"]).sort_values("Observation Date")
    fig = go.Figure(go.Scatter(
        x=clean.get("Observation Date", []), y=clean.get("Electric Power Construction", pd.Series(dtype=float)) / 1000.0,
        mode="lines", name="Electric power construction", line={"width": 2.7, "color": COLORS["blue"]},
        hovertemplate="%{x|%Y-%m}<br>$%{y:,.1f}B SAAR<extra></extra>",
    ))
    fig.update_yaxes(tickprefix="$", ticksuffix="B")
    return add_axis_headroom(_base_layout(fig, height=height, legend=False, margin=dict(l=54, r=20, t=24, b=38)), upper=0.12, lower=0.05)


def storage_pipeline_by_region(queue: pd.DataFrame | None, *, height: int = 420, top_n: int = 10):
    clean = queue.copy() if isinstance(queue, pd.DataFrame) else pd.DataFrame()
    if clean.empty:
        summary = pd.DataFrame(columns=["region", "Storage GW"])
    else:
        clean["Storage MW"] = pd.to_numeric(clean.get("Storage MW"), errors="coerce")
        clean = clean.loc[clean.get("q_status", "").fillna("").astype(str).eq("active") & clean["Storage MW"].gt(0)]
        summary = clean.groupby("region", as_index=False)["Storage MW"].sum().rename(columns={"Storage MW":"Storage GW"})
        summary["Storage GW"] = summary["Storage GW"] / 1000.0
        summary = summary.sort_values("Storage GW", ascending=True, kind="stable").tail(top_n)
    fig = go.Figure(go.Bar(
        x=summary.get("Storage GW", []), y=summary.get("region", []), orientation="h",
        marker_color=COLORS["violet"], text=[f"{v:,.0f} GW" for v in summary.get("Storage GW", [])], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:,.1f} GW active storage capacity<extra></extra>",
    ))
    fig.update_xaxes(ticksuffix=" GW")
    return add_axis_headroom(_base_layout(fig, height=height, legend=False, margin=dict(l=36, r=74, t=20, b=38)), axis="x", upper=0.16, lower=0.02, include_zero=True)
