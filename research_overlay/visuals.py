"""Plotly figures for the professional research overlay."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from helpers.labels import sector_display_name


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
        # Plotly 6 can retain an empty title object from a template or prior
        # figure. In some Streamlit front ends that object renders literally
        # as ``undefined``. Remove the property rather than setting it to None.
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
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{name}: %{{y:.1f}}<extra></extra>",
            )
        )
    if reference is not None:
        fig.add_hline(y=reference, line_dash="dot", line_color="#64748b", opacity=0.75)
    if y_range:
        fig.update_yaxes(range=list(y_range))
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


def financial_conditions_history(history, *, height=275):
    """Plot NFCI as the headline series with ANFCI as a contextual comparator."""
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
        ("Internal Funding Coverage", COLORS["violet"]),
        ("Cash Reserve Coverage", COLORS["blue"]),
        ("Debt Financing Pulse", "#8b5cf6"),
        ("Forward Commitment Load", COLORS["slate"]),
    ]
    frame = history.copy()
    frame["Date"] = pd.to_datetime(frame.get("Date"), errors="coerce", format="mixed")
    frame = frame.loc[frame["Date"].notna()].copy()
    if not frame.empty and years:
        cutoff = frame["Date"].max() - pd.DateOffset(years=years)
        frame = frame.loc[frame["Date"] >= cutoff].copy()
    fig = go.Figure()
    for column, color in specs:
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
                name=column,
                line={"color": color, "width": 2.2},
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{column}: %{{y:.2f}}<extra></extra>",
            )
        )
    fig.add_hline(y=0, line_dash="dot", line_color="#64748b", opacity=0.6)
    fig.add_hline(y=1, line_dash="dot", line_color="#64748b", opacity=0.6)
    return _base_layout(fig, height=330, legend=False, margin=dict(l=42, r=18, t=18, b=36))


def restyle_figure(fig, *, height=None):
    if fig is None:
        return fig
    _base_layout(fig, height=height or getattr(fig.layout, "height", None) or 360)
    fig.layout.pop("title", None)
    return fig


def hhi_component_chart(frame: pd.DataFrame):
    """Show the additive company contributions to raw HHI."""
    if frame is None or frame.empty:
        return _base_layout(go.Figure(), height=285)
    data = frame.copy()
    data["HHI Contribution Share"] = pd.to_numeric(
        data.get("HHI Contribution Share"), errors="coerce"
    )
    data["Market Cap Share"] = pd.to_numeric(
        data.get("Market Cap Share"), errors="coerce"
    )
    data["Raw HHI Contribution"] = pd.to_numeric(
        data.get("Raw HHI Contribution"), errors="coerce"
    )
    data = data.dropna(subset=["HHI Contribution Share"])
    if data.empty:
        return _base_layout(go.Figure(), height=285)

    data = data.iloc[::-1].copy()
    customdata = np.empty((len(data), 2), dtype=object)
    customdata[:, 0] = [
        f"{value * 100:.2f}%" if pd.notna(value) else "n/a"
        for value in data["Market Cap Share"]
    ]
    customdata[:, 1] = [
        f"{value:.5f}" if pd.notna(value) else "n/a"
        for value in data["Raw HHI Contribution"]
    ]
    fig = go.Figure(
        go.Bar(
            x=data["HHI Contribution Share"],
            y=data["Company"].astype(str),
            orientation="h",
            marker_color=COLORS["slate"],
            text=[f"{value:.1f}%" for value in data["HHI Contribution Share"]],
            textposition="outside",
            cliponaxis=False,
            customdata=customdata,
            hovertemplate=(
                "%{y}<br>Share of total HHI: %{x:.2f}%<br>"
                "Market-cap share: %{customdata[0]}<br>"
                "Raw HHI contribution: %{customdata[1]}<extra></extra>"
            ),
        )
    )
    fig.update_xaxes(title="Share of HHI", range=[0, max(100.0, float(data["HHI Contribution Share"].max()) * 1.18)])
    return _base_layout(fig, height=285, margin=dict(l=88, r=54, t=12, b=42))


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
    """Map positive EV/EBIT multiples onto a bounded log display scale.

    Raw profitable-cohort multiples remain unchanged in the analytical data and
    hover text. The transform is used only for chart position and color so a
    high-multiple sector cannot determine the entire cross-sectional scale.
    """
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
    """Return normalized positions labelled in raw EV/EBIT terms."""
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
    """Build Plotly customdata without coercing numeric values to strings."""
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
    """Cross-sector repricing relative to profitable operating-earnings support."""
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


# Backward-compatible alias for earlier overlay imports.
def earnings_supported_repricing_map(macro_df: pd.DataFrame):
    return earnings_support_map(macro_df)


def speculative_load_matrix(macro_df: pd.DataFrame):
    """Abnormal trading pressure relative to sector equity support."""
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


# Backward-compatible alias for earlier overlay imports.
def pressure_burden_matrix(macro_df: pd.DataFrame):
    return speculative_load_matrix(macro_df)
