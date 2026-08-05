from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom, _nice_axis_range

def debt_market_history(history, *, height=315, years=10):
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
    fig = _base_layout(
        fig,
        height=height,
        legend=len(fig.data) > 1,
        margin=dict(l=42, r=18, t=30 if len(fig.data) > 1 else 18, b=34),
    )
    return add_axis_headroom(fig, upper=0.20, lower=0.10, extra_values=[0])

def current_gap_bars(gaps: dict[str, float]):
    rows = [
        (label, pd.to_numeric(value, errors="coerce"))
        for label, value in gaps.items()
    ]
    rows = [(label, float(value)) for label, value in rows if pd.notna(value)]
    labels = [label for label, _ in rows]
    values = [value for _, value in rows]
    colors = [
        COLORS["violet"] if pd.notna(value) and value >= 0 else COLORS["blue"]
        for value in values
    ]
    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            marker_color=colors,
            text=[f"{value:+.0f}" for value in values],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:+.1f}<extra></extra>",
        )
    )
    fig.add_vline(x=0, line_dash="dot", line_color="#64748b")
    fig.update_xaxes(range=[-100, 100])
    fig.update_yaxes(autorange="reversed")
    return _base_layout(fig, height=270, margin=dict(l=160, r=45, t=15, b=28))

def component_bars(components: dict, *, signed=False, height=285, color=None, headroom=False):
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
    limit = 110 if headroom else 100
    if signed:
        fig.add_vline(x=0, line_dash="dot", line_color="#64748b")
        fig.update_xaxes(range=[-limit, limit])
    else:
        fig.update_xaxes(range=[0, limit])
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
    fig = _base_layout(fig, height=330, legend=False, margin=dict(l=42, r=18, t=18, b=36))
    return add_axis_headroom(fig, upper=0.20, lower=0.10, extra_values=[0, 1])


def private_capital_ledger_chart(metrics: dict, *, height=190):
    """Show mature-cohort value split between distributions and remaining NAV."""
    dpi = pd.to_numeric((metrics or {}).get("dpi"), errors="coerce")
    rvpi = pd.to_numeric((metrics or {}).get("rvpi"), errors="coerce")
    fig = go.Figure()
    if pd.isna(dpi) or pd.isna(rvpi):
        fig.add_annotation(
            text="Private-capital realization data unavailable.",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font={"color": COLORS["slate"], "size": 12},
        )
        return _base_layout(fig, height=height, margin=dict(l=20, r=20, t=20, b=28))

    fig.add_trace(
        go.Bar(
            x=[float(dpi)], y=["Mature cohort"], orientation="h",
            name="Distributed value (DPI)", marker_color=COLORS["violet"],
            text=[f"{float(dpi):.2f}x distributed"], textposition="inside",
            insidetextanchor="middle",
            hovertemplate="Distributed value: %{x:.2f}x paid-in capital<extra></extra>",
        )
    )
    fig.add_trace(
        go.Bar(
            x=[float(rvpi)], y=["Mature cohort"], orientation="h",
            name="Remaining NAV (RVPI)", marker_color=COLORS["blue"],
            text=[f"{float(rvpi):.2f}x NAV"], textposition="inside",
            insidetextanchor="middle",
            hovertemplate="Remaining NAV: %{x:.2f}x paid-in capital<extra></extra>",
        )
    )
    total = float(dpi + rvpi)
    upper = max(2.5, total * 1.20)
    fig.add_vline(
        x=1.0, line_dash="dot", line_color=COLORS["slate"], line_width=1.2,
        annotation_text="1.0x paid in", annotation_position="top",
        annotation_font={"color": COLORS["slate"], "size": 10},
    )
    fig.update_layout(barmode="stack", bargap=0.48, legend_traceorder="normal")
    fig.update_xaxes(range=[0, upper], title="Value relative to paid-in capital", ticksuffix="x")
    fig.update_yaxes(showticklabels=False, title=None)
    return _base_layout(
        fig,
        height=height,
        legend=True,
        margin=dict(l=18, r=18, t=52, b=38),
    )


def private_capital_realization_map(funds: pd.DataFrame, *, height=430):
    """Map cash realization against total value for the retained fund cohort."""
    fig = go.Figure()
    required = {
        "Manager", "Fund", "Vintage", "Paid In Capital", "DPI", "RVPI", "TVPI",
        "Net IRR", "Maturity", "Exposure Tier",
    }
    if funds is None or funds.empty or not required.issubset(funds.columns):
        fig.add_annotation(
            text="Private-capital realization data unavailable.",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font={"color": COLORS["slate"], "size": 12},
        )
        return _base_layout(fig, height=height)

    frame = funds.copy()
    for column in ("Paid In Capital", "DPI", "RVPI", "TVPI", "Net IRR", "Vintage"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["DPI", "TVPI", "Paid In Capital"])
    maturity_specs = [
        ("Mature (5y+)", COLORS["violet"], 0.90),
        ("Developing (3-4y)", COLORS["blue"], 0.76),
        ("Young (0-2y)", COLORS["slate"], 0.62),
    ]
    max_paid = float(frame["Paid In Capital"].max()) if not frame.empty else 1.0
    for maturity, color, opacity in maturity_specs:
        subset = frame.loc[frame["Maturity"].eq(maturity)].copy()
        if subset.empty:
            continue
        marker_size = 10 + 24 * np.sqrt(subset["Paid In Capital"].clip(lower=0) / max_paid)
        customdata = np.column_stack([
            subset["Fund"].astype(str),
            subset["Manager"].astype(str),
            subset["Vintage"].map(lambda value: f"{int(value)}" if pd.notna(value) else "n/a"),
            subset["RVPI"].map(lambda value: f"{value:.2f}x"),
            subset["Net IRR"].map(lambda value: f"{value:+.1f}%" if pd.notna(value) else "n/a"),
            subset["Paid In Capital"].map(lambda value: f"${value / 1e6:,.0f}M"),
            subset["Exposure Tier"].astype(str),
        ])
        fig.add_trace(
            go.Scatter(
                x=subset["DPI"], y=subset["TVPI"], mode="markers", name=maturity,
                marker={
                    "size": marker_size,
                    "color": color,
                    "opacity": opacity,
                    "line": {"color": "rgba(226,232,240,0.34)", "width": 0.8},
                },
                customdata=customdata,
                hovertemplate=(
                    "<b>%{customdata[0]}</b><br>%{customdata[1]} · vintage %{customdata[2]}<br>"
                    "%{customdata[6]}<br>DPI %{x:.2f}x · RVPI %{customdata[3]} · TVPI %{y:.2f}x<br>"
                    "Net IRR %{customdata[4]} · paid in %{customdata[5]}<extra></extra>"
                ),
            )
        )

    raw_x = max(4.25, float(frame["DPI"].max())) if not frame.empty else 4.25
    raw_y = max(4.25, float(frame["TVPI"].max())) if not frame.empty else 4.25
    _, x_max, x_step = _nice_axis_range(0.0, raw_x, upper=0.16, lower=0.0, include_zero=True)
    _, y_max, y_step = _nice_axis_range(0.0, raw_y, upper=0.16, lower=0.0, include_zero=True)
    fig.add_vline(x=1.0, line_dash="dot", line_color=COLORS["slate"], opacity=0.72)
    fig.add_hline(y=1.5, line_dash="dot", line_color=COLORS["slate"], opacity=0.72)
    fig.add_annotation(
        x=1.0, y=y_max * 0.98, text="1.0x DPI", showarrow=False,
        xanchor="left", font={"color": COLORS["slate"], "size": 10},
    )
    fig.add_annotation(
        x=x_max * 0.98, y=1.5, text="1.5x TVPI", showarrow=False,
        xanchor="right", yanchor="bottom", font={"color": COLORS["slate"], "size": 10},
    )
    fig.update_xaxes(range=[0, x_max], dtick=x_step, title="Cash returned (DPI)", ticksuffix="x")
    fig.update_yaxes(range=[0, y_max], dtick=y_step, title="Total value (TVPI)", ticksuffix="x")
    return _base_layout(
        fig,
        height=height,
        legend=True,
        margin=dict(l=54, r=22, t=46, b=48),
    )
