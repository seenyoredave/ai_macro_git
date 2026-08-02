from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, clean_history

def infrastructure_construction_history(history: pd.DataFrame | None, *, height: int = 330, years: int = 10):
    columns = [
        ("Data Center Construction", "Data centers", COLORS["violet"]),
        ("Computer, Electronic & Electrical Manufacturing Construction", "Computer, electronic & electrical manufacturing", COLORS["blue"]),
        ("Electric Power Construction", "Electric power", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Observation Date" not in history.columns:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean["Observation Date"], errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]

    figure = go.Figure()
    for column, name, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"],
            y=rows[column] / 1000.0,
            mode="lines",
            name=name,
            line={"color": color, "width": 2.6},
            hovertemplate=f"%{{x|%Y-%m}}<br>{name}: $%{{y:,.1f}}B SAAR<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="B", tickprefix="$", separatethousands=True)
    return _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))

def power_utilization_history(history: pd.DataFrame | None, *, reference: float = 80.0, height: int = 300, years: int = 8):
    clean = clean_history(history)
    if not clean.empty and years:
        clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=years)]
    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(go.Scatter(
            x=clean["Date"], y=clean["Value"], mode="lines", name="Utilization",
            line={"color": COLORS["violet"], "width": 2.7},
            hovertemplate="%{x|%Y-%m}<br>Utilization: %{y:,.1f}%<extra></extra>",
        ))
    fig.add_hline(
        y=reference, line={"color": COLORS["amber"], "dash": "dash", "width": 1.5},
        annotation_text=f"90th-percentile tightness reference ({reference:.1f}%)", annotation_position="top left",
        annotation_font={"color": COLORS["amber"], "size": 11},
    )
    fig.update_yaxes(title="Utilization", ticksuffix="%")
    return _base_layout(fig, height=height, legend=False, margin=dict(l=52, r=18, t=30, b=36))

def compute_manufacturing_output_history(history: pd.DataFrame | None, *, height: int = 320):
    columns = [
        ("Computer and Peripheral Equipment Output", "Computers and peripherals", COLORS["violet"]),
        ("Communications Equipment Output", "Communications equipment", COLORS["blue"]),
        ("Semiconductor and Electronic Component Output", "Semiconductors and components", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[c for c, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column], mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.1f}}<extra></extra>",
        ))
    figure.update_yaxes(title="Output index")
    return _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=18, t=24, b=36))

def compute_capacity_utilization_history(history: pd.DataFrame | None, *, height: int = 300):
    columns = [
        ("Computer and Peripheral Equipment Capacity Utilization", "Computers and peripherals", COLORS["violet"]),
        ("Semiconductor and Electronic Component Capacity Utilization", "Semiconductors and components", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[c for c, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column], mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.1f}}%<extra></extra>",
        ))
    figure.update_yaxes(title="Utilization", ticksuffix="%")
    return _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=18, t=24, b=36))

def compute_project_investment_bars(projects: pd.DataFrame | None, *, height: int = 360):
    required = {"Recipient", "Portfolio ID", "Expected CapEx USD B", "Direct Funding USD B"}
    if projects is None or not isinstance(projects, pd.DataFrame) or projects.empty or not required.issubset(projects.columns):
        clean = pd.DataFrame(columns=["Recipient", "Expected CapEx USD B", "Direct Funding USD B", "Projects"])
    else:
        frame = projects.copy()
        frame["Expected CapEx USD B"] = pd.to_numeric(frame["Expected CapEx USD B"], errors="coerce")
        frame["Direct Funding USD B"] = pd.to_numeric(frame["Direct Funding USD B"], errors="coerce")
        portfolio = (
            frame.groupby(["Recipient", "Portfolio ID"], dropna=False)
            .agg(
                **{
                    "Expected CapEx USD B": ("Expected CapEx USD B", "max"),
                    "Direct Funding USD B": ("Direct Funding USD B", "sum"),
                    "Projects": ("Facility", "size"),
                }
            )
            .reset_index()
        )
        clean = (
            portfolio.groupby("Recipient", dropna=False)
            .agg(
                **{
                    "Expected CapEx USD B": ("Expected CapEx USD B", "sum"),
                    "Direct Funding USD B": ("Direct Funding USD B", "sum"),
                    "Projects": ("Projects", "sum"),
                }
            )
            .reset_index()
            .dropna(subset=["Expected CapEx USD B"])
            .loc[lambda frame: frame["Expected CapEx USD B"].gt(0)]
            .sort_values("Expected CapEx USD B", ascending=True, kind="stable")
        )
    figure = go.Figure()
    if not clean.empty:
        custom = np.column_stack([
            clean["Direct Funding USD B"].map(lambda value: "n/a" if pd.isna(value) else f"${value:,.2f}B"),
            clean["Projects"].astype(int).astype(str),
        ])
        figure.add_trace(go.Bar(
            x=clean["Expected CapEx USD B"],
            y=clean["Recipient"],
            orientation="h",
            marker={"color": COLORS["violet"]},
            customdata=custom,
            text=clean["Expected CapEx USD B"].map(lambda value: f"${value:,.1f}B"),
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "%{y}<br>Expected investment: $%{x:,.1f}B"
                "<br>Direct awards: %{customdata[0]}"
                "<br>Projects: %{customdata[1]}<extra></extra>"
            ),
        ))
    figure.update_xaxes(title="Expected capital spending", ticksuffix="B", tickprefix="$")
    figure.update_yaxes(title="")
    return _base_layout(figure, height=height, legend=False, margin=dict(l=205, r=52, t=18, b=48))

def supporting_construction_history(history: pd.DataFrame | None, *, height: int = 315, years: int = 8):
    columns = [
        ("Communication Construction", "Communication", COLORS["violet"]),
        ("Public Highway and Street Construction", "Highways and streets", COLORS["blue"]),
        ("Public Transportation Construction", "Transportation", COLORS["slate"]),
        ("Public Water Supply Construction", "Water supply", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Observation Date" not in history.columns:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean["Observation Date"], errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, name, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"],
            y=rows[column] / 1000.0,
            mode="lines",
            name=name,
            line={"color": color, "width": 2.2},
            hovertemplate=f"%{{x|%Y-%m}}<br>{name}: $%{{y:,.1f}}B SAAR<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="B", tickprefix="$", separatethousands=True)
    return _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))

def infrastructure_attribution_history(history: pd.DataFrame | None, *, height: int = 340, years: int = 12):
    columns = ["Date", "Broader Supporting Construction", "Expected Baseline", "Excess Above Baseline"]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or not set(columns).issubset(history.columns):
        clean = pd.DataFrame(columns=columns)
    else:
        clean = history[columns].copy()
        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
        for column in columns[1:]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Date"]).sort_values("Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Scatter(
            x=clean["Date"], y=clean["Broader Supporting Construction"] / 1000.0,
            mode="lines", name="Observed supporting construction",
            line={"color": COLORS["violet"], "width": 2.6},
            hovertemplate="%{x|%Y-%m}<br>Observed: $%{y:,.1f}B SAAR<extra></extra>",
        ))
        figure.add_trace(go.Scatter(
            x=clean["Date"], y=clean["Expected Baseline"] / 1000.0,
            mode="lines", name="Historical baseline",
            line={"color": COLORS["slate"], "width": 2.0, "dash": "dash"},
            hovertemplate="%{x|%Y-%m}<br>Baseline: $%{y:,.1f}B SAAR<extra></extra>",
        ))
        figure.add_trace(go.Bar(
            x=clean["Date"], y=clean["Excess Above Baseline"] / 1000.0,
            name="Excess above baseline", marker={"color": COLORS["amber"], "opacity": 0.45},
            hovertemplate="%{x|%Y-%m}<br>Excess: $%{y:,.1f}B SAAR<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="B", tickprefix="$", separatethousands=True)
    return _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))
