from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom

def adaptation_history(history: pd.DataFrame | None, *, height: int = 325, years: int = 3):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Date" not in history.columns:
        clean = pd.DataFrame(columns=["Date", "Current AI Use", "Expected AI Use"])
    else:
        clean = history.copy()
        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
        for column in ["Current AI Use", "Expected AI Use", "Current AI Use SE", "Expected AI Use SE"]:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Date"]).sort_values("Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color, dash in [
        ("Current AI Use", "Current use", COLORS["violet"], "solid"),
        ("Expected AI Use", "Expected use within six months", COLORS["blue"], "dash"),
    ]:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        se_column = f"{column} SE"
        error_values = (1.96 * pd.to_numeric(rows.get(se_column), errors="coerce")) if se_column in rows.columns else None
        figure.add_trace(go.Scatter(
            x=rows["Date"],
            y=rows[column],
            mode="lines",
            name=label,
            line={"color": color, "width": 2.6, "dash": dash},
            error_y={
                "type": "data",
                "array": error_values,
                "visible": error_values is not None,
                "color": color,
                "thickness": 1.0,
                "width": 2,
            },
            hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.1f}}%<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="%", rangemode="tozero")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=44, r=18, t=28, b=36))
    return add_axis_headroom(figure, upper=0.20, lower=0.05, include_zero=True)

def adaptation_sector_bars(sector_snapshot: pd.DataFrame | None, *, height: int = 680, limit: int | None = None):
    required = {"Sector", "Current AI Use", "Expected AI Use"}
    if sector_snapshot is None or not isinstance(sector_snapshot, pd.DataFrame) or sector_snapshot.empty or not required.issubset(sector_snapshot.columns):
        clean = pd.DataFrame(columns=list(required))
    else:
        clean = sector_snapshot.copy()
        clean = clean.loc[clean.get("Sector Code", "").astype(str) != "XX"] if "Sector Code" in clean.columns else clean
        for column in ["Current AI Use", "Expected AI Use", "Current AI Use SE", "Expected AI Use SE"]:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Current AI Use"])
        if limit is not None:
            clean = clean.nlargest(int(limit), "Current AI Use")
        clean = clean.sort_values("Current AI Use")
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Bar(
            x=clean["Current AI Use"], y=clean["Sector"], orientation="h", name="Current use",
            marker_color=COLORS["violet"],
            error_x={"type": "data", "array": 1.96 * clean["Current AI Use SE"], "visible": True, "color": COLORS["violet"], "thickness": 1.0},
            hovertemplate="%{y}<br>Current use: %{x:.1f}%<extra></extra>",
        ))
        figure.add_trace(go.Bar(
            x=clean["Expected AI Use"], y=clean["Sector"], orientation="h", name="Expected within six months",
            marker_color=COLORS["blue"], opacity=0.72,
            error_x={"type": "data", "array": 1.96 * clean["Expected AI Use SE"], "visible": True, "color": COLORS["blue"], "thickness": 1.0},
            hovertemplate="%{y}<br>Expected use: %{x:.1f}%<extra></extra>",
        ))
    figure.update_layout(barmode="group")
    figure.update_xaxes(ticksuffix="%", rangemode="tozero")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=255, r=34, t=30, b=36))
    return add_axis_headroom(figure, axis="x", upper=0.20, lower=0.0, include_zero=True)
