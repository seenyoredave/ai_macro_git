from __future__ import annotations

import numpy as np
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
    "U.S. total private average": COLORS["slate"],
}

WAGE_BENCHMARK = "U.S. total private average"


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
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=20, t=92, b=46))
    fig.update_layout(legend={"orientation": "h", "y": 1.04, "x": 0, "font": {"color": COLORS["muted"], "size": 10}})
    return add_axis_headroom(fig, upper=0.22, lower=0.14, include_zero=False)


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
        marker_color=colors,
        hovertemplate="%{y}<br>%{x:+.1f}% YoY<extra></extra>",
    ))
    fig.add_vline(x=0, line_width=1, line_color="rgba(148,163,184,0.55)")
    fig.update_xaxes(
        ticksuffix="%", zeroline=False, tickmode="array", tickvals=[-5, 0, 5],
        ticktext=["−5%", "0", "5%"],
    )
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=118, r=78, t=20, b=40))
    fig.update_yaxes(automargin=True)
    _add_value_rail(fig, labels, frame.get("YoY Change", []))
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


def earnings_history(
    frame: pd.DataFrame | None,
    cpi_history: pd.DataFrame | None,
    *,
    inflation_adjusted: bool = True,
    height: int = 440,
):
    clean = _clean(frame)
    value_column = "Value"
    y_title = "Nominal dollars per hour"
    hover_label = "Nominal hourly earnings"

    if inflation_adjusted and not clean.empty and isinstance(cpi_history, pd.DataFrame) and not cpi_history.empty:
        cpi = cpi_history.copy()
        cpi["Date"] = pd.to_datetime(cpi.get("Date"), errors="coerce", format="mixed")
        cpi["CPI"] = pd.to_numeric(cpi.get("CPI"), errors="coerce")
        cpi = cpi.dropna(subset=["Date", "CPI"]).sort_values("Date", kind="stable")
        if not cpi.empty:
            merged = pd.merge_asof(
                clean.sort_values("Date", kind="stable"),
                cpi[["Date", "CPI"]],
                on="Date",
                direction="backward",
            )
            earnings_end = clean["Date"].max()
            reference_rows = cpi.loc[cpi["Date"] <= earnings_end]
            reference_cpi = pd.to_numeric(
                reference_rows.iloc[-1]["CPI"] if not reference_rows.empty else np.nan,
                errors="coerce",
            )
            if pd.notna(reference_cpi) and reference_cpi > 0:
                merged["Real Value"] = merged["Value"] * float(reference_cpi) / merged["CPI"]
                clean = merged.dropna(subset=["Real Value"]).sort_values(["Series", "Date"], kind="stable")
                value_column = "Real Value"
                y_title = "Dollars per hour, latest CPI purchasing power"
                hover_label = "Real hourly earnings"

    fig = go.Figure()
    for series, group in clean.groupby("Series", sort=False):
        is_benchmark = str(series) == WAGE_BENCHMARK
        fig.add_trace(go.Scatter(
            x=group["Date"],
            y=group[value_column],
            mode="lines",
            name=str(series),
            line={
                "width": 2.2 if is_benchmark else 2.4,
                "dash": "dash" if is_benchmark else "solid",
                "color": SERIES_COLORS.get(str(series), COLORS["slate"]),
            },
            customdata=group[["Value"]].to_numpy(),
            hovertemplate=(
                f"%{{x|%Y-%m}}<br>{series}<br>{hover_label}: $%{{y:,.2f}}"
                + ("<br>Nominal: $%{customdata[0]:,.2f}" if value_column != "Value" else "")
                + "<extra></extra>"
            ),
        ))
    fig.update_yaxes(tickprefix="$", title_text=y_title)
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=62, r=20, t=88, b=38))
    fig.update_layout(legend={"orientation": "h", "y": 1.04, "x": 0, "font": {"color": COLORS["muted"], "size": 10}})
    return add_axis_headroom(
        fig,
        upper=0.15,
        lower=0.04,
    )


def workforce_outcomes_matrix(frame: pd.DataFrame | None, *, height: int = 430):
    """Compare observed demand, mobility, separation, employment, and real earnings.

    Color encodes each measure's position within its own 2020-present history;
    annotations preserve the raw latest value. Layoffs are inverted so a higher
    percentile means lower separation pressure.
    """
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    columns = [
        ("Employment support", "Employment", "Employment YoY", True),
        ("Real earnings support", "Real earnings", "Real earnings YoY", True),
        ("Openings support", "Openings", "Openings rate", False),
        ("Hires support", "Hires", "Hires rate", False),
        ("Quits support", "Mobility", "Quits rate", False),
        ("Low-layoff support", "Low layoffs", "Layoffs rate", False),
    ]
    labels = [DISPLAY_LABELS.get(str(value), str(value)) for value in clean.get("Channel", [])]
    z = []
    text = []
    custom = []
    for _, row in clean.iterrows():
        z_row = []
        text_row = []
        custom_row = []
        for support_col, _, raw_col, signed in columns:
            score = pd.to_numeric(row.get(support_col), errors="coerce")
            raw = pd.to_numeric(row.get(raw_col), errors="coerce")
            z_row.append(float(score) if pd.notna(score) else np.nan)
            if pd.isna(raw):
                text_row.append("—")
            elif signed:
                text_row.append(f"{float(raw):+.1f}%")
            else:
                text_row.append(f"{float(raw):.1f}%")
            custom_row.append([str(row.get("Status", "")), str(row.get("Labor market", "")), raw_col])
        z.append(z_row)
        text.append(text_row)
        custom.append(custom_row)
    fig = go.Figure(go.Heatmap(
        z=z,
        x=[item[1] for item in columns],
        y=labels,
        text=text,
        texttemplate="%{text}",
        textfont={"size": 11},
        customdata=custom,
        zmin=0,
        zmax=100,
        colorscale=[
            [0.0, "rgba(71,85,105,0.25)"],
            [0.5, "rgba(59,130,246,0.55)"],
            [1.0, "rgba(34,197,94,0.9)"],
        ],
        colorbar={
            "title": {"text": "History<br>percentile", "side": "right"},
            "tickvals": [0, 50, 100],
            "ticktext": ["Low", "Typical", "High"],
            "thickness": 12,
            "len": 0.82,
        },
        hovertemplate=(
            "%{y} · %{x}<br>%{customdata[2]}: %{text}"
            "<br>2020-present percentile: %{z:.0f}"
            "<br>%{customdata[0]}"
            "<br>JOLTS market: %{customdata[1]}<extra></extra>"
        ),
        hoverongaps=False,
    ))
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=158, r=84, t=26, b=54))
    fig.update_xaxes(side="bottom", tickangle=0, automargin=True)
    fig.update_yaxes(autorange="reversed", automargin=True)
    return fig


def labor_flow_history(frame: pd.DataFrame | None, metric: str, *, height: int = 420):
    clean = _clean(frame)
    if "Metric" in clean.columns:
        clean = clean.loc[clean["Metric"].astype(str).eq(metric)]
    fig = go.Figure()
    for series, group in clean.groupby("Series", sort=False):
        fig.add_trace(go.Scatter(
            x=group["Date"],
            y=group["Value"],
            mode="lines",
            name=str(series),
            line={"width": 2.4, "color": SERIES_COLORS.get(str(series), COLORS["slate"])},
            hovertemplate=f"%{{x|%Y-%m}}<br>{series}: %{{y:.1f}}%<extra></extra>",
        ))
    fig.update_yaxes(ticksuffix="%", title_text="Rate")
    return add_axis_headroom(
        _base_layout(fig, height=height, legend=True, margin=dict(l=52, r=20, t=24, b=38)),
        upper=0.14,
        lower=0.06,
        include_zero=True,
    )


def occupation_exposure_by_group(frame: pd.DataFrame | None, *, height: int = 430):
    """Show the static task-exposure benchmark without implying employment effects."""
    clean = frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    required = {"Major Occupational Group", "Occupations", "Median direct exposure", "Median LLM + software exposure"}
    if clean.empty or not required.issubset(clean.columns):
        clean = pd.DataFrame(columns=list(required))
    for column in ["Occupations", "Median direct exposure", "Median LLM + software exposure", "High-exposure share"]:
        if column in clean.columns:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
    clean = clean.dropna(subset=["Major Occupational Group", "Median LLM + software exposure"])
    clean = clean.sort_values("Median LLM + software exposure", ascending=True, kind="stable")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=clean.get("Median LLM + software exposure", []),
        y=clean.get("Major Occupational Group", []),
        orientation="h",
        name="LLM + software",
        marker_color=COLORS["violet"],
        customdata=clean[["Median direct exposure", "Occupations", "High-exposure share"]].to_numpy() if not clean.empty else [],
        hovertemplate=(
            "%{y}<br>Median LLM + software exposure: %{x:.1f}%"
            "<br>Median direct-LLM exposure: %{customdata[0]:.1f}%"
            "<br>Occupations in benchmark: %{customdata[1]:.0f}"
            "<br>At least 50% exposed: %{customdata[2]:.1f}%<extra></extra>"
        ),
    ))
    fig.update_xaxes(range=[0, 100], ticksuffix="%", title_text="Unweighted median share of tasks")
    fig.update_yaxes(automargin=True)
    return _base_layout(fig, height=height, legend=False, margin=dict(l=186, r=24, t=22, b=54))
