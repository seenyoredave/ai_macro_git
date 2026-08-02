from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout

def debt_market_history(history, *, height=315, years=10):
    columns = [
        ("Corporate Bond Market Distress", "Market CMDI", COLORS["violet"]),
        ("Investment-Grade Bond Distress", "IG CMDI", COLORS["blue"]),
        ("High-Yield Bond Distress", "HY CMDI", COLORS["slate"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        frame = pd.DataFrame(columns=["Date", *[column for column, _, _ in columns]])
    else:
        selected = ["Date", *[column for column, _, _ in columns if column in history.columns]]
        frame = history[selected].copy() if "Date" in history.columns else pd.DataFrame()
        if not frame.empty:
            frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
            for column, _, _ in columns:
                if column not in frame.columns:
                    frame[column] = np.nan
                frame[column] = pd.to_numeric(frame[column], errors="coerce").replace(
                    [np.inf, -np.inf], np.nan
                )
            frame = frame.dropna(subset=["Date"]).sort_values("Date", kind="stable")
            frame = frame.drop_duplicates("Date", keep="last")
            if not frame.empty and years:
                cutoff = frame["Date"].max() - pd.DateOffset(years=years)
                frame = frame.loc[frame["Date"] >= cutoff].copy()

    fig = go.Figure()
    for column, label, color in columns:
        if frame.empty or column not in frame.columns:
            continue
        clean = frame.dropna(subset=[column])
        if clean.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=clean["Date"],
                y=clean[column],
                mode="lines",
                name=label,
                line={"color": color, "width": 2.4},
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.2f}}<extra></extra>",
            )
        )
    fig.update_yaxes(range=[0, 0.9])
    return _base_layout(
        fig,
        height=height,
        legend=True,
        margin=dict(l=42, r=18, t=28, b=36),
    )

def financial_conditions_history(history, *, height=275):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Date", "Value", "ANFCI"])
    else:
        selected = ["Date", "Value"] + (["ANFCI"] if "ANFCI" in history.columns else [])
        clean = history[selected].copy()
        if "ANFCI" not in clean.columns:
            clean["ANFCI"] = np.nan
        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
        for column in ["Value", "ANFCI"]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce").replace(
                [np.inf, -np.inf], np.nan
            )
        clean = clean.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
        clean = clean.drop_duplicates("Date", keep="last")

    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(
            go.Scatter(
                x=clean["Date"],
                y=clean["Value"],
                mode="lines",
                name="NFCI",
                line={"color": COLORS["blue"], "width": 2.8},
                hovertemplate="%{x|%Y-%m-%d}<br>NFCI %{y:+.3f}<extra></extra>",
            )
        )
        anfci = clean.dropna(subset=["ANFCI"])
        if not anfci.empty:
            fig.add_trace(
                go.Scatter(
                    x=anfci["Date"],
                    y=anfci["ANFCI"],
                    mode="lines",
                    name="ANFCI",
                    line={"color": COLORS["violet"], "width": 1.8, "dash": "dash"},
                    hovertemplate="%{x|%Y-%m-%d}<br>ANFCI %{y:+.3f}<extra></extra>",
                )
            )
    fig.add_hline(y=0, line_dash="dot", line_color="#64748b", opacity=0.78)
    return _base_layout(
        fig,
        height=height,
        legend=len(fig.data) > 1,
        margin=dict(l=42, r=18, t=30 if len(fig.data) > 1 else 18, b=34),
    )

def current_gap_bars(gaps: dict[str, float]):
    labels = list(gaps.keys())
    values = [pd.to_numeric(gaps[label], errors="coerce") for label in labels]
    colors = [
        COLORS["violet"] if pd.notna(value) and value >= 0 else COLORS["blue"]
        for value in values
    ]
    plot_values = [0.0 if pd.isna(value) else float(value) for value in values]

    fig = go.Figure(
        go.Bar(
            x=plot_values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=["n/a" if pd.isna(value) else f"{value:+.0f}" for value in values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:+.1f}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_dash="dot", line_color="#64748b")
    fig.update_xaxes(range=[-100, 100])
    fig.update_yaxes(autorange="reversed")
    return _base_layout(fig, height=270, margin=dict(l=160, r=45, t=15, b=28))

def component_bars(components: dict, *, signed=False, height=285, color=None):
    rows = []
    for name, payload in (components or {}).items():
        if isinstance(payload, dict):
            score = payload.get("score", np.nan)
        else:
            score = payload
        score = pd.to_numeric(score, errors="coerce")
        if pd.notna(score):
            rows.append((str(name), float(score)))

    rows = sorted(rows, key=lambda item: item[1])
    names = [item[0] for item in rows]
    values = [item[1] for item in rows]
    bar_colors = [
        (COLORS["blue"] if signed and value < 0 else color or COLORS["violet"])
        for value in values
    ]

    fig = go.Figure()
    if rows:
        fig.add_trace(
            go.Bar(
                x=values,
                y=names,
                orientation="h",
                marker_color=bar_colors,
                text=[f"{value:+.0f}" if signed else f"{value:.0f}" for value in values],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}<br>%{x:.1f}<extra></extra>",
            )
        )
    if signed:
        fig.add_vline(x=0, line_dash="dot", line_color="#64748b")
        fig.update_xaxes(range=[-100, 100])
    else:
        fig.update_xaxes(range=[0, 100])
    return _base_layout(fig, height=height, margin=dict(l=165, r=45, t=12, b=30))

def funding_history(history: pd.DataFrame, *, years=10):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return _base_layout(go.Figure(), height=330)

    specs = [
        ("Internal Funding Coverage", "Internal Funding Coverage", COLORS["violet"]),
        ("Cash Reserve Coverage", "Cash Reserve Runway", COLORS["blue"]),
        ("Debt Financing Pulse", "Debt Financing Pulse", "#8b5cf6"),
        ("Forward Commitment Load", "Forward Commitment Load", COLORS["slate"]),
    ]
    frame = history.copy()
    frame["Date"] = pd.to_datetime(frame.get("Date"), errors="coerce", format="mixed")
    frame = frame.loc[frame["Date"].notna()].copy()
    if not frame.empty and years:
        cutoff = frame["Date"].max() - pd.DateOffset(years=years)
        frame = frame.loc[frame["Date"] >= cutoff].copy()
    fig = go.Figure()
    for column, label, color in specs:
        if column not in frame.columns:
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        mask = frame["Date"].notna() & values.notna()
        if not mask.any():
            continue
        fig.add_trace(
            go.Scatter(
                x=frame.loc[mask, "Date"],
                y=values.loc[mask],
                mode="lines",
                name=label,
                line={"color": color, "width": 2.2},
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.2f}}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#64748b", opacity=0.6)
    fig.add_hline(y=1, line_dash="dot", line_color="#64748b", opacity=0.6)
    return _base_layout(fig, height=330, legend=False, margin=dict(l=42, r=18, t=18, b=36))
