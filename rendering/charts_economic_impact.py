from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom

MEASURE_COLORS = {
    "Labor productivity (output per hour)": COLORS["violet"],
    "Real value-added output": COLORS["blue"],
    "Hourly compensation": COLORS["green"],
    "Unit labor costs": COLORS["amber"],
}


def _selection(frame, *, sector: str, metric: str) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["Date", "measure_text", "Value"])
    clean = frame.copy()
    clean["Date"] = pd.to_datetime(clean.get("Date"), errors="coerce", format="mixed")
    clean["Value"] = pd.to_numeric(clean.get("Value"), errors="coerce")
    mask = clean.get("sector_name", pd.Series("", index=clean.index)).astype(str).eq(sector) & clean.get("Metric", pd.Series("", index=clean.index)).astype(str).eq(metric)
    return clean.loc[mask].dropna(subset=["Date", "measure_text", "Value"]).sort_values(["measure_text", "Date"], kind="stable")


def productivity_index(frame, *, sector: str = "Nonfarm Business", height: int = 420):
    clean = _selection(frame, sector=sector, metric="Index")
    clean = clean.loc[clean["Date"] >= pd.Timestamp("2020-01-01")].copy()
    fig = go.Figure()
    for measure, group in clean.groupby("measure_text", sort=False):
        fig.add_trace(go.Scatter(
            x=group["Date"], y=group["Value"], mode="lines", name=str(measure),
            line={"width": 2.5, "color": MEASURE_COLORS.get(str(measure), COLORS["slate"])},
            hovertemplate=f"%{{x|%Y-%m}}<br>{measure}: %{{y:.1f}}<extra></extra>",
        ))
    fig.update_yaxes(title_text="Index, 2017 = 100")
    return add_axis_headroom(_base_layout(fig, height=height, legend=True, margin=dict(l=54, r=20, t=24, b=38)), upper=0.12, lower=0.05)


def _real_growth(value: float, inflation_yoy: float) -> float:
    value = pd.to_numeric(value, errors="coerce")
    inflation_yoy = pd.to_numeric(inflation_yoy, errors="coerce")
    if pd.isna(value) or pd.isna(inflation_yoy):
        return float("nan")
    denominator = 1.0 + float(inflation_yoy) / 100.0
    if denominator <= 0:
        return float("nan")
    return ((1.0 + float(value) / 100.0) / denominator - 1.0) * 100.0


def current_outcomes(
    frame,
    *,
    sector: str = "Nonfarm Business",
    inflation_yoy: float | None = None,
    inflation_adjusted: bool = False,
    height: int = 390,
):
    clean = _selection(frame, sector=sector, metric="Year-over-year change")
    if clean.empty:
        latest = pd.DataFrame(columns=["measure_text", "Value"])
    else:
        latest = clean.sort_values("Date", kind="stable").groupby("measure_text", as_index=False).tail(1)
        latest = latest.loc[latest["measure_text"].isin(MEASURE_COLORS)].copy()

    if inflation_adjusted and not latest.empty:
        nominal_measures = {"Hourly compensation", "Unit labor costs"}
        latest["Value"] = [
            _real_growth(value, inflation_yoy) if measure in nominal_measures else value
            for measure, value in zip(latest["measure_text"], latest["Value"])
        ]
    latest = latest.dropna(subset=["Value"]).sort_values("Value", kind="stable")

    fig = go.Figure(go.Bar(
        x=latest.get("Value", []), y=latest.get("measure_text", []), orientation="h",
        marker_color=[MEASURE_COLORS.get(str(m), COLORS["slate"]) for m in latest.get("measure_text", [])],
        text=[f"{v:+.1f}%" for v in latest.get("Value", [])], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:+.1f}% YoY<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=1, line_color="rgba(148,163,184,0.55)")
    fig.update_xaxes(ticksuffix="%")
    return add_axis_headroom(
        _base_layout(fig, height=height, legend=False, margin=dict(l=34, r=70, t=20, b=38)),
        axis="x", upper=0.20, lower=0.16, include_zero=True,
    )


def investment_vs_output(investment, productivity, *, height: int = 420):
    inv = investment.copy() if isinstance(investment, pd.DataFrame) else pd.DataFrame()
    if not inv.empty:
        inv["Observation Date"] = pd.to_datetime(inv.get("Observation Date"), errors="coerce", format="mixed")
        inv["Value"] = pd.to_numeric(inv.get("Info Processing Investment Level"), errors="coerce")
        inv = inv.dropna(subset=["Observation Date", "Value"]).sort_values("Observation Date")
        inv = inv.loc[inv["Observation Date"] >= pd.Timestamp("2020-01-01")]
        if not inv.empty:
            inv["Indexed"] = inv["Value"] / inv.iloc[0]["Value"] * 100.0
    prod = _selection(productivity, sector="Nonfarm Business", metric="Index")
    prod = prod.loc[prod["measure_text"].isin(["Labor productivity (output per hour)", "Real value-added output"])]
    fig = go.Figure()
    if not inv.empty:
        fig.add_trace(go.Scatter(x=inv["Observation Date"], y=inv["Indexed"], mode="lines", name="Information-processing investment", line={"width": 2.7, "color": COLORS["violet"]}, hovertemplate="%{x|%Y-%m}<br>Investment: %{y:.1f}<extra></extra>"))
    for measure, group in prod.groupby("measure_text", sort=False):
        group = group.loc[group["Date"] >= pd.Timestamp("2020-01-01")].copy()
        if group.empty:
            continue
        group["Indexed"] = group["Value"] / group.iloc[0]["Value"] * 100.0
        fig.add_trace(go.Scatter(x=group["Date"], y=group["Indexed"], mode="lines", name=str(measure), line={"width": 2.4, "color": MEASURE_COLORS.get(str(measure), COLORS["slate"])}, hovertemplate=f"%{{x|%Y-%m}}<br>{measure}: %{{y:.1f}}<extra></extra>"))
    fig.add_hline(y=100, line_width=1, line_dash="dot", line_color="rgba(148,163,184,0.5)")
    fig.update_yaxes(title_text="First 2020 observation = 100")
    return add_axis_headroom(_base_layout(fig, height=height, legend=True, margin=dict(l=54, r=20, t=24, b=38)), upper=0.12, lower=0.05)
