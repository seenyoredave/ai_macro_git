from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from rendering.charts_common import COLORS, _base_layout, add_axis_headroom, add_stacked_axis_headroom, _nice_axis_range



DATA_CENTER_COLORS = {
    "operating": "#60a5fa",
    "expanding": "#818cf8",
    "construction": "#a78bfa",
    "proposed": "#7c3aed",
    "inactive": "#64748b",
    "cancelled": "#475569",
    "reference": "#94a3b8",
}

FACILITY_SIZE_METRICS = {
    "Facility count": None,
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

FACILITY_STATUS_ALIASES = {
    "Approved / under construction": "Approved / permitted / under construction",
    "Operating": "Operational",
    "Proposed": "Planned",
    "Unknown": "Status unknown",
    "": "Status unknown",
}

FACILITY_STATUS_STYLES = {
    "Operational": (COLORS["green"], "Operational"),
    "Expanding": (COLORS["blue"], "Expanding"),
    "Approved / permitted / under construction": (COLORS["amber"], "Approved / permitted / construction"),
    "Under construction": (COLORS["amber"], "Under construction"),
    "Planned": (COLORS["violet"], "Planned / proposed"),
    "Announced": (COLORS["violet_deep"], "Announced"),
    "Suspended": (COLORS["slate"], "Suspended"),
    "Cancelled": (COLORS["red"], "Cancelled"),
    "Blocked": (COLORS["red"], "Blocked"),
    "Observed footprint": ("#64748b", "Observed footprint"),
    "Status unknown": ("#475569", "Status unknown"),
}

def _status_groups(values: pd.Series) -> pd.Series:
    return values.fillna("").astype(str).replace(FACILITY_STATUS_ALIASES)

def facility_map_legend_items(locations: pd.DataFrame | None) -> list[tuple[str, str]]:
    if locations is None or not isinstance(locations, pd.DataFrame) or locations.empty:
        return []
    status = locations.get("Status", pd.Series("", index=locations.index))
    present = set(_status_groups(status).dropna().astype(str))
    ordered = [
        (label, color)
        for key, (color, label) in FACILITY_STATUS_STYLES.items()
        if key in present
    ]
    known = set(FACILITY_STATUS_STYLES)
    ordered.extend((key, "#475569") for key in sorted(present - known))
    return ordered

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
    evidence_type = str(row.get("Evidence Type") or "")
    source_class = str(row.get("Source Class") or "")
    lines = [facility, operator, place, f"Status: {status}", f"Evidence: {evidence}", f"Location: {precision}"]
    if source_class:
        lines.append(f"Record: {source_class}")
    if evidence_type:
        lines.append(f"Basis: {evidence_type}")
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
    required = {"Latitude", "Longitude"}
    if locations is None or not isinstance(locations, pd.DataFrame) or locations.empty or not required.issubset(locations.columns):
        clean = pd.DataFrame(columns=["Latitude", "Longitude", "Facility", "Operator", "County", "State"])
    else:
        clean = locations.copy()
        for column in ["Latitude", "Longitude"]:
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        for column in [
            "Facility", "Operator", "County", "State", "Status", "Evidence Grade",
            "Evidence Type", "Source Class", "Location Precision",
        ]:
            if column not in clean.columns:
                clean[column] = ""
            clean[column] = clean[column].fillna("").astype(str)
        clean = clean.dropna(subset=["Latitude", "Longitude"]).reset_index(drop=True)

    metric_column = FACILITY_SIZE_METRICS.get(size_by)
    figure = go.Figure()
    if not clean.empty:
        if metric_column is None:
            clean["_known"] = True
            clean["_marker_size"] = 6.5
        else:
            if metric_column not in clean.columns:
                clean[metric_column] = np.nan
            clean[metric_column] = pd.to_numeric(clean[metric_column], errors="coerce")
            clean["_known"] = clean[metric_column].notna() & (clean[metric_column] > 0)
            clean["_marker_size"] = _bubble_sizes(clean[metric_column])

        clean["_status_group"] = _status_groups(clean["Status"])
        order = list(FACILITY_STATUS_STYLES)
        present = clean["_status_group"].dropna().astype(str).unique().tolist()
        for status in order + sorted(set(present) - set(order)):
            rows = clean.loc[clean["_status_group"].eq(status)].copy()
            if rows.empty:
                continue
            color, label = FACILITY_STATUS_STYLES.get(status, ("#475569", status))
            known = rows.loc[rows["_known"]].copy()
            unknown = rows.loc[~rows["_known"]].copy()
            if not known.empty:
                figure.add_trace(go.Scattergeo(
                    lon=known["Longitude"],
                    lat=known["Latitude"],
                    text=[_facility_hover(row, metric_column, size_by) for _, row in known.iterrows()],
                    mode="markers",
                    hovertemplate="%{text}<extra></extra>",
                    marker={
                        "size": known["_marker_size"],
                        "color": color,
                        "opacity": 0.76,
                        "line": {"width": 0.55, "color": "#0f172a"},
                        "sizemode": "diameter",
                    },
                    name=label,
                    legendgroup=status,
                ))
            if not unknown.empty:
                figure.add_trace(go.Scattergeo(
                    lon=unknown["Longitude"],
                    lat=unknown["Latitude"],
                    text=[_facility_hover(row, metric_column, size_by) for _, row in unknown.iterrows()],
                    mode="markers",
                    hovertemplate="%{text}<extra></extra>",
                    marker={
                        "size": 6.0,
                        "color": "rgba(15,23,42,0.18)",
                        "opacity": 0.92,
                        "line": {"width": 1.35, "color": color},
                    },
                    name=f"{label} · metric unavailable",
                    legendgroup=status,
                    showlegend=known.empty,
                ))
    figure.update_layout(
        height=height,
        margin=dict(l=0, r=0, t=4, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
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

def data_center_service_trajectory(registry: pd.DataFrame | None, *, height: int = 300):
    if registry is None or not isinstance(registry, pd.DataFrame) or registry.empty:
        grouped = pd.DataFrame(columns=["Year", "Stage", "Capacity GW", "Facilities"])
    else:
        clean = registry.copy()
        service_dates = (
            clean["Expected Service Date"]
            if "Expected Service Date" in clean.columns
            else pd.Series(pd.NaT, index=clean.index)
        )
        clean["Expected Service Date"] = pd.to_datetime(service_dates, errors="coerce", format="mixed")
        published = pd.to_numeric(
            clean["Published Capacity Estimate MW"]
            if "Published Capacity Estimate MW" in clean.columns
            else pd.Series(np.nan, index=clean.index),
            errors="coerce",
        )
        structured = pd.to_numeric(
            clean["Planned Data Center Capacity MW"]
            if "Planned Data Center Capacity MW" in clean.columns
            else pd.Series(np.nan, index=clean.index),
            errors="coerce",
        )
        clean["Capacity MW"] = structured.combine_first(published)
        active_statuses = {
            "Operational", "Expanding", "Approved / permitted / under construction",
            "Under construction", "Proposed", "Planned", "Announced",
        }
        clean = clean.loc[clean.get("Status", "").isin(active_statuses)].dropna(
            subset=["Expected Service Date", "Capacity MW"]
        ).copy()
        clean["Year"] = clean["Expected Service Date"].dt.year.astype(int)
        clean["Stage"] = np.where(clean["Status"].eq("Operational"), "Online", "Pipeline")
        grouped = (clean.groupby(["Year", "Stage"], dropna=False)
                   .agg(**{"Capacity GW": ("Capacity MW", lambda x: x.sum()/1000.0), "Facilities": ("Stage", "size")})
                   .reset_index())
    fig = go.Figure()
    for stage, color in [("Online", COLORS["green"]), ("Pipeline", COLORS["violet"])]:
        rows = grouped.loc[grouped["Stage"].eq(stage)] if not grouped.empty else grouped
        if rows.empty:
            continue
        fig.add_trace(go.Bar(
            x=rows["Year"].astype(str), y=rows["Capacity GW"], name=stage, marker={"color": color},
            customdata=rows[["Facilities"]],
            hovertemplate=f"%{{x}}<br>{stage}: %{{y:,.1f}} GW<br>%{{customdata[0]}} projects<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    if not grouped.empty:
        cumulative = (
            grouped.groupby("Year", as_index=False)["Capacity GW"].sum()
            .sort_values("Year", kind="stable")
        )
        cumulative["Cumulative GW"] = cumulative["Capacity GW"].cumsum()
        fig.add_trace(go.Scatter(
            x=cumulative["Year"],
            y=cumulative["Cumulative GW"],
            mode="lines+markers",
            name="Cumulative published capacity estimate",
            line={"color": COLORS["amber"], "width": 2.2, "dash": "dot"},
            marker={"size": 6},
            hovertemplate="%{x}<br>Cumulative published capacity estimate: %{y:,.1f} GW<extra></extra>",
        ))
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(title="Published capacity estimate", ticksuffix=" GW")
    return _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=18, t=28, b=42))

def data_center_national_stage(stage: pd.DataFrame | None, *, height: int = 350):
    expected = [
        "Cancelled",
        "Suspended",
        "Operating",
        "Expanding",
        "Approved / under construction",
        "Proposed",
    ]
    if stage is None or not isinstance(stage, pd.DataFrame) or stage.empty:
        clean = pd.DataFrame(columns=["Stage", "Sites", "Published MW", "Published Square Feet"])
    else:
        clean = stage.copy()
        for column in ["Sites", "Published MW", "Published Square Feet"]:
            if column not in clean.columns:
                clean[column] = np.nan
            clean[column] = pd.to_numeric(clean[column], errors="coerce")
        clean["Stage"] = clean["Stage"].astype(str)
        clean["_order"] = clean["Stage"].map({name: index for index, name in enumerate(expected)})
        clean = clean.sort_values("_order", kind="stable").drop(columns="_order")
    fig = go.Figure()
    if not clean.empty:
        colors = {
            "Operating": COLORS["green"],
            "Expanding": COLORS["blue"],
            "Approved / under construction": COLORS["amber"],
            "Proposed": COLORS["violet"],
            "Suspended": COLORS["slate"],
            "Cancelled": COLORS["red"],
        }
        custom = np.column_stack([
            clean["Published MW"].map(lambda value: "n/a" if pd.isna(value) else f"{value / 1000:,.1f} GW"),
            clean["Published Square Feet"].map(lambda value: "n/a" if pd.isna(value) else f"{value / 1_000_000:,.1f}M sq ft"),
        ])
        fig.add_trace(go.Bar(
            y=clean["Stage"],
            x=clean["Sites"],
            orientation="h",
            marker={"color": clean["Stage"].map(colors).fillna(COLORS["slate"]).tolist()},
            text=clean["Sites"].map(lambda value: f"{int(value):,}"),
            textposition="outside",
            cliponaxis=False,
            customdata=custom,
            hovertemplate=(
                "%{y}<br>%{x:,.0f} sites"
                "<br>Published capacity: %{customdata[0]}"
                "<br>Published floor area: %{customdata[1]}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Sites")
    fig.update_yaxes(title="")
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=175, r=54, t=18, b=48))
    return add_axis_headroom(fig, axis="x", upper=0.22, lower=0.0, include_zero=True)



def data_center_stage_profile(stage: pd.DataFrame | None, *, height: int = 455):
    """Pair site counts and published capacity in one calm lifecycle view."""
    order = [
        "Operating",
        "Expanding",
        "Approved / under construction",
        "Proposed",
        "Suspended",
        "Cancelled",
    ]
    if stage is None or not isinstance(stage, pd.DataFrame) or stage.empty:
        clean = pd.DataFrame({"Stage": order, "Sites": 0.0, "Published GW": 0.0})
    else:
        clean = stage.copy()
        clean["Sites"] = pd.to_numeric(clean.get("Sites"), errors="coerce").fillna(0)
        clean["Published MW"] = pd.to_numeric(clean.get("Published MW"), errors="coerce")
        clean["Published GW"] = clean["Published MW"] / 1000.0
        clean = pd.DataFrame({"Stage": order}).merge(
            clean[["Stage", "Sites", "Published GW"]], on="Stage", how="left"
        ).fillna({"Sites": 0, "Published GW": 0})

    colors = {
        "Operating": DATA_CENTER_COLORS["operating"],
        "Expanding": DATA_CENTER_COLORS["expanding"],
        "Approved / under construction": DATA_CENTER_COLORS["construction"],
        "Proposed": DATA_CENTER_COLORS["proposed"],
        "Suspended": DATA_CENTER_COLORS["inactive"],
        "Cancelled": DATA_CENTER_COLORS["cancelled"],
    }
    display_order = list(reversed(order))
    clean["Stage"] = pd.Categorical(clean["Stage"], categories=display_order, ordered=True)
    clean = clean.sort_values("Stage", kind="stable")

    fig = make_subplots(
        rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.08,
        column_widths=[0.46, 0.54],
        subplot_titles=("Sites", "Published capacity"),
    )
    fig.add_trace(
        go.Bar(
            y=clean["Stage"].astype(str), x=clean["Sites"], orientation="h",
            marker={"color": [colors.get(str(value), DATA_CENTER_COLORS["inactive"]) for value in clean["Stage"]]},
            text=clean["Sites"].map(lambda value: f"{int(value):,}" if value else ""),
            textposition="outside", cliponaxis=False, showlegend=False,
            hovertemplate="%{y}<br>%{x:,.0f} sites<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(
            y=clean["Stage"].astype(str), x=clean["Published GW"], orientation="h",
            marker={"color": [colors.get(str(value), DATA_CENTER_COLORS["inactive"]) for value in clean["Stage"]]},
            text=clean["Published GW"].map(lambda value: f"{value:,.1f}" if value else ""),
            textposition="outside", cliponaxis=False, showlegend=False,
            customdata=clean[["Sites"]],
            hovertemplate="%{y}<br>%{x:,.1f} GW published<br>%{customdata[0]:,.0f} sites<extra></extra>",
        ),
        row=1, col=2,
    )
    sites_max = float(pd.to_numeric(clean["Sites"], errors="coerce").max() or 0.0)
    capacity_max = float(pd.to_numeric(clean["Published GW"], errors="coerce").max() or 0.0)
    _, sites_upper, sites_step = _nice_axis_range(0.0, sites_max, upper=0.22, lower=0.0, include_zero=True)
    _, capacity_upper, capacity_step = _nice_axis_range(0.0, capacity_max, upper=0.22, lower=0.0, include_zero=True)
    fig.update_xaxes(title="Sites", range=[0, sites_upper], dtick=sites_step, row=1, col=1)
    fig.update_xaxes(title="Published capacity (GW)", range=[0, capacity_upper], dtick=capacity_step, row=1, col=2)
    fig.update_yaxes(title="", categoryorder="array", categoryarray=display_order, row=1, col=1)
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=180, r=54, t=52, b=48))
    fig.update_layout(plot_bgcolor="rgba(15,23,42,0.24)")
    fig.update_annotations(font={"color": COLORS["muted"], "size": 11})
    return fig


def data_center_region_landscape(regions: pd.DataFrame | None, *, height: int = 350):
    if regions is None or not isinstance(regions, pd.DataFrame) or regions.empty:
        clean = pd.DataFrame(columns=["Region", "Operating", "Development"])
    else:
        clean = regions.copy()
        for column in ["Operating", "Development"]:
            clean[column] = pd.to_numeric(clean.get(column), errors="coerce")
        clean["Total"] = clean[["Operating", "Development"]].sum(axis=1)
        clean = clean.sort_values("Total", ascending=True, kind="stable")
    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(go.Bar(
            y=clean["Region"], x=clean["Operating"], orientation="h", name="Operating",
            marker={"color": DATA_CENTER_COLORS["operating"]},
            hovertemplate="%{y}<br>Operating: %{x:,.0f}<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            y=clean["Region"], x=clean["Development"], orientation="h", name="In development",
            marker={"color": DATA_CENTER_COLORS["proposed"]},
            customdata=clean[["Total"]],
            hovertemplate="%{y}<br>In development: %{x:,.0f}<br>Total: %{customdata[0]:,.0f}<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Facilities")
    fig.update_yaxes(title="")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=92, r=28, t=30, b=48))
    return add_stacked_axis_headroom(fig, upper=0.20, lower=0.0, include_zero=True)

def data_center_state_pipeline(states: pd.DataFrame | None, *, top_n: int = 15, height: int = 430):
    columns = ["Proposed", "Approved or Under Construction", "Expanding"]
    if states is None or not isinstance(states, pd.DataFrame) or states.empty:
        clean = pd.DataFrame(columns=["State", *columns, "Active Pipeline"])
    else:
        clean = states.copy()
        for column in columns:
            clean[column] = pd.to_numeric(clean.get(column), errors="coerce").fillna(0)
        clean["Active Pipeline"] = clean[columns].sum(axis=1)
        clean = clean.nlargest(top_n, "Active Pipeline").sort_values("Active Pipeline", ascending=True, kind="stable")
    fig = go.Figure()
    colors = {
        "Proposed": DATA_CENTER_COLORS["proposed"],
        "Approved or Under Construction": DATA_CENTER_COLORS["construction"],
        "Expanding": DATA_CENTER_COLORS["expanding"],
    }
    labels = {
        "Proposed": "Proposed",
        "Approved or Under Construction": "Approved / construction",
        "Expanding": "Expanding",
    }
    for column in columns:
        if clean.empty:
            continue
        fig.add_trace(go.Bar(
            y=clean["State"], x=clean[column], orientation="h", name=labels[column],
            marker={"color": colors[column]},
            hovertemplate=f"%{{y}}<br>{labels[column]}: %{{x:,.0f}}<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Active pipeline sites")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=116, r=34, t=30, b=50))
    return add_stacked_axis_headroom(fig, upper=0.20, lower=0.0, include_zero=True)


def data_center_state_published_capacity(
    campuses: pd.DataFrame | None,
    *,
    top_n: int = 15,
    height: int = 430,
):
    """Rank active-development states by disclosed campus capacity.

    This intentionally uses only ``Published Capacity Estimate MW``. Missing
    capacity remains missing, and operating campuses are excluded so the view
    stays comparable with the active-development pipeline chart beside it.
    """
    stage_order = ["Proposed / announced", "Approved / construction", "Expanding"]
    status_to_stage = {
        "Proposed": "Proposed / announced",
        "Planned": "Proposed / announced",
        "Announced": "Proposed / announced",
        "Approved / permitted / under construction": "Approved / construction",
        "Under construction": "Approved / construction",
        "Expanding": "Expanding",
    }

    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        clean = pd.DataFrame(columns=["State", *stage_order, "Published capacity GW"])
    else:
        clean = campuses.copy()
        clean["State"] = clean.get(
            "State", pd.Series("", index=clean.index)
        ).fillna("").astype(str).str.strip()
        clean["Stage"] = clean.get(
            "Status", pd.Series("", index=clean.index)
        ).map(status_to_stage)
        clean["Published capacity GW"] = (
            pd.to_numeric(
                clean.get(
                    "Published Capacity Estimate MW",
                    pd.Series(np.nan, index=clean.index),
                ),
                errors="coerce",
            )
            / 1000.0
        )
        clean = clean.loc[
            clean["State"].ne("")
            & clean["Stage"].notna()
            & clean["Published capacity GW"].gt(0)
        ]

        if clean.empty:
            clean = pd.DataFrame(columns=["State", *stage_order, "Published capacity GW"])
        else:
            grouped = (
                clean.groupby(["State", "Stage"], as_index=False)["Published capacity GW"]
                .sum(min_count=1)
                .pivot(index="State", columns="Stage", values="Published capacity GW")
                .fillna(0.0)
            )
            grouped = grouped.reindex(columns=stage_order, fill_value=0.0)
            grouped["Published capacity GW"] = grouped[stage_order].sum(axis=1)
            clean = (
                grouped.nlargest(top_n, "Published capacity GW")
                .sort_values("Published capacity GW", ascending=True, kind="stable")
                .reset_index()
            )

    colors = {
        "Proposed / announced": DATA_CENTER_COLORS["proposed"],
        "Approved / construction": DATA_CENTER_COLORS["construction"],
        "Expanding": DATA_CENTER_COLORS["expanding"],
    }
    fig = go.Figure()
    for column in stage_order:
        if clean.empty:
            continue
        fig.add_trace(go.Bar(
            y=clean["State"],
            x=clean[column],
            orientation="h",
            name=column,
            marker={"color": colors[column]},
            customdata=clean[["Published capacity GW"]],
            hovertemplate=(
                f"%{{y}}<br>{column}: %{{x:,.2f}} GW"
                "<br>Total published development capacity: %{customdata[0]:,.2f} GW"
                "<extra></extra>"
            ),
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Published capacity estimate (GW)")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=116, r=34, t=30, b=50))
    return add_stacked_axis_headroom(fig, upper=0.20, lower=0.0, include_zero=True)

def data_center_state_footprint(states: pd.DataFrame | None, *, metric: str = "Total", height: int = 500):
    allowed = {
        "Total": ("Total", "Facilities"),
        "Pipeline": ("Active Pipeline", "Pipeline sites"),
        "Active Pipeline": ("Active Pipeline", "Pipeline sites"),
        "Operating": ("Operating", "Operating sites"),
        "Proposed": ("Proposed", "Proposed sites"),
    }
    metric = metric if metric in allowed else "Total"
    metric_column, metric_label = allowed[metric]
    if states is None or not isinstance(states, pd.DataFrame) or states.empty:
        clean = pd.DataFrame(columns=["State", "State Code", metric_column])
    else:
        clean = states.copy()
        clean[metric_column] = pd.to_numeric(clean.get(metric_column), errors="coerce").fillna(0)
    fig = go.Figure()
    if not clean.empty:
        fig.add_trace(go.Choropleth(
            locations=clean["State Code"],
            z=clean[metric_column],
            locationmode="USA-states",
            text=clean["State"],
            customdata=clean[["State Code"]],
            colorscale=[[0.0, "#1e293b"], [0.5, COLORS["blue_deep"]], [1.0, COLORS["violet"]]],
            marker_line_color="rgba(148,163,184,0.45)",
            marker_line_width=0.7,
            colorbar={"title": metric_label, "thickness": 13, "len": 0.75},
            hovertemplate=f"%{{text}}<br>{metric_label}: %{{z:,.0f}}<extra></extra>",
        ))
    fig.update_layout(
        height=height,
        clickmode="event+select",
        margin=dict(l=0, r=0, t=8, b=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": COLORS["text"], "family": "Inter, ui-sans-serif, system-ui"},
        hoverlabel={"bgcolor": "#0f172a", "font": {"color": COLORS["text"]}},
        geo={
            "scope": "usa", "projection": {"type": "albers usa"},
            "bgcolor": "rgba(0,0,0,0)", "showland": True,
            "landcolor": "rgba(30,41,59,0.72)", "showlakes": True,
            "lakecolor": "rgba(15,23,42,0.78)", "showcoastlines": False,
        },
    )
    return fig

def data_center_state_detail_map(
    states: pd.DataFrame | None,
    locations: pd.DataFrame | None,
    *,
    state_code: str,
    size_by: str = "Facility count",
    height: int = 540,
):
    code = str(state_code or "").strip().upper()
    if isinstance(locations, pd.DataFrame) and not locations.empty and "State" in locations.columns:
        filtered = locations.loc[locations["State"].fillna("").astype(str).str.upper().eq(code)].copy()
    else:
        filtered = pd.DataFrame()

    figure = data_center_map(filtered, size_by=size_by, height=height)
    state_name = code
    if isinstance(states, pd.DataFrame) and not states.empty and {"State", "State Code"}.issubset(states.columns):
        match = states.loc[states["State Code"].fillna("").astype(str).str.upper().eq(code)]
        if not match.empty:
            state_name = str(match.iloc[0]["State"])

    if code:
        figure.add_trace(go.Choropleth(
            locations=[code],
            z=[1],
            locationmode="USA-states",
            text=[state_name],
            colorscale=[[0.0, "rgba(37,99,235,0.16)"], [1.0, "rgba(37,99,235,0.16)"]],
            showscale=False,
            marker_line_color="rgba(167,139,250,0.95)",
            marker_line_width=1.6,
            hovertemplate=f"{state_name}<extra></extra>",
            name=state_name,
            showlegend=False,
        ))
        figure.data = (figure.data[-1],) + figure.data[:-1]
        figure.update_geos(fitbounds="locations", visible=False)
    figure.update_layout(showlegend=False)
    return figure

CENSUS_REGIONS = {
    "CT": "Northeast", "ME": "Northeast", "MA": "Northeast", "NH": "Northeast", "RI": "Northeast", "VT": "Northeast",
    "NJ": "Northeast", "NY": "Northeast", "PA": "Northeast",
    "IL": "Midwest", "IN": "Midwest", "MI": "Midwest", "OH": "Midwest", "WI": "Midwest",
    "IA": "Midwest", "KS": "Midwest", "MN": "Midwest", "MO": "Midwest", "NE": "Midwest", "ND": "Midwest", "SD": "Midwest",
    "DE": "South", "DC": "South", "FL": "South", "GA": "South", "MD": "South", "NC": "South", "SC": "South", "VA": "South", "WV": "South",
    "AL": "South", "KY": "South", "MS": "South", "TN": "South", "AR": "South", "LA": "South", "OK": "South", "TX": "South",
    "AZ": "West", "CO": "West", "ID": "West", "MT": "West", "NV": "West", "NM": "West", "UT": "West", "WY": "West",
    "AK": "West", "CA": "West", "HI": "West", "OR": "West", "WA": "West",
}

ACTIVE_CAMPUS_STATUSES = {
    "Expanding", "Approved / permitted / under construction", "Under construction",
    "Proposed", "Planned", "Announced",
}
INACTIVE_CAMPUS_STATUSES = {"Suspended", "Cancelled", "Blocked"}


def _campus_stage(value) -> str:
    status = str(value or "").strip()
    if status == "Operational":
        return "Operating"
    if status == "Expanding":
        return "Expanding"
    if status in {"Approved / permitted / under construction", "Under construction"}:
        return "Approved / construction"
    if status in {"Proposed", "Planned", "Announced"}:
        return "Proposed / announced"
    if status in INACTIVE_CAMPUS_STATUSES:
        return "Suspended / cancelled"
    return "Footprint / status unknown"


def _campus_capacity(frame: pd.DataFrame) -> pd.Series:
    published = pd.to_numeric(frame.get("Published Capacity Estimate MW"), errors="coerce")
    planned = pd.to_numeric(frame.get("Planned Data Center Capacity MW"), errors="coerce")
    return planned.combine_first(published).where(lambda values: values > 0)


def data_center_campus_region(campuses: pd.DataFrame | None, *, height: int = 320):
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        grouped = pd.DataFrame(columns=["Region", "Operating", "Active pipeline"])
    else:
        clean = campuses.copy()
        clean["Region"] = clean.get("State", "").map(CENSUS_REGIONS).fillna("Other")
        clean["Operating"] = clean.get("Status", "").eq("Operational").astype(int)
        clean["Active pipeline"] = clean.get("Status", "").isin(ACTIVE_CAMPUS_STATUSES).astype(int)
        grouped = clean.groupby("Region", as_index=False)[["Operating", "Active pipeline"]].sum()
        grouped["Total"] = grouped[["Operating", "Active pipeline"]].sum(axis=1)
        grouped = grouped.sort_values("Total", ascending=True, kind="stable")
    fig = go.Figure()
    for column, color in [("Operating", DATA_CENTER_COLORS["operating"]), ("Active pipeline", DATA_CENTER_COLORS["proposed"])]:
        if grouped.empty:
            continue
        fig.add_trace(go.Bar(
            y=grouped["Region"], x=grouped[column], orientation="h", name=column,
            marker={"color": color},
            text=grouped[column].map(lambda value: f"{int(value):,}" if value else ""),
            textposition="inside",
            hovertemplate=f"%{{y}}<br>{column}: %{{x:,.0f}} campuses<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Campuses")
    fig.update_yaxes(title="")
    return _base_layout(fig, height=height, legend=True, margin=dict(l=88, r=28, t=22, b=46))


def data_center_campus_stage(campuses: pd.DataFrame | None, *, height: int = 340):
    order = ["Operating", "Expanding", "Approved / construction", "Proposed / announced", "Suspended / cancelled"]
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        grouped = pd.DataFrame({"Stage": order, "Campuses": 0})
    else:
        clean = campuses.copy()
        clean["Stage"] = clean.get("Status", "").map(_campus_stage)
        grouped = clean.loc[clean["Stage"].isin(order)].groupby("Stage", as_index=False).size().rename(columns={"size": "Campuses"})
        grouped = pd.DataFrame({"Stage": order}).merge(grouped, on="Stage", how="left").fillna({"Campuses": 0})
    colors = {
        "Operating": DATA_CENTER_COLORS["operating"], "Expanding": DATA_CENTER_COLORS["expanding"],
        "Approved / construction": DATA_CENTER_COLORS["construction"], "Proposed / announced": DATA_CENTER_COLORS["proposed"],
        "Suspended / cancelled": DATA_CENTER_COLORS["inactive"],
    }
    fig = go.Figure(go.Bar(
        y=grouped["Stage"], x=grouped["Campuses"], orientation="h",
        marker={"color": grouped["Stage"].map(colors).tolist()},
        text=grouped["Campuses"].map(lambda value: f"{int(value):,}"),
        textposition="outside", cliponaxis=False,
        hovertemplate="%{y}<br>%{x:,.0f} campuses<extra></extra>",
    ))
    fig.update_xaxes(title="Campuses")
    fig.update_yaxes(title="", categoryorder="array", categoryarray=list(reversed(order)))
    return _base_layout(fig, height=height, legend=False, margin=dict(l=170, r=46, t=18, b=46))


def data_center_capacity_by_stage(campuses: pd.DataFrame | None, *, height: int = 340):
    order = ["Operating", "Expanding", "Approved / construction", "Proposed / announced"]
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        grouped = pd.DataFrame({"Stage": order, "Capacity GW": 0.0, "Campuses": 0})
    else:
        clean = campuses.copy()
        clean["Stage"] = clean.get("Status", "").map(_campus_stage)
        clean["Capacity MW"] = _campus_capacity(clean)
        grouped = (
            clean.loc[clean["Stage"].isin(order) & clean["Capacity MW"].notna()]
            .groupby("Stage", as_index=False)
            .agg(**{"Capacity GW": ("Capacity MW", lambda values: values.sum() / 1000.0), "Campuses": ("Capacity MW", "size")})
        )
        grouped = pd.DataFrame({"Stage": order}).merge(grouped, on="Stage", how="left").fillna({"Capacity GW": 0, "Campuses": 0})
    colors = {
        "Operating": DATA_CENTER_COLORS["operating"], "Expanding": DATA_CENTER_COLORS["expanding"],
        "Approved / construction": DATA_CENTER_COLORS["construction"], "Proposed / announced": DATA_CENTER_COLORS["proposed"],
    }
    fig = go.Figure(go.Bar(
        y=grouped["Stage"], x=grouped["Capacity GW"], orientation="h",
        marker={"color": grouped["Stage"].map(colors).tolist()},
        text=grouped["Capacity GW"].map(lambda value: f"{value:,.1f}" if value else ""),
        textposition="outside", cliponaxis=False,
        customdata=grouped[["Campuses"]],
        hovertemplate="%{y}<br>%{x:,.1f} GW<br>%{customdata[0]:,.0f} campuses with published capacity estimates<extra></extra>",
    ))
    fig.update_xaxes(title="Published capacity estimate", ticksuffix=" GW")
    fig.update_yaxes(title="", categoryorder="array", categoryarray=list(reversed(order)))
    return _base_layout(fig, height=height, legend=False, margin=dict(l=170, r=52, t=18, b=46))


def _state_operating_pipeline(campuses: pd.DataFrame | None) -> pd.DataFrame:
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        return pd.DataFrame(columns=["State", "Operating", "Active pipeline", "Pipeline intensity"])
    clean = campuses.copy()
    clean = clean.loc[clean.get("State", "").fillna("").astype(str).str.len().eq(2)].copy()
    clean["Operating"] = clean.get("Status", "").eq("Operational").astype(int)
    clean["Active pipeline"] = clean.get("Status", "").isin(ACTIVE_CAMPUS_STATUSES).astype(int)
    grouped = clean.groupby("State", as_index=False)[["Operating", "Active pipeline"]].sum()
    grouped["Pipeline intensity"] = grouped["Active pipeline"] / grouped["Operating"].replace(0, np.nan)
    grouped["Total"] = grouped[["Operating", "Active pipeline"]].sum(axis=1)
    return grouped


def data_center_state_landscape(campuses: pd.DataFrame | None, *, top_n: int = 15, height: int = 440):
    grouped = _state_operating_pipeline(campuses)
    grouped = grouped.nlargest(top_n, "Total").sort_values("Total", ascending=True, kind="stable") if not grouped.empty else grouped
    fig = go.Figure()
    for column, color in [("Operating", DATA_CENTER_COLORS["operating"]), ("Active pipeline", DATA_CENTER_COLORS["proposed"])]:
        if grouped.empty:
            continue
        fig.add_trace(go.Bar(
            y=grouped["State"], x=grouped[column], orientation="h", name=column,
            marker={"color": color},
            hovertemplate=f"%{{y}}<br>{column}: %{{x:,.0f}} campuses<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Campuses")
    fig.update_yaxes(title="")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=54, r=34, t=18, b=46))
    return add_stacked_axis_headroom(fig, upper=0.20, lower=0.0, include_zero=True)


def data_center_pipeline_intensity(campuses: pd.DataFrame | None, *, top_n: int = 15, height: int = 440):
    grouped = _state_operating_pipeline(campuses)
    if not grouped.empty:
        grouped = grouped.loc[(grouped["Operating"] >= 3) & (grouped["Active pipeline"] >= 3)].copy()
        grouped = grouped.nlargest(top_n, "Pipeline intensity").sort_values("Pipeline intensity", ascending=True, kind="stable")
    fig = go.Figure()
    if not grouped.empty:
        fig.add_trace(go.Bar(
            y=grouped["State"], x=grouped["Pipeline intensity"], orientation="h",
            marker={"color": COLORS["amber"]},
            text=grouped["Pipeline intensity"].map(lambda value: f"{value:.1f}x"),
            textposition="outside", cliponaxis=False,
            customdata=grouped[["Operating", "Active pipeline"]],
            hovertemplate=(
                "%{y}<br>Pipeline intensity: %{x:.2f}x"
                "<br>Operating: %{customdata[0]:,.0f}"
                "<br>Active pipeline: %{customdata[1]:,.0f}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Active pipeline / operating campuses", ticksuffix="x")
    fig.update_yaxes(title="")
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=54, r=64, t=18, b=46))
    return add_axis_headroom(fig, axis="x", upper=0.22, lower=0.0, include_zero=True)


def data_center_capacity_distribution(campuses: pd.DataFrame | None, *, height: int = 350):
    labels = ["Under 25", "25–99", "100–249", "250–499", "500–999", "1,000+"]
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        grouped = pd.DataFrame(columns=["Capacity band", "Portfolio", "Campuses"])
    else:
        clean = campuses.copy()
        clean["Capacity MW"] = _campus_capacity(clean)
        clean = clean.loc[clean["Capacity MW"].notna()].copy()
        clean["Portfolio"] = np.where(clean.get("Status", "").eq("Operational"), "Operating", np.where(clean.get("Status", "").isin(ACTIVE_CAMPUS_STATUSES), "Active pipeline", "Other"))
        clean = clean.loc[clean["Portfolio"].isin(["Operating", "Active pipeline"])]
        clean["Capacity band"] = pd.cut(
            clean["Capacity MW"], bins=[0, 25, 100, 250, 500, 1000, np.inf],
            labels=labels, right=False, include_lowest=True,
        )
        grouped = clean.groupby(["Capacity band", "Portfolio"], observed=False).size().reset_index(name="Campuses")
    fig = go.Figure()
    for portfolio, color in [("Operating", DATA_CENTER_COLORS["operating"]), ("Active pipeline", DATA_CENTER_COLORS["proposed"])]:
        rows = grouped.loc[grouped["Portfolio"].eq(portfolio)] if not grouped.empty else grouped
        rows = pd.DataFrame({"Capacity band": labels}).merge(rows, on="Capacity band", how="left").fillna({"Campuses": 0})
        fig.add_trace(go.Bar(
            x=rows["Capacity band"].astype(str), y=rows["Campuses"], name=portfolio,
            marker={"color": color},
            hovertemplate=f"%{{x}} MW<br>{portfolio}: %{{y:,.0f}} campuses<extra></extra>",
        ))
    fig.update_layout(barmode="group")
    fig.update_xaxes(title="Published capacity estimate (MW)")
    fig.update_yaxes(title="Campuses")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=52, r=18, t=18, b=58))
    return add_axis_headroom(fig, upper=0.20, lower=0.0, include_zero=True)


def data_center_largest_campuses(campuses: pd.DataFrame | None, *, top_n: int = 12, height: int = 420):
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        clean = pd.DataFrame(columns=["Facility", "Capacity MW", "Status", "Operator", "State"])
    else:
        clean = campuses.copy()
        clean["Capacity MW"] = _campus_capacity(clean)
        clean = clean.loc[clean["Capacity MW"].notna() & ~clean.get("Status", "").isin(INACTIVE_CAMPUS_STATUSES)].copy()
        clean["Facility"] = clean.get("Facility", "").replace("", "Unnamed campus")
        clean = clean.nlargest(top_n, "Capacity MW").sort_values("Capacity MW", ascending=True, kind="stable")
    colors = clean.get("Status", pd.Series(dtype=str)).map({
        "Operational": DATA_CENTER_COLORS["operating"], "Expanding": DATA_CENTER_COLORS["expanding"],
        "Approved / permitted / under construction": DATA_CENTER_COLORS["construction"], "Under construction": DATA_CENTER_COLORS["construction"],
        "Proposed": DATA_CENTER_COLORS["proposed"], "Planned": DATA_CENTER_COLORS["proposed"], "Announced": "#6d28d9",
    }).fillna(DATA_CENTER_COLORS["inactive"]) if not clean.empty else []
    fig = go.Figure()
    if not clean.empty:
        custom = np.column_stack([
            clean.get("Operator", "").replace("", "Unreported"),
            clean.get("State", ""),
            clean.get("Status", ""),
        ])
        fig.add_trace(go.Bar(
            y=clean["Facility"], x=clean["Capacity MW"] / 1000.0, orientation="h",
            marker={"color": colors.tolist()},
            customdata=custom,
            hovertemplate=(
                "%{y}<br>%{x:,.2f} GW"
                "<br>%{customdata[0]} · %{customdata[1]}"
                "<br>%{customdata[2]}<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Published capacity estimate", ticksuffix=" GW")
    fig.update_yaxes(title="")
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=210, r=44, t=18, b=46))
    return add_axis_headroom(fig, axis="x", upper=0.22, lower=0.0, include_zero=True)


def data_center_operator_label(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.casefold()
    aliases = {
        "amazon": "Amazon / AWS", "aws": "Amazon / AWS", "amazon web services": "Amazon / AWS",
        "meta": "Meta", "meta platforms": "Meta", "facebook": "Meta",
        "google": "Google", "google llc": "Google",
        "microsoft": "Microsoft", "microsoft corporation": "Microsoft",
        "crusoe": "Crusoe", "digitalrealty": "Digital Realty", "digital realty": "Digital Realty",
    }
    return aliases.get(lowered, text)


def data_center_operator_pipeline(campuses: pd.DataFrame | None, *, top_n: int = 15, height: int = 430):
    if campuses is None or not isinstance(campuses, pd.DataFrame) or campuses.empty:
        grouped = pd.DataFrame(columns=["Operator", "Campuses", "Capacity GW"])
    else:
        clean = campuses.loc[campuses.get("Status", "").isin(ACTIVE_CAMPUS_STATUSES)].copy()
        clean["Operator"] = clean.get("Operator", "").map(data_center_operator_label)
        clean = clean.loc[clean["Operator"].ne("")]
        clean["Capacity MW"] = _campus_capacity(clean)
        grouped = (
            clean.groupby("Operator", as_index=False)
            .agg(**{"Campuses": ("Facility ID", "size"), "Capacity GW": ("Capacity MW", lambda values: values.sum(min_count=1) / 1000.0)})
        )
        grouped = grouped.nlargest(top_n, "Campuses").sort_values("Campuses", ascending=True, kind="stable")
    fig = go.Figure()
    if not grouped.empty:
        custom = grouped[["Capacity GW"]].copy()
        fig.add_trace(go.Bar(
            y=grouped["Operator"], x=grouped["Campuses"], orientation="h",
            marker={"color": DATA_CENTER_COLORS["operating"]},
            text=grouped["Campuses"].map(lambda value: f"{int(value):,}"),
            textposition="outside", cliponaxis=False,
            customdata=custom,
            hovertemplate=(
                "%{y}<br>%{x:,.0f} active campuses"
                "<br>Published capacity estimate: %{customdata[0]:,.1f} GW<extra></extra>"
            ),
        ))
    fig.update_xaxes(title="Active pipeline campuses")
    fig.update_yaxes(title="")
    fig = _base_layout(fig, height=height, legend=False, margin=dict(l=180, r=58, t=18, b=46))
    return add_axis_headroom(fig, axis="x", upper=0.22, lower=0.0, include_zero=True)
