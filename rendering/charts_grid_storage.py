from __future__ import annotations

import numpy as np
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


def queue_conversion_funnel(outcomes: pd.DataFrame | None, *, height: int = 390):
    frame = outcomes.copy() if isinstance(outcomes, pd.DataFrame) else pd.DataFrame()
    labels = ["Operational", "Still active", "Withdrawn"]
    values = [0.0, 0.0, 0.0]
    if not frame.empty:
        row = frame.iloc[-1]
        values = [
            pd.to_numeric(row.get("Historical Operational Share Percent"), errors="coerce"),
            pd.to_numeric(row.get("Historical Active Share Percent"), errors="coerce"),
            pd.to_numeric(row.get("Historical Withdrawn Share Percent"), errors="coerce"),
        ]
    fig = go.Figure(go.Bar(
        x=values, y=labels, orientation="h",
        marker_color=[COLORS["green"], COLORS["blue"], COLORS["slate"]],
        text=[f"{value:.0f}%" if pd.notna(value) else "n/a" for value in values],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:.1f}% of submitted capacity<extra></extra>",
    ))
    fig.update_xaxes(title="Share of 2000–2020 submitted capacity", ticksuffix="%")
    fig.update_yaxes(title="")
    return add_axis_headroom(_base_layout(fig, height=height, legend=False, margin=dict(l=90, r=70, t=22, b=48)), axis="x", upper=0.18, lower=0.0, include_zero=True)


def queue_age_by_region(profile: pd.DataFrame | None, *, height: int = 430, top_n: int = 10):
    frame = profile.copy() if isinstance(profile, pd.DataFrame) else pd.DataFrame()
    if not frame.empty:
        frame = frame.sort_values("Queue GW", ascending=False, kind="stable").head(top_n).sort_values("Median Queue Age Years", ascending=True, kind="stable")
    fig = go.Figure(go.Bar(
        x=frame.get("Median Queue Age Years", []), y=frame.get("Region", []), orientation="h",
        marker_color=COLORS["blue"],
        customdata=np.stack([
            pd.to_numeric(frame.get("Queue GW"), errors="coerce").fillna(0),
            pd.to_numeric(frame.get("Advanced Share Percent"), errors="coerce").fillna(0),
            pd.to_numeric(frame.get("Past Target Share Percent"), errors="coerce").fillna(0),
        ], axis=-1) if not frame.empty else None,
        hovertemplate=("%{y}<br>Median queue age: %{x:.1f} years"
                       "<br>Active queue: %{customdata[0]:,.0f} GW"
                       "<br>Advanced-stage share: %{customdata[1]:.1f}%"
                       "<br>Past target year: %{customdata[2]:.1f}%<extra></extra>"),
    ))
    fig.update_xaxes(title="Median years since interconnection request")
    fig.update_yaxes(title="")
    return add_axis_headroom(_base_layout(fig, height=height, legend=False, margin=dict(l=60, r=30, t=20, b=46)), axis="x", upper=0.12, lower=0.0, include_zero=True)


def reserve_margin_stress(profile: pd.DataFrame | None, *, height: int = 500):
    frame = profile.copy() if isinstance(profile, pd.DataFrame) else pd.DataFrame()
    if not frame.empty:
        frame = frame.sort_values("Extreme Conditions Margin Percent", ascending=True, kind="stable")
    fig = go.Figure()
    for column, name, color in (
        ("Anticipated Reserve Margin Percent", "Anticipated", COLORS["slate"]),
        ("Typical Conditions Margin Percent", "Typical outages", COLORS["blue"]),
        ("Extreme Conditions Margin Percent", "Extreme conditions", COLORS["violet"]),
    ):
        fig.add_trace(go.Bar(
            x=pd.to_numeric(frame.get(column), errors="coerce"),
            y=frame.get("Assessment Area", []), orientation="h", name=name, marker_color=color,
            hovertemplate=f"%{{y}}<br>{name}: %{{x:.1f}}%<extra></extra>",
        ))
    fig.add_vline(x=0, line_width=1, line_dash="dot", line_color="rgba(226,232,240,0.55)")
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="On-peak reserve margin", ticksuffix="%")
    fig.update_yaxes(title="")
    return _base_layout(fig, height=height, legend=True, margin=dict(l=120, r=24, t=70, b=48))


def storage_duration_distribution(profile: pd.DataFrame | None, *, height: int = 390):
    frame = profile.copy() if isinstance(profile, pd.DataFrame) else pd.DataFrame()
    fig = go.Figure(go.Bar(
        x=pd.to_numeric(frame.get("Power GW"), errors="coerce"),
        y=frame.get("Duration Band", []), orientation="h", marker_color=COLORS["violet"],
        customdata=np.stack([
            pd.to_numeric(frame.get("Energy GWh"), errors="coerce").fillna(0),
            pd.to_numeric(frame.get("Generators"), errors="coerce").fillna(0),
            pd.to_numeric(frame.get("Weighted Duration Hours"), errors="coerce").fillna(0),
        ], axis=-1) if not frame.empty else None,
        hovertemplate=("%{y}<br>Power: %{x:,.1f} GW"
                       "<br>Energy: %{customdata[0]:,.1f} GWh"
                       "<br>Generators: %{customdata[1]:,.0f}"
                       "<br>Weighted duration: %{customdata[2]:.1f} hours<extra></extra>"),
    ))
    fig.update_xaxes(title="Operating battery power", ticksuffix=" GW")
    fig.update_yaxes(title="")
    return add_axis_headroom(_base_layout(fig, height=height, legend=False, margin=dict(l=100, r=35, t=22, b=48)), axis="x", upper=0.16, lower=0.0, include_zero=True)
