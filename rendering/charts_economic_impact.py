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

OUTCOME_LABELS = {
    "Labor productivity (output per hour)": "Labor productivity",
    "Real value-added output": "Real output",
    "Hourly compensation": "Hourly compensation",
    "Unit labor costs": "Unit labor costs",
}


def _add_value_rail(fig, categories, values, *, suffix="%", digits=1) -> None:
    """Place values in a fixed right-side rail, clear of labels and bars."""
    annotations = []
    for category, raw_value in zip(list(categories), list(values)):
        value = pd.to_numeric(raw_value, errors="coerce")
        if pd.isna(value):
            continue
        annotations.append({
            "xref": "paper",
            "yref": "y",
            "x": 1.02,
            "y": category,
            "text": f"{float(value):+.{digits}f}{suffix}",
            "showarrow": False,
            "xanchor": "left",
            "yanchor": "middle",
            "font": {"color": COLORS["text"], "size": 11},
        })
    fig.update_layout(annotations=annotations)


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
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=54, r=20, t=86, b=38))
    fig.update_layout(legend={"orientation": "h", "y": 1.04, "x": 0, "font": {"color": COLORS["muted"], "size": 10}})
    return add_axis_headroom(fig, upper=0.22, lower=0.05)


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

    labels = [OUTCOME_LABELS.get(str(measure), str(measure)) for measure in latest.get("measure_text", [])]
    fig = go.Figure(go.Bar(
        x=latest.get("Value", []), y=labels, orientation="h",
        marker_color=[MEASURE_COLORS.get(str(m), COLORS["slate"]) for m in latest.get("measure_text", [])],
        customdata=latest.get("measure_text", []),
        hovertemplate="%{customdata}<br>%{x:+.1f}% YoY<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=1, line_color="rgba(148,163,184,0.55)")
    fig.update_xaxes(ticksuffix="%")
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=34, r=82, t=20, b=38))
    fig.update_yaxes(automargin=True)
    _add_value_rail(fig, labels, latest.get("Value", []))
    return add_axis_headroom(
        fig,
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


def worker_capture_history(frame: pd.DataFrame | None, *, height: int = 420):
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if not clean.empty:
        clean["Date"] = pd.to_datetime(clean.get("Date"), errors="coerce", format="mixed")
        clean["Value"] = pd.to_numeric(clean.get("Value"), errors="coerce")
        clean = clean.dropna(subset=["Date", "Series", "Value"]).sort_values(["Series", "Date"], kind="stable")
    series_colors = {
        "Labor productivity": COLORS["violet"],
        "Real hourly compensation": COLORS["green"],
        "Labor share": COLORS["amber"],
    }
    fig = go.Figure()
    for series, group in clean.groupby("Series", sort=False):
        base = pd.to_numeric(group.iloc[0]["Value"], errors="coerce")
        if pd.isna(base) or base == 0:
            continue
        indexed = group["Value"] / float(base) * 100.0
        fig.add_trace(go.Scatter(
            x=group["Date"], y=indexed, mode="lines", name=str(series),
            line={"width": 2.6, "color": series_colors.get(str(series), COLORS["slate"])},
            customdata=group[["Value"]].to_numpy(),
            hovertemplate=f"%{{x|%Y-Q%q}}<br>{series}: %{{y:.1f}} (2020=100)<br>Published index: %{{customdata[0]:.1f}}<extra></extra>",
        ))
    fig.add_hline(y=100, line_width=1, line_dash="dot", line_color="rgba(148,163,184,0.5)")
    fig.update_yaxes(title_text="First 2020 observation = 100")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=20, t=82, b=38))
    fig.update_layout(legend={"orientation": "h", "y": 1.03, "x": 0, "font": {"color": COLORS["muted"], "size": 10}})
    return add_axis_headroom(fig, upper=0.16, lower=0.08)


def earnings_distribution_change(frame: pd.DataFrame | None, *, height: int = 390):
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if clean.empty:
        clean = pd.DataFrame(columns=["Series", "Since 2020", "Dimension"])
    clean["Since 2020"] = pd.to_numeric(clean.get("Since 2020"), errors="coerce")
    clean = clean.dropna(subset=["Series", "Since 2020"]).sort_values("Since 2020", kind="stable")
    color_map = {"All": COLORS["violet"], "Sex": COLORS["green"], "Race and ethnicity": COLORS["blue"]}
    fig = go.Figure(go.Bar(
        x=clean.get("Since 2020", []),
        y=clean.get("Series", []),
        orientation="h",
        marker_color=[color_map.get(str(value), COLORS["slate"]) for value in clean.get("Dimension", [])],
        customdata=list(zip(clean.get("YoY", []), clean.get("Relative to all workers", []), clean.get("Seasonality", []))),
        hovertemplate=(
            "%{y}<br>Change since 2020: %{x:+.1f}%"
            "<br>Latest YoY: %{customdata[0]:+.1f}%"
            "<br>Level vs all workers: %{customdata[1]:+.1f}%"
            "<br>%{customdata[2]}<extra></extra>"
        ),
    ))
    fig.add_vline(x=0, line_width=1, line_color="rgba(148,163,184,0.55)")
    fig.update_xaxes(ticksuffix="%", title_text="Four-quarter-average real earnings change")
    fig.update_yaxes(automargin=True)
    return add_axis_headroom(_base_layout(fig, height=height, legend=False, margin=dict(l=126, r=28, t=20, b=48)), axis="x", upper=0.18, lower=0.18, include_zero=True)


def earnings_distribution_history(frame: pd.DataFrame | None, dimension: str, *, height: int = 420):
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    if not clean.empty:
        clean["Date"] = pd.to_datetime(clean.get("Date"), errors="coerce", format="mixed")
        clean["Value"] = pd.to_numeric(clean.get("Value"), errors="coerce")
        clean = clean.loc[clean.get("Dimension", pd.Series("", index=clean.index)).astype(str).eq(dimension)]
        clean = clean.dropna(subset=["Date", "Series", "Value"]).sort_values(["Series", "Date"], kind="stable")
    palette = [COLORS["violet"], COLORS["blue"], COLORS["green"], COLORS["amber"], COLORS["slate"]]
    fig = go.Figure()
    for index, (series, group) in enumerate(clean.groupby("Series", sort=False)):
        group = group.copy()
        group["Four-quarter average"] = group["Value"].rolling(4, min_periods=4).mean()
        group = group.dropna(subset=["Four-quarter average"])
        if group.empty:
            continue
        base = float(group.iloc[0]["Four-quarter average"])
        group["Indexed"] = group["Four-quarter average"] / base * 100.0 if base else np.nan
        fig.add_trace(go.Scatter(
            x=group["Date"], y=group["Indexed"], mode="lines", name=str(series),
            line={"width": 2.4, "color": palette[index % len(palette)]},
            customdata=group[["Four-quarter average", "Seasonality"]].to_numpy(),
            hovertemplate=(
                f"%{{x|%Y-Q%q}}<br>{series}: %{{y:.1f}} (2020=100)"
                "<br>Real weekly earnings: %{customdata[0]:.1f}"
                "<br>%{customdata[1]}<extra></extra>"
            ),
        ))
    fig.add_hline(y=100, line_width=1, line_dash="dot", line_color="rgba(148,163,184,0.5)")
    fig.update_yaxes(title_text="First four-quarter average = 100")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=20, t=82, b=38))
    fig.update_layout(legend={"orientation": "h", "y": 1.03, "x": 0, "font": {"color": COLORS["muted"], "size": 10}})
    return add_axis_headroom(fig, upper=0.14, lower=0.08)
