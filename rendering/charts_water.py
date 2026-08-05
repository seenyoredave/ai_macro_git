from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from analytics.water_competition import (
    competing_freshwater_profile,
    current_top_withdrawal_profile,
    evidence_ladder,
    state_competition_exposure,
    state_facility_evidence_profile,
)
from rendering.charts_common import COLORS, _base_layout, add_axis_headroom, add_stacked_axis_headroom

WATER_COLORS = {
    "ground": "#2563eb",
    "surface": "#60a5fa",
    "primary": "#8b5cf6",
    "secondary": "#6366f1",
    "neutral": "#94a3b8",
    "deep": "#334155",
    "plot": "rgba(15,23,42,0.28)",
}


def _water_layout(fig, *, height=360, margin=None, legend=False):
    fig = _base_layout(fig, height=height, margin=margin, legend=legend)
    fig.update_layout(
        plot_bgcolor=WATER_COLORS["plot"],
        hoverlabel={"bgcolor": "#111827", "font": {"color": COLORS["text"]}},
    )
    return fig


def water_competing_uses(category_frame, *, height=410):
    profile = competing_freshwater_profile(category_frame)
    fig = go.Figure()
    if not profile.empty:
        for column, label, color in (
            ("Fresh Groundwater Bgal/day", "Fresh groundwater", WATER_COLORS["ground"]),
            ("Fresh Surface Water Bgal/day", "Fresh surface water", WATER_COLORS["surface"]),
        ):
            fig.add_trace(go.Bar(
                x=profile[column],
                y=profile["Party"],
                orientation="h",
                name=label,
                marker={"color": color, "line": {"width": 0.6, "color": "rgba(15,23,42,0.55)"}},
                customdata=np.stack([
                    profile["Freshwater Bgal/day"],
                    profile["Freshwater Share"] * 100.0,
                ], axis=-1),
                hovertemplate=(
                    "%{y}<br>" + label + ": %{x:,.1f} Bgal/day"
                    "<br>Total freshwater: %{customdata[0]:,.1f} Bgal/day"
                    "<br>Share of represented freshwater: %{customdata[1]:.1f}%<extra></extra>"
                ),
            ))
    fig.update_layout(barmode="stack", bargap=0.28)
    fig.update_xaxes(title="Freshwater withdrawal · billion gallons per day")
    fig.update_yaxes(title="", categoryorder="array", categoryarray=list(reversed(profile["Party"].tolist())) if not profile.empty else None)
    fig = _water_layout(fig, height=height, margin=dict(l=190, r=26, t=58, b=50), legend=True)
    fig.update_layout(legend={"orientation": "h", "y": 1.13, "x": 0, "xanchor": "left", "yanchor": "bottom"})
    return add_stacked_axis_headroom(fig, upper=0.18, lower=0.0, include_zero=True)


def water_evidence_ladder(summary: dict | None, *, height=410):
    frame = evidence_ladder(summary)
    fig = go.Figure()
    if not frame.empty:
        shades = ["#8b5cf6", "#6366f1", "#3b82f6", "#64748b", "#475569"]
        fig.add_trace(go.Bar(
            x=frame["Facilities"],
            y=frame["Evidence Stage"],
            orientation="h",
            marker={"color": shades[: len(frame)], "line": {"width": 0.7, "color": "rgba(15,23,42,0.55)"}},
            text=[f"{int(value):,}" for value in frame["Facilities"]],
            textposition="outside",
            cliponaxis=False,
            customdata=frame["Coverage"] * 100.0,
            hovertemplate="%{y}<br>Facilities: %{x:,.0f}<br>Coverage: %{customdata:.1f}%<extra></extra>",
        ))
    fig.update_xaxes(title="Facilities")
    fig.update_yaxes(
        title="",
        categoryorder="array",
        categoryarray=list(reversed(frame["Evidence Stage"].tolist())) if not frame.empty else None,
    )
    fig = _water_layout(fig, height=height, margin=dict(l=175, r=48, t=26, b=48))
    return add_axis_headroom(fig, axis="x", upper=0.22, lower=0.0, include_zero=True)


def water_state_exposure(facility_context, state_categories, *, height=410, top_n=16):
    frame = state_competition_exposure(facility_context, state_categories)
    fig = go.Figure()
    if not frame.empty:
        frame = frame.head(max(int(top_n), 1)).copy()
        direct = pd.to_numeric(frame["Direct_Evidence"], errors="coerce").fillna(0)
        size = np.clip(10 + np.sqrt(direct) * 5, 10, 34)
        color = pd.to_numeric(frame["County Context Coverage"], errors="coerce").fillna(0) * 100.0
        custom = np.stack([
            frame["Agriculture Share"] * 100.0,
            frame["Household & Public Share"] * 100.0,
            frame["Thermoelectric Share"] * 100.0,
            frame["County_Context"],
            frame["Direct_Evidence"],
        ], axis=-1)
        fig.add_trace(go.Scatter(
            x=frame["Mapped Facilities"],
            y=frame["Community + Agriculture Share"] * 100.0,
            mode="markers+text",
            text=frame["State"],
            textposition="top center",
            textfont={"size": 10, "color": COLORS["muted"]},
            marker={
                "size": size,
                "color": color,
                "colorscale": [[0, "#334155"], [0.45, "#2563eb"], [1, "#a78bfa"]],
                "cmin": 0,
                "cmax": 100,
                "showscale": True,
                "colorbar": {
                    "title": {"text": "County context<br>coverage", "font": {"size": 10}},
                    "ticksuffix": "%",
                    "thickness": 10,
                    "len": 0.68,
                    "x": 1.02,
                },
                "line": {"width": 1.0, "color": "rgba(226,232,240,0.42)"},
                "opacity": 0.9,
            },
            customdata=custom,
            hovertemplate=(
                "<b>%{text}</b><br>Mapped facilities: %{x:,.0f}"
                "<br>Household + agriculture share: %{y:.1f}%"
                "<br>Agriculture: %{customdata[0]:.1f}%"
                "<br>Households & public systems: %{customdata[1]:.1f}%"
                "<br>Thermoelectric power: %{customdata[2]:.1f}%"
                "<br>County-context records: %{customdata[3]:,.0f}"
                "<br>Direct-evidence records: %{customdata[4]:,.0f}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Mapped data-center facilities")
    fig.update_yaxes(title="Household + agriculture share of freshwater withdrawals", ticksuffix="%")
    fig = _water_layout(fig, height=height, margin=dict(l=72, r=88, t=34, b=54))
    return add_axis_headroom(fig, upper=0.18, lower=0.06, include_zero=True)


def water_withdrawal_components(category_frame, *, height=390):
    frame = category_frame.copy() if isinstance(category_frame, pd.DataFrame) else pd.DataFrame()
    label_map = {
        "public_supply": "Public supply",
        "domestic_self_supply": "Domestic self-supply",
        "industrial_self_supply": "Industrial self-supply",
        "irrigation": "Irrigation",
        "livestock": "Livestock",
        "aquaculture": "Aquaculture",
        "mining": "Mining",
        "thermoelectric_power": "Thermoelectric power",
    }
    components = [
        ("Fresh Groundwater Mgal/d", "Fresh groundwater", COLORS["blue_deep"]),
        ("Fresh Surface Water Mgal/d", "Fresh surface water", COLORS["blue"]),
        ("Saline Groundwater Mgal/d", "Saline groundwater", COLORS["violet_deep"]),
        ("Saline Surface Water Mgal/d", "Saline surface water", COLORS["violet"]),
    ]
    fig = go.Figure()
    if not frame.empty and "Use Category" in frame.columns:
        frame = frame.copy()
        frame["Display"] = frame["Use Category"].map(label_map).fillna(frame["Use Category"])
        frame["Total Withdrawal Mgal/d"] = pd.to_numeric(frame.get("Total Withdrawal Mgal/d"), errors="coerce")
        frame = frame.sort_values("Total Withdrawal Mgal/d", ascending=True, kind="stable")
        for column, label, color in components:
            values = pd.to_numeric(frame.get(column), errors="coerce").fillna(0)
            fig.add_trace(go.Bar(
                x=values / 1000.0,
                y=frame["Display"],
                orientation="h",
                name=label,
                marker_color=color,
                customdata=values,
                hovertemplate=f"%{{y}}<br>{label}: %{{customdata:,.1f}} Mgal/d<extra></extra>",
            ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Billion gallons per day")
    fig.update_yaxes(title="")
    fig = _water_layout(fig, height=height, legend=True, margin=dict(l=158, r=28, t=70, b=48))
    fig.update_layout(legend={"orientation": "h", "y": 1.12, "x": 0, "yanchor": "bottom"})
    return add_stacked_axis_headroom(fig, upper=0.18, lower=0.0, include_zero=True)


def thermoelectric_water_groups(group_frame, *, metric="Withdrawal", height=360):
    frame = group_frame.copy() if isinstance(group_frame, pd.DataFrame) else pd.DataFrame()
    column = f"{metric} Bgal/day"
    fig = go.Figure()
    if not frame.empty and {"Group", column}.issubset(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=[column]).sort_values(column, ascending=True, kind="stable")
        fig.add_trace(go.Bar(
            x=frame[column],
            y=frame["Group"].astype(str),
            orientation="h",
            marker_color=COLORS["blue"] if metric == "Withdrawal" else COLORS["violet"],
            customdata=np.stack([
                pd.to_numeric(frame.get("Plants"), errors="coerce").fillna(0),
                pd.to_numeric(frame.get("Records"), errors="coerce").fillna(0),
            ], axis=-1),
            hovertemplate=(
                f"%{{y}}<br>{metric}: %{{x:,.3f}} Bgal/day equivalent"
                "<br>Plants: %{customdata[0]:,.0f}<br>Records: %{customdata[1]:,.0f}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Billion gallons per day equivalent")
    fig.update_yaxes(title="")
    fig = _water_layout(fig, height=height, margin=dict(l=125, r=34, t=26, b=48))
    return add_axis_headroom(fig, axis="x", upper=0.20, lower=0.0, include_zero=True)


def water_top_withdrawals_2020(frame: pd.DataFrame | None, *, height: int = 390):
    """Show the latest retained national comparison of the top three water uses."""
    profile = current_top_withdrawal_profile(frame)
    fig = go.Figure()
    if not profile.empty:
        ordered = profile.sort_values("Withdrawal Bgal/day", ascending=True, kind="stable")
        color_map = {
            "Crop irrigation": "#8b5cf6",
            "Thermoelectric power": "#60a5fa",
            "Public supply": "#94a3b8",
        }
        colors = [color_map.get(str(label), WATER_COLORS["neutral"]) for label in ordered["Use Category"]]
        fig.add_trace(go.Bar(
            x=ordered["Withdrawal Bgal/day"],
            y=ordered["Use Category"],
            orientation="h",
            marker={"color": colors, "line": {"width": 0.7, "color": "rgba(15,23,42,0.58)"}},
            text=[f"{value:,.1f}" for value in ordered["Withdrawal Bgal/day"]],
            textposition="outside",
            cliponaxis=False,
            customdata=np.stack([
                ordered["Share of Top Three"] * 100.0,
                ordered["Observation Year"].astype(float),
            ], axis=-1),
            hovertemplate=(
                "%{y}<br>Withdrawal: %{x:,.1f} Bgal/day"
                "<br>Share of retained top-three total: %{customdata[0]:.1f}%"
                "<br>Observation year: %{customdata[1]:.0f}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Average daily withdrawal · billion gallons per day")
    fig.update_yaxes(title="")
    fig = _water_layout(fig, height=height, margin=dict(l=165, r=58, t=26, b=50))
    return add_axis_headroom(fig, axis="x", upper=0.18, lower=0.0, include_zero=True)


def water_state_evidence_profile(facility_context: pd.DataFrame | None, *, height: int = 430, top_n: int = 16):
    """Show where facilities are concentrated and where direct evidence exists."""
    frame = state_facility_evidence_profile(facility_context)
    fig = go.Figure()
    if not frame.empty:
        frame = frame.head(max(int(top_n), 1)).sort_values("Mapped Facilities", ascending=True, kind="stable")
        fig.add_trace(go.Bar(
            x=frame["Mapped Facilities"],
            y=frame["State"],
            orientation="h",
            name="Mapped facilities",
            marker={"color": "#475569", "line": {"width": 0.6, "color": "rgba(15,23,42,0.55)"}},
            customdata=np.stack([
                frame["Direct Water Evidence"],
                frame["Quantified Use"],
                frame["Direct Evidence Coverage"] * 100.0,
            ], axis=-1),
            hovertemplate=(
                "%{y}<br>Mapped facilities: %{x:,.0f}"
                "<br>Direct water evidence: %{customdata[0]:,.0f}"
                "<br>Quantified use records: %{customdata[1]:,.0f}"
                "<br>Direct-evidence coverage: %{customdata[2]:.1f}%<extra></extra>"
            ),
        ))
        fig.add_trace(go.Scatter(
            x=frame["Direct Water Evidence"],
            y=frame["State"],
            mode="markers",
            name="Direct water evidence",
            marker={
                "size": 9,
                "color": WATER_COLORS["primary"],
                "line": {"width": 1.0, "color": "rgba(248,250,252,0.65)"},
            },
            customdata=np.stack([
                frame["Mapped Facilities"],
                frame["Quantified Use"],
                frame["Direct Evidence Coverage"] * 100.0,
            ], axis=-1),
            hovertemplate=(
                "%{y}<br>Direct water evidence: %{x:,.0f}"
                "<br>Mapped facilities: %{customdata[0]:,.0f}"
                "<br>Quantified use records: %{customdata[1]:,.0f}"
                "<br>Direct-evidence coverage: %{customdata[2]:.1f}%<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Facility records")
    fig.update_yaxes(title="")
    fig = _water_layout(fig, height=height, margin=dict(l=56, r=42, t=72, b=48), legend=True)
    fig.update_layout(legend={"orientation": "h", "y": 1.13, "x": 0, "yanchor": "bottom"}, bargap=0.28)
    return add_axis_headroom(fig, axis="x", upper=0.18, lower=0.0, include_zero=True)


def wastewater_construction_history(history: pd.DataFrame | None, *, height: int = 390):
    """Chronological public wastewater-system construction spending since 2020."""
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", "Public Sewage and Waste Disposal Construction"])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        clean["Public Sewage and Waste Disposal Construction"] = pd.to_numeric(
            clean.get("Public Sewage and Waste Disposal Construction"), errors="coerce"
        )
        clean = clean.loc[clean["Observation Date"] >= pd.Timestamp("2020-01-01")].dropna(
            subset=["Observation Date", "Public Sewage and Waste Disposal Construction"]
        ).sort_values("Observation Date", kind="stable")
    fig = go.Figure(go.Scatter(
        x=clean.get("Observation Date", []),
        y=clean.get("Public Sewage and Waste Disposal Construction", pd.Series(dtype=float)) / 1000.0,
        mode="lines",
        name="Public wastewater construction",
        line={"color": WATER_COLORS["primary"], "width": 2.7},
        hovertemplate="%{x|%Y-%m}<br>$%{y:,.1f}B SAAR<extra></extra>",
    ))
    fig.update_yaxes(tickprefix="$", ticksuffix="B")
    fig = _water_layout(fig, height=height, margin=dict(l=54, r=22, t=24, b=40))
    return add_axis_headroom(fig, upper=0.12, lower=0.05)
