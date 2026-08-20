from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom

def adoption_history(history: pd.DataFrame | None, *, height: int = 325, years: int = 3):
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

def adoption_sector_bars(sector_snapshot: pd.DataFrame | None, *, height: int = 680, limit: int | None = None):
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

CONSUMER_SERIES_COLORS = {
    "Overall use": COLORS["violet"],
    "Personal / outside work": COLORS["green"],
    "Work use": COLORS["blue"],
    "Used last week": COLORS["amber"],
    "Daily use": COLORS["slate"],
}


def consumer_adoption_history(history: pd.DataFrame | None, *, height: int = 340):
    required = {"Date", "Series", "Value"}
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or not required.issubset(history.columns):
        clean = pd.DataFrame(columns=list(required))
    else:
        clean = history.copy()
        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
        clean["Value"] = pd.to_numeric(clean["Value"], errors="coerce")
        clean = clean.dropna(subset=["Date", "Series", "Value"]).sort_values(["Series", "Date"], kind="stable")

    figure = go.Figure()
    for series in ["Overall use", "Personal / outside work", "Work use", "Used last week", "Daily use"]:
        group = clean.loc[clean.get("Series", pd.Series("", index=clean.index)).astype(str).eq(series)]
        if group.empty:
            continue
        figure.add_trace(go.Scatter(
            x=group["Date"],
            y=group["Value"],
            mode="lines+markers",
            name=series,
            line={
                "color": CONSUMER_SERIES_COLORS.get(series, COLORS["slate"]),
                "width": 2.6,
                "dash": "dash" if series == "Used last week" else "dot" if series == "Daily use" else "solid",
            },
            marker={"size": 6},
            hovertemplate=f"%{{x|%Y-%m}}<br>{series}: %{{y:.1f}}%<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="%", rangemode="tozero", title_text="Reported use (%)")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=56, r=18, t=28, b=36))
    figure.update_layout(legend={"orientation": "h", "y": 1.05, "x": 0})
    return add_axis_headroom(figure, upper=0.18, lower=0.05, include_zero=True)


def adoption_function_bars(functions: pd.DataFrame | None, *, height: int = 650):
    required = {"Function", "Share"}
    if functions is None or not isinstance(functions, pd.DataFrame) or functions.empty or not required.issubset(functions.columns):
        clean = pd.DataFrame(columns=["Function", "Share", "SE"])
    else:
        clean = functions.copy()
        clean["Share"] = pd.to_numeric(clean["Share"], errors="coerce")
        clean["SE"] = pd.to_numeric(clean.get("SE"), errors="coerce")
        clean = clean.dropna(subset=["Share"]).sort_values("Share", kind="stable")

    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Bar(
            x=clean["Share"],
            y=clean["Function"],
            orientation="h",
            marker_color=COLORS["violet"],
            error_x={
                "type": "data",
                "array": 1.96 * clean["SE"],
                "visible": bool(clean["SE"].notna().any()),
                "color": COLORS["violet"],
                "thickness": 1.0,
            },
            hovertemplate="%{y}<br>%{x:.1f}%<extra></extra>",
            showlegend=False,
        ))
    figure.update_xaxes(ticksuffix="%", rangemode="tozero")
    figure = _base_layout(figure, height=height, legend=False, margin=dict(l=255, r=34, t=30, b=36))
    return add_axis_headroom(figure, axis="x", upper=0.18, lower=0.0, include_zero=True)

def adoption_depth_bars(
    frame: pd.DataFrame | None,
    *,
    category: str,
    value: str,
    height: int = 420,
):
    required = {category, value}
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty or not required.issubset(frame.columns):
        clean = pd.DataFrame(columns=[category, value, "SE"])
    else:
        clean = frame.copy()
        clean[value] = pd.to_numeric(clean[value], errors="coerce")
        clean["SE"] = pd.to_numeric(clean.get("SE"), errors="coerce")
        clean = clean.dropna(subset=[value]).sort_values(value, kind="stable")

    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Bar(
            x=clean[value],
            y=clean[category],
            orientation="h",
            marker_color=COLORS["green"],
            error_x={"type": "data", "array": 1.96 * clean["SE"], "visible": bool(clean["SE"].notna().any()), "color": COLORS["green"], "thickness": 1.0},
            hovertemplate="%{y}<br>%{x:.1f}%<extra></extra>",
            showlegend=False,
        ))
    figure.update_xaxes(ticksuffix="%", rangemode="tozero")
    figure = _base_layout(figure, height=height, legend=False, margin=dict(l=255, r=34, t=22, b=36))
    return add_axis_headroom(figure, axis="x", upper=0.18, lower=0.0, include_zero=True)
