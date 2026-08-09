from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom, clean_history

def infrastructure_construction_history(history: pd.DataFrame | None, *, height: int = 330, years: int = 10):
    columns = [
        ("Data Center Construction", "Data centers", COLORS["violet"]),
        ("Computer, Electronic & Electrical Manufacturing Construction", "Computer, electronic & electrical manufacturing", COLORS["blue"]),
        ("Electric Power Construction", "Electric power", COLORS["green"]),
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
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)

def power_utilization_history(history: pd.DataFrame | None, *, reference: float = 80.0, height: int = 300, years: int = 8):
    clean = clean_history(history)
    if not clean.empty and years:
        clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=years)]
    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(go.Scatter(
            x=clean["Date"], y=clean["Value"], mode="lines", name="Utilization",
            line={"color": COLORS["violet"], "width": 2.7},
            hovertemplate="%{x|%Y-%m}<br>Utilization: %{y:,.1f}%<extra></extra>",
        ))
    fig.add_hline(
        y=reference, line={"color": COLORS["amber"], "dash": "dash", "width": 1.5},
        annotation_text=f"90th-percentile tightness reference ({reference:.1f}%)", annotation_position="top left",
        annotation_font={"color": COLORS["amber"], "size": 11},
    )
    fig.update_yaxes(title="Utilization", ticksuffix="%")
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=52, r=18, t=30, b=36))
    return add_axis_headroom(fig, upper=0.16, lower=0.06, extra_values=[reference])

def compute_manufacturing_output_history(history: pd.DataFrame | None, *, height: int = 320, years: int = 10):
    columns = [
        ("Computer and Peripheral Equipment Output", "Computers and peripherals", COLORS["violet"]),
        ("Communications Equipment Output", "Communications equipment", COLORS["blue"]),
        ("Semiconductor and Electronic Component Output", "Semiconductors and components", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[c for c, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column], mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.1f}}<extra></extra>",
        ))
    figure.update_yaxes(title="Output index")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=18, t=24, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)

def compute_capacity_utilization_history(history: pd.DataFrame | None, *, height: int = 300, years: int = 10):
    columns = [
        ("Computer and Peripheral Equipment Capacity Utilization", "Computers and peripherals", COLORS["violet"]),
        ("Communications Equipment Capacity Utilization", "Communications equipment", COLORS["blue"]),
        ("Semiconductor and Electronic Component Capacity Utilization", "Semiconductors and components", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[c for c, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column], mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.1f}}%<extra></extra>",
        ))
    figure.update_yaxes(title="Utilization", ticksuffix="%")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=18, t=24, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)

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
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)

def infrastructure_attribution_history(history: pd.DataFrame | None, *, height: int = 340, years: int = 12):
    columns = ["Date", "Broader Supporting Construction", "Expected Baseline", "Excess Above Baseline"]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty or not set(columns).issubset(history.columns):
        clean = pd.DataFrame(columns=columns)
    else:
        clean = history[columns].copy()
        clean["Date"] = pd.to_datetime(clean["Date"], errors="coerce", format="mixed")
        for column in columns[1:]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Date"]).sort_values("Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Scatter(
            x=clean["Date"], y=clean["Broader Supporting Construction"] / 1000.0,
            mode="lines", name="Observed supporting construction",
            line={"color": COLORS["violet"], "width": 2.6},
            hovertemplate="%{x|%Y-%m}<br>Observed: $%{y:,.1f}B SAAR<extra></extra>",
        ))
        figure.add_trace(go.Scatter(
            x=clean["Date"], y=clean["Expected Baseline"] / 1000.0,
            mode="lines", name="Historical baseline",
            line={"color": COLORS["slate"], "width": 2.0, "dash": "dash"},
            hovertemplate="%{x|%Y-%m}<br>Baseline: $%{y:,.1f}B SAAR<extra></extra>",
        ))
        figure.add_trace(go.Bar(
            x=clean["Date"], y=clean["Excess Above Baseline"] / 1000.0,
            name="Excess above baseline", marker={"color": COLORS["amber"], "opacity": 0.45},
            hovertemplate="%{x|%Y-%m}<br>Excess: $%{y:,.1f}B SAAR<extra></extra>",
        ))
    figure.update_yaxes(ticksuffix="B", tickprefix="$", separatethousands=True)
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=52, r=18, t=28, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06, include_zero=True)


def compute_manufacturing_capacity_history(history: pd.DataFrame | None, *, height: int = 300, years: int = 10):
    columns = [
        ("Computer and Peripheral Equipment Capacity", "Computers and peripherals", COLORS["violet"]),
        ("Communications Equipment Capacity", "Communications equipment", COLORS["blue"]),
        ("Semiconductor and Electronic Component Capacity", "Semiconductors and components", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column], mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.1f}}<extra></extra>",
        ))
    figure.update_yaxes(title="Capacity index")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=18, t=24, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)


def compute_info_processing_investment_history(history: pd.DataFrame | None, *, height: int = 300, years: int = 10):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", "Info Processing Investment Level"])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        clean["Info Processing Investment Level"] = pd.to_numeric(
            clean.get("Info Processing Investment Level"), errors="coerce"
        )
        clean = clean.dropna(subset=["Observation Date", "Info Processing Investment Level"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Scatter(
            x=clean["Observation Date"], y=clean["Info Processing Investment Level"] / 1000.0,
            mode="lines", name="Investment", line={"color": COLORS["violet"], "width": 2.6},
            fill="tozeroy", fillcolor="rgba(167,139,250,0.12)",
            hovertemplate="%{x|%Y-%m}<br>Investment: $%{y:,.2f}T SAAR<extra></extra>",
        ))
    figure.update_yaxes(title="Real investment", tickprefix="$", ticksuffix="T")
    figure = _base_layout(figure, height=height, legend=False, margin=dict(l=62, r=18, t=24, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.0, include_zero=True)


def compute_m3_orders_shipments(history: pd.DataFrame | None, *, height: int = 300, years: int = 10):
    columns = [
        ("Computer and Electronic Product New Orders", "New orders", COLORS["violet"]),
        ("Computer and Electronic Product Shipments", "Shipments", COLORS["blue"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column] / 1000.0, mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: $%{{y:,.1f}}B<extra></extra>",
        ))
    figure.update_yaxes(title="Monthly value", tickprefix="$", ticksuffix="B")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=62, r=18, t=24, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)


def compute_m3_backlog_inventory(history: pd.DataFrame | None, *, height: int = 300, years: int = 10):
    columns = [
        ("Computer and Electronic Product Unfilled Orders to Shipments", "Unfilled orders / shipments", COLORS["amber"]),
        ("Computer and Electronic Product Inventory to Shipments", "Inventory / shipments", COLORS["green"]),
    ]
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", *[column for column, _, _ in columns]])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in columns:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean = clean.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if not clean.empty and years:
            clean = clean.loc[clean["Observation Date"] >= clean["Observation Date"].max() - pd.DateOffset(years=years)]
    figure = go.Figure()
    for column, label, color in columns:
        rows = clean.dropna(subset=[column]) if not clean.empty else clean
        if rows.empty:
            continue
        figure.add_trace(go.Scatter(
            x=rows["Observation Date"], y=rows[column], mode="lines", name=label,
            line={"color": color, "width": 2.4},
            hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.2f}}<extra></extra>",
        ))
    figure.update_yaxes(title="Ratio")
    figure = _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=18, t=24, b=36))
    return add_axis_headroom(figure, upper=0.14, lower=0.06)


def compute_project_layer_sites(projects: pd.DataFrame | None, *, height: int = 340):
    if projects is None or not isinstance(projects, pd.DataFrame) or projects.empty or "Supply Chain Layer" not in projects.columns:
        clean = pd.DataFrame(columns=["Supply Chain Layer", "Sites"])
    else:
        clean = (
            projects.groupby("Supply Chain Layer", dropna=False)
            .size().rename("Sites").reset_index()
            .sort_values(["Sites", "Supply Chain Layer"], ascending=[True, True], kind="stable")
        )
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Bar(
            x=clean["Sites"], y=clean["Supply Chain Layer"], orientation="h",
            marker={"color": COLORS["violet"]}, text=clean["Sites"], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br>Sites: %{x:,.0f}<extra></extra>",
        ))
    figure.update_xaxes(title="Sites", dtick=1)
    figure.update_yaxes(title="")
    figure = _base_layout(figure, height=height, legend=False, margin=dict(l=175, r=34, t=18, b=42))
    return add_axis_headroom(figure, axis="x", upper=0.18, lower=0.0, include_zero=True)


def compute_project_state_sites(projects: pd.DataFrame | None, *, height: int = 340):
    if projects is None or not isinstance(projects, pd.DataFrame) or projects.empty or "State" not in projects.columns:
        clean = pd.DataFrame(columns=["State", "Sites"])
    else:
        clean = (
            projects.assign(State=projects["State"].fillna("").astype(str).str.strip())
            .loc[lambda frame: frame["State"].ne("")]
            .groupby("State", dropna=False).size().rename("Sites").reset_index()
            .sort_values(["Sites", "State"], ascending=[True, True], kind="stable")
        )
    figure = go.Figure()
    if not clean.empty:
        figure.add_trace(go.Bar(
            x=clean["Sites"], y=clean["State"], orientation="h",
            marker={"color": COLORS["blue"]}, text=clean["Sites"], textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br>Sites: %{x:,.0f}<extra></extra>",
        ))
    figure.update_xaxes(title="Sites", dtick=1)
    figure.update_yaxes(title="")
    figure = _base_layout(figure, height=height, legend=False, margin=dict(l=54, r=34, t=18, b=42))
    return add_axis_headroom(figure, axis="x", upper=0.18, lower=0.0, include_zero=True)

# v6.4 capital-cycle views ---------------------------------------------------
from plotly.subplots import make_subplots as _make_subplots
from analytics.infrastructure_cycle import (
    BUILDOUT_SERIES as _BUILDOUT_SERIES,
    current_buildout_momentum as _current_buildout_momentum,
    quarterly_rotation_matrix as _quarterly_rotation_matrix,
)

_INFRA_COLORS = {
    "primary": "#a78bfa",
    "secondary": "#60a5fa",
    "neutral": "#94a3b8",
    "neutral_deep": "#64748b",
    "plot": "rgba(15,23,42,0.28)",
}


def _infra_layout(fig, *, height=400, margin=None, legend=False):
    fig = _base_layout(fig, height=height, margin=margin, legend=legend)
    fig.update_layout(
        plot_bgcolor=_INFRA_COLORS["plot"],
        hoverlabel={"bgcolor": "#111827", "font": {"color": COLORS["text"]}},
    )
    return fig


def infrastructure_leadership_rotation(history: pd.DataFrame | None, *, height: int = 470, years: int = 6):
    matrix = _quarterly_rotation_matrix(history, years=years)
    current = _current_buildout_momentum(history)
    order = [label for _, label in _BUILDOUT_SERIES]
    current = current.set_index("Series").reindex(order).dropna(how="all").reset_index() if not current.empty else current

    fig = _make_subplots(
        rows=1, cols=2, shared_yaxes=True,
        column_widths=[0.70, 0.30], horizontal_spacing=0.115,
    )
    if not matrix.empty:
        quarter_labels = [f"{period.year} Q{period.quarter}" for period in matrix.columns]
        fig.add_trace(go.Heatmap(
            z=matrix.to_numpy(),
            x=quarter_labels,
            y=matrix.index.tolist(),
            zmin=-60,
            zmax=60,
            zmid=0,
            colorscale=[
                [0.00, "#334155"],
                [0.28, "#64748b"],
                [0.50, "#111827"],
                [0.72, "#2563eb"],
                [1.00, "#a78bfa"],
            ],
            colorbar={
                "title": {"text": "YoY", "font": {"size": 10}},
                "ticksuffix": "%",
                "thickness": 10,
                "len": 0.72,
                "x": 1.035,
            },
            hovertemplate="%{y}<br>%{x}<br>Growth: %{z:+.1f}%<extra></extra>",
        ), row=1, col=1)
    if not current.empty:
        growth = pd.to_numeric(current["YoY Growth"], errors="coerce") * 100.0
        colors = [
            _INFRA_COLORS["primary"] if value >= 8 else
            _INFRA_COLORS["secondary"] if value >= 0 else
            _INFRA_COLORS["neutral_deep"]
            for value in growth.fillna(0)
        ]
        fig.add_trace(go.Bar(
            x=growth,
            y=current["Series"],
            orientation="h",
            marker={"color": colors, "line": {"width": 0.7, "color": "rgba(15,23,42,0.58)"}},
            text=[f"{value:+.1f}%" if pd.notna(value) else "n/a" for value in growth],
            textposition="outside",
            cliponaxis=False,
            customdata=pd.to_numeric(current["Level"], errors="coerce") / 1000.0,
            hovertemplate="%{y}<br>Current growth: %{x:+.1f}%<br>Construction: $%{customdata:,.1f}B SAAR<extra></extra>",
            showlegend=False,
        ), row=1, col=2)
    fig.update_xaxes(title="Leadership rotation · quarterly YoY growth", tickangle=0, row=1, col=1)
    if not matrix.empty:
        labels = [f"{period.year} Q{period.quarter}" for period in matrix.columns]
        step = max(len(labels) // 6, 1)
        fig.update_xaxes(tickmode="array", tickvals=labels[::step], ticktext=labels[::step], row=1, col=1)
    fig.update_xaxes(title="Current", ticksuffix="%", zeroline=True, zerolinecolor="rgba(148,163,184,0.45)", row=1, col=2)
    fig.update_yaxes(title="", categoryorder="array", categoryarray=list(reversed(order)), row=1, col=1)
    fig = _infra_layout(fig, height=height, margin=dict(l=168, r=104, t=34, b=62))
    if not current.empty:
        max_abs = float(np.nanmax(np.abs(pd.to_numeric(current["YoY Growth"], errors="coerce") * 100.0)))
        bound = max(20.0, np.ceil(max_abs / 10.0) * 10.0 + 10.0)
        fig.update_xaxes(range=[-bound, bound], dtick=20, row=1, col=2)
    return fig


def infrastructure_support_alignment(components: pd.DataFrame | None, *, height: int = 480):
    frame = components.copy() if isinstance(components, pd.DataFrame) else pd.DataFrame()
    fig = go.Figure()
    if not frame.empty:
        if "Deviation from Baseline" not in frame.columns:
            frame["Deviation from Baseline"] = (
                pd.to_numeric(frame.get("Observed"), errors="coerce") -
                pd.to_numeric(frame.get("Expected Baseline"), errors="coerce")
            )
        frame["Deviation from Baseline"] = pd.to_numeric(frame["Deviation from Baseline"], errors="coerce")
        frame = frame.dropna(subset=["Deviation from Baseline"]).sort_values("Deviation from Baseline", kind="stable")
        values = frame["Deviation from Baseline"] / 1000.0
        groups = frame.get("Group", pd.Series("Enabling system", index=frame.index)).fillna("Enabling system").astype(str)
        colors = []
        for value, group in zip(values, groups):
            if value >= 0:
                colors.append(_INFRA_COLORS["secondary"] if group == "Public-system mix" else _INFRA_COLORS["primary"])
            else:
                colors.append(_INFRA_COLORS["neutral"] if group == "Public-system mix" else _INFRA_COLORS["neutral_deep"])
        methods = frame.get("Baseline Method", pd.Series("Lagged baseline", index=frame.index)).fillna("Lagged baseline").astype(str)
        fig.add_trace(go.Bar(
            x=values,
            y=frame["Component"],
            orientation="h",
            marker={"color": colors, "line": {"width": 0.7, "color": "rgba(15,23,42,0.58)"}},
            text=[f"{value:+.1f}B" for value in values],
            textposition="outside",
            cliponaxis=False,
            customdata=np.stack([
                pd.to_numeric(frame["Observed"], errors="coerce") / 1000.0,
                pd.to_numeric(frame["Expected Baseline"], errors="coerce") / 1000.0,
                groups,
                methods,
            ], axis=-1),
            hovertemplate=(
                "%{y}<br>%{customdata[2]}"
                "<br>Deviation: $%{x:+.1f}B SAAR"
                "<br>Observed: $%{customdata[0]:,.1f}B"
                "<br>Baseline: $%{customdata[1]:,.1f}B"
                "<br>%{customdata[3]}<extra></extra>"
            ),
        ))
        net = float(frame["Deviation from Baseline"].sum()) / 1000.0
        fig.add_annotation(
            x=1, y=1.12, xref="paper", yref="paper", showarrow=False, xanchor="right",
            text=f"Net support balance <b>{net:+.1f}B</b>",
            font={"size": 12, "color": COLORS["muted"]},
        )
    fig.add_vline(x=0, line_color="rgba(148,163,184,0.58)", line_width=1.1)
    fig.update_xaxes(title="Deviation from lagged baseline · $B SAAR", ticksuffix="B", tickprefix="$")
    fig.update_yaxes(title="")
    fig = _infra_layout(fig, height=height, margin=dict(l=164, r=82, t=58, b=50))
    return add_axis_headroom(fig, axis="x", upper=0.20, lower=0.20, include_zero=True)


def wider_system_profile(history: pd.DataFrame | None, *, mode: str = "Indexed history", height: int = 390, years: int = 10):
    specs = [
        ("Communication Construction", "Communications", "#a78bfa"),
        ("Electric Power Construction", "Electric power", "#60a5fa"),
        ("Public Water Supply Construction", "Public water", "#6366f1"),
        ("Public Highway and Street Construction", "Roads", "#94a3b8"),
        ("Public Transportation Construction", "Transit", "#64748b"),
    ]
    frame = history.copy() if isinstance(history, pd.DataFrame) else pd.DataFrame()
    if not frame.empty:
        frame["Observation Date"] = pd.to_datetime(frame.get("Observation Date"), errors="coerce", format="mixed")
        for column, _, _ in specs:
            frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
        frame = frame.dropna(subset=["Observation Date"]).sort_values("Observation Date", kind="stable")
        if years:
            frame = frame.loc[frame["Observation Date"] >= frame["Observation Date"].max() - pd.DateOffset(years=years)]
    fig = go.Figure()
    if mode == "Indexed history":
        for column, label, color in specs:
            clean = frame.dropna(subset=[column]) if not frame.empty else frame
            if clean.empty:
                continue
            base = float(clean.iloc[0][column])
            values = clean[column] / base * 100.0 if base else np.nan
            fig.add_trace(go.Scatter(
                x=clean["Observation Date"], y=values, mode="lines", name=label,
                line={"color": color, "width": 2.4},
                hovertemplate=f"%{{x|%Y-%m}}<br>{label}: %{{y:,.1f}} (start=100)<extra></extra>",
            ))
        fig.update_yaxes(title="Indexed construction", ticksuffix="")
        fig = _infra_layout(fig, height=height, margin=dict(l=62, r=24, t=72, b=48), legend=True)
        fig.update_layout(legend={"orientation": "h", "y": 1.14, "x": 0, "yanchor": "bottom"})
        return add_axis_headroom(fig, upper=0.15, lower=0.06)

    rows = []
    for column, label, color in specs:
        clean = frame.dropna(subset=[column]) if not frame.empty else frame
        if clean.empty:
            continue
        latest = clean.iloc[-1]
        if mode == "Spending levels":
            value = float(latest[column]) / 1000.0
        else:
            prior = clean.loc[clean["Observation Date"] <= latest["Observation Date"] - pd.DateOffset(years=1)]
            base = float(prior.iloc[-1][column]) if not prior.empty else np.nan
            value = float(latest[column]) / base - 1.0 if pd.notna(base) and base else np.nan
        rows.append((label, value, color))
    rows.sort(key=lambda item: item[1] if pd.notna(item[1]) else -np.inf)
    if rows:
        values = [item[1] * (100.0 if mode == "Year-over-year momentum" else 1.0) for item in rows]
        colors = [item[2] if value >= 0 else _INFRA_COLORS["neutral_deep"] for item, value in zip(rows, values)]
        fig.add_trace(go.Bar(
            x=values, y=[item[0] for item in rows], orientation="h",
            marker={"color": colors}, text=[f"{v:+.1f}%" if mode == "Year-over-year momentum" else f"${v:,.1f}B" for v in values],
            textposition="outside", cliponaxis=False,
            hovertemplate="%{y}<br>%{x:,.1f}<extra></extra>",
        ))
    if mode == "Year-over-year momentum":
        fig.add_vline(x=0, line_color="rgba(148,163,184,0.55)", line_width=1.0)
        fig.update_xaxes(title="Year-over-year growth", ticksuffix="%")
        fig = _infra_layout(fig, height=height, margin=dict(l=128, r=56, t=28, b=48))
        return add_axis_headroom(fig, axis="x", upper=0.18, lower=0.18, include_zero=True)
    fig.update_xaxes(title="Construction spending · $B SAAR", tickprefix="$", ticksuffix="B")
    fig = _infra_layout(fig, height=height, margin=dict(l=128, r=56, t=28, b=48))
    return add_axis_headroom(fig, axis="x", upper=0.18, lower=0.0, include_zero=True)


def compute_critical_supply_chain(layers: pd.DataFrame | None, *, height: int = 390):
    """Show the available AI-critical manufacturing layers without implying full national coverage."""
    frame = layers.copy() if isinstance(layers, pd.DataFrame) else pd.DataFrame()
    figure = go.Figure()
    if not frame.empty:
        layer_col = next((column for column in ["Supply Chain Layer", "Layer"] if column in frame.columns), None)
        site_col = next((column for column in ["Sites", "Projects"] if column in frame.columns), None)
        if layer_col and site_col:
            frame[site_col] = pd.to_numeric(frame[site_col], errors="coerce")
            capex_col = next((column for column in ["Expected CapEx USD B", "Expected CapEx (USD B)"] if column in frame.columns), None)
            funding_col = next((column for column in ["Direct Funding USD B", "Direct Funding (USD B)"] if column in frame.columns), None)
            if capex_col:
                frame[capex_col] = pd.to_numeric(frame[capex_col], errors="coerce")
            if funding_col:
                frame[funding_col] = pd.to_numeric(frame[funding_col], errors="coerce")
            frame = frame.dropna(subset=[site_col]).sort_values(site_col, ascending=True, kind="stable")
            custom = np.stack(
                [
                    pd.to_numeric(frame.get(capex_col, pd.Series(np.nan, index=frame.index)), errors="coerce"),
                    pd.to_numeric(frame.get(funding_col, pd.Series(np.nan, index=frame.index)), errors="coerce"),
                    frame.get("States", pd.Series("", index=frame.index)).fillna("").astype(str),
                ],
                axis=-1,
            )
            figure.add_trace(
                go.Bar(
                    x=frame[site_col],
                    y=frame[layer_col],
                    orientation="h",
                    marker={"color": COLORS["violet"]},
                    text=[f"{int(value):,}" for value in frame[site_col]],
                    textposition="outside",
                    cliponaxis=False,
                    customdata=custom,
                    hovertemplate=(
                        "%{y}<br>Announced sites: %{x:,.0f}"
                        "<br>Announced capex: $%{customdata[0]:,.1f}B"
                        "<br>Direct awards: $%{customdata[1]:,.1f}B"
                        "<br>States: %{customdata[2]}<extra></extra>"
                    ),
                    showlegend=False,
                )
            )
    figure.update_xaxes(title="Announced manufacturing sites", dtick=1)
    figure.update_yaxes(title="")
    figure = _base_layout(figure, height=height, legend=False, margin=dict(l=126, r=55, t=22, b=46))
    return add_axis_headroom(figure, axis="x", upper=0.24, lower=0.0, include_zero=True)



def _select_connectivity_states(
    state_summary: pd.DataFrame | None,
    *,
    lens: str = "Mismatch screen",
    limit: int = 16,
) -> pd.DataFrame:
    """Select a balanced connectivity comparison without hiding mismatches.

    The default is a screening view, not a synthetic bandwidth score. It keeps
    high-capacity/low-depth states visible beside large connectivity hubs.
    """
    frame = state_summary.copy() if isinstance(state_summary, pd.DataFrame) else pd.DataFrame()
    required = {"State", "Reported Memberships", "Published Development MW"}
    if frame.empty or not required.issubset(frame.columns):
        return pd.DataFrame()
    frame["State"] = frame["State"].fillna("").astype(str).str.strip().str.upper()
    frame = frame.loc[frame["State"].str.fullmatch(r"[A-Z]{2,3}", na=False)].copy()
    for column in ["Reported Memberships", "Published Development MW", "IXPs", "Published Campuses", "Mismatch Priority"]:
        frame[column] = pd.to_numeric(frame.get(column), errors="coerce")
    frame["Reported Memberships"] = frame["Reported Memberships"].fillna(0)
    frame["Published Development MW"] = frame["Published Development MW"].fillna(0)
    frame["Mismatch Priority"] = frame["Mismatch Priority"].fillna(
        np.log1p(frame["Published Development MW"].clip(lower=0))
        / np.log1p(frame["Reported Memberships"].clip(lower=0) + 2)
    )
    flag = frame.get("Capacity-Connectivity Flag", pd.Series("No mismatch flag", index=frame.index)).astype(str)
    frame["Flagged mismatch"] = flag.ne("No mismatch flag")

    if lens == "Connectivity depth":
        selected = frame.sort_values(["Reported Memberships", "Published Development MW"], ascending=False, kind="stable").head(limit)
    elif lens == "Published capacity":
        selected = frame.sort_values(["Published Development MW", "Reported Memberships"], ascending=False, kind="stable").head(limit)
    else:
        # Reserve explicit space for three views of the system: mismatch risk,
        # published buildout scale, and established interconnection depth.
        # Quotas keep a long tail of zero-membership states from crowding every
        # major hub out of the default chart.
        mismatch_quota = max(4, limit // 3)
        capacity_quota = max(4, limit // 3)
        depth_quota = max(4, limit - mismatch_quota - capacity_quota)
        flagged = (
            frame.loc[frame["Flagged mismatch"] & frame["Published Development MW"].ge(1000)]
            .sort_values(["Mismatch Priority", "Published Development MW"], ascending=False, kind="stable")
            .head(mismatch_quota)
        )
        remaining = frame.loc[~frame["State"].isin(flagged["State"])].copy()
        capacity = (
            remaining.sort_values(["Published Development MW", "Reported Memberships"], ascending=False, kind="stable")
            .head(capacity_quota)
        )
        remaining = remaining.loc[~remaining["State"].isin(capacity["State"])].copy()
        depth = (
            remaining.sort_values(["Reported Memberships", "Published Development MW"], ascending=False, kind="stable")
            .head(depth_quota)
        )
        selected = pd.concat([flagged, capacity, depth], ignore_index=True, sort=False).drop_duplicates("State", keep="first")
        if len(selected) < limit:
            fill = frame.loc[~frame["State"].isin(selected["State"])].sort_values(
                ["Reported Memberships", "Published Development MW"], ascending=False, kind="stable"
            ).head(limit - len(selected))
            selected = pd.concat([selected, fill], ignore_index=True, sort=False)
    return selected.sort_values(["Reported Memberships", "Published Development MW"], ascending=True, kind="stable").reset_index(drop=True)


def data_center_connectivity_state(
    state_summary: pd.DataFrame | None,
    *,
    height: int = 520,
    limit: int = 16,
    lens: str = "Mismatch screen",
):
    """Compare public interconnection depth with published development capacity."""
    frame = _select_connectivity_states(state_summary, lens=lens, limit=limit)
    figure = go.Figure()
    if not frame.empty:
        custom = np.stack(
            [
                frame["IXPs"].fillna(0),
                frame["Published Development MW"].fillna(0) / 1000.0,
                frame["Published Campuses"].fillna(0),
                frame.get("Capacity-Connectivity Flag", pd.Series("No mismatch flag", index=frame.index)).astype(str),
            ],
            axis=-1,
        )
        figure.add_trace(
            go.Bar(
                x=frame["Reported Memberships"],
                y=frame["State"],
                orientation="h",
                name="Reported IXP memberships",
                marker={"color": COLORS["blue"]},
                customdata=custom,
                hovertemplate=(
                    "%{y}<br>Reported IXP memberships: %{x:,.0f}"
                    "<br>Active IXPs: %{customdata[0]:,.0f}"
                    "<br>Published development: %{customdata[1]:,.1f} GW"
                    "<br>Capacity-bearing campuses: %{customdata[2]:,.0f}"
                    "<br>Gap flag: %{customdata[3]}<extra></extra>"
                ),
            )
        )
        capacity = frame["Published Development MW"] / 1000.0
        capacity_mask = capacity.gt(0)
        if capacity_mask.any():
            figure.add_trace(
                go.Scatter(
                    x=capacity.loc[capacity_mask],
                    y=frame.loc[capacity_mask, "State"],
                    xaxis="x2",
                    mode="markers",
                    name="Published development",
                    marker={"color": COLORS["amber"], "size": 9, "symbol": "diamond"},
                    customdata=frame.loc[capacity_mask, "Published Campuses"].fillna(0),
                    hovertemplate=(
                        "%{y}<br>Published development: %{x:,.1f} GW"
                        "<br>Capacity-bearing campuses: %{customdata:,.0f}<extra></extra>"
                    ),
                )
            )
    figure.update_layout(
        xaxis={"title": "Reported IXP memberships", "rangemode": "tozero"},
        xaxis2={
            "title": "Published development capacity · GW",
            "overlaying": "x",
            "side": "top",
            "showgrid": False,
            "rangemode": "tozero",
        },
        legend={"orientation": "h", "y": 1.17, "x": 0, "yanchor": "bottom"},
    )
    figure.update_yaxes(title="")
    return _base_layout(figure, height=height, legend=True, margin=dict(l=58, r=30, t=92, b=52))
