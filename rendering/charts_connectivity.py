from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout


def _layout(figure: go.Figure, *, height: int, legend: bool = False) -> go.Figure:
    """Use the platform chart shell while preserving Connectivity's geography."""
    return _base_layout(
        figure,
        height=height,
        legend=legend,
        margin=dict(l=42, r=24, t=46, b=48),
    )


def cable_pipeline_status(frame: pd.DataFrame, *, height: int = 390) -> go.Figure:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _layout(go.Figure(), height=height)
    data = frame.copy()
    counts = (
        data.get("Temporal Status", pd.Series("Unclassified", index=data.index))
        .fillna("Unclassified")
        .astype(str)
        .value_counts()
        .rename_axis("Status")
        .reset_index(name="Cable systems")
    )
    order = ["RFS year not listed", "Current-year / planned or entering service", "Planned", "Unclassified"]
    counts["_order"] = counts["Status"].map({name: i for i, name in enumerate(order)}).fillna(99)
    counts = counts.sort_values("_order", kind="stable")
    fig = go.Figure(go.Bar(
        x=counts["Status"],
        y=counts["Cable systems"],
        marker={"color": [COLORS["blue"], COLORS["violet"], COLORS["amber"], COLORS["slate"]][:len(counts)]},
        hovertemplate="%{x}<br>%{y:,.0f} catalog entries<extra></extra>",
    ))
    fig.update_xaxes(title="")
    fig.update_yaxes(title="U.S.-connected catalog entries", rangemode="tozero")
    return _layout(fig, height=height)


def landing_markets_by_region(frame: pd.DataFrame, *, height: int = 390) -> go.Figure:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _layout(go.Figure(), height=height)
    grouped = (
        frame.groupby("Ocean / Region", as_index=False)
        .agg(**{"Landing markets": ("Landing Market", "nunique")})
        .sort_values("Landing markets", ascending=True, kind="stable")
    )
    fig = go.Figure(go.Bar(
        x=grouped["Landing markets"],
        y=grouped["Ocean / Region"],
        orientation="h",
        marker={"color": COLORS["violet"]},
        hovertemplate="%{y}<br>%{x:,.0f} selected landing markets<extra></extra>",
    ))
    fig.update_xaxes(title="Selected landing markets", rangemode="tozero")
    fig.update_yaxes(title="")
    return _layout(fig, height=height)



def landing_gateway_map(frame: pd.DataFrame, *, height: int = 500) -> go.Figure:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _layout(go.Figure(), height=height)
    data = frame.copy()
    data["Latitude"] = pd.to_numeric(data.get("Latitude"), errors="coerce")
    data["Longitude"] = pd.to_numeric(data.get("Longitude"), errors="coerce")
    data = data.dropna(subset=["Latitude", "Longitude"])
    if data.empty:
        return _layout(go.Figure(), height=height)
    custom = np.column_stack([
        data.get("State / Territory", pd.Series("", index=data.index)).fillna("").astype(str),
        data.get("Ocean / Region", pd.Series("", index=data.index)).fillna("").astype(str),
        data.get("Role", pd.Series("", index=data.index)).fillna("").astype(str),
    ])
    fig = go.Figure(go.Scattergeo(
        lat=data["Latitude"],
        lon=data["Longitude"],
        text=data.get("Landing Market", pd.Series("", index=data.index)).astype(str),
        customdata=custom,
        mode="markers",
        marker={"size": 9, "color": COLORS["violet"], "line": {"width": 0.8, "color": COLORS["text"]}},
        hovertemplate=(
            "%{text}<br>%{customdata[0]} · %{customdata[1]}"
            "<br>%{customdata[2]}<extra></extra>"
        ),
    ))
    fig.update_geos(
        projection_type="natural earth",
        showland=True,
        landcolor="rgba(30,41,59,0.68)",
        showocean=True,
        oceancolor="rgba(2,6,23,0.72)",
        showcountries=True,
        countrycolor="rgba(148,163,184,0.28)",
        showcoastlines=True,
        coastlinecolor="rgba(148,163,184,0.34)",
        lataxis_range=[-5, 72],
    )
    fig.update_layout(geo={"bgcolor": "rgba(0,0,0,0)"})
    return _layout(fig, height=height)

def interconnection_market_depth(frame: pd.DataFrame, *, metric: str = "Reported Memberships", height: int = 520, limit: int = 18) -> go.Figure:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty or metric not in frame.columns:
        return _layout(go.Figure(), height=height)
    data = frame.copy()
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    data = data.dropna(subset=[metric]).nlargest(limit, metric).sort_values(metric, ascending=True, kind="stable")
    label = data.get("Interconnection Market", pd.Series("", index=data.index)).astype(str)
    state = data.get("State", pd.Series("", index=data.index)).fillna("").astype(str)
    label = np.where(state.ne(""), label + " · " + state, label)
    custom = np.column_stack([
        pd.to_numeric(data.get("IXPs"), errors="coerce").fillna(0),
        pd.to_numeric(data.get("IXP Physical Location References"), errors="coerce").fillna(0),
    ])
    fig = go.Figure(go.Bar(
        x=data[metric],
        y=label,
        orientation="h",
        marker={"color": COLORS["blue"]},
        customdata=custom,
        hovertemplate=(
            "%{y}<br>" + metric + ": %{x:,.0f}"
            "<br>IXPs: %{customdata[0]:,.0f}"
            "<br>IXP physical-location references: %{customdata[1]:,.0f}<extra></extra>"
        ),
    ))
    fig.update_xaxes(title=metric, rangemode="tozero")
    fig.update_yaxes(title="")
    return _layout(fig, height=height)


def middle_mile_awards_by_state(frame: pd.DataFrame, *, metric: str = "Federal Award", height: int = 520, limit: int = 18) -> go.Figure:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty or metric not in frame.columns:
        return _layout(go.Figure(), height=height)
    data = frame.copy()
    data[metric] = pd.to_numeric(data[metric], errors="coerce")
    grouped = data.groupby("State / Territory", as_index=False).agg(
        **{
            "Federal Award": ("Federal Award", "sum"),
            "Award records": ("Award Recipient", "size"),
            "Disclosed route miles": ("Disclosed Route Miles", lambda values: pd.to_numeric(values, errors="coerce").sum(min_count=1)),
        }
    )
    grouped = grouped.nlargest(limit, metric).sort_values(metric, ascending=True, kind="stable")
    custom = np.column_stack([
        grouped["Award records"].fillna(0),
        grouped["Disclosed route miles"].fillna(np.nan),
    ])
    fig = go.Figure(go.Bar(
        x=grouped[metric] / 1_000_000,
        y=grouped["State / Territory"],
        orientation="h",
        marker={"color": COLORS["amber"]},
        customdata=custom,
        hovertemplate=(
            "%{y}<br>Federal awards: $%{x:,.1f}M"
            "<br>Award records: %{customdata[0]:,.0f}"
            "<br>Published route miles in award detail: %{customdata[1]:,.0f}<extra></extra>"
        ),
    ))
    fig.update_xaxes(title="Federal award · USD millions", rangemode="tozero")
    fig.update_yaxes(title="")
    return _layout(fig, height=height)


def campus_distance_distribution(frame: pd.DataFrame, *, height: int = 390) -> go.Figure:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return _layout(go.Figure(), height=height)
    distance = pd.to_numeric(frame.get("Miles to Selected Landing Market"), errors="coerce").dropna()
    if distance.empty:
        return _layout(go.Figure(), height=height)
    bins = [0, 50, 100, 250, 500, 1000, np.inf]
    labels = ["≤50", "51–100", "101–250", "251–500", "501–1,000", ">1,000"]
    counts = pd.cut(distance, bins=bins, labels=labels, include_lowest=True).value_counts(sort=False)
    fig = go.Figure(go.Bar(
        x=counts.index.astype(str),
        y=counts.values,
        marker={"color": COLORS["violet"]},
        hovertemplate="%{x} miles<br>%{y:,.0f} screened campuses<extra></extra>",
    ))
    fig.update_xaxes(title="Great-circle distance to nearest selected landing market · miles")
    fig.update_yaxes(title="Screened campuses", rangemode="tozero")
    return _layout(fig, height=height)
