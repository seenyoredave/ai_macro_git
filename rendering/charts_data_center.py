from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout
from rendering.map_geometry import map_layers, map_view


ACTIVE_CAMPUS_STATUSES = {
    "Operational",
    "Expanding",
    "Under construction",
    "Approved / permitted / under construction",
    "Proposed",
    "Planned",
    "Announced",
}

CAMPUS_SIZE_METRICS = {
    "Campus count": None,
    "Square feet": "Square Feet",
    "Published capacity estimate": "Published Capacity Estimate MW",
    "Planned data-center capacity": "Planned Data Center Capacity MW",
    "Contracted utility capacity": "Contracted Utility Capacity MW",
    "Energized capacity": "Energized Capacity MW",
    "Annual electricity consumption": "Annual Electricity Consumption MWh",
    "Water withdrawal": "Water Withdrawal Gallons/Year",
    "Water consumption": "Water Consumption Gallons/Year",
    "Planned onsite generation": "Planned Onsite Generation MW",
}

_STATUS_COLORS = {
    "Operational": COLORS.get("green", "#22c55e"),
    "Expanding": COLORS.get("blue", "#60a5fa"),
    "Under construction": COLORS.get("amber", "#f59e0b"),
    "Approved / permitted / under construction": COLORS.get("amber", "#f59e0b"),
    "Proposed": COLORS.get("violet", "#8b5cf6"),
    "Planned": COLORS.get("violet", "#8b5cf6"),
    "Announced": COLORS.get("violet_deep", "#7c3aed"),
    "Suspended": COLORS.get("slate", "#64748b"),
    "Cancelled": COLORS.get("red", "#ef4444"),
    "Blocked": COLORS.get("red", "#ef4444"),
    "Observed footprint": "#94a3b8",
    "Status unknown": "#64748b",
}


def _campuses(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    if "Campus ID" not in frame.columns:
        raise ValueError("Data-center charts require Campus ID from the Universal Data Center Registry")
    if frame["Campus ID"].astype(str).duplicated().any():
        raise ValueError("Data-center charts require exactly one row per canonical Campus ID")
    return frame.copy()


def _capacity(frame: pd.DataFrame) -> pd.Series:
    planned = pd.to_numeric(frame.get("Planned Data Center Capacity MW", pd.Series(np.nan, index=frame.index)), errors="coerce")
    published = pd.to_numeric(frame.get("Published Capacity Estimate MW", pd.Series(np.nan, index=frame.index)), errors="coerce")
    return planned.combine_first(published).where(lambda values: values > 0)


def _layout(fig: go.Figure, *, height: int, legend: bool = False, margin: dict | None = None) -> go.Figure:
    return _base_layout(fig, height=height, legend=legend, margin=margin or dict(l=55, r=18, t=24, b=44))


def _marker_sizes(frame: pd.DataFrame, size_by: str) -> pd.Series:
    metric = CAMPUS_SIZE_METRICS.get(size_by)
    if metric is None or metric not in frame.columns:
        return pd.Series(8.0, index=frame.index, dtype=float)
    values = pd.to_numeric(frame[metric], errors="coerce").where(lambda item: item > 0)
    if not values.notna().any():
        return pd.Series(8.0, index=frame.index, dtype=float)
    reference = float(values.quantile(0.90))
    if not np.isfinite(reference) or reference <= 0:
        reference = float(values.max())
    scaled = np.sqrt(values.clip(lower=0) / reference).clip(upper=1.35)
    return (7.0 + 14.0 * scaled).fillna(7.0)


def data_center_map(
    campuses: pd.DataFrame | None,
    *,
    state: str | None = None,
    size_by: str = "Campus count",
    selected_campus_id: str | None = None,
    height: int = 560,
) -> go.Figure:
    """Canonical MapLibre campus map used by every product surface."""
    frame = _campuses(campuses)
    if frame.empty:
        return _layout(go.Figure(), height=height, margin=dict(l=8, r=8, t=8, b=8))

    frame["Latitude"] = pd.to_numeric(frame.get("Latitude"), errors="coerce")
    frame["Longitude"] = pd.to_numeric(frame.get("Longitude"), errors="coerce")
    frame = frame.dropna(subset=["Latitude", "Longitude"]).copy()
    selected_state = str(state or "").strip().upper()
    if selected_state:
        state_series = frame.get("State", pd.Series("", index=frame.index)).fillna("").astype(str).str.upper().str.strip()
        frame = frame.loc[state_series.eq(selected_state)].copy()
    if frame.empty:
        fig = _layout(go.Figure(), height=height, margin=dict(l=8, r=8, t=8, b=8))
        fig.add_annotation(
            text="No mapped campuses in this view.",
            showarrow=False,
            x=.5,
            y=.5,
            xref="paper",
            yref="paper",
            font={"color": COLORS["muted"], "size": 13},
        )
        return fig

    frame["Marker Size"] = _marker_sizes(frame, size_by)
    frame["Campus Label"] = frame.get("Campus Label", frame.get("Campus Name", pd.Series("", index=frame.index))).fillna("").astype(str)
    frame["Operator"] = frame.get("Operator", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["County"] = frame.get("County", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["State"] = frame.get("State", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["Status"] = frame.get("Status", pd.Series("Status unknown", index=frame.index)).fillna("Status unknown").astype(str)
    frame["Identity Confidence"] = frame.get("Identity Confidence", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["Building Count"] = pd.to_numeric(frame.get("Building Count", pd.Series(np.nan, index=frame.index)), errors="coerce")
    frame["Capacity MW"] = _capacity(frame)

    fig = go.Figure()
    status_order = list(dict.fromkeys([*list(_STATUS_COLORS), *frame["Status"].tolist()]))
    for status in status_order:
        subset = frame.loc[frame["Status"].eq(status)].copy()
        if subset.empty:
            continue
        capacity_text = subset["Capacity MW"].map(lambda value: "n/a" if pd.isna(value) else f"{float(value):,.0f} MW")
        building_text = subset["Building Count"].map(lambda value: "n/a" if pd.isna(value) else f"{int(value):,}")
        custom = np.column_stack([
            subset["Campus ID"].astype(str),
            subset["Campus Label"].astype(str),
            subset["Operator"].replace("", "Unreported").astype(str),
            subset["County"].astype(str),
            subset["State"].astype(str),
            capacity_text.astype(str),
            building_text.astype(str),
            subset["Identity Confidence"].replace("", "n/a").astype(str),
        ])
        selectedpoints = None
        if selected_campus_id:
            local_positions = [position for position, campus_id in enumerate(subset["Campus ID"].astype(str)) if campus_id == str(selected_campus_id)]
            selectedpoints = local_positions or None
        fig.add_trace(go.Scattermap(
            lon=subset["Longitude"],
            lat=subset["Latitude"],
            mode="markers",
            name=status,
            marker={
                "size": subset["Marker Size"],
                "color": _STATUS_COLORS.get(status, "#94a3b8"),
                "opacity": 0.90,
            },
            selectedpoints=selectedpoints,
            selected={"marker": {"opacity": 1.0, "size": 18.0}},
            unselected={"marker": {"opacity": 0.66}},
            customdata=custom,
            hovertemplate=(
                "<b>%{customdata[1]}</b>"
                "<br>%{customdata[2]}"
                "<br>%{customdata[3]}, %{customdata[4]}"
                f"<br>Status: {status}"
                "<br>Published / planned capacity: %{customdata[5]}"
                "<br>Buildings: %{customdata[6]}"
                "<br>Identity confidence: %{customdata[7]}"
                "<extra></extra>"
            ),
        ))

    view = map_view(selected_state or None, height=height)
    view["layers"] = map_layers(selected_state or None)
    fig.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        dragmode="pan",
        map=view,
        uirevision=f"canonical-campus-map:{selected_state or 'US'}",
    )
    return fig


def data_center_stage_profile(stage: pd.DataFrame | None, *, height: int = 520):
    frame = pd.DataFrame(stage).copy()
    if frame.empty:
        return _layout(go.Figure(), height=height)
    stage_col = "Stage" if "Stage" in frame.columns else frame.columns[0]
    sites_col = next((column for column in ("Sites", "Campuses", "Projects") if column in frame.columns), None)
    if sites_col is None:
        return _layout(go.Figure(), height=height)
    frame[sites_col] = pd.to_numeric(frame[sites_col], errors="coerce")
    fig = go.Figure(go.Bar(x=frame[stage_col], y=frame[sites_col], marker={"color": COLORS.get("violet", "#8b5cf6")}, hovertemplate="%{x}<br>%{y:,.0f}<extra></extra>"))
    return _layout(fig, height=height)


def data_center_state_pipeline(states: pd.DataFrame | None, *, height: int = 520):
    frame = pd.DataFrame(states).copy()
    if frame.empty or "State" not in frame.columns:
        return _layout(go.Figure(), height=height)
    metric = next((column for column in ("Active Pipeline", "Development", "Total") if column in frame.columns), None)
    if metric is None:
        return _layout(go.Figure(), height=height)
    frame[metric] = pd.to_numeric(frame[metric], errors="coerce")
    frame = frame.nlargest(20, metric)
    fig = go.Figure(go.Bar(x=frame[metric], y=frame["State"], orientation="h", marker={"color": COLORS.get("violet", "#8b5cf6")}, hovertemplate="%{y}<br>%{x:,.0f}<extra></extra>"))
    fig.update_yaxes(categoryorder="total ascending")
    return _layout(fig, height=height)


def data_center_region_landscape(regions: pd.DataFrame | None, *, height: int = 520):
    frame = pd.DataFrame(regions).copy()
    if frame.empty or "Region" not in frame.columns:
        return _layout(go.Figure(), height=height)
    fig = go.Figure()
    for column, color in (("Operating", COLORS.get("blue", "#60a5fa")), ("Development", COLORS.get("violet", "#8b5cf6"))):
        if column in frame.columns:
            fig.add_bar(name=column, x=frame["Region"], y=pd.to_numeric(frame[column], errors="coerce"), marker={"color": color})
    fig.update_layout(barmode="group")
    return _layout(fig, height=height, legend=True)


def data_center_operator_pipeline(campuses: pd.DataFrame | None, *, height: int = 470):
    frame = _campuses(campuses)
    if frame.empty:
        return _layout(go.Figure(), height=height)
    status = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame = frame.loc[status.isin(ACTIVE_CAMPUS_STATUSES)].copy()
    frame["Operator"] = frame.get("Operator", pd.Series("", index=frame.index)).fillna("").astype(str).str.strip().replace("", np.nan)
    grouped = frame.dropna(subset=["Operator"]).groupby("Operator", as_index=False)["Campus ID"].nunique().rename(columns={"Campus ID": "Campuses"}).nlargest(15, "Campuses")
    fig = go.Figure(go.Bar(x=grouped["Campuses"], y=grouped["Operator"], orientation="h", marker={"color": COLORS.get("violet", "#8b5cf6")}, hovertemplate="%{y}<br>%{x:,.0f} campuses<extra></extra>"))
    fig.update_yaxes(categoryorder="total ascending")
    return _layout(fig, height=height)


def data_center_capacity_distribution(campuses: pd.DataFrame | None, *, height: int = 420):
    frame = _campuses(campuses)
    values = _capacity(frame).dropna() if not frame.empty else pd.Series(dtype=float)
    fig = go.Figure(go.Histogram(x=values, nbinsx=30, marker={"color": COLORS.get("blue", "#60a5fa")}, hovertemplate="%{x:,.0f} MW<br>%{y} campuses<extra></extra>"))
    return _layout(fig, height=height)


def data_center_largest_campuses(campuses: pd.DataFrame | None, *, height: int = 420, top_n: int = 15):
    frame = _campuses(campuses)
    if frame.empty:
        return _layout(go.Figure(), height=height)
    frame["Capacity MW"] = _capacity(frame)
    frame["Campus Label"] = frame.get("Campus Label", frame.get("Campus Name", pd.Series("", index=frame.index))).fillna("").astype(str)
    frame = frame.dropna(subset=["Capacity MW"]).nlargest(top_n, "Capacity MW").sort_values("Capacity MW")
    fig = go.Figure(go.Bar(
        x=frame["Capacity MW"] / 1000.0,
        y=frame["Campus Label"],
        orientation="h",
        marker={"color": COLORS.get("blue", "#60a5fa")},
        customdata=np.column_stack([frame.get("Operator", pd.Series("", index=frame.index)).astype(str), frame.get("State", pd.Series("", index=frame.index)).astype(str)]),
        hovertemplate="<b>%{y}</b><br>%{x:.2f} GW<br>%{customdata[0]} · %{customdata[1]}<extra></extra>",
    ))
    fig.update_xaxes(title="Published / planned capacity (GW)")
    return _layout(fig, height=height)


__all__ = [
    "ACTIVE_CAMPUS_STATUSES",
    "CAMPUS_SIZE_METRICS",
    "data_center_map",
    "data_center_stage_profile",
    "data_center_state_pipeline",
    "data_center_region_landscape",
    "data_center_operator_pipeline",
    "data_center_capacity_distribution",
    "data_center_largest_campuses",
]
