from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from rendering.charts_common import (
    COLORS,
    _base_layout,
    add_axis_headroom,
    add_stacked_axis_headroom,
    _nice_axis_range,
)
from rendering.charts_data_center import ACTIVE_CAMPUS_STATUSES

TECH_COLORS = {
    "Natural gas": "#8b5cf6",
    "Coal": "#64748b",
    "Nuclear": "#c4b5fd",
    "Hydro": "#38bdf8",
    "Solar": "#34d399",
    "Wind": "#60a5fa",
    "Wind + other renewables": "#60a5fa",
    "Battery storage": "#7c3aed",
    "Other renewables": "#6ee7b7",
    "Other thermal": "#818cf8",
    "Other": "#475569",
}


def _reserve_legend_band(fig, *, top: int = 62, font_size: int = 10):
    """Keep horizontal legends in a dedicated band above the plotting area."""
    margin = fig.layout.margin.to_plotly_json() if fig.layout.margin else {}
    margin["t"] = max(int(margin.get("t", 0) or 0), int(top))
    fig.update_layout(
        margin=margin,
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "left",
            "x": 0,
            "font": {"color": COLORS["muted"], "size": font_size},
            "bgcolor": "rgba(0,0,0,0)",
            "borderwidth": 0,
            "itemsizing": "constant",
            "itemwidth": 30,
            "traceorder": "normal",
        },
    )
    return fig


def _frame(frame):
    return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()


def _numeric(frame, columns):
    for column in columns:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


def _dates(frame, columns):
    for column in columns:
        if column in frame:
            frame[column] = pd.to_datetime(frame[column], errors="coerce", format="mixed")
    return frame


def electricity_demand_history(frame, *, height=365):
    clean = _dates(_numeric(_frame(frame), ["Sales MWh"]), ["Date"])
    clean = clean.loc[
        clean.get("Geography", "").eq("United States")
        & clean.get("Sector", "").isin(["Residential", "Commercial", "Industrial"])
    ].dropna(subset=["Date", "Sales MWh"])
    pivot = clean.pivot_table(index="Date", columns="Sector", values="Sales MWh", aggfunc="sum").sort_index()
    rolling = pivot.rolling(12, min_periods=12).sum() / 1_000_000.0
    if not rolling.empty:
        rolling = rolling.loc[rolling.index >= rolling.index.max() - pd.DateOffset(years=10)]
    fig = go.Figure()
    for name, color in [("Residential", COLORS["blue"]), ("Commercial", COLORS["violet"]), ("Industrial", COLORS["amber"])]:
        if name not in rolling:
            continue
        fig.add_trace(go.Scatter(
            x=rolling.index,
            y=rolling[name],
            mode="lines",
            name=name,
            line={"width": 2.5, "color": color},
            hovertemplate=f"%{{x|%b %Y}}<br>{name}: %{{y:,.0f}} TWh<extra></extra>",
        ))
    fig.update_yaxes(title="Rolling 12-month TWh")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=18, t=30, b=38))
    fig = _reserve_legend_band(fig, top=58)
    return add_axis_headroom(fig, upper=0.22, lower=0.04)


def commercial_markets(frame, *, height=365, top_n=15):
    clean = _dates(_numeric(_frame(frame), ["Sales MWh"]), ["Date"])
    clean = clean.loc[
        clean.get("Sector", "").eq("Commercial")
        & ~clean.get("Geography", "").eq("United States")
    ].dropna(subset=["Date", "Sales MWh"])
    rows = []
    for geography, group in clean.groupby("Geography"):
        group = group.sort_values("Date").drop_duplicates("Date", keep="last")
        latest = group["Date"].max()
        current = group.loc[group["Date"] > latest - pd.DateOffset(months=12), "Sales MWh"].sum()
        previous = group.loc[
            (group["Date"] <= latest - pd.DateOffset(months=12))
            & (group["Date"] > latest - pd.DateOffset(months=24)),
            "Sales MWh",
        ].sum()
        growth = (current / previous - 1.0) * 100.0 if previous > 0 else np.nan
        rows.append({"State": geography, "TWh": current / 1_000_000.0, "Growth": growth})
    summary = pd.DataFrame(rows).nlargest(top_n, "TWh").sort_values("TWh")
    fig = go.Figure(go.Bar(
        x=summary.get("TWh", []),
        y=summary.get("State", []),
        orientation="h",
        marker_color=COLORS["violet"],
        text=[f"{value:+.1f}%" if pd.notna(value) else "" for value in summary.get("Growth", [])],
        textposition="outside",
        customdata=np.column_stack([summary.get("Growth", [])]) if not summary.empty else None,
        hovertemplate="%{y}<br>Sales: %{x:,.1f} TWh<br>YoY: %{customdata[0]:+.1f}%<extra></extra>",
    ))
    fig.update_xaxes(title="Rolling 12-month TWh")
    fig = _base_layout(fig, height=height, margin=dict(l=52, r=65, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.20, lower=0.02, include_zero=True)


def retail_price_history(frame, *, height=350):
    clean = _dates(_numeric(_frame(frame), ["Price Cents per kWh"]), ["Date"])
    clean = clean.loc[
        clean.get("Geography", "").eq("United States")
        & clean.get("Sector", "").isin(["Residential", "Commercial", "Industrial"])
    ].dropna(subset=["Date", "Price Cents per kWh"])
    if not clean.empty:
        clean = clean.loc[clean["Date"] >= clean["Date"].max() - pd.DateOffset(years=10)]
    fig = go.Figure()
    for name, color in [("Residential", COLORS["blue"]), ("Commercial", COLORS["violet"]), ("Industrial", COLORS["amber"])]:
        group = clean.loc[clean["Sector"].eq(name)].sort_values("Date")
        fig.add_trace(go.Scatter(
            x=group.get("Date", []), y=group.get("Price Cents per kWh", []), mode="lines", name=name,
            line={"width": 2.4, "color": color},
            hovertemplate=f"%{{x|%b %Y}}<br>{name}: %{{y:.2f}}¢/kWh<extra></extra>",
        ))
    fig.update_yaxes(title="Cents per kWh")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=18, t=30, b=38))
    fig = _reserve_legend_band(fig, top=58)
    return add_axis_headroom(fig, upper=0.12, lower=0.04)


def wholesale_price_history(frame, *, height=350, hubs=5):
    clean = _dates(_numeric(_frame(frame), ["Price $/MWh", "Volume MWh"]), ["Trade Date"])
    clean = clean.dropna(subset=["Trade Date", "Hub", "Price $/MWh"])
    if clean.empty:
        return _base_layout(go.Figure(), height=height)
    top = clean.groupby("Hub")["Volume MWh"].sum(min_count=1).nlargest(hubs).index
    clean = clean.loc[clean["Hub"].isin(top)].copy()
    clean["Month"] = clean["Trade Date"].dt.to_period("M").dt.to_timestamp()
    rows = []
    for (month, hub), group in clean.groupby(["Month", "Hub"]):
        weight = group["Volume MWh"].where(group["Volume MWh"] > 0)
        price = np.average(group["Price $/MWh"], weights=weight) if weight.notna().all() and weight.sum() > 0 else group["Price $/MWh"].mean()
        rows.append({"Month": month, "Hub": hub, "Price": price})
    monthly = pd.DataFrame(rows)
    palette = [COLORS["violet"], COLORS["blue"], COLORS["amber"], COLORS["green"], COLORS["red"]]
    fig = go.Figure()
    for (hub, group), color in zip(monthly.groupby("Hub"), palette):
        fig.add_trace(go.Scatter(
            x=group["Month"], y=group["Price"], mode="lines", name=hub,
            line={"width": 2.2, "color": color},
            hovertemplate=f"%{{x|%b %Y}}<br>{hub}: $%{{y:.1f}}/MWh<extra></extra>",
        ))
    fig.update_yaxes(title="$/MWh")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=56, r=18, t=30, b=38))
    fig = _reserve_legend_band(fig, top=70, font_size=9)
    return add_axis_headroom(fig, upper=0.15, lower=0.08)




def energy_supply_profile(generation, changes, *, height=600):
    """Combine the generation base and current fleet change into one system view."""
    generation_clean = _dates(_numeric(_frame(generation), ["Generation GWh"]), ["Date"])
    generation_clean = generation_clean.loc[
        generation_clean.get("Period Type", "").eq("Annual")
    ].dropna(subset=["Date", "Generation GWh"])
    order = ["Natural gas", "Coal", "Nuclear", "Hydro", "Wind + other renewables", "Solar", "Other"]
    pivot = (
        generation_clean.pivot_table(index="Date", columns="Source", values="Generation GWh", aggfunc="sum")
        .fillna(0) / 1000.0
    )
    if not pivot.empty:
        pivot = pivot.sort_index()
        pivot = pivot.loc[pivot.index >= pd.Timestamp("2020-01-01")]

    change_clean = _numeric(_frame(changes), ["Net Summer Capacity (MW)"])
    if {"Technology Group", "Pipeline Type", "Net Summer Capacity (MW)"}.issubset(change_clean.columns):
        grouped = change_clean.groupby(
            ["Technology Group", "Pipeline Type"], as_index=False
        )["Net Summer Capacity (MW)"].sum()
        grouped["GW"] = grouped["Net Summer Capacity (MW)"] / 1000.0
        grouped.loc[grouped["Pipeline Type"].eq("Retirement"), "GW"] *= -1
        tech_order = grouped.groupby("Technology Group")["GW"].apply(lambda values: values.abs().sum()).sort_values().index
    else:
        grouped = pd.DataFrame(columns=["Technology Group", "Pipeline Type", "GW"])
        tech_order = []

    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.62, 0.38],
        vertical_spacing=0.16,
        subplot_titles=("Annual generation mix", "Current-year capacity additions and retirements"),
    )
    for name in order:
        if name not in pivot:
            continue
        fig.add_trace(
            go.Bar(
                x=pivot.index.year, y=pivot[name], name=name,
                marker_color=TECH_COLORS.get(name, COLORS["slate"]),
                hovertemplate=f"%{{x}}<br>{name}: %{{y:,.0f}} TWh<extra></extra>",
                legendgroup="generation",
            ),
            row=1, col=1,
        )

    for kind, color in [("Addition", "#60a5fa"), ("Retirement", "#818cf8")]:
        subset = (
            grouped.loc[grouped["Pipeline Type"].eq(kind)]
            .set_index("Technology Group")
            .reindex(tech_order)
            .reset_index()
        ) if len(tech_order) else grouped.iloc[0:0].copy()
        fig.add_trace(
            go.Bar(
                x=subset.get("GW", []), y=subset.get("Technology Group", []),
                orientation="h", name=kind, marker_color=color, showlegend=False,
                text=[f"{value:+.1f}" if pd.notna(value) and value != 0 else "" for value in subset.get("GW", [])],
                textposition="outside", cliponaxis=False,
                hovertemplate=f"%{{y}}<br>{kind}: %{{x:+.2f}} GW<extra></extra>",
            ),
            row=2, col=1,
        )

    fig.update_layout(barmode="relative")
    fig.update_yaxes(title="TWh", row=1, col=1)
    fig.update_xaxes(title="Year", row=1, col=1)
    fig.update_xaxes(title="Net summer capacity (GW)", row=2, col=1, zeroline=False)
    fig.update_yaxes(title="", row=2, col=1)
    fig.add_vline(x=0, line_color="rgba(148,163,184,0.5)", line_width=1, row=2, col=1)
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=118, r=48, t=102, b=48))
    fig = _reserve_legend_band(fig, top=102, font_size=9)
    fig.update_layout(plot_bgcolor="rgba(15,23,42,0.24)")
    fig.update_annotations(font={"color": COLORS["muted"], "size": 11})
    # Use cumulative annual totals for the top subplot and signed fleet changes for the lower subplot.
    if not pivot.empty:
        total = pivot.sum(axis=1)
        lower_bound, upper_bound, step = _nice_axis_range(
            0.0, float(total.max()), upper=0.18, lower=0.0, include_zero=True
        )
        fig.update_yaxes(range=[lower_bound, upper_bound], dtick=step, row=1, col=1)
    if not grouped.empty:
        lower = float(grouped["GW"].min())
        upper = float(grouped["GW"].max())
        lower_bound, upper_bound, step = _nice_axis_range(
            lower, upper, upper=0.24, lower=0.20, include_zero=True
        )
        fig.update_xaxes(range=[lower_bound, upper_bound], dtick=step, row=2, col=1)
    return fig


def generation_mix(frame, *, height=390):
    clean = _dates(_numeric(_frame(frame), ["Generation GWh"]), ["Date"])
    clean = clean.loc[clean.get("Period Type", "").eq("Annual")].dropna(subset=["Date", "Generation GWh"])
    order = ["Natural gas", "Coal", "Nuclear", "Hydro", "Wind + other renewables", "Solar", "Other"]
    pivot = clean.pivot_table(index="Date", columns="Source", values="Generation GWh", aggfunc="sum").fillna(0) / 1000.0
    pivot = pivot.sort_index()
    pivot = pivot.loc[pivot.index >= pd.Timestamp("2020-01-01")]
    fig = go.Figure()
    for name in order:
        if name not in pivot:
            continue
        fig.add_trace(go.Bar(
            x=pivot.index.year, y=pivot[name], name=name,
            marker_color=TECH_COLORS.get(name, COLORS["slate"]),
            hovertemplate=f"%{{x}}<br>{name}: %{{y:,.0f}} TWh<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(title="TWh")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=18, t=30, b=40))
    fig = _reserve_legend_band(fig, top=96, font_size=9)
    return add_stacked_axis_headroom(fig, upper=0.18, lower=0, include_zero=True)


def generation_change(frame, *, height=390):
    clean = _dates(_numeric(_frame(frame), ["Generation GWh"]), ["Date"])
    clean = clean.loc[clean.get("Period Type", "").eq("Monthly")].dropna(subset=["Date", "Generation GWh"])
    rows = []
    for source, group in clean.groupby("Source"):
        group = group.sort_values("Date")
        latest = group["Date"].max()
        current = group.loc[group["Date"] > latest - pd.DateOffset(months=12), "Generation GWh"].sum()
        previous = group.loc[(group["Date"] <= latest - pd.DateOffset(months=12)) & (group["Date"] > latest - pd.DateOffset(months=24)), "Generation GWh"].sum()
        rows.append({"Source": source, "Change": current / previous * 100.0 - 100.0 if previous > 0 else np.nan})
    summary = pd.DataFrame(rows).dropna().sort_values("Change")
    colors = [COLORS["violet"] if value < 0 else COLORS["blue"] for value in summary.get("Change", [])]
    fig = go.Figure(go.Bar(
        x=summary.get("Change", []), y=summary.get("Source", []), orientation="h",
        marker_color=colors, text=[f"{value:+.1f}%" for value in summary.get("Change", [])], textposition="outside",
        hovertemplate="%{y}: %{x:+.1f}%<extra></extra>",
    ))
    fig.add_vline(x=0, line_color="rgba(148,163,184,0.5)", line_width=1)
    fig.update_xaxes(title="Rolling 12-month change")
    fig = _base_layout(fig, height=height, margin=dict(l=112, r=58, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.20, lower=0.20, include_zero=True)


def operating_capacity(frame, *, height=390):
    clean = _numeric(_frame(frame), ["Net Summer Capacity MW"])
    clean = clean.dropna(subset=["Technology Group", "Net Summer Capacity MW"]).copy()
    clean["Capacity GW"] = clean["Net Summer Capacity MW"] / 1000.0
    clean = clean.sort_values("Capacity GW")
    fig = go.Figure(go.Bar(
        x=clean.get("Capacity GW", []), y=clean.get("Technology Group", []), orientation="h",
        marker_color=[TECH_COLORS.get(name, COLORS["slate"]) for name in clean.get("Technology Group", [])],
        text=[f"{value:,.1f}" for value in clean.get("Capacity GW", [])], textposition="outside",
        hovertemplate="%{y}: %{x:,.1f} GW<extra></extra>",
    ))
    fig.update_xaxes(title="Net summer capacity (GW)")
    fig = _base_layout(fig, height=height, margin=dict(l=112, r=62, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.16, lower=0, include_zero=True)


def capacity_changes(frame, *, height=390):
    clean = _numeric(_frame(frame), ["Net Summer Capacity (MW)"])
    grouped = clean.groupby(["Technology Group", "Pipeline Type"], as_index=False)["Net Summer Capacity (MW)"].sum()
    grouped["GW"] = grouped["Net Summer Capacity (MW)"] / 1000.0
    grouped.loc[grouped["Pipeline Type"].eq("Retirement"), "GW"] *= -1
    order = grouped.groupby("Technology Group")["GW"].sum().sort_values().index
    fig = go.Figure()
    for kind, color in [("Addition", COLORS["blue"]), ("Retirement", COLORS["violet"])]:
        subset = grouped.loc[grouped["Pipeline Type"].eq(kind)].set_index("Technology Group").reindex(order).reset_index()
        fig.add_trace(go.Bar(
            x=subset.get("GW", []), y=subset.get("Technology Group", []), orientation="h", name=kind,
            marker_color=color, hovertemplate=f"%{{y}}<br>{kind}: %{{x:+.2f}} GW<extra></extra>",
        ))
    fig.update_layout(barmode="relative")
    fig.add_vline(x=0, line_color="rgba(148,163,184,0.5)", line_width=1)
    fig.update_xaxes(title="Net summer capacity (GW)")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=112, r=24, t=30, b=40))
    fig = _reserve_legend_band(fig, top=54)
    return add_axis_headroom(fig, axis="x", upper=0.15, lower=0.15, include_zero=True)


def planned_capacity(frame, *, height=390, end_year=2030):
    clean = _numeric(_frame(frame), ["Nameplate Capacity (MW)", "Expected Year"])
    clean = clean.loc[clean["Expected Year"].between(pd.Timestamp.now().year, end_year)].copy()
    grouped = clean.groupby(["Expected Year", "Pipeline Type", "Technology Group"], as_index=False)["Nameplate Capacity (MW)"].sum()
    grouped["GW"] = grouped["Nameplate Capacity (MW)"] / 1000.0
    grouped.loc[grouped["Pipeline Type"].eq("Retirement"), "GW"] *= -1
    fig = go.Figure()
    for name, group in grouped.groupby("Technology Group"):
        fig.add_trace(go.Bar(
            x=group["Expected Year"].astype(int).astype(str), y=group["GW"], name=name,
            marker_color=TECH_COLORS.get(name, COLORS["slate"]),
            hovertemplate=f"%{{x}}<br>{name}: %{{y:+.1f}} GW<extra></extra>",
        ))
    fig.update_layout(barmode="relative")
    fig.add_hline(y=0, line_color="rgba(148,163,184,0.5)", line_width=1)
    fig.update_yaxes(title="Nameplate capacity (GW)")
    fig = _base_layout(fig, height=height, legend=True, margin=dict(l=58, r=18, t=30, b=40))
    fig = _reserve_legend_band(fig, top=86, font_size=9)
    return add_stacked_axis_headroom(fig, upper=0.18, lower=0.16, include_zero=True)


def queue_by_technology(frame, *, height=390):
    clean = _numeric(_frame(frame), ["Queue MW", "Queue GW"])
    if "Technology Group" not in clean.columns:
        summary = pd.DataFrame(columns=["Technology Group", "GW"])
    elif "Queue GW" in clean.columns and clean["Queue GW"].notna().any():
        summary = clean.groupby("Technology Group", as_index=False)["Queue GW"].sum().dropna()
        summary["GW"] = summary["Queue GW"]
    elif "Queue MW" in clean.columns and clean["Queue MW"].notna().any():
        summary = clean.groupby("Technology Group", as_index=False)["Queue MW"].sum().dropna()
        summary["GW"] = summary["Queue MW"] / 1000.0
    else:
        summary = pd.DataFrame(columns=["Technology Group", "GW"])
    summary = summary.sort_values("GW")
    fig = go.Figure(go.Bar(
        x=summary.get("GW", []), y=summary.get("Technology Group", []), orientation="h",
        marker_color=[TECH_COLORS.get(name, COLORS["slate"]) for name in summary.get("Technology Group", [])],
        text=[f"{value:,.0f}" for value in summary.get("GW", [])], textposition="outside",
        hovertemplate="%{y}: %{x:,.1f} GW<extra></extra>",
    ))
    fig.update_xaxes(title="Active queue capacity (GW)")
    fig = _base_layout(fig, height=height, margin=dict(l=112, r=64, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.17, lower=0, include_zero=True)


def queue_by_region(frame, *, height=390):
    clean = _numeric(_frame(frame), ["Queue MW"])
    if {"region", "Queue MW"}.issubset(clean.columns):
        summary = clean.groupby("region", as_index=False)["Queue MW"].sum().dropna()
        summary["GW"] = summary["Queue MW"] / 1000.0
    else:
        summary = pd.DataFrame(columns=["region", "GW"])
    summary = summary.sort_values("GW")
    fig = go.Figure(go.Bar(
        x=summary.get("GW", []), y=summary.get("region", []), orientation="h",
        marker_color=COLORS["violet"], text=[f"{value:,.0f}" for value in summary.get("GW", [])], textposition="outside",
        hovertemplate="%{y}: %{x:,.1f} GW<extra></extra>",
    ))
    fig.update_xaxes(title="Active queue capacity (GW)")
    fig = _base_layout(fig, height=height, margin=dict(l=82, r=64, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.17, lower=0, include_zero=True)


def gas_pipeline_capacity(frame, *, height=390):
    clean = _numeric(_frame(frame), ["Additional Capacity (MMcf/d)"])
    summary = clean.groupby("Status", as_index=False)["Additional Capacity (MMcf/d)"].sum().dropna()
    summary["Bcf/d"] = summary["Additional Capacity (MMcf/d)"] / 1000.0
    summary = summary.loc[summary["Bcf/d"] > 0].nlargest(9, "Bcf/d").sort_values("Bcf/d")
    fig = go.Figure(go.Bar(
        x=summary.get("Bcf/d", []), y=summary.get("Status", []), orientation="h",
        marker_color=COLORS["violet"], text=[f"{value:,.1f}" for value in summary.get("Bcf/d", [])], textposition="outside",
        hovertemplate="%{y}: %{x:,.1f} Bcf/d<extra></extra>",
    ))
    fig.update_xaxes(title="Additional capacity (Bcf/d)")
    fig = _base_layout(fig, height=height, margin=dict(l=140, r=64, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.17, lower=0, include_zero=True)


def lng_capacity(frame, *, height=390):
    clean = _numeric(_frame(frame), ["Baseload Bcf/d", "Design Bcf/d"])
    clean["Capacity Bcf/d"] = clean["Baseload Bcf/d"].combine_first(clean["Design Bcf/d"])
    status = clean.get("Status", pd.Series("", index=clean.index)).fillna("").astype(str)
    clean["Stage"] = np.select(
        [status.str.contains("commercial", case=False), status.str.contains("commission", case=False), status.str.contains("construction", case=False), clean.get("Pipeline Type", "").eq("Approved")],
        ["Commercial operation", "Commissioning", "Under construction", "Approved / proposed"],
        default="Other",
    )
    summary = clean.groupby("Stage", as_index=False)["Capacity Bcf/d"].sum(min_count=1).dropna().sort_values("Capacity Bcf/d")
    fig = go.Figure(go.Bar(
        x=summary.get("Capacity Bcf/d", []), y=summary.get("Stage", []), orientation="h",
        marker_color=COLORS["blue"], text=[f"{value:,.1f}" for value in summary.get("Capacity Bcf/d", [])], textposition="outside",
        hovertemplate="%{y}: %{x:,.1f} Bcf/d<extra></extra>",
    ))
    fig.update_xaxes(title="Liquefaction capacity (Bcf/d)")
    fig = _base_layout(fig, height=height, margin=dict(l=140, r=64, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.17, lower=0, include_zero=True)


def data_center_power_by_state(frame, *, height=390, top_n=15):
    clean = _frame(frame)
    if clean.empty:
        return _base_layout(go.Figure(), height=height)
    status = clean.get("Status", pd.Series("", index=clean.index)).fillna("").astype(str)
    active = status.eq("Operational") | status.isin(ACTIVE_CAMPUS_STATUSES)
    published = pd.to_numeric(clean.get("Published Capacity Estimate MW"), errors="coerce")
    clean["Capacity MW"] = published.where(published > 0)
    clean = clean.loc[active & clean["Capacity MW"].notna()].copy()
    summary = clean.groupby("State", as_index=False)["Capacity MW"].sum().nlargest(top_n, "Capacity MW").sort_values("Capacity MW")
    summary["GW"] = summary["Capacity MW"] / 1000.0
    fig = go.Figure(go.Bar(
        x=summary.get("GW", []), y=summary.get("State", []), orientation="h",
        marker_color=COLORS["violet"], text=[f"{value:,.1f}" for value in summary.get("GW", [])], textposition="outside",
        hovertemplate="%{y}: %{x:,.1f} GW<extra></extra>",
    ))
    fig.update_xaxes(title="Published campus capacity estimate (GW)")
    fig = _base_layout(fig, height=height, margin=dict(l=52, r=64, t=18, b=40))
    return add_axis_headroom(fig, axis="x", upper=0.17, lower=0, include_zero=True)
