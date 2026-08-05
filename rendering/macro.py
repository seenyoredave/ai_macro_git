from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from analytics.gaps import industrial_growth_gap
from analytics.infrastructure_cycle import current_buildout_momentum
from config.metric_definitions import METRIC_DEFINITIONS
from rendering.labels import adoption_label, power_capacity_gap_label, speculation_label, validation_label
from rendering.charts_common import history_from_frame
from rendering.charts_finance import current_gap_bars
from rendering.charts_infrastructure import infrastructure_leadership_rotation
from rendering.common import _fallback, _fred_value, _metric_context, _render_tab_metric_registry, _source, _value
from rendering.components import fmt_number, metric_card, render_domain_read, render_line_break, render_panel_heading, render_section, render_statline, render_tab_header
from rendering.spatial import render_spatial_explorer

def _render_primary_macro_cards(regime_metrics, trends, adaptation_data):
    adaptation_history_frame = history_from_frame(
        (adaptation_data or {}).get("national_history"),
        "Current AI Use",
    )
    adaptation_value = pd.to_numeric(
        (adaptation_data or {}).get("current_use"), errors="coerce"
    )
    specs = [
        (
            "macro-card-aei",
            "AI Equity Index",
            _value(regime_metrics, "AI Equity Index"),
            trends.get("aei_trend", {}).get("history"),
            (0, 100),
            "YFinance + EDGAR",
            _fallback(regime_metrics, "AEI"),
            "violet",
            _metric_context("AI Equity Index", _value(regime_metrics, "AI Equity Index")),
        ),
        (
            "macro-card-adi",
            "AI Development Intensity",
            _value(regime_metrics, "AI Development Intensity"),
            trends.get("adi_trend", {}).get("history"),
            (0, 100),
            "YFinance + EDGAR + Census + FRED",
            _fallback(regime_metrics, "ADI"),
            "blue",
            _metric_context("AI Development Intensity", _value(regime_metrics, "AI Development Intensity")),
        ),
        (
            "macro-card-power",
            "Power Stress Index",
            _value(regime_metrics, "Power Stress Index"),
            trends.get("power_stress_trend", {}).get("history"),
            (-100, 100),
            "FRED + EIA",
            _fallback(regime_metrics, "Power Stress"),
            "violet",
            _metric_context("Power Stress Index", _value(regime_metrics, "Power Stress Index")),
        ),
        (
            "macro-card-adaptation",
            "Business Adaptation",
            adaptation_value,
            adaptation_history_frame,
            (0, 100),
            "U.S. Census BTOS",
            (adaptation_data or {}).get("snapshot_date"),
            "green",
            "Employer businesses reporting current AI use",
        ),
    ]

    for col, spec in zip(st.columns(4), specs):
        key, label, value, history, scale, source, fallback, accent, context = spec
        with col:
            metric_card(
                key=key,
                label=label,
                value=value,
                value_text=fmt_number(value, 1, suffix="%" if label == "Business Adaptation" else ""),
                context=context,
                history=history,
                scale=scale,
                source=source,
                fallback_date=fallback,
                accent=accent,
                reference=0 if scale[0] < 0 else None,
            )

def _render_gap_measures(regime_metrics, fred_data, dashboard_data):
    del dashboard_data

    industrial_growth = _fred_value(fred_data, "Industrial Production YoY")
    industrial_gap = industrial_growth_gap(
        _value(regime_metrics, "AI Development Intensity"),
        industrial_growth,
    )
    gaps = {
        "Speculation Gap": _value(regime_metrics, "Speculation Gap"),
        "Economic Validation Gap": _value(regime_metrics, "Economic Validation Gap"),
        "AI–Industrial Growth Gap": industrial_gap,
        "Power Capacity Gap": _value(regime_metrics, "Power Capacity Gap"),
    }

    with st.container(border=True):
        render_panel_heading("Current divergence")
        chart_col, measures_col = st.columns([1.05, 1.25])
        with chart_col:
            st.plotly_chart(
                current_gap_bars(gaps),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="macro-current-divergence-chart",
            )
        with measures_col:
            render_statline(
                [
                    ("Speculation", fmt_number(gaps["Speculation Gap"], 0, signed=True), speculation_label(gaps["Speculation Gap"])),
                    ("Economic Validation", fmt_number(gaps["Economic Validation Gap"], 0, signed=True), validation_label(gaps["Economic Validation Gap"])),
                ],
                key_prefix="macro-current-divergence-primary",
            )
            render_statline(
                [
                    ("Industrial", fmt_number(gaps["AI–Industrial Growth Gap"], 0, signed=True), adoption_label(gaps["AI–Industrial Growth Gap"])),
                    ("Power Capacity", fmt_number(gaps["Power Capacity Gap"], 0, signed=True), power_capacity_gap_label(gaps["Power Capacity Gap"])),
                ],
                key_prefix="macro-current-divergence-context",
            )


def _render_buildout_rotation(infrastructure_data):
    history = (infrastructure_data or {}).get("construction_history")
    current = current_buildout_momentum(history)
    leader = current.iloc[0] if isinstance(current, pd.DataFrame) and not current.empty else None
    meta = "Quarterly year-over-year construction growth"
    if leader is not None:
        meta = f"Current leader: {leader['Series']} · {float(leader['YoY Growth']) * 100:+.1f}% YoY"
    with st.container(border=True, key="macro-panel-buildout-rotation"):
        render_panel_heading("Buildout leadership rotation", meta)
        st.plotly_chart(
            infrastructure_leadership_rotation(history),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
            key="macro-buildout-leadership-rotation",
        )
        st.caption(
            "This is a capital-flow view across the physical AI stack. A falling growth rate can reflect normalization from an unusually high base; read momentum alongside spending levels and project evidence."
        )

def _render_front_page_purpose() -> None:
    statement = METRIC_DEFINITIONS["Purpose Statement"].strip()
    with st.container(key="front-page-purpose"):
        with st.expander("Purpose statement", expanded=False):
            st.markdown(
                f'<div class="rm-purpose-copy">{html.escape(statement)}</div>',
                unsafe_allow_html=True,
            )
    st.markdown('<div class="rm-purpose-divider" aria-hidden="true"></div>', unsafe_allow_html=True)


def render_macro_tab(sector_metrics, sector_data, fred_data, regime_metrics, dashboard_data, adaptation_data, infrastructure_data, tab_read=None):
    del sector_metrics, sector_data
    _render_front_page_purpose()
    render_tab_header(
        "AI Macro",
        "Market, physical buildout, power, adaptation, and validation signals across the AI economy.",
        "YFinance / SEC / FRED / Census / EIA",
    )
    render_line_break()
    _render_tab_metric_registry("macro")
    render_domain_read(tab_read or (regime_metrics or {}).get("Macro Interpretation"), label="AI Macro Read", accent="violet", macro=True)
    render_section("Regime board", "Top-level indicators with historical context.")
    _render_primary_macro_cards(regime_metrics, dashboard_data["trends"], adaptation_data)
    render_section("Buildout leadership", "Where construction momentum is rotating across data centers, compute manufacturing, power, communications, and water systems.")
    _render_buildout_rotation(infrastructure_data)
    render_section("Gap Measures", "AI development relative to equity, industrial, economic-validation, and power-capacity benchmarks.")
    _render_gap_measures(regime_metrics, fred_data, dashboard_data)
    render_section("National landscape", "Facility geography with linked power, water, and infrastructure evidence.")
    render_spatial_explorer(infrastructure_data, key_prefix="macro-national-landscape")
