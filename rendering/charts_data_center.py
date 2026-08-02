from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rendering.charts_common import COLORS, _base_layout

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
            name="Cumulative disclosed capacity",
            line={"color": COLORS["amber"], "width": 2.2, "dash": "dot"},
            marker={"size": 6},
            hovertemplate="%{x}<br>Cumulative disclosed capacity: %{y:,.1f} GW<extra></extra>",
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
    return _base_layout(fig, height=height, legend=False, margin=dict(l=175, r=42, t=18, b=48))

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
            marker={"color": COLORS["green"]},
            hovertemplate="%{y}<br>Operating: %{x:,.0f}<extra></extra>",
        ))
        fig.add_trace(go.Bar(
            y=clean["Region"], x=clean["Development"], orientation="h", name="In development",
            marker={"color": COLORS["violet"]},
            customdata=clean[["Total"]],
            hovertemplate="%{y}<br>In development: %{x:,.0f}<br>Total: %{customdata[0]:,.0f}<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(title="Facilities")
    fig.update_yaxes(title="")
    return _base_layout(fig, height=height, legend=True, margin=dict(l=92, r=18, t=30, b=48))

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
        "Proposed": COLORS["violet"],
        "Approved or Under Construction": COLORS["amber"],
        "Expanding": COLORS["blue"],
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
    return _base_layout(fig, height=height, legend=True, margin=dict(l=116, r=20, t=30, b=50))

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
