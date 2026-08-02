from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

COLORS = {
    "text": "#e5e7eb",
    "muted": "#94a3b8",
    "grid": "rgba(100,116,139,0.18)",
    "panel": "rgba(15,23,42,0.35)",
    "violet": "#a78bfa",
    "violet_deep": "#7c3aed",
    "blue": "#60a5fa",
    "blue_deep": "#2563eb",
    "slate": "#94a3b8",
    "amber": "#fbbf24",
    "red": "#fb7185",
    "green": "#34d399",
}

def clean_history(history) -> pd.DataFrame:
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if not {"Date", "Value"}.issubset(history.columns):
        return pd.DataFrame(columns=["Date", "Value"])
    out = history[["Date", "Value"]].copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    return (
        out.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates("Date", keep="last")
        .reset_index(drop=True)
    )

def history_from_frame(frame, column) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if "Date" not in frame.columns or column not in frame.columns:
        return pd.DataFrame(columns=["Date", "Value"])
    return clean_history(frame[["Date", column]].rename(columns={column: "Value"}))

def _base_layout(fig, *, height=300, margin=None, legend=False, title=None):
    layout = {
        "height": height,
        "margin": margin or dict(l=42, r=18, t=42 if title else 18, b=34),
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": COLORS["panel"],
        "font": {"color": COLORS["text"], "family": "Inter, ui-sans-serif, system-ui"},
        "showlegend": legend,
        "hoverlabel": {"bgcolor": "#0f172a", "font": {"color": COLORS["text"]}},
        "legend": {
            "orientation": "h",
            "y": 1.10,
            "x": 0,
            "font": {"color": COLORS["muted"], "size": 11},
        },
        "xaxis": {
            "gridcolor": COLORS["grid"],
            "zeroline": False,
            "linecolor": "rgba(148,163,184,0.25)",
            "tickfont": {"color": COLORS["muted"]},
        },
        "yaxis": {
            "gridcolor": COLORS["grid"],
            "zeroline": False,
            "linecolor": "rgba(148,163,184,0.25)",
            "tickfont": {"color": COLORS["muted"]},
        },
    }
    if title:
        layout["title"] = {
            "text": str(title),
            "font": {"size": 15, "color": COLORS["text"]},
        }

    fig.update_layout(**layout)
    if not title:

        fig.layout.pop("title", None)
    return fig

def compact_sparkline(history, *, color=None, reference=None, years=5, height=80):
    clean = clean_history(history)
    if not clean.empty and years:
        cutoff = clean["Date"].max() - pd.DateOffset(years=years)
        clean = clean[clean["Date"] >= cutoff]

    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(
            go.Scatter(
                x=clean["Date"],
                y=clean["Value"],
                mode="lines",
                line={"color": color or COLORS["violet"], "width": 2.3},
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[clean["Date"].iloc[-1]],
                y=[clean["Value"].iloc[-1]],
                mode="markers",
                marker={
                    "size": 6,
                    "color": color or COLORS["violet"],
                    "line": {"width": 1.2, "color": "#111827"},
                },
                hoverinfo="skip",
            )
        )
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dot", line_color="#64748b", opacity=0.75)
    fig.update_layout(
        height=height,
        margin=dict(l=2, r=2, t=3, b=2),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis={"visible": False, "fixedrange": True},
        yaxis={"visible": False, "fixedrange": True},
    )
    return fig

def dual_history(
    first,
    second,
    *,
    first_name,
    second_name,
    first_color=None,
    second_color=None,
    y_range=None,
    reference=None,
    height=330,
    years=6,
    value_suffix="",
):
    frames = [clean_history(first), clean_history(second)]
    latest = [frame["Date"].max() for frame in frames if not frame.empty]
    if latest and years:
        cutoff = max(latest) - pd.DateOffset(years=years)
        frames = [frame[frame["Date"] >= cutoff] for frame in frames]

    fig = go.Figure()
    for frame, name, color in [
        (frames[0], first_name, first_color or COLORS["violet"]),
        (frames[1], second_name, second_color or COLORS["blue"]),
    ]:
        if frame.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=frame["Date"],
                y=frame["Value"],
                mode="lines",
                name=name,
                line={"color": color, "width": 2.6},
                hovertemplate=(
                    f"%{{x|%Y-%m-%d}}<br>{name}: %{{y:.1f}}{value_suffix}<extra></extra>"
                ),
            )
        )
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dot", line_color="#64748b", opacity=0.75)
    if y_range:
        fig.update_yaxes(range=list(y_range))
    if value_suffix:
        fig.update_yaxes(ticksuffix=value_suffix)
    return _base_layout(fig, height=height, legend=True, margin=dict(l=42, r=18, t=26, b=36))

def single_history(
    history,
    *,
    color=None,
    reference=None,
    y_range=None,
    height=285,
    step=False,
    years=None,
):
    clean = clean_history(history)
    if not clean.empty and years:
        cutoff = clean["Date"].max() - pd.DateOffset(years=years)
        clean = clean.loc[clean["Date"] >= cutoff].copy()
    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(
            go.Scatter(
                x=clean["Date"],
                y=clean["Value"],
                mode="lines",
                line={
                    "color": color or COLORS["violet"],
                    "width": 2.5,
                    "shape": "hv" if step else "linear",
                },
                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            )
        )
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dot", line_color="#64748b", opacity=0.78)
    if y_range:
        fig.update_yaxes(range=list(y_range))
    return _base_layout(fig, height=height, margin=dict(l=42, r=18, t=18, b=34))
