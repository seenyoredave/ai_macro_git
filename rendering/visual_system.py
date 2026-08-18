from __future__ import annotations

import copy
import html
from typing import Any

import plotly.graph_objects as go
import streamlit as st

from config.visual_design import matching_signature_tools
from rendering.charts_common import COLORS


DEFAULT_PLOTLY_CONFIG: dict[str, Any] = {
    "displaylogo": False,
    "responsive": True,
    "showTips": False,
    "scrollZoom": False,
}


def apply_platform_chart_contract(figure: go.Figure, *, key: str, role: str | None = None) -> go.Figure:
    """Apply the shared chart grammar without changing analytical meaning."""
    fig = go.Figure(figure)
    current_font = dict(fig.layout.font.to_plotly_json()) if fig.layout.font else {}
    current_font.setdefault("family", "Inter, ui-sans-serif, system-ui")
    current_font.setdefault("color", COLORS["text"])
    current_font.setdefault("size", 12)

    hoverlabel = dict(fig.layout.hoverlabel.to_plotly_json()) if fig.layout.hoverlabel else {}
    hoverlabel.setdefault("bgcolor", "#0f172a")
    hoverlabel.setdefault("font", {"color": COLORS["text"], "family": "Inter, ui-sans-serif, system-ui"})
    hoverlabel.setdefault("bordercolor", "rgba(148,163,184,0.26)")

    legend = dict(fig.layout.legend.to_plotly_json()) if fig.layout.legend else {}
    legend_font = dict(legend.get("font") or {})
    legend_font.setdefault("color", COLORS["muted"])
    legend_font.setdefault("size", 11)
    legend["font"] = legend_font
    legend.setdefault("title", {"font": {"color": COLORS["muted"], "size": 11}})

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=current_font,
        hoverlabel=hoverlabel,
        legend=legend,
        uirevision=f"ai-macro:{key}",
        transition={"duration": 0},
        separators=".,",
    )
    fig.update_xaxes(
        gridcolor=COLORS["grid"],
        linecolor="rgba(148,163,184,0.25)",
        tickfont={"color": COLORS["muted"]},
        title_font={"color": COLORS["muted"], "size": 11},
        automargin=True,
    )
    fig.update_yaxes(
        gridcolor=COLORS["grid"],
        linecolor="rgba(148,163,184,0.25)",
        tickfont={"color": COLORS["muted"]},
        title_font={"color": COLORS["muted"], "size": 11},
        automargin=True,
    )
    if role == "map":
        fig.update_layout(transition={"duration": 0})
    return fig


def _signature_description(key: str) -> str | None:
    matches = matching_signature_tools(key)
    if not matches:
        return None
    return " ".join(tool.analytical_job for tool in matches)


def selection_points(event) -> list[dict]:
    """Normalize Streamlit Plotly selection events in one shared place."""
    if event is None:
        return []
    try:
        return list(event.selection.points or [])
    except Exception:
        pass
    try:
        selection = event.get("selection", {})
        return list(selection.get("points", []) or [])
    except Exception:
        return []


def render_plotly_chart(
    figure: go.Figure,
    *,
    key: str,
    width: str = "stretch",
    config: dict[str, Any] | None = None,
    role: str | None = None,
    description: str | None = None,
    on_select: str | None = None,
    selection_mode: str | tuple[str, ...] | list[str] | None = None,
):
    """Render a Plotly surface through the shared platform interaction contract."""
    merged = copy.deepcopy(DEFAULT_PLOTLY_CONFIG)
    merged.update(config or {})
    merged["displayModeBar"] = role != "trend" if "displayModeBar" not in (config or {}) else bool((config or {})["displayModeBar"])
    merged["responsive"] = True
    if role == "map":
        # One interaction contract for every analytical map. Plotly's
        # scrollZoom config enables wheel/two-finger zoom; geographic freedom
        # itself is controlled by the absence of layout.map.bounds.
        merged["scrollZoom"] = True
        merged["displayModeBar"] = True

    chart_description = str(description or _signature_description(key) or "").strip()
    if chart_description:
        st.markdown(
            f'<div class="rm-visually-hidden" id="{html.escape(key, quote=True)}-description">'
            f'{html.escape(chart_description)}</div>',
            unsafe_allow_html=True,
        )

    kwargs: dict[str, Any] = {
        "width": width,
        "config": merged,
        "key": key,
    }
    if on_select is not None:
        kwargs["on_select"] = on_select
    if selection_mode is not None:
        kwargs["selection_mode"] = selection_mode
    return st.plotly_chart(
        apply_platform_chart_contract(figure, key=key, role=role),
        **kwargs,
    )


__all__ = [
    "DEFAULT_PLOTLY_CONFIG",
    "apply_platform_chart_contract",
    "render_plotly_chart",
    "selection_points",
]
