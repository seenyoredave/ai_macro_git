from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom


DISPLAY_LABELS = {
    "Computer systems design": "Systems design",
    "Computing infrastructure": "Compute infrastructure",
    "Semiconductor manufacturing": "Semiconductors",
    "Power & communication construction": "Power & comms construction",
}

SERIES_COLORS = {
    "Computer systems design": COLORS["violet"],
    "Computing infrastructure": COLORS["blue"],
    "Semiconductor manufacturing": COLORS["green"],
    "Power & communication construction": COLORS["amber"],
    "Information": COLORS["blue"],
    "Professional and business services": COLORS["violet"],
    "Manufacturing": COLORS["green"],
    "Construction": COLORS["amber"],
}


def _clean(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["Date", "Series", "Value"])
    out = frame.copy()
    out["Date"] = pd.to_datetime(out.get("Date"), errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out.get("Value"), errors="coerce")
    return out.dropna(subset=["Date", "Series", "Value"]).sort_values(["Series", "Date"], kind="stable")


def indexed_history(frame: pd.DataFrame | None, *, height: int = 420, title_suffix: str = ""):
    clean = _clean(frame)
    fig = go.Figure()
    for series, group in clean.groupby("Series", sort=False):
        group = group.sort_values("Date", kind="stable")
        base = pd.to_numeric(group.iloc[0]["Value"], errors="coerce")
        if pd.isna(base) or base == 0:
            continue
        values = group["Value"] / float(base) * 100.0
        fig.add_trace(go.Scatter(
            x=group["Date"], y=values, mode="lines", name=str(series),
            line={"width": 2.5, "color": SERIES_COLORS.get(str(series), COLORS["slate"])},
            hovertemplate=f"%{{x|%Y-%m}}<br>{series}: %{{y:.1f}}{title_suffix}<extra></extra>",
        ))
    fig.add_hline(y=100, line_width=1, line_dash="dot", line_color="rgba(148,163,184,0.5)")
    fig.update_yaxes(ticksuffix="", title_text="Jan. 2020 = 100", title_standoff=10)
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=20, t=76, b=46))
    fig.update_layout(legend={"orientation": "h", "y": 1.04, "x": 0, "font": {"color": COLORS["muted"], "size": 10}})
    return add_axis_headroom(fig, upper=0.12, lower=0.14, include_zero=False)


def current_momentum(latest: pd.DataFrame | None, *, height: int = 380):
    frame = latest.copy() if isinstance(latest, pd.DataFrame) else pd.DataFrame()
    if frame.empty:
        frame = pd.DataFrame(columns=["Series", "YoY Change"])
    frame["YoY Change"] = pd.to_numeric(frame.get("YoY Change"), errors="coerce") * 100.0
    frame = frame.dropna(subset=["Series", "YoY Change"]).sort_values("YoY Change", kind="stable")
    colors = [SERIES_COLORS.get(str(name), COLORS["slate"]) for name in frame.get("Series", [])]
    labels = [DISPLAY_LABELS.get(str(name), str(name)) for name in frame.get("Series", [])]
    fig = go.Figure(go.Bar(
        x=frame.get("YoY Change", []), y=labels, orientation="h",
        marker_color=colors, text=[f"{v:+.1f}%" for v in frame.get("YoY Change", [])],
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:+.1f}% YoY<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=1, line_color="rgba(148,163,184,0.55)")
    fig.update_xaxes(
        ticksuffix="%", zeroline=False, tickmode="array", tickvals=[-5, 0, 5],
        ticktext=["−5%", "0", "5%"],
    )
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=118, r=60, t=20, b=40))
    fig = add_axis_headroom(fig, axis="x", upper=0.22, lower=0.18, include_zero=True)
    current_range = list(fig.layout.xaxis.range or [-5.5, 5.5])
    fig.update_xaxes(range=[min(float(current_range[0]), -5.5), max(float(current_range[1]), 5.5)])
    return fig


def level_history(frame: pd.DataFrame | None, *, height: int = 420, value_suffix: str = "", value_prefix: str = ""):
    clean = _clean(frame)
    fig = go.Figure()
    for series, group in clean.groupby("Series", sort=False):
        fig.add_trace(go.Scatter(
            x=group["Date"], y=group["Value"], mode="lines", name=str(series),
            line={"width": 2.4, "color": SERIES_COLORS.get(str(series), COLORS["slate"])},
            hovertemplate=f"%{{x|%Y-%m}}<br>{series}: {value_prefix}%{{y:,.1f}}{value_suffix}<extra></extra>",
        ))
    fig.update_yaxes(tickprefix=value_prefix, ticksuffix=value_suffix)
    return add_axis_headroom(_base_layout(fig, height=height, legend=True, margin=dict(l=52, r=20, t=24, b=38)), upper=0.12, lower=0.04)
