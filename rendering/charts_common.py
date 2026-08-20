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


def _nice_step(span: float, target_ticks: int = 5) -> float:
    """Return a human-friendly axis interval for the supplied span."""
    if not np.isfinite(span) or span <= 0:
        return 1.0
    raw = float(span) / max(int(target_ticks), 2)
    magnitude = 10.0 ** np.floor(np.log10(raw))
    normalized = raw / magnitude
    for candidate in (1.0, 2.0, 2.5, 5.0, 10.0):
        if normalized <= candidate:
            return float(candidate * magnitude)
    return float(10.0 * magnitude)


def _nice_axis_range(minimum: float, maximum: float, *, upper: float, lower: float, include_zero: bool, target_ticks: int = 5) -> tuple[float, float, float]:
    """Build padded bounds that leave a visible reference line beyond the data."""
    if include_zero:
        minimum = min(float(minimum), 0.0)
        maximum = max(float(maximum), 0.0)
    span = float(maximum - minimum)
    if not np.isfinite(span) or span <= 0:
        span = max(abs(float(maximum)), abs(float(minimum)), 1.0)
    step = _nice_step(span, target_ticks=target_ticks)
    padded_min = float(minimum) - span * float(lower)
    padded_max = float(maximum) + span * float(upper)
    lower_bound = np.floor(padded_min / step) * step
    upper_bound = np.ceil(padded_max / step) * step

    # Ensure at least one full grid interval remains beyond the extreme value.
    if upper_bound - float(maximum) < step * 0.45:
        upper_bound += step
    if float(minimum) - lower_bound < step * 0.20 and minimum < 0:
        lower_bound -= step
    if minimum >= 0:
        lower_bound = 0.0 if include_zero or padded_min <= 0 else max(0.0, lower_bound)
    if maximum <= 0:
        upper_bound = 0.0 if include_zero else min(0.0, upper_bound)
    return float(lower_bound), float(upper_bound), float(step)


def add_axis_headroom(
    fig,
    *,
    axis="y",
    upper=0.14,
    lower=0.05,
    extra_values=None,
    include_zero=False,
):
    values = []
    for trace in fig.data:
        raw = getattr(trace, axis, None)
        if raw is None:
            continue
        numeric = pd.to_numeric(pd.Series(list(raw)), errors="coerce").replace(
            [np.inf, -np.inf], np.nan
        ).dropna()
        values.extend(numeric.astype(float).tolist())
    for value in extra_values or []:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric) and np.isfinite(numeric):
            values.append(float(numeric))
    if include_zero:
        values.append(0.0)
    if not values:
        return fig

    minimum = float(min(values))
    maximum = float(max(values))
    lower_bound, upper_bound, step = _nice_axis_range(
        minimum, maximum, upper=upper, lower=lower, include_zero=include_zero
    )

    updater = fig.update_yaxes if axis == "y" else fig.update_xaxes
    updater(range=[lower_bound, upper_bound], dtick=step)
    return fig

def add_stacked_axis_headroom(
    fig,
    *,
    upper=0.10,
    lower=0.10,
    include_zero=True,
):
    """Size a bar-chart value axis from cumulative stack totals.

    Plotly's ordinary trace-based autorange helpers see each bar segment in
    isolation.  Stacked and relative bars need the positive and negative
    segments summed by category before a safe range can be calculated.
    """
    totals = {}
    value_axis = "y"

    for trace in fig.data:
        if getattr(trace, "type", None) != "bar":
            continue
        orientation = getattr(trace, "orientation", None) or "v"
        if orientation == "h":
            categories = getattr(trace, "y", None)
            values = getattr(trace, "x", None)
            value_axis = "x"
        else:
            categories = getattr(trace, "x", None)
            values = getattr(trace, "y", None)
            value_axis = "y"
        if categories is None or values is None:
            continue

        for category, raw_value in zip(list(categories), list(values)):
            value = pd.to_numeric(raw_value, errors="coerce")
            if pd.isna(value) or not np.isfinite(value):
                continue
            positive, negative = totals.get(str(category), (0.0, 0.0))
            value = float(value)
            if value >= 0:
                positive += value
            else:
                negative += value
            totals[str(category)] = (positive, negative)

    if not totals:
        return fig

    maximum = max(positive for positive, _ in totals.values())
    minimum = min(negative for _, negative in totals.values())
    if include_zero:
        maximum = max(maximum, 0.0)
        minimum = min(minimum, 0.0)

    lower_bound, upper_bound, step = _nice_axis_range(
        minimum, maximum, upper=upper, lower=lower, include_zero=include_zero
    )
    updater = fig.update_yaxes if value_axis == "y" else fig.update_xaxes
    updater(range=[lower_bound, upper_bound], dtick=step)
    return fig


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
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=42, r=18, t=26, b=36))
    if y_range:
        return fig
    return add_axis_headroom(
        fig,
        axis="y",
        upper=0.14,
        lower=0.06,
        extra_values=[reference] if reference is not None else None,
    )

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
    fig = _base_layout(fig, height=height, margin=dict(l=42, r=18, t=18, b=34))
    if y_range:
        return fig
    return add_axis_headroom(
        fig,
        axis="y",
        upper=0.14,
        lower=0.06,
        extra_values=[reference] if reference is not None else None,
    )
