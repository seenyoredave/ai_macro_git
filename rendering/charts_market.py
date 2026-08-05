from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from rendering.labels import sector_display_name
from rendering.charts_common import COLORS, _base_layout, add_axis_headroom, _nice_axis_range


# Market-page visual language.  The global dashboard palette remains available,
# but charts in this module intentionally use a smaller set of roles so the page
# reads as one product rather than a collection of unrelated Plotly templates.
MARKET_COLORS = {
    "primary": "#a78bfa",
    "primary_deep": "#7c3aed",
    "secondary": "#60a5fa",
    "secondary_deep": "#2563eb",
    "neutral": "#94a3b8",
    "neutral_deep": "#64748b",
    "positive": "#34d399",
    "negative": "#818cf8",
    "reference": "#64748b",
    "plot": "rgba(15,23,42,0.28)",
    "hover": "#111827",
    "marker_line": "rgba(226,232,240,0.34)",
}

MARKET_SEQUENTIAL_SCALE = [
    [0.00, "#334155"],
    [0.28, "#2563eb"],
    [0.58, "#6366f1"],
    [0.82, "#8b5cf6"],
    [1.00, "#c084fc"],
]


def _market_layout(fig, *, height=300, margin=None, legend=False, title=None):
    fig = _base_layout(
        fig,
        height=height,
        margin=margin,
        legend=legend,
        title=title,
    )
    fig.update_layout(
        plot_bgcolor=MARKET_COLORS["plot"],
        hoverlabel={
            "bgcolor": MARKET_COLORS["hover"],
            "font": {"color": COLORS["text"]},
            "bordercolor": "rgba(148,163,184,0.24)",
        },
        colorway=[
            MARKET_COLORS["primary"],
            MARKET_COLORS["secondary"],
            MARKET_COLORS["neutral"],
        ],
    )
    return fig


SECTOR_COLORS = {
    "COMPUTE": "#8b5cf6",
    "SEMICAP_EQUIPMENT": "#6366f1",
    "CLOUD_HYPERSCALERS": "#3b82f6",
    "DATA_AI_INFRASTRUCTURE": "#0ea5e9",
    "DATA_CENTER_INFRASTRUCTURE": "#06b6d4",
    "POWER_GRID": "#14b8a6",
    "ENTERPRISE_AI_SOFTWARE": "#a855f7",
    "CYBERSECURITY_AI_TRUST": "#c026d3",
    "INDUSTRIAL_AUTOMATION": "#4f46e5",
    "ROBOTICS": "#7c3aed",
    "DEFENSE_NATIONAL_SECURITY": "#2563eb",
    "CONSUMER_AI": "#0284c7",
    "HEALTHCARE_LIFE_SCIENCES_AI": "#0d9488",
    "TRANSPORTATION_LOGISTICS": "#64748b",
    "INSURANCE_RISK": "#94a3b8",
}

TREEMAP_BACKGROUND = MARKET_COLORS["hover"]
TREEMAP_BORDER = "#111827"


def _sector_color_map(sectors) -> dict[str, str]:
    names = sorted({str(value) for value in sectors if pd.notna(value)})
    fallback = ("#8b5cf6", "#3b82f6", "#0ea5e9", "#14b8a6", "#64748b")
    return {
        name: SECTOR_COLORS.get(name, fallback[index % len(fallback)])
        for index, name in enumerate(names)
    }


def _blend_hex(foreground: str, background: str, weight: float) -> str:
    """Blend two hex colors into a solid tile color."""
    weight = float(np.clip(weight, 0.0, 1.0))

    def _channels(value: str) -> tuple[int, int, int]:
        clean = str(value).lstrip("#")
        if len(clean) != 6:
            clean = "475569"
        return tuple(int(clean[index:index + 2], 16) for index in (0, 2, 4))

    front = _channels(foreground)
    back = _channels(background)
    mixed = tuple(round(weight * fg + (1.0 - weight) * bg) for fg, bg in zip(front, back))
    return "#" + "".join(f"{channel:02x}" for channel in mixed)


def _treemap_sector_label(name: str) -> str:
    wraps = {
        "Robotics & Autonomy": "Robotics &<br>Autonomy",
        "Data Center Infrastructure": "Data Center<br>Infrastructure",
        "Defense & National Security": "Defense &<br>National Security",
        "Enterprise AI Software": "Enterprise AI<br>Software",
        "Cybersecurity & AI Trust": "Cybersecurity &<br>AI Trust",
    }
    return wraps.get(str(name), str(name))


def market_ownership_treemap(
    companies: pd.DataFrame,
    *,
    top_n_per_sector: int = 4,
    height: int = 500,
):
    """Show sector ownership first, with a consistent company drill-down."""
    fig = go.Figure()
    required = {"Ticker", "Company", "Sector", "Market Cap", "Market Cap Share"}
    if companies is None or companies.empty or not required.issubset(companies.columns):
        return _market_layout(fig, height=height)

    frame = companies.copy()
    frame["Market Cap"] = pd.to_numeric(frame["Market Cap"], errors="coerce")
    frame["Market Cap Share"] = pd.to_numeric(frame["Market Cap Share"], errors="coerce")
    frame["Ticker"] = frame["Ticker"].fillna("").astype(str).str.upper().str.strip()
    frame["Company"] = frame["Company"].fillna(frame["Ticker"]).astype(str)
    frame["Sector"] = frame["Sector"].fillna("").astype(str)
    frame = frame.loc[frame["Market Cap"].gt(0) & frame["Ticker"].ne("")].copy()
    if frame.empty:
        return _market_layout(fig, height=height)

    top_n_per_sector = max(int(top_n_per_sector), 1)
    total_cap = float(frame["Market Cap"].sum())
    colors = _sector_color_map(frame["Sector"])
    sectors = (
        frame.groupby("Sector", as_index=False)
        .agg(Market_Cap=("Market Cap", "sum"), Company_Count=("Ticker", "nunique"))
        .sort_values("Market_Cap", ascending=False, kind="stable")
    )

    root_id = "universe"
    ids: list[str] = [root_id]
    labels: list[str] = ["Universe"]
    parents: list[str] = [""]
    values: list[float] = [total_cap]
    display_text: list[str] = [""]
    marker_colors: list[str] = [TREEMAP_BACKGROUND]
    hover_text: list[str] = [""]

    company_weights = (0.92, 0.76, 0.62, 0.50)

    for _, sector_row in sectors.iterrows():
        sector = str(sector_row["Sector"])
        sector_label = sector_display_name(sector)
        sector_cap = float(sector_row["Market_Cap"])
        company_count = int(sector_row["Company_Count"])
        universe_share = sector_cap / total_cap if total_cap > 0 else np.nan
        sector_id = f"sector::{sector}"
        base_color = colors.get(sector, "#64748b")

        ids.append(sector_id)
        labels.append(sector_label)
        parents.append(root_id)
        values.append(sector_cap)
        display_text.append(
            f"<b>{_treemap_sector_label(sector_label)}</b><br>"
            f"<span style='font-size:10px'>{universe_share * 100:.1f}% · {company_count} companies</span>"
        )
        marker_colors.append(_blend_hex(base_color, TREEMAP_BACKGROUND, 0.58))
        hover_text.append(
            f"<b>{sector_label}</b><br>"
            f"Market cap: ${sector_cap / 1e12:.2f}T<br>"
            f"Share of universe: {universe_share * 100:.2f}%<br>"
            f"Companies: {company_count}"
        )

        group = frame.loc[frame["Sector"].eq(sector)].sort_values(
            "Market Cap", ascending=False, kind="stable"
        )
        leaders = group.head(top_n_per_sector)

        for rank, (_, company) in enumerate(leaders.iterrows()):
            ticker = str(company["Ticker"])
            company_cap = float(company["Market Cap"])
            sector_share = company_cap / sector_cap if sector_cap > 0 else np.nan
            universe_company_share = company_cap / total_cap if total_cap > 0 else np.nan
            color_weight = company_weights[min(rank, len(company_weights) - 1)]

            ids.append(f"company::{sector}::{ticker}")
            labels.append(ticker)
            parents.append(sector_id)
            values.append(company_cap)
            display_text.append(
                f"<b>{ticker}</b><br>"
                f"<span style='font-size:10px'>{sector_share * 100:.1f}% of sector</span>"
            )
            marker_colors.append(_blend_hex(base_color, TREEMAP_BACKGROUND, color_weight))
            hover_text.append(
                f"<b>{ticker}</b><br>{company['Company']}<br>"
                f"{sector_label}<br>"
                f"Market cap: ${company_cap / 1e12:.3f}T<br>"
                f"Share of sector: {sector_share * 100:.2f}%<br>"
                f"Share of universe: {universe_company_share * 100:.2f}%"
            )

        remainder = group.iloc[top_n_per_sector:]
        if not remainder.empty:
            other_cap = float(remainder["Market Cap"].sum())
            other_share = other_cap / sector_cap if sector_cap > 0 else np.nan
            other_universe_share = other_cap / total_cap if total_cap > 0 else np.nan
            other_count = int(remainder["Ticker"].nunique())

            ids.append(f"other::{sector}")
            labels.append("Other")
            parents.append(sector_id)
            values.append(other_cap)
            display_text.append(
                f"<b>Other</b><br>"
                f"<span style='font-size:10px'>{other_share * 100:.1f}% · {other_count} companies</span>"
            )
            marker_colors.append(_blend_hex(base_color, TREEMAP_BACKGROUND, 0.34))
            hover_text.append(
                f"<b>Other {sector_label} companies</b><br>"
                f"Companies: {other_count}<br>"
                f"Market cap: ${other_cap / 1e12:.3f}T<br>"
                f"Share of sector: {other_share * 100:.2f}%<br>"
                f"Share of universe: {other_universe_share * 100:.2f}%"
            )

    fig.add_trace(
        go.Treemap(
            ids=ids,
            labels=labels,
            parents=parents,
            values=values,
            text=display_text,
            branchvalues="total",
            sort=False,
            maxdepth=2,
            marker={
                "colors": marker_colors,
                "line": {"color": TREEMAP_BORDER, "width": 2.2},
            },
            texttemplate="%{text}",
            textfont={
                "family": "Inter, ui-sans-serif, system-ui",
                "size": 12,
                "color": "#f8fafc",
            },
            customdata=hover_text,
            hovertemplate="%{customdata}<extra></extra>",
            hoverlabel={"bgcolor": TREEMAP_BACKGROUND, "font": {"color": "#f8fafc"}},
            pathbar={
                "visible": True,
                "side": "top",
                "thickness": 24,
                "textfont": {
                    "family": "Inter, ui-sans-serif, system-ui",
                    "size": 11,
                    "color": "#cbd5e1",
                },
            },
            tiling={"packing": "squarify", "pad": 4},
            root={"color": TREEMAP_BACKGROUND},
        )
    )
    fig = _market_layout(fig, height=height, margin=dict(l=4, r=4, t=4, b=4))
    fig.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        uniformtext={"minsize": 9, "mode": "hide"},
        hoverlabel={"bgcolor": TREEMAP_BACKGROUND, "font": {"color": "#f8fafc"}},
    )
    return fig


def return_contribution_chart(contributions: pd.DataFrame, *, max_companies=10, height=500):
    fig = go.Figure()
    required = {"Ticker", "Contribution", "Start Weight", "Price Return"}
    if contributions is None or contributions.empty or not required.issubset(contributions.columns):
        fig.add_annotation(
            text="1-year return data unavailable.",
            x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False,
            font={"size": 12, "color": COLORS["slate"]},
        )
        return _market_layout(fig, height=height)

    frame = contributions.copy()
    for column in ("Contribution", "Start Weight", "Price Return"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["Contribution"])
    if frame.empty:
        return _market_layout(fig, height=height)

    max_companies = max(int(max_companies), 1)
    selected_index = frame["Contribution"].abs().nlargest(max_companies).index
    leaders = frame.loc[selected_index].copy().sort_values(
        "Contribution", ascending=True, kind="stable"
    )
    remainder = frame.drop(index=selected_index)

    rows = []
    if not remainder.empty:
        other_weight = float(remainder["Start Weight"].sum())
        other_contribution = float(remainder["Contribution"].sum())
        rows.append({
            "Ticker": "Other",
            "Company": f"Remaining {len(remainder)} companies",
            "Sector": "Multiple sectors",
            "Start Weight": other_weight,
            "Price Return": other_contribution / other_weight if other_weight > 0 else np.nan,
            "Contribution": other_contribution,
            "Is Other": True,
        })
    if not leaders.empty:
        leaders["Is Other"] = False
        rows.extend(leaders.to_dict("records"))
    selected = pd.DataFrame(rows)

    contribution_pct = selected["Contribution"] * 100.0
    colors = np.where(
        contribution_pct.gt(0),
        MARKET_COLORS["positive"],
        MARKET_COLORS["negative"],
    )
    colors = [
        MARKET_COLORS["neutral_deep"] if bool(is_other) else color
        for is_other, color in zip(selected["Is Other"], colors)
    ]
    company = selected.get("Company", selected["Ticker"]).fillna(selected["Ticker"]).astype(str)
    sector = selected.get("Sector", pd.Series("", index=selected.index)).fillna("").astype(str)
    fig.add_trace(
        go.Bar(
            x=contribution_pct,
            y=selected["Ticker"],
            orientation="h",
            marker={
                "color": colors,
                "line": {"width": 0.8, "color": "rgba(15,23,42,0.58)"},
            },
            text=[f"{value:+.2f} pp" for value in contribution_pct],
            textposition="auto",
            textfont={"size": 10},
            insidetextanchor="end",
            cliponaxis=False,
            customdata=_typed_customdata(
                company,
                sector.map(sector_display_name),
                selected["Start Weight"].map(lambda value: _hover_number(value * 100.0, suffix="%")),
                selected["Price Return"].map(lambda value: _hover_number(value * 100.0, signed=True, suffix="%")),
            ),
            hovertemplate=(
                "<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]}<br>"
                "Start weight: %{customdata[2]}<br>Price return: %{customdata[3]}<br>"
                "Return contribution: %{x:+.2f} pp<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_color=MARKET_COLORS["reference"], line_width=1.1)
    fig.update_xaxes(title="Contribution to 1-year return", ticksuffix=" pp")
    fig.update_yaxes(
        categoryorder="array",
        categoryarray=selected["Ticker"].tolist(),
        tickfont={"color": COLORS["muted"], "size": 11},
    )
    fig = _market_layout(fig, height=height, margin=dict(l=82, r=64, t=12, b=48))
    fig.update_layout(bargap=0.28, barcornerradius=4)
    return add_axis_headroom(fig, axis="x", upper=0.22, lower=0.20, include_zero=True)


def concentration_history_chart(history: pd.DataFrame):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    required = {"Date", "Top 6 Share", "Top 10 Share", "Effective Firms"}
    if history is None or history.empty or not required.issubset(history.columns):
        return _market_layout(fig, height=330)
    frame = history.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    for column in ("Top 6 Share", "Top 10 Share", "Effective Firms"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["Date"]).sort_values("Date", kind="stable")

    for column, label, color in (
        ("Top 6 Share", "Top 6 share", MARKET_COLORS["primary"]),
        ("Top 10 Share", "Top 10 share", MARKET_COLORS["secondary"]),
    ):
        fig.add_trace(
            go.Scatter(
                x=frame["Date"],
                y=frame[column] * 100.0,
                mode="lines",
                name=label,
                line={"color": color, "width": 2.6},
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:.1f}}%<extra></extra>",
            ),
            secondary_y=False,
        )
    fig.add_trace(
        go.Scatter(
            x=frame["Date"],
            y=frame["Effective Firms"],
            mode="lines",
            name="Effective firms",
            line={"color": MARKET_COLORS["neutral"], "width": 2.2, "dash": "dot"},
            hovertemplate="%{x|%Y-%m-%d}<br>Effective firms: %{y:.1f}<extra></extra>",
        ),
        secondary_y=True,
    )
    share_values = pd.concat([
        pd.to_numeric(frame["Top 6 Share"], errors="coerce"),
        pd.to_numeric(frame["Top 10 Share"], errors="coerce"),
    ]).dropna() * 100.0
    firm_values = pd.to_numeric(frame["Effective Firms"], errors="coerce").dropna()
    if not share_values.empty:
        share_low, share_high, share_step = _nice_axis_range(
            float(share_values.min()), float(share_values.max()), upper=0.20, lower=0.08, include_zero=False
        )
        fig.update_yaxes(title_text="Market-cap share", ticksuffix="%", range=[share_low, share_high], dtick=share_step, secondary_y=False)
    else:
        fig.update_yaxes(title_text="Market-cap share", ticksuffix="%", secondary_y=False)
    if not firm_values.empty:
        firm_low, firm_high, firm_step = _nice_axis_range(
            float(firm_values.min()), float(firm_values.max()), upper=0.20, lower=0.08, include_zero=False
        )
        fig.update_yaxes(title_text="Effective firms", showgrid=False, range=[firm_low, firm_high], dtick=firm_step, secondary_y=True)
    else:
        fig.update_yaxes(title_text="Effective firms", showgrid=False, secondary_y=True)
    return _market_layout(fig, height=330, legend=True, margin=dict(l=52, r=62, t=28, b=38))


def participation_history_chart(history: pd.DataFrame):
    fig = go.Figure()
    required = {"Date", "Cap-Weighted Return", "Equal-Weighted Return", "Median Return"}
    if history is None or history.empty or not required.issubset(history.columns):
        return _market_layout(fig, height=330)
    frame = history.copy()
    frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce", format="mixed")
    frame = frame.dropna(subset=["Date"]).sort_values("Date", kind="stable")
    for column, label, color, dash in (
        ("Cap-Weighted Return", "Cap-weighted", MARKET_COLORS["primary"], None),
        ("Equal-Weighted Return", "Equal-weighted", MARKET_COLORS["secondary"], None),
        ("Median Return", "Median company", MARKET_COLORS["neutral"], "dot"),
    ):
        values = pd.to_numeric(frame[column], errors="coerce") * 100.0
        fig.add_trace(
            go.Scatter(
                x=frame["Date"],
                y=values,
                mode="lines",
                name=label,
                line={"color": color, "width": 2.5, **({"dash": dash} if dash else {})},
                hovertemplate=f"%{{x|%Y-%m-%d}}<br>{label}: %{{y:+.2f}}%<extra></extra>",
            )
        )
    fig.add_hline(
        y=0,
        line_dash="dot",
        line_color=MARKET_COLORS["reference"],
        opacity=0.8,
    )
    fig.update_yaxes(title="Price return since fixed start", ticksuffix="%")
    fig = _market_layout(fig, height=330, legend=True, margin=dict(l=52, r=20, t=28, b=38))
    return add_axis_headroom(fig, upper=0.20, lower=0.12, extra_values=[0])


def sector_signal_anatomy_chart(
    scored_factors: pd.DataFrame,
    components: pd.DataFrame,
    *,
    height: int = 440,
):
    """Coordinate AEI drivers and trading-pressure drivers on one 0–100 system."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.16,
        row_heights=[0.40, 0.60],
        subplot_titles=("EQUITY STRENGTH", "TRADING PRESSURE"),
    )

    factors = scored_factors.copy() if isinstance(scored_factors, pd.DataFrame) else pd.DataFrame()
    pressure = components.copy() if isinstance(components, pd.DataFrame) else pd.DataFrame()

    factor_order = {
        "Forward EBIT-Yield Valuation": 0,
        "Valuation positioning": 0,
        "1Y Relative Return": 1,
        "Relative Performance": 1,
        "Market Breadth": 2,
    }
    if not factors.empty:
        factors["Score"] = pd.to_numeric(factors.get("Score"), errors="coerce")
        factors["Raw Value"] = pd.to_numeric(factors.get("Raw Value"), errors="coerce")
        factors = factors.dropna(subset=["Score"])
        factors["__order"] = factors.get("Factor", pd.Series(index=factors.index, dtype=object)).map(
            lambda value: factor_order.get(str(value), 99)
        )
        factors = factors.sort_values(["__order", "Factor"], kind="stable")

    pressure_order = {
        "Valuation Stretch": 0,
        "Price Extension": 1,
        "Momentum Acceleration": 2,
        "Volatility Expansion": 3,
        "Volume Activity": 4,
    }
    if not pressure.empty:
        pressure["Score"] = pd.to_numeric(pressure.get("Score"), errors="coerce")
        pressure["Raw Value"] = pd.to_numeric(pressure.get("Raw Value"), errors="coerce")
        pressure = pressure.dropna(subset=["Score"])
        pressure["__order"] = pressure.get("Component", pd.Series(index=pressure.index, dtype=object)).map(
            lambda value: pressure_order.get(str(value), 99)
        )
        pressure = pressure.sort_values(["__order", "Component"], kind="stable")

    def raw_factor_text(label, value):
        if pd.isna(value):
            return "n/a"
        lowered = str(label).lower()
        if "return" in lowered or "performance" in lowered or "valuation" in lowered or "yield" in lowered:
            return f"{value * 100:+.2f} pp"
        if "breadth" in lowered:
            return f"{value * 100:.1f}%"
        return f"{value:.4f}"

    if not factors.empty:
        factor_labels = factors.get("Factor", pd.Series(dtype=str)).astype(str)
        factor_raw = [
            raw_factor_text(label, value)
            for label, value in zip(factor_labels, factors["Raw Value"])
        ]
        fig.add_trace(
            go.Bar(
                x=factors["Score"],
                y=factor_labels,
                orientation="h",
                name="Equity strength",
                marker={
                    "color": MARKET_COLORS["primary"],
                    "line": {"width": 0.8, "color": "rgba(15,23,42,0.58)"},
                },
                text=[f"{value:.0f}" for value in factors["Score"]],
                textposition="outside",
                cliponaxis=False,
                customdata=np.asarray(factor_raw, dtype=object).reshape(-1, 1),
                hovertemplate=(
                    "%{y}<br>Normalized score: %{x:.1f}<br>Raw observation: %{customdata[0]}"
                    "<extra></extra>"
                ),
            ),
            row=1,
            col=1,
        )

    if not pressure.empty:
        pressure_labels = pressure.get("Component", pd.Series(dtype=str)).astype(str)
        fig.add_trace(
            go.Bar(
                x=pressure["Score"],
                y=pressure_labels,
                orientation="h",
                name="Trading pressure",
                marker={
                    "color": MARKET_COLORS["secondary"],
                    "line": {"width": 0.8, "color": "rgba(15,23,42,0.58)"},
                },
                text=[f"{value:.0f}" for value in pressure["Score"]],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="%{y}<br>Normalized score: %{x:.1f}<extra></extra>",
            ),
            row=2,
            col=1,
        )

    if factors.empty and pressure.empty:
        fig.add_annotation(
            text="Sector signal data unavailable.",
            x=0.5,
            y=0.5,
            xref="paper",
            yref="paper",
            showarrow=False,
            font={"size": 12, "color": COLORS["slate"]},
        )

    for row in (1, 2):
        fig.update_xaxes(
            range=[0, 108],
            tickvals=[0, 25, 50, 75, 100],
            row=row,
            col=1,
        )
        fig.update_yaxes(
            categoryorder="array",
            categoryarray=(
                list(reversed(factors.get("Factor", pd.Series(dtype=str)).astype(str).tolist()))
                if row == 1
                else list(reversed(pressure.get("Component", pd.Series(dtype=str)).astype(str).tolist()))
            ),
            tickfont={"color": COLORS["muted"], "size": 11},
            row=row,
            col=1,
        )

    fig.add_vline(
        x=50,
        line_dash="dot",
        line_color=MARKET_COLORS["reference"],
        line_width=1,
        opacity=0.60,
    )
    fig = _market_layout(
        fig,
        height=height,
        margin=dict(l=190, r=46, t=38, b=42),
        legend=False,
    )
    fig.update_layout(bargap=0.30)
    for annotation, color in zip(
        fig.layout.annotations,
        (MARKET_COLORS["primary"], MARKET_COLORS["secondary"]),
    ):
        annotation.update(
            x=0,
            xanchor="left",
            font={"size": 11, "color": color, "family": "Inter, ui-sans-serif, system-ui"},
        )
    fig.update_xaxes(title_text="Normalized score", row=2, col=1)
    return fig


def sector_factor_chart(scored_factors: pd.DataFrame):
    if scored_factors is None or scored_factors.empty:
        return _market_layout(go.Figure(), height=245)
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
            marker={
                "color": MARKET_COLORS["primary"],
                "line": {"width": 0.8, "color": "rgba(15,23,42,0.58)"},
            },
            text=[f"{value:.2f}" for value in frame["Score"]],
            textposition="outside",
            cliponaxis=False,
            customdata=np.array(raw_labels, dtype=object).reshape(-1, 1),
            hovertemplate="%{y}<br>Normalized score %{x:.2f}<br>Raw %{customdata[0]}<extra></extra>",
        )
    )
    fig.update_xaxes(range=[0, 100])
    return _market_layout(fig, height=245, margin=dict(l=210, r=52, t=12, b=28))

def pressure_component_chart(components: pd.DataFrame):
    if components is None or components.empty:
        return _market_layout(go.Figure(), height=285)
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
            marker={
                "color": MARKET_COLORS["secondary"],
                "line": {"width": 0.8, "color": "rgba(15,23,42,0.58)"},
            },
            text=[f"{value:.0f}" for value in frame["Score"]],
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>Score %{x:.1f}<extra></extra>",
        )
    )
    fig.update_xaxes(range=[0, 100])
    return _market_layout(fig, height=285, margin=dict(l=175, r=42, t=12, b=28))

def _bounded_positive_log_normalize(values, quantile=0.90):
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
    fig = go.Figure()
    if macro_df is None or macro_df.empty:
        return _market_layout(fig, height=390)

    frame = macro_df.copy()
    frame["Forward EV/EBIT"] = pd.to_numeric(frame.get("Forward EV/EBIT"), errors="coerce")
    frame["Loss-Making EV Share"] = pd.to_numeric(frame.get("Loss-Making EV Share"), errors="coerce")
    frame["Avg Return"] = pd.to_numeric(frame.get("Avg Return"), errors="coerce")
    frame["Sector Score"] = pd.to_numeric(frame.get("Sector Score"), errors="coerce")
    frame["Pressure"] = pd.to_numeric(frame.get("Pressure"), errors="coerce")
    frame = frame.dropna(subset=["Forward EV/EBIT", "Avg Return"])
    frame = frame.loc[frame["Forward EV/EBIT"] > 0].copy()

    if frame.empty:
        return _market_layout(fig, height=390)

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
                "colorscale": MARKET_SEQUENTIAL_SCALE,
                "cmin": 0,
                "cmax": 100,
                "opacity": 0.90,
                "line": {"width": 1.0, "color": MARKET_COLORS["marker_line"]},
                "showscale": True,
                "colorbar": {
                    "title": "AEI",
                    "thickness": 10,
                    "len": 0.72,
                    "outlinewidth": 0,
                    "tickfont": {"color": COLORS["muted"], "size": 10},
                },
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
    fig.add_hline(
        y=0,
        line_dash="dot",
        line_color=MARKET_COLORS["reference"],
        opacity=0.85,
    )
    fig.update_xaxes(
        title="Forward EV/EBIT",
        range=[0.0, x_max],
    )
    fig.update_yaxes(title="1Y Return")
    return _market_layout(fig, height=390, margin=dict(l=52, r=24, t=18, b=48))

def speculative_load_matrix(macro_df: pd.DataFrame):
    fig = go.Figure()
    if macro_df is None or macro_df.empty:
        return _market_layout(fig, height=390)

    frame = macro_df.copy()
    frame["Sector Score"] = pd.to_numeric(frame.get("Sector Score"), errors="coerce")
    frame["Pressure"] = pd.to_numeric(frame.get("Pressure"), errors="coerce")
    frame["Avg Return"] = pd.to_numeric(frame.get("Avg Return"), errors="coerce")
    frame["Forward EV/EBIT"] = pd.to_numeric(frame.get("Forward EV/EBIT"), errors="coerce")
    frame["Loss-Making EV Share"] = pd.to_numeric(frame.get("Loss-Making EV Share"), errors="coerce")
    frame = frame.dropna(subset=["Sector Score", "Pressure"])
    if frame.empty:
        return _market_layout(fig, height=390)

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
                "colorscale": MARKET_SEQUENTIAL_SCALE,
                "cmin": 0.0,
                "cmax": 1.0,
                "opacity": 0.90,
                "line": {"width": 1.0, "color": MARKET_COLORS["marker_line"]},
                "showscale": True,
                "colorbar": {
                    "title": "FWD EV/EBIT",
                    "tickmode": "array",
                    "tickvals": color_tickvals,
                    "ticktext": color_ticktext,
                    "thickness": 10,
                    "len": 0.72,
                    "outlinewidth": 0,
                    "tickfont": {"color": COLORS["muted"], "size": 10},
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
        line={"color": MARKET_COLORS["neutral"], "dash": "dot", "width": 1.4},
    )
    fig.update_xaxes(title="AI Equity Index", range=[0, 100])
    fig.update_yaxes(title="Trading Pressure", range=[0, 100])
    return _market_layout(fig, height=390, margin=dict(l=52, r=24, t=18, b=48))
