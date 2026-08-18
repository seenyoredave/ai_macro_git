from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from loaders.data_center_registry import campus_display_labels
from analytics.water_campus import state_campus_evidence_profile
from analytics.water_competition import current_top_withdrawal_profile, local_context_coverage_profile
from rendering.charts_common import COLORS, _base_layout, add_axis_headroom
from rendering.map_geometry import map_layers, map_view

WATER_COLORS = {
    "ground": "#2563eb",
    "surface": "#60a5fa",
    "primary": "#8b5cf6",
    "secondary": "#6366f1",
    "neutral": "#94a3b8",
    "deep": "#334155",
    "plot": "rgba(15,23,42,0.28)",
}

_LATITUDE_CANDIDATES = (
    "Latitude", "Campus Latitude", "Lat", "latitude", "lat",
)
_LONGITUDE_CANDIDATES = (
    "Longitude", "Campus Longitude", "Lon", "Lng", "longitude", "lon", "lng",
)

def _water_layout(fig, *, height=360, margin=None, legend=False):
    fig = _base_layout(fig, height=height, margin=margin, legend=legend)
    fig.update_layout(
        plot_bgcolor=WATER_COLORS["plot"],
        hoverlabel={"bgcolor": "#111827", "font": {"color": COLORS["text"]}},
    )
    return fig

def _resolve_coordinate_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    for column in candidates:
        if column in frame.columns:
            return column
    return None

def _normalize_fips(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(5) if digits else ""

def _county_geojson() -> dict:
    path = Path(__file__).resolve().parents[1] / "assets" / "geo" / "us_counties.geojson"
    if not path.exists():
        return {"type": "FeatureCollection", "features": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

def _county_geometry_frame() -> pd.DataFrame:
    rows = []
    for feature in _county_geojson().get("features", []):
        properties = feature.get("properties") or {}
        fips = _normalize_fips(feature.get("id"))
        if not fips:
            continue
        rows.append({
            "FIPS": fips,
            "State": str(properties.get("STATE") or "").strip().upper(),
            "County": str(properties.get("NAME") or "").strip(),
        })
    return pd.DataFrame(rows)

def county_state_for_fips(fips) -> str:
    key = _normalize_fips(fips)
    if not key:
        return ""
    frame = _county_geometry_frame()
    if frame.empty:
        return ""
    match = frame.loc[frame["FIPS"].eq(key), "State"]
    return str(match.iloc[0]) if not match.empty else ""

def _county_drought_frame(county_drought: pd.DataFrame | None) -> pd.DataFrame:
    geometry = _county_geometry_frame().copy()
    if geometry.empty:
        return geometry
    drought = county_drought.copy() if isinstance(county_drought, pd.DataFrame) else pd.DataFrame()
    if drought.empty or "FIPS" not in drought.columns:
        for column in ("D0+ Area Percent", "D1+ Area Percent", "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent"):
            geometry[column] = np.nan
        geometry["Snapshot Date"] = ""
        geometry["Has Current Drought Data"] = False
        return geometry

    drought = drought.copy()
    drought["FIPS"] = drought["FIPS"].map(_normalize_fips)
    drought = drought.loc[drought["FIPS"].ne("")].drop_duplicates("FIPS", keep="last")
    keep = [
        "FIPS", "Snapshot Date", "D0+ Area Percent", "D1+ Area Percent",
        "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent",
    ]
    drought = drought[[column for column in keep if column in drought.columns]].copy()
    for column in ("D0+ Area Percent", "D1+ Area Percent", "D2+ Area Percent", "D3+ Area Percent", "D4 Area Percent"):
        if column not in drought.columns:
            drought[column] = np.nan
        drought[column] = pd.to_numeric(drought[column], errors="coerce")
    drought["Has Current Drought Data"] = drought["D2+ Area Percent"].notna()
    merged = geometry.merge(drought, on="FIPS", how="left")
    merged["Has Current Drought Data"] = merged["Has Current Drought Data"].eq(True)
    if "Snapshot Date" not in merged.columns:
        merged["Snapshot Date"] = ""
    merged["Snapshot Date"] = merged["Snapshot Date"].fillna("").astype(str)
    return merged

def _campus_fips_counts(campus_context: pd.DataFrame | None) -> pd.DataFrame:
    if campus_context is None or not isinstance(campus_context, pd.DataFrame) or campus_context.empty:
        return pd.DataFrame(columns=["FIPS", "Mapped Campuses"])
    frame = campus_context.copy()
    if "FIPS" not in frame.columns:
        return pd.DataFrame(columns=["FIPS", "Mapped Campuses"])
    frame["FIPS"] = frame["FIPS"].map(_normalize_fips)
    frame = frame.loc[frame["FIPS"].ne("")].copy()
    if frame.empty:
        return pd.DataFrame(columns=["FIPS", "Mapped Campuses"])
    if "Campus ID" in frame.columns:
        counts = frame.groupby("FIPS")["Campus ID"].nunique().rename("Mapped Campuses")
    else:
        counts = frame.groupby("FIPS").size().rename("Mapped Campuses")
    return counts.reset_index()

def _campus_points(campus_context: pd.DataFrame | None, state: str) -> pd.DataFrame:
    if campus_context is None or not isinstance(campus_context, pd.DataFrame) or campus_context.empty:
        return pd.DataFrame()
    lat_col = _resolve_coordinate_column(campus_context, _LATITUDE_CANDIDATES)
    lon_col = _resolve_coordinate_column(campus_context, _LONGITUDE_CANDIDATES)
    if not lat_col or not lon_col:
        return pd.DataFrame()
    frame = campus_context.copy()
    frame["State"] = frame.get("State", pd.Series("", index=frame.index)).fillna("").astype(str).str.upper().str.strip()
    frame = frame.loc[frame["State"].eq(str(state or "").upper().strip())].copy()
    if frame.empty:
        return frame
    frame["Latitude"] = pd.to_numeric(frame.get(lat_col), errors="coerce")
    frame["Longitude"] = pd.to_numeric(frame.get(lon_col), errors="coerce")
    frame = frame.dropna(subset=["Latitude", "Longitude"]).copy()
    if frame.empty:
        return frame

    published = pd.to_numeric(frame.get("Published Capacity Estimate MW", pd.Series(np.nan, index=frame.index)), errors="coerce")
    planned = pd.to_numeric(frame.get("Planned Data Center Capacity MW", pd.Series(np.nan, index=frame.index)), errors="coerce")
    frame["Published Capacity MW"] = published.combine_first(planned)
    frame["Marker Size"] = np.clip(7.5 + np.sqrt(frame["Published Capacity MW"].fillna(0).clip(lower=0)) * 0.22, 7.5, 18)
    frame["Campus Name"] = campus_display_labels(frame)
    frame["Operator"] = frame.get("Operator", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["County"] = frame.get("County", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["Status"] = frame.get("Status", pd.Series("", index=frame.index)).fillna("").astype(str)
    frame["County D2+ Area Percent"] = pd.to_numeric(
        frame.get("County D2+ Area Percent", pd.Series(np.nan, index=frame.index)), errors="coerce"
    )
    frame["EPA Overlap"] = frame.get("PWS Service Area Overlap", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    frame["Direct Evidence"] = frame.get("Direct Water Evidence", pd.Series(False, index=frame.index)).fillna(False).astype(bool)
    return frame

def water_local_context_coverage(summary: dict | None, *, height: int = 450):
    frame = local_context_coverage_profile(summary)
    fig = go.Figure()
    if not frame.empty:
        color_map = {
            "registry": "#475569",
            "physical context": WATER_COLORS["primary"],
            "service-area context": WATER_COLORS["secondary"],
            "campus evidence": WATER_COLORS["surface"],
        }
        colors = [color_map.get(str(value), WATER_COLORS["neutral"]) for value in frame["Layer Type"]]
        fig.add_trace(go.Bar(
            x=frame["Campuses"],
            y=frame["Coverage Layer"],
            orientation="h",
            marker={"color": colors, "line": {"width": 0.7, "color": "rgba(15,23,42,0.55)"}},
            text=[f"{int(value):,}" for value in frame["Campuses"]],
            textposition="outside",
            cliponaxis=False,
            customdata=np.stack([frame["Coverage"] * 100.0, frame["Layer Type"]], axis=-1),
            hovertemplate=(
                "%{y}<br>Campuses: %{x:,.0f}"
                "<br>Coverage: %{customdata[0]:.1f}%"
                "<br>Layer: %{customdata[1]}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Campus records")
    fig.update_yaxes(
        title="",
        categoryorder="array",
        categoryarray=list(reversed(frame["Coverage Layer"].tolist())) if not frame.empty else None,
    )
    fig = _water_layout(fig, height=height, margin=dict(l=205, r=54, t=24, b=48))
    return add_axis_headroom(fig, axis="x", upper=0.20, lower=0.0, include_zero=True)

def water_county_drought_map(
    county_drought: pd.DataFrame | None,
    campus_context: pd.DataFrame | None = None,
    *,
    state: str | None = None,
    height: int = 560,
):
    """Render current D2+ drought as filled county polygons.

    National view colors every county with a current observation. State view
    keeps the county surface and adds mapped campus points for local detail.
    """
    geojson = _county_geojson()
    frame = _county_drought_frame(county_drought)
    fig = go.Figure()
    if frame.empty or not geojson.get("features"):
        fig = _water_layout(fig, height=height, margin=dict(l=16, r=16, t=16, b=16), legend=False)
        fig.add_annotation(
            text="County boundary geometry is unavailable.",
            showarrow=False,
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            font={"size": 13, "color": COLORS["muted"]},
        )
        return fig

    selected_state = str(state or "").upper().strip()
    if selected_state:
        frame = frame.loc[frame["State"].eq(selected_state)].copy()
        feature_ids = set(frame["FIPS"].tolist())
        map_geojson = {
            "type": "FeatureCollection",
            "features": [feature for feature in geojson.get("features", []) if _normalize_fips(feature.get("id")) in feature_ids],
        }
    else:
        map_geojson = geojson

    counts = _campus_fips_counts(campus_context)
    if not counts.empty:
        frame = frame.merge(counts, on="FIPS", how="left")
    if "Mapped Campuses" not in frame.columns:
        frame["Mapped Campuses"] = 0
    frame["Mapped Campuses"] = pd.to_numeric(frame["Mapped Campuses"], errors="coerce").fillna(0)

    # -1 is reserved for counties without a current observation. Zero is a
    # valid D2+ reading and receives its own neutral fill.
    frame["Map D2"] = pd.to_numeric(frame["D2+ Area Percent"], errors="coerce").fillna(-1.0)
    d1 = pd.to_numeric(frame["D1+ Area Percent"], errors="coerce")
    d2 = pd.to_numeric(frame["D2+ Area Percent"], errors="coerce")
    d3 = pd.to_numeric(frame["D3+ Area Percent"], errors="coerce")
    d1_text = d1.map(lambda value: "n/a" if pd.isna(value) else f"{float(value):.1f}%")
    d2_text = d2.map(lambda value: "n/a" if pd.isna(value) else f"{float(value):.1f}%")
    d3_text = d3.map(lambda value: "n/a" if pd.isna(value) else f"{float(value):.1f}%")
    snapshot_text = frame["Snapshot Date"].map(lambda value: str(value).strip() or "n/a")
    custom = np.column_stack([
        frame["County"].astype(str),
        frame["State"].astype(str),
        d1_text.astype(str),
        d2_text.astype(str),
        d3_text.astype(str),
        frame["Mapped Campuses"].astype(float),
        snapshot_text.astype(str),
    ])

    fig.add_trace(go.Choroplethmap(
        geojson=map_geojson,
        locations=frame["FIPS"],
        z=frame["Map D2"],
        featureidkey="id",
        zmin=-1,
        zmax=100,
        colorscale=[
            [0.0000, "#111827"],
            [0.0098, "#111827"],
            [0.0099, "#263244"],
            [0.0101, "#fde047"],
            [0.2550, "#facc15"],
            [0.5050, "#fb923c"],
            [0.7525, "#ef4444"],
            [1.0000, "#7f1d1d"],
        ],
        marker={"line": {"color": "rgba(203,213,225,0.30)", "width": 0.35}},
        colorbar={
            "title": {"text": "D2+ county area", "font": {"size": 10}},
            "tickvals": [0, 25, 50, 75, 100],
            "ticktext": ["0%", "25%", "50%", "75%", "100%"],
            "thickness": 11,
            "len": 0.72,
            "x": 1.015,
        },
        customdata=custom,
        hovertemplate=(
            "<b>%{customdata[0]}, %{customdata[1]}</b>"
            "<br>D1+ county area: %{customdata[2]}"
            "<br>D2+ county area: %{customdata[3]}"
            "<br>D3+ county area: %{customdata[4]}"
            "<br>Mapped campuses: %{customdata[5]:,.0f}"
            "<br>Snapshot: %{customdata[6]}<extra></extra>"
        ),
        selected={"marker": {"opacity": 1.0}},
        unselected={"marker": {"opacity": 1.0}},
        name="County drought",
    ))

    if selected_state:
        points = _campus_points(campus_context, selected_state)
        if not points.empty:
            capacity = points["Published Capacity MW"]
            capacity_text = capacity.map(lambda value: "Not published" if pd.isna(value) else f"{float(value):,.0f} MW")
            d2_text = points["County D2+ Area Percent"].map(lambda value: "n/a" if pd.isna(value) else f"{float(value):.1f}%")
            custom_points = np.column_stack([
                points.get("Campus ID", pd.Series("", index=points.index)).astype(str),
                points["Operator"].astype(str),
                points["County"].astype(str),
                points["Status"].astype(str),
                capacity_text.astype(str),
                d2_text.astype(str),
                points["EPA Overlap"].map({True: "Yes", False: "No"}).astype(str),
                points["Direct Evidence"].map({True: "Yes", False: "No"}).astype(str),
            ])
            fig.add_trace(go.Scattermap(
                lon=points["Longitude"],
                lat=points["Latitude"],
                text=points["Campus Name"],
                mode="markers",
                marker={
                    "size": points["Marker Size"],
                    "color": "#f8fafc",
                    "opacity": 0.94,
                },
                customdata=custom_points,
                hovertemplate=(
                    "<b>%{text}</b>"
                    "<br>%{customdata[1]}"
                    "<br>%{customdata[2]}"
                    "<br>Status: %{customdata[3]}"
                    "<br>Published capacity: %{customdata[4]}"
                    "<br>County D2+: %{customdata[5]}"
                    "<br>EPA boundary overlap: %{customdata[6]}"
                    "<br>Direct water evidence: %{customdata[7]}<extra></extra>"
                ),
                name="Campuses",
                showlegend=False,
            ))

    fig = _water_layout(fig, height=height, margin=dict(l=0, r=0, t=0, b=0), legend=False)
    view = map_view(selected_state or None, height=height)
    view["layers"] = map_layers(selected_state or None)
    fig.update_layout(
        map=view,
        dragmode="pan",
        uirevision=f"water-county-map:{selected_state or 'US'}",
    )
    return fig

def thermoelectric_water_groups(group_frame, *, metric="Withdrawal", height=360):
    frame = group_frame.copy() if isinstance(group_frame, pd.DataFrame) else pd.DataFrame()
    column = f"{metric} Bgal/day"
    fig = go.Figure()
    if not frame.empty and {"Group", column}.issubset(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame.dropna(subset=[column]).sort_values(column, ascending=True, kind="stable")
        fig.add_trace(go.Bar(
            x=frame[column], y=frame["Group"].astype(str), orientation="h",
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
    profile = current_top_withdrawal_profile(frame)
    fig = go.Figure()
    if not profile.empty:
        ordered = profile.sort_values("Withdrawal Bgal/day", ascending=True, kind="stable")
        color_map = {"Crop irrigation": "#8b5cf6", "Thermoelectric power": "#60a5fa", "Public supply": "#94a3b8"}
        colors = [color_map.get(str(label), WATER_COLORS["neutral"]) for label in ordered["Use Category"]]
        fig.add_trace(go.Bar(
            x=ordered["Withdrawal Bgal/day"], y=ordered["Use Category"], orientation="h",
            marker={"color": colors, "line": {"width": 0.7, "color": "rgba(15,23,42,0.58)"}},
            text=[f"{value:,.1f}" for value in ordered["Withdrawal Bgal/day"]], textposition="outside", cliponaxis=False,
            customdata=np.stack([ordered["Share of Top Three"] * 100.0, ordered["Observation Year"].astype(float)], axis=-1),
            hovertemplate=(
                "%{y}<br>Withdrawal: %{x:,.1f} Bgal/day"
                "<br>Share of selected top-three total: %{customdata[0]:.1f}%"
                "<br>Observation year: %{customdata[1]:.0f}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Average daily withdrawal · billion gallons per day")
    fig.update_yaxes(title="")
    fig = _water_layout(fig, height=height, margin=dict(l=165, r=58, t=26, b=50))
    return add_axis_headroom(fig, axis="x", upper=0.18, lower=0.0, include_zero=True)

def water_state_evidence_profile(campus_context: pd.DataFrame | None, *, height: int = 430, top_n: int = 16):
    frame = state_campus_evidence_profile(campus_context)
    fig = go.Figure()
    if not frame.empty:
        frame = frame.head(max(int(top_n), 1)).sort_values("Mapped Campuses", ascending=True, kind="stable")
        fig.add_trace(go.Bar(
            x=frame["Mapped Campuses"], y=frame["State"], orientation="h", name="Mapped campuses",
            marker={"color": "#475569", "line": {"width": 0.6, "color": "rgba(15,23,42,0.55)"}},
            customdata=np.stack([frame["Direct Water Evidence"], frame["Quantified Use"], frame["Direct Evidence Coverage"] * 100.0], axis=-1),
            hovertemplate=(
                "%{y}<br>Mapped campuses: %{x:,.0f}"
                "<br>Direct water evidence: %{customdata[0]:,.0f}"
                "<br>Quantified use records: %{customdata[1]:,.0f}"
                "<br>Direct-evidence coverage: %{customdata[2]:.1f}%<extra></extra>"
            ),
        ))
        fig.add_trace(go.Scatter(
            x=frame["Direct Water Evidence"], y=frame["State"], mode="markers", name="Direct water evidence",
            marker={"size": 9, "color": WATER_COLORS["primary"], "line": {"width": 1.0, "color": "rgba(248,250,252,0.65)"}},
            customdata=np.stack([frame["Mapped Campuses"], frame["Quantified Use"], frame["Direct Evidence Coverage"] * 100.0], axis=-1),
            hovertemplate=(
                "%{y}<br>Direct water evidence: %{x:,.0f}"
                "<br>Mapped campuses: %{customdata[0]:,.0f}"
                "<br>Quantified use records: %{customdata[1]:,.0f}"
                "<br>Direct-evidence coverage: %{customdata[2]:.1f}%<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Campus records")
    fig.update_yaxes(title="")
    fig = _water_layout(fig, height=height, margin=dict(l=56, r=42, t=72, b=48), legend=True)
    fig.update_layout(legend={"orientation": "h", "y": 1.13, "x": 0, "yanchor": "bottom"}, bargap=0.28)
    return add_axis_headroom(fig, axis="x", upper=0.18, lower=0.0, include_zero=True)

def wastewater_construction_history(history: pd.DataFrame | None, *, height: int = 390):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        clean = pd.DataFrame(columns=["Observation Date", "Public Sewage and Waste Disposal Construction"])
    else:
        clean = history.copy()
        clean["Observation Date"] = pd.to_datetime(clean.get("Observation Date"), errors="coerce", format="mixed")
        clean["Public Sewage and Waste Disposal Construction"] = pd.to_numeric(clean.get("Public Sewage and Waste Disposal Construction"), errors="coerce")
        clean = clean.loc[clean["Observation Date"] >= pd.Timestamp("2020-01-01")].dropna(
            subset=["Observation Date", "Public Sewage and Waste Disposal Construction"]
        ).sort_values("Observation Date", kind="stable")
    fig = go.Figure(go.Scatter(
        x=clean.get("Observation Date"),
        y=clean.get("Public Sewage and Waste Disposal Construction") / 1000.0 if not clean.empty else None,
        mode="lines",
        line={"color": "#8b5cf6", "width": 2.4},
        fill="tozeroy",
        fillcolor="rgba(139,92,246,0.16)",
        hovertemplate="%{x|%Y-%m}<br>$%{y:,.1f}B<extra></extra>",
    ))
    fig.update_xaxes(title="Observation date")
    fig.update_yaxes(title="SAAR · billions of dollars")
    fig = _water_layout(fig, height=height, margin=dict(l=56, r=22, t=26, b=48))
    return add_axis_headroom(fig, axis="y", upper=0.16, lower=0.0, include_zero=True)

__all__ = [
    "county_state_for_fips",
    "water_local_context_coverage",
    "water_county_drought_map",
    "thermoelectric_water_groups",
    "water_top_withdrawals_2020",
    "water_state_evidence_profile",
    "wastewater_construction_history",
]
