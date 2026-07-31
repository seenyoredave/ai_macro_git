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


def debt_market_history(history, *, height=315, years=10):
    """Plot the New York Fed market, investment-grade, and high-yield CMDI."""
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




FACILITY_SIZE_METRICS = {
    "Facility count": None,
    "Square feet": "Square Feet",
    "Planned data-center capacity": "Planned Data Center Capacity MW",
    "Contracted utility capacity": "Contracted Utility Capacity MW",
    "Energized capacity": "Energized Capacity MW",
    "Annual electricity consumption": "Annual Electricity Consumption MWh",
    "Water withdrawal": "Water Withdrawal Gallons/Year",
    "Water consumption": "Water Consumption Gallons/Year",
}


def _bubble_sizes(values: pd.Series, *, minimum: float = 6.0, maximum: float = 30.0) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.where(numeric > 0)
    if valid.notna().sum() <= 1:
        return pd.Series(np.where(valid.notna(), (minimum + maximum) / 2.0, minimum), index=values.index)
    transformed = np.sqrt(valid)
    lower = transformed.min()
    upper = transformed.quantile(0.95)
    if pd.isna(upper) or upper <= lower:
        upper = transformed.max()
    if pd.isna(upper) or upper <= lower:
        return pd.Series(np.where(valid.notna(), (minimum + maximum) / 2.0, minimum), index=values.index)
    scaled = minimum + (transformed.clip(upper=upper) - lower) / (upper - lower) * (maximum - minimum)
    return scaled.fillna(minimum)


def _facility_hover(row: pd.Series, metric_column: str | None = None, metric_label: str | None = None) -> str:
    facility = str(row.get("Facility") or "Unnamed facility")
    operator = str(row.get("Operator") or "Operator not reported")
    place = ", ".join(part for part in [str(row.get("County") or ""), str(row.get("State") or "")] if part)
    status = str(row.get("Status") or "Status unknown")
    evidence = str(row.get("Evidence Grade") or "Evidence not graded")
    precision = str(row.get("Location Precision") or "Location precision not reported")
    lines = [facility, operator, place, f"Status: {status}", f"Evidence: {evidence}", f"Location: {precision}"]
    if metric_column:
        value = pd.to_numeric(row.get(metric_column), errors="coerce")
        if pd.notna(value):
            if "Gallons" in metric_column:
                rendered = f"{value:,.0f} gal/year"
            elif "MWh" in metric_column:
                rendered = f"{value:,.0f} MWh/year"
            elif "MW" in metric_column:
                rendered = f"{value:,.0f} MW"
            elif metric_column == "Square Feet":
                rendered = f"{value:,.0f} sq ft"
            else:
                rendered = f"{value:,.2f}"
            lines.append(f"{metric_label or metric_column}: {rendered}")
        else:
            lines.append(f"{metric_label or metric_column}: unavailable")
    return "<br>".join(lines)


def data_center_map(
    locations: pd.DataFrame | None,
    *,
    size_by: str = "Facility count",
    height: int = 510,
):
    """Map evidence-graded data-center records using one homogeneous size field.

    Records missing the selected field remain visible as small outlined markers;
    they are never treated as zero and never sized from a different metric.
    """
    required = {"Latitude", "Longitude"}
    if locations is None or not isinstance(locations, pd.DataFrame) or locations.empty or not required.issubset(locations.columns):
        clean = pd.DataFrame(columns=["Latitude", "Longitude", "Facility", "Operator", "County", "State"])
    else:
        clean = locations.copy()
        for column in ["Latitude", "Longitude"]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        for column in ["Facility", "Operator", "County", "State", "Status", "Evidence Grade", "Location Precision"]:
            if column not in clean.columns:
                clean[column] = ""
            clean[column] = clean[column].fillna("").astype(str)
        clean = clean.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)

    metric_column = FACILITY_SIZE_METRICS.get(size_by)
    figure = go.Figure()
    if not clean.empty:
        if metric_column is None:
            clean["_known"] = True
            clean["_marker_size"] = 6.0
        else:
            if metric_column not in clean.columns:
                clean[metric_column] = np.nan
            clean[metric_column] = pd.to_numeric(clean[metric_column], errors="coerce")
            clean["_known"] = clean[metric_column].notna() & (clean[metric_column] > 0)
            clean["_marker_size"] = _bubble_sizes(clean[metric_column])

        known = clean.loc[clean["_known"]].copy()
        unknown = clean.loc[~clean["_known"]].copy()
        if not known.empty:
            figure.add_trace(
                go.Scattergeo(
                    lon=known["Longitude"],
                    lat=known["Latitude"],
                    text=[_facility_hover(row, metric_column, size_by) for _, row in known.iterrows()],
                    mode="markers",
                    hovertemplate="%{text}<extra></extra>",
                    marker={
                        "size": known["_marker_size"],
                        "color": COLORS["violet"],
                        "opacity": 0.70,
                        "line": {"width": 0.45, "color": "#111827"},
                        "sizemode": "diameter",
                    },
                    name="Metric available" if metric_column else "Facility records",
                )
            )
        if not unknown.empty:
            figure.add_trace(
                go.Scattergeo(
                    lon=unknown["Longitude"],
                    lat=unknown["Latitude"],
                    text=[_facility_hover(row, metric_column, size_by) for _, row in unknown.iterrows()],
                    mode="markers",
                    hovertemplate="%{text}<extra></extra>",
                    marker={
                        "size": 6.0,
                        "color": "rgba(15,23,42,0.30)",
                        "opacity": 0.86,
                        "line": {"width": 1.25, "color": COLORS["slate"]},
                    },
                    name="Metric unavailable",
                )
            )
    figure.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=bool(metric_column),
        legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"color": COLORS["muted"], "size": 11}},
        font={"color": COLORS["text"], "family": "Inter, ui-sans-serif, system-ui"},
        hoverlabel={"bgcolor": "#0f172a", "font": {"color": COLORS["text"]}},
        geo={
            "scope": "usa",
            "projection": {"type": "albers usa"},
            "bgcolor": "rgba(0,0,0,0)",
            "showland": True,
            "landcolor": "rgba(30,41,59,0.72)",
            "showlakes": True,
            "lakecolor": "rgba(15,23,42,0.78)",
            "showsubunits": True,
            "subunitcolor": "rgba(148,163,184,0.28)",
            "subunitwidth": 0.65,
            "showcountries": False,
            "showcoastlines": False,
        },
    )
    return figure


def water_availability_context_map(
    water: pd.DataFrame | None,
    geojson: dict | None,
    facilities: pd.DataFrame | None = None,
    *,
    height: int = 560,
):
    """Display a physical surface-water context layer without legal inference."""
    required = {"HUC8", "Median SUI"}
    if water is None or not isinstance(water, pd.DataFrame) or water.empty or not required.issubset(water.columns):
        clean = pd.DataFrame(columns=["HUC8", "Median SUI", "P75 SUI", "HUC12 Count", "Watershed"])
    else:
        clean = water.copy()
        clean["HUC8"] = clean["HUC8"].astype(str).str.zfill(8)
        for column in ["Median SUI", "P75 SUI", "HUC12 Count"]:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        if "Watershed" not in clean.columns:
            clean["Watershed"] = ""
        clean = clean.dropna(subset=["Median SUI"])

    figure = go.Figure()
    if not clean.empty and isinstance(geojson, dict) and geojson.get("features"):
        custom = np.column_stack(
            [
                clean["Watershed"].fillna(""),
                clean["P75 SUI"],
                clean["HUC12 Count"],
            ]
        )
        figure.add_trace(
            go.Choropleth(
                geojson=geojson,
                locations=clean["HUC8"],
                z=clean["Median SUI"],
                featureidkey="properties.huc8",
                zmin=0,
                zmax=1,
                colorscale=[
                    [0.00, "#0f766e"],
                    [0.25, "#34d399"],
                    [0.50, "#fbbf24"],
                    [0.75, "#fb923c"],
                    [1.00, "#fb7185"],
                ],
                marker_line_color="rgba(15,23,42,0.65)",
                marker_line_width=0.45,
                colorbar={
                    "title": {"text": "Surface-water<br>supply/use index", "font": {"color": COLORS["muted"]}},
                    "tickfont": {"color": COLORS["muted"]},
                    "thickness": 12,
                    "len": 0.68,
                },
                customdata=custom,
                hovertemplate=(
                    "%{customdata[0]}<br>HUC8 %{location}"
                    "<br>Median SUI: %{z:.2f}"
                    "<br>75th percentile: %{customdata[1]:.2f}"
                    "<br>HUC12 observations: %{customdata[2]:.0f}<extra></extra>"
                ),
                name="Surface-water context",
            )
        )

    if isinstance(facilities, pd.DataFrame) and not facilities.empty and {"Latitude", "Longitude"}.issubset(facilities.columns):
        points = facilities.copy()
        points["Latitude"] = pd.to_numeric(points["Latitude"], errors="coerce")
        points["Longitude"] = pd.to_numeric(points["Longitude"], errors="coerce")
        points = points.dropna(subset=["Latitude", "Longitude"])
        if not points.empty:
            figure.add_trace(
                go.Scattergeo(
                    lon=points["Longitude"],
                    lat=points["Latitude"],
                    text=[_facility_hover(row) for _, row in points.iterrows()],
                    mode="markers",
                    hovertemplate="%{text}<extra></extra>",
                    marker={"size": 7, "color": COLORS["violet"], "line": {"width": 0.8, "color": "#111827"}},
                    name="Facility records",
                )
            )

    figure.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True,
        legend={"orientation": "h", "y": 1.02, "x": 0, "font": {"color": COLORS["muted"], "size": 11}},
        font={"color": COLORS["text"], "family": "Inter, ui-sans-serif, system-ui"},
        hoverlabel={"bgcolor": "#0f172a", "font": {"color": COLORS["text"]}},
        geo={
            "projection": {"type": "albers usa"},
            "fitbounds": "locations",
            "visible": False,
            "bgcolor": "rgba(0,0,0,0)",
        },
    )
    return figure

def infrastructure_construction_history(history: pd.DataFrame | None, *, height: int = 330, years: int = 10):
    """Plot data-center and semiconductor-facility construction rates."""
    columns = [
        ("Data Center Construction", "Data centers", COLORS["violet"]),
        ("Computer, Electronic & Electrical Manufacturing Construction", "Computer, electronic & electrical manufacturing", COLORS["blue"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Observation Date" not in history.columns:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean["Observation Date"], errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]

    figure = go.Figure()
    for column, name, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"],
            y=rows[column] / 1000.0,
            mode="lines",
            name=name,
            line={"color": color, "width": 2.6},
            hovertemplate=f"%{{x|%Y-%m}}<br>{name}: $%{{y:,.1f}}B SAAR<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="B", tickprefix="$", separatethousands=True)
    return _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))


def supporting_construction_history(history: pd.DataFrame | None, *, height: int = 315, years: int = 8):
    columns = [
        ("Communication Construction", "Communication", COLORS["violet"]),
        ("Public Highway and Street Construction", "Highways and streets", COLORS["blue"]),
        ("Public Transportation Construction", "Transportation", COLORS["slate"]),
        ("Public Water Supply Construction", "Water supply", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Observation Date" not in history.columns:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean["Observation Date"], errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, name, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"],
            y=rows[column] / 1000.0,
            mode="lines",
            name=name,
            line={"color": color, "width": 2.2},
            hovertemplate=f"%{{x|%Y-%m}}<br>{name}: $%{{y:,.1f}}B SAAR<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="B", tickprefix="$", separatethousands=True)
    return _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))


def adaptation_history(history: pd.DataFrame | None, *, height: int = 325, years: int = 3):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or "Date" not in history.columns:
        clean = pd.DataFrame(columns=["Date", "Current AI Use", "Expected AI Use"])
    else:
        clean = history.copy()
        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
        for column in ["Current AI Use", "Expected AI Use", "Current AI Use SE", "Expected AI Use SE"]:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Date"]).sort_values("Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color, dash in [
        ("Current AI Use", "Current use", COLORS["violet"], "solid"),
        ("Expected AI Use", "Expected use within six months", COLORS["blue"], "dash"),
    ]:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        se_column = f"{column} SE"
        error_values = (1.96 * pd.to_numeric(rows.get(se_column), errors="coerce")) if se_column in rows.columns else None
        figure.add_trace(go.Scatter(
            x=rows["Date"],
            y=rows[column],
            mode="lines",
            name=label,
            line={"color": color, "width": 2.6, "dash": dash},
            error_y={
                "type": "data",
                "array": error_values,
                "visible": error_values is not None,
                "color": color,
                "thickness": 1.0,
                "width": 2,
            },
            hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.1f}}%<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="%", rangemode="tozero")
    return _base_layout(figure, height=height, legend=True, margin=dict(l=44, r=18, t=28, b=36))


def adaptation_sector_bars(sector_snapshot: pd.DataFrame | None, *, height: int = 520, limit: int = 12):
    required = {"Sector", "Current AI Use", "Expected AI Use"}
    if sector_snapshot is None or not isinstance(sector_snapshot, pd.DataFrame) or sector_snapshot.empty or not required.issubset(sector_snapshot.columns):
        clean = pd.DataFrame(columns=list(required))
    else:
        clean = sector_snapshot.copy()
        clean = clean.loc[clean.get("Sector Code", "").astype(str) != "XX"] if "Sector Code" in clean.columns else clean
        for column in ["Current AI Use", "Expected AI Use", "Current AI Use SE", "Expected AI Use SE"]:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Current AI Use"]).nlargest(limit, "Current AI Use").sort_values("Current AI Use")
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Bar(
            x=clean["Current AI Use"], y=clean["Sector"], orientation="h", name="Current use",
            marker_color=COLORS["violet"],
            error_x={"type": "data", "array": 1.96 * clean["Current AI Use SE"], "visible": True, "color": COLORS["violet"], "thickness": 1.0},
            hovertemplate="%{y}<br>Current use: %{x:.1f}%<extra></extra>",
        ))
        figure.add_trace(go.Bar(
            x=clean["Expected AI Use"], y=clean["Sector"], orientation="h", name="Expected within six months",
            marker_color=COLORS["blue"], opacity=0.72,
            error_x={"type": "data", "array": 1.96 * clean["Expected AI Use SE"], "visible": True, "color": COLORS["blue"], "thickness": 1.0},
            hovertemplate="%{y}<br>Expected use: %{x:.1f}%<extra></extra>",
        ))
    figure.update_layout(barmode="group")
    figure.update_xaxes(ticksuffix="%", rangemode="tozero")
    return _base_layout(figure, height=height, legend=True, margin=dict(l=255, r=18, t=30, b=36))
