from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.labels import sector_display_name
from rendering.charts_common import COLORS, _base_layout

def sector_factor_chart(scored_factors: pd.DataFrame):
    if scored_factors is None or scored_factors.empty:
        return _base_layout(go.Figure(), height=245)
    frame = scored_factors.copy()
    frame["Score"] = pd.to_numeric(frame.get("Score"), errors="coerce")
    frame["Raw Value"] = pd.to_numeric(frame.get("Raw Value"), errors="coerce")
    frame = frame.dropna(subset=["Score"])
    order_map = {
        "Forward EBIT-Yield Valuation": 0,
        "1Y Relative Return": 1,
        "Relative Performance": 1,
        "Market Breadth": 2,
    }
    if "Factor" in frame.columns:
        frame["__order"] = frame["Factor"].map(lambda value: order_map.get(str(value), 99))
        frame = frame.sort_values(["__order", "Factor"], kind="stable")
    labels = frame.get("Factor", pd.Series(dtype=str)).astype(str)

    def raw_text(label, value):
        if pd.isna(value):
            return "n/a"
        lowered = str(label).lower()
        if "relative return" in lowered or "relative performance" in lowered:
            return f"{value * 100:+.2f} pp"
        if "valuation" in lowered or "yield" in lowered:
            return f"{value * 100:+.2f} pp"
        if "breadth" in lowered:
            return f"{value * 100:.2f}%"
        return f"{value:.4f}"

    raw_labels = [raw_text(label, value) for label, value in zip(labels, frame["Raw Value"])]
    fig = go.Figure(
        go.Bar(
            x=frame["Score"],
            y=labels,
            orientation="h",
            marker_color=COLORS["violet"],
            text=[f"{value:.2f}" for value in frame["Score"]],
            textposition="outside",
            cliponaxis=False,
            customdata=np.array(raw_labels, dtype=object).reshape(-1, 1),
            hovertemplate="%{y}<br>Normalized score %{x:.2f}<br>Raw %{customdata[0]}<extra></extra>",
        )
    )
    fig.update_xaxes(range=[0, 100])
    return _base_layout(fig, height=245, margin=dict(l=210, r=52, t=12, b=28))

def pressure_component_chart(components: pd.DataFrame):
    if components is None or components.empty:
        return _base_layout(go.Figure(), height=285)
    frame = components.copy()
    frame["Score"] = pd.to_numeric(frame.get("Score"), errors="coerce")
    order_map = {"Valuation Stretch": 0, "Price Extension": 1, "Momentum Acceleration": 2, "Volatility Expansion": 3, "Volume Activity": 4}
    if "Component" in frame.columns:
        frame["__order"] = frame["Component"].map(lambda value: order_map.get(str(value), 99))
    frame = frame.dropna(subset=["Score"]).sort_values("__order", kind="stable")
    fig = go.Figure(
        go.Bar(
            x=frame["Score"],
            y=frame["Component"],
            orientation="h",
            marker_color=COLORS["blue"],
            text=[f"{value:.0f}" for value in frame["Score"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>Score %{x:.1f}<extra></extra>",
        )
    )
    fig.update_xaxes(range=[0, 100])
    return _base_layout(fig, height=285, margin=dict(l=175, r=42, t=12, b=28))

def _bounded_positive_log_normalize(values, quantile=0.90):
    numeric = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    numeric = numeric.where(numeric > 0)
    transformed = np.log1p(numeric)
    finite = transformed.dropna()

    if finite.empty:
        cap = float(np.log1p(20.0))
    else:
        cap = float(finite.quantile(quantile))
        cap = max(cap, float(np.log1p(20.0)))

    normalized = (transformed / cap).clip(0.0, 1.0)
    return normalized, cap

def _bounded_positive_log_tick_spec(cap):
    positions = [0.0, 0.25, 0.50, 0.75, 1.0]
    raw_values = [float(np.expm1(position * cap)) for position in positions]

    def label(value, edge=False):
        if value >= 100:
            rendered = f"{value:.0f}"
        elif value >= 10:
            rendered = f"{value:.1f}"
        else:
            rendered = f"{value:.2f}"
        return f"≥{rendered}" if edge else rendered

    labels = [
        "0",
        label(raw_values[1]),
        label(raw_values[2]),
        label(raw_values[3]),
        label(raw_values[4], edge=True),
    ]
    return positions, labels

def _loss_share_marker_sizes(values):
    share = pd.to_numeric(values, errors="coerce").clip(0.0, 1.0)
    return (10.0 + 24.0 * np.sqrt(share.fillna(0.0))).clip(10.0, 34.0)

def _hover_number(value, *, digits=2, signed=False, suffix=""):
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.isna(numeric) or not np.isfinite(numeric):
        return "n/a"
    spec = f"+.{digits}f" if signed else f".{digits}f"
    return f"{numeric:{spec}}{suffix}"

def _typed_customdata(*columns):
    if not columns:
        return np.empty((0, 0), dtype=object)
    length = len(columns[0])
    out = np.empty((length, len(columns)), dtype=object)
    for index, column in enumerate(columns):
        values = column.tolist() if hasattr(column, "tolist") else list(column)
        if len(values) != length:
            raise ValueError("Customdata columns must have equal length")
        out[:, index] = values
    return out

def earnings_support_map(macro_df: pd.DataFrame):
    fig = go.Figure()
    if macro_df is None or macro_df.empty:
        return _base_layout(fig, height=390)

    frame = macro_df.copy()
    frame["Forward EV/EBIT"] = pd.to_numeric(frame.get("Forward EV/EBIT"), errors="coerce")
    frame["Loss-Making EV Share"] = pd.to_numeric(frame.get("Loss-Making EV Share"), errors="coerce")
    frame["Avg Return"] = pd.to_numeric(frame.get("Avg Return"), errors="coerce")
    frame["Sector Score"] = pd.to_numeric(frame.get("Sector Score"), errors="coerce")
    frame["Pressure"] = pd.to_numeric(frame.get("Pressure"), errors="coerce")
    frame = frame.dropna(subset=["Forward EV/EBIT", "Avg Return"])
    frame = frame.loc[frame["Forward EV/EBIT"] > 0].copy()

    if frame.empty:
        return _base_layout(fig, height=390)

    multiple = frame["Forward EV/EBIT"]
    return_pct = frame["Avg Return"] * 100.0
    x_max = float(multiple.max()) if multiple.notna().any() else 10.0
    x_max = max(x_max * 1.08, 10.0)
    earnings_support_bps = frame["Avg Return"] / multiple * 10000.0
    sector_names = frame["Sector"].apply(sector_display_name)
    loss_share = frame["Loss-Making EV Share"].clip(0.0, 1.0)

    fig.add_trace(
        go.Scatter(
            x=multiple,
            y=return_pct,
            mode="markers",
            marker={
                "size": _loss_share_marker_sizes(loss_share),
                "color": frame["Sector Score"],
                "colorscale": "Viridis",
                "cmin": 0,
                "cmax": 100,
                "opacity": 0.84,
                "line": {"width": 1.0, "color": "rgba(226,232,240,0.45)"},
                "showscale": True,
                "colorbar": {"title": "AEI"},
            },
            customdata=_typed_customdata(
                sector_names,
                multiple.map(lambda value: _hover_number(value, suffix="x")),
                return_pct.map(lambda value: _hover_number(value, signed=True, suffix="%")),
                frame["Pressure"].map(lambda value: _hover_number(value)),
                earnings_support_bps.map(lambda value: _hover_number(value, signed=True, suffix=" bp")),
                (loss_share * 100.0).map(lambda value: _hover_number(value, suffix="%")),
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>FWD EV/EBIT: %{customdata[1]}<br>"
                "1Y Return: %{customdata[2]}<br>Trading Pressure: %{customdata[3]}<br>"
                "Earnings Support: %{customdata[4]}<br>Loss-Making EV Share: %{customdata[5]}"
                "<extra></extra>"
            ),
        )
    )
    fig.add_hline(y=0, line_dash="dot", line_color="#64748b", opacity=0.85)
    fig.update_xaxes(
        title="Forward EV/EBIT",
        range=[0.0, x_max],
    )
    fig.update_yaxes(title="1Y Return")
    return _base_layout(fig, height=390, margin=dict(l=52, r=24, t=18, b=48))

def speculative_load_matrix(macro_df: pd.DataFrame):
    fig = go.Figure()
    if macro_df is None or macro_df.empty:
        return _base_layout(fig, height=390)

    frame = macro_df.copy()
    frame["Sector Score"] = pd.to_numeric(frame.get("Sector Score"), errors="coerce")
    frame["Pressure"] = pd.to_numeric(frame.get("Pressure"), errors="coerce")
    frame["Avg Return"] = pd.to_numeric(frame.get("Avg Return"), errors="coerce")
    frame["Forward EV/EBIT"] = pd.to_numeric(frame.get("Forward EV/EBIT"), errors="coerce")
    frame["Loss-Making EV Share"] = pd.to_numeric(frame.get("Loss-Making EV Share"), errors="coerce")
    frame = frame.dropna(subset=["Sector Score", "Pressure"])
    if frame.empty:
        return _base_layout(fig, height=390)

    load = np.where(
        frame["Sector Score"] > 0,
        frame["Pressure"] / frame["Sector Score"],
        np.nan,
    )
    sector_names = frame["Sector"].apply(sector_display_name)
    loss_share = frame["Loss-Making EV Share"].clip(0.0, 1.0)
    normalized_multiple, multiple_cap = _bounded_positive_log_normalize(frame["Forward EV/EBIT"])
    color_tickvals, color_ticktext = _bounded_positive_log_tick_spec(multiple_cap)

    fig.add_trace(
        go.Scatter(
            x=frame["Sector Score"],
            y=frame["Pressure"],
            mode="markers",
            marker={
                "size": _loss_share_marker_sizes(loss_share),
                "color": normalized_multiple,
                "colorscale": "Viridis",
                "cmin": 0.0,
                "cmax": 1.0,
                "opacity": 0.84,
                "line": {"width": 1.0, "color": "rgba(226,232,240,0.45)"},
                "showscale": True,
                "colorbar": {
                    "title": "FWD EV/EBIT",
                    "tickmode": "array",
                    "tickvals": color_tickvals,
                    "ticktext": color_ticktext,
                },
            },
            customdata=_typed_customdata(
                sector_names,
                pd.Series(load, index=frame.index).map(lambda value: _hover_number(value, suffix="x")),
                frame["Avg Return"].mul(100.0).map(lambda value: _hover_number(value, signed=True, suffix="%")),
                frame["Forward EV/EBIT"].map(lambda value: _hover_number(value, suffix="x")),
                frame["Sector Score"].map(lambda value: _hover_number(value)),
                frame["Pressure"].map(lambda value: _hover_number(value)),
                (loss_share * 100.0).map(lambda value: _hover_number(value, suffix="%")),
            ),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>AEI: %{customdata[4]}<br>"
                "Trading Pressure: %{customdata[5]}<br>FWD EV/EBIT: %{customdata[3]}<br>"
                "Speculative Load: %{customdata[1]}<br>1Y Return: %{customdata[2]}<br>"
                "Loss-Making EV Share: %{customdata[6]}<extra></extra>"
            ),
        )
    )
    fig.add_shape(
        type="line",
        x0=0,
        y0=0,
        x1=100,
        y1=100,
        line={"color": "#94a3b8", "dash": "dot", "width": 1.4},
    )
    fig.update_xaxes(title="AI Equity Index", range=[0, 100])
    fig.update_yaxes(title="Trading Pressure", range=[0, 100])
    return _base_layout(fig, height=390, margin=dict(l=52, r=24, t=18, b=48))
