"""Plotly visualization utilities used throughout the AI Macro Dashboard."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from helpers.labels import sector_display_name


GAUGE_COLORS = [
    "#111827",
    "#172554",
    "#1e3a8a",
    "#1d4ed8",
    "#2563eb",
    "#4f46e5",
    "#6d28d9",
    "#7c3aed",
    "#a78bfa",
    "#ddd6fe",
]


def safe_gauge_value(value, default=None):
    """Return a finite gauge value or the caller-provided missing sentinel.

    Rendering code must decide whether to draw a gauge. Missing values are not
    converted to zero.
    """
    numeric = pd.to_numeric(value, errors="coerce")
    return float(numeric) if pd.notna(numeric) and np.isfinite(numeric) else default


def gauge_gradient_steps(start, end, colors, repeats=1):
    expanded = []
    for color in colors:
        expanded.extend([color] * repeats)

    step_size = (end - start) / len(expanded)
    return [
        {
            "range": [start + i * step_size, start + (i + 1) * step_size],
            "color": color,
        }
        for i, color in enumerate(expanded)
    ]


def _build_gauge(value, title, *, axis_range=(0, 100), suffix=""):
    value = safe_gauge_value(value)
    if value is None:
        raise ValueError(f"Cannot build {title!r} gauge from missing data")

    axis_min, axis_max = axis_range
    axis_mid = (axis_min + axis_max) / 2
    tick_values = [axis_min, axis_mid, axis_max]
    tick_text = [f"{value:g}" for value in tick_values]

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        number={"suffix": suffix},
        title={"text": title},
        domain={"x": [0.08, 0.92], "y": [0.0, 1.0]},
        gauge={
            "axis": {
                "range": list(axis_range),
                "tickmode": "array",
                "tickvals": tick_values,
                "ticktext": tick_text,
            },
            "bar": {"color": "#a78bfa"},
            "steps": gauge_gradient_steps(
                axis_range[0],
                axis_range[1],
                GAUGE_COLORS,
                repeats=5,
            ),
        },
    ))
    fig.update_layout(
        height=300,
        margin=dict(l=35, r=35, t=60, b=20),
        autosize=True,
        paper_bgcolor="rgba(0,0,0,0)",
        font={"color": "#e5e7eb"},
    )
    return fig


def build_equity_gauge(value):
    return _build_gauge(value, "AI Equity Index")


def build_development_gauge(value):
    return _build_gauge(value, "AI Development Intensity")


def build_power_stress_gauge(value):
    return _build_gauge(value, "Power Stress Index", axis_range=(-100, 100))


def build_concentration_gauge(value):
    return _build_gauge(value, "Concentration HHI")


def build_capital_stress_gauge(value):
    return _build_gauge(value, "Capital Stress", axis_range=(-100, 100))


def build_intermediation_stress_gauge(value):
    return _build_gauge(
        value,
        "Credit Intermediation Stress",
        axis_range=(-100, 100),
    )


def _clean_history_frame(history):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])

    out = history.copy()
    if "Date" not in out.columns or "Value" not in out.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    return (
        out.dropna(subset=["Date", "Value"])
        .sort_values("Date", kind="stable")
        .drop_duplicates(subset=["Date"], keep="last")
        .reset_index(drop=True)
    )


def build_nfci_sparkline(history, months=12):
    """Compact NFCI line for the confirmation strip."""
    clean = _clean_history_frame(history)
    if not clean.empty:
        cutoff = clean["Date"].max() - pd.DateOffset(months=months)
        recent = clean.loc[clean["Date"] >= cutoff].copy()
        if not recent.empty:
            clean = recent

    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(go.Scatter(
            x=clean["Date"],
            y=clean["Value"],
            mode="lines",
            line={"width": 3, "color": "#60a5fa"},
            hovertemplate="%{x|%Y-%m-%d}<br>NFCI %{y:+.3f}<extra></extra>",
        ))

    fig.add_hline(y=0, line_dash="dot", line_color="#64748b", opacity=0.8)
    fig.update_layout(
        height=118,
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        font={"color": "#e5e7eb"},
        xaxis={"visible": False, "type": "date"},
        yaxis={"visible": False, "fixedrange": True},
    )
    return fig


def build_nfci_history(history):
    """Full NFCI history with the long-run average reference at zero."""
    clean = _clean_history_frame(history)
    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(go.Scatter(
            x=clean["Date"],
            y=clean["Value"],
            mode="lines",
            name="NFCI",
            line={"width": 2.5, "color": "#60a5fa"},
            fill="tozeroy",
            fillcolor="rgba(96,165,250,0.12)",
            hovertemplate="%{x|%Y-%m-%d}<br>NFCI %{y:+.3f}<extra></extra>",
        ))
    else:
        fig.add_annotation(
            text="NFCI history is unavailable",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#9ca3af"},
        )

    fig.add_hline(
        y=0,
        line_dash="dot",
        line_color="#94a3b8",
        opacity=0.9,
        annotation_text="Long-run average",
        annotation_position="top left",
    )
    fig.update_layout(
        title={"text": "National Financial Conditions Index History", "font": {"size": 16}},
        height=330,
        margin=dict(l=45, r=15, t=50, b=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.45)",
        font={"color": "#e5e7eb"},
        showlegend=False,
        xaxis={"title": None, "gridcolor": "#374151", "type": "date"},
        yaxis={"title": "NFCI", "gridcolor": "#374151", "tickformat": "+.2f"},
    )
    return fig


def _adaptive_history_range(values, bounds, min_span=20.0, padding_fraction=0.12):
    """Return a readable local range while respecting the metric's full bounds."""
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return list(bounds) if bounds is not None else None

    data_min = float(clean.min())
    data_max = float(clean.max())
    span = data_max - data_min
    target_span = max(float(min_span), span * (1.0 + 2.0 * padding_fraction))
    center = (data_min + data_max) / 2.0
    lower = center - target_span / 2.0
    upper = center + target_span / 2.0

    if bounds is None:
        return [lower, upper]

    bound_min, bound_max = map(float, bounds)
    if lower < bound_min:
        upper += bound_min - lower
        lower = bound_min
    if upper > bound_max:
        lower -= upper - bound_max
        upper = bound_max

    lower = max(bound_min, lower)
    upper = min(bound_max, upper)
    if upper <= lower:
        return [bound_min, bound_max]
    return [lower, upper]


def build_metric_history(
    trend,
    title,
    *,
    y_range=None,
    adaptive_range=False,
    min_span=20.0,
    step=False,
    flat_annotation=None,
):
    history = (trend or {}).get("history")
    fig = go.Figure()
    clean_history = pd.DataFrame()

    if history is not None and not history.empty:
        clean_history = history.copy()
        clean_history["Date"] = pd.to_datetime(
            clean_history["Date"], errors="coerce", format="mixed"
        )
        clean_history["Value"] = pd.to_numeric(
            clean_history["Value"], errors="coerce"
        ).replace([np.inf, -np.inf], np.nan)
        clean_history = clean_history.dropna(subset=["Date", "Value"])

        line = {"width": 3, "color": "#a78bfa"}
        if step:
            line["shape"] = "hv"

        fig.add_trace(go.Scatter(
            x=clean_history["Date"],
            y=clean_history["Value"],
            mode="lines+markers",
            name=title,
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}<extra></extra>",
            line=line,
            marker={"size": 6},
        ))

    fig.update_layout(
        title={"text": f"{title} History", "font": {"size": 16}},
        height=300,
        margin=dict(l=45, r=15, t=50, b=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.45)",
        font={"color": "#e5e7eb"},
        showlegend=False,
        xaxis={
            "title": None,
            "gridcolor": "#374151",
            "type": "date",
            "tickformat": "%Y-%m-%d",
            "hoverformat": "%Y-%m-%d",
        },
        yaxis={"title": None, "gridcolor": "#374151", "tickformat": ".1f"},
    )

    if adaptive_range and not clean_history.empty:
        local_range = _adaptive_history_range(
            clean_history["Value"], y_range, min_span=min_span
        )
        if local_range is not None:
            fig.update_yaxes(range=local_range)
    elif y_range is not None:
        fig.update_yaxes(range=list(y_range))

    if y_range is not None and float(y_range[0]) < 0 < float(y_range[1]):
        fig.add_hline(y=0, line_dash="dot", line_color="#6b7280", opacity=0.8)

    if clean_history.empty:
        fig.add_annotation(
            text="History begins with the first valid archived observation",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#9ca3af"},
        )
    elif clean_history["Value"].nunique(dropna=True) == 1 and flat_annotation:
        fig.add_annotation(
            text=flat_annotation,
            x=0.5,
            y=0.08,
            xref="paper",
            yref="paper",
            showarrow=False,
            bgcolor="rgba(17,24,39,0.82)",
            bordercolor="#4b5563",
            borderwidth=1,
            font={"color": "#d1d5db", "size": 11},
        )

    return fig


def build_component_score_chart(components, title="Component Scores", *, x_range=(0, 100)):
    names = []
    values = []

    for name, payload in (components or {}).items():
        score = pd.to_numeric((payload or {}).get("score", np.nan), errors="coerce")
        if pd.notna(score) and np.isfinite(score):
            names.append(name)
            values.append(float(score))

    fig = go.Figure()
    if names:
        fig.add_trace(go.Bar(
            x=values,
            y=names,
            orientation="h",
            text=[f"{value:.0f}" for value in values],
            textposition="auto",
            marker={"color": "#7c3aed"},
            hovertemplate="%{y}: %{x:.1f}<extra></extra>",
        ))

    fig.update_layout(
        title={"text": title, "font": {"size": 16}},
        height=300,
        margin=dict(l=20, r=20, t=50, b=35),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(17,24,39,0.45)",
        font={"color": "#e5e7eb"},
        showlegend=False,
        xaxis={"range": list(x_range), "gridcolor": "#374151", "title": None, "zeroline": True},
        yaxis={"title": None, "autorange": "reversed"},
    )

    if not names:
        fig.add_annotation(
            text="No valid component scores",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"color": "#9ca3af"},
        )

    return fig


def build_positioning_map(macro_df):
    fig = go.Figure()

    pressure_size = pd.to_numeric(macro_df["Pressure"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    pressure_size = (
        pd.Series(50, index=macro_df.index)
        if pressure_size.notna().sum() == 0
        else pressure_size.fillna(pressure_size.median())
    )

    fig.add_trace(go.Scatter(
        x=macro_df["Forward P/E"],
        y=macro_df["Avg Return"] * 100,
        mode="markers",
        hovertemplate=(
            "<b>%{text}</b><br>Forward P/E: %{x:.1f}<br>"
            "1Y Return: %{y:.1f}%<extra></extra>"
        ),
        text=macro_df["Sector"].apply(sector_display_name),
        marker=dict(
            size=np.clip(pressure_size / 4, 8, 22),
            color=macro_df["Sector Score"],
            colorscale="Viridis",
            opacity=0.78,
            showscale=True,
            colorbar=dict(title="AEI"),
        ),
    ))

    fig.update_layout(
        xaxis_title="Forward P/E",
        yaxis_title="1Y Return (%)",
        template="plotly_dark",
        height=500,
    )

    x_series = pd.to_numeric(macro_df["Forward P/E"], errors="coerce")
    y_series = pd.to_numeric(macro_df["Avg Return"], errors="coerce") * 100
    if x_series.notna().any() and y_series.notna().any():
        fig.add_vline(x=x_series.median(), line_dash="dot")
        fig.add_hline(y=y_series.median(), line_dash="dot")

    return fig


def build_rotation_matrix(macro_df):
    fig = go.Figure()

    return_size = pd.to_numeric(macro_df["Avg Return"], errors="coerce").replace(
        [np.inf, -np.inf], np.nan
    )
    size_base = abs(return_size * 100) / 2
    size_base = (
        pd.Series(18, index=macro_df.index)
        if size_base.notna().sum() == 0
        else size_base.fillna(size_base.median())
    )

    fig.add_trace(go.Scatter(
        x=macro_df["Sector Score"],
        y=macro_df["Pressure"],
        mode="markers",
        text=macro_df["Sector"].apply(sector_display_name),
        hovertemplate=(
            "<b>%{text}</b><br>AEI: %{x:.0f}<br>"
            "Pressure: %{y:.0f}<extra></extra>"
        ),
        marker=dict(
            size=np.clip(size_base, 10, 30),
            color=macro_df["Forward P/E"],
            colorscale="Viridis",
            opacity=0.78,
            showscale=True,
            colorbar=dict(title="F P/E"),
        ),
    ))

    fig.update_layout(
        xaxis_title="AI Equity Index",
        yaxis_title="Trading Pressure",
        template="plotly_dark",
        height=500,
    )

    aei_mid = pd.to_numeric(macro_df["Sector Score"], errors="coerce").median()
    pressure_mid = pd.to_numeric(macro_df["Pressure"], errors="coerce").median()

    if pd.notna(aei_mid) and pd.notna(pressure_mid):
        fig.add_vline(x=aei_mid, line_dash="dot")
        fig.add_hline(y=pressure_mid, line_dash="dot")

    return fig


def factor_color(score):
    if pd.isna(score):
        return "#374151"
    if score < 25:
        return "#2563eb"
    if score < 50:
        return "#60a5fa"
    if score < 75:
        return "#bfdbfe"
    return "#ffffff"
