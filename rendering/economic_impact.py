from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from rendering.visual_system import render_plotly_chart
from rendering.charts_economic_impact import (
    earnings_distribution_change,
    earnings_distribution_history,
    investment_vs_output,
    productivity_index,
    worker_capture_history,
)
from rendering.common import _render_floating_terms
from rendering.commercialization import filtered_ledger, metric_value
from rendering.components import (
    fmt_date,
    fmt_number,
    render_compact_chart_rail,
    render_domain_read,
    render_metric_stack,
    render_panel_heading,
    render_section,
    render_statline,
    render_summary_row,
    render_tab_header,
)
from rendering.dataframe import arrow_safe_dataframe
from rendering.layout_contracts import value_realization_bridge_html


def _metric_text(payload: dict) -> str:
    return fmt_number((payload or {}).get("value"), 1, signed=True, suffix="%")


def _build_value_bridge(data: dict, commercialization_data) -> dict[str, object]:
    capture = data.get("capture_summary", {}) or {}
    productivity = capture.get("productivity", {}) or {}
    real_comp = capture.get("real_compensation", {}) or {}
    labor_share = capture.get("labor_share", {}) or {}
    median = capture.get("median_real_earnings", {}) or {}
    spread = pd.to_numeric(capture.get("group_growth_spread_ppts"), errors="coerce")

    microsoft_arr = metric_value(commercialization_data, "Microsoft", "Annual revenue run rate")
    openai_arr = metric_value(commercialization_data, "OpenAI", "Annualized revenue run rate")
    commercial_display = "n/a"
    if pd.notna(microsoft_arr) and pd.notna(openai_arr):
        commercial_display = f"${microsoft_arr:.0f}B Microsoft · ${openai_arr:.0f}B+ OpenAI ARR"

    prod_since = pd.to_numeric(productivity.get("since_2020"), errors="coerce")
    real_since = pd.to_numeric(real_comp.get("since_2020"), errors="coerce")
    share_since = pd.to_numeric(labor_share.get("since_2020"), errors="coerce")
    median_since = pd.to_numeric(median.get("Since 2020"), errors="coerce")
    return {
        "commercial_value": commercial_display,
        "production_value": (
            f"Productivity {prod_since:+.1f}% since 2020"
            if pd.notna(prod_since)
            else "Productivity n/a"
        ),
        "distribution_rows": [
            ("Real compensation", fmt_number(real_since, 1, signed=True, suffix="%")),
            ("Labor share", fmt_number(share_since, 1, signed=True, suffix="%")),
            ("Median earnings", fmt_number(median_since, 1, signed=True, suffix="%")),
            ("Group spread", fmt_number(spread, 1, suffix=" pts")),
        ],
    }


def _render_pulse(data: dict, commercialization_data) -> None:
    render_section("Outcomes pulse", "Commercial scale, production response, and distribution to workers and households.", first=True, compact=True)
    bridge = _build_value_bridge(data, commercialization_data)
    with st.container(key="economic-outcomes-value-bridge"):
        st.markdown(value_realization_bridge_html(commercial_value=bridge["commercial_value"], production_value=bridge["production_value"], distribution_rows=bridge["distribution_rows"], namespace="economic-outcomes-overview"), unsafe_allow_html=True, width="stretch")
    with st.container(key="full-width-layout-economic-realized-history"):
        with st.container(border=True, key="economic-outcomes-overview-realized"):
            render_panel_heading("National outcome history", "BLS indexes · 2017 = 100")
            render_summary_row(_realized_growth_metrics(data), key_prefix="economic-impact-current-growth")
            render_plotly_chart(productivity_index(data.get("productivity_history"), height=460), width="stretch", config={"responsive": True}, key="economic-impact-index-history")

def _realized_growth_metrics(data: dict) -> list[tuple[str, str, str]]:
    return [
        ("Labor productivity", _metric_text(data.get("nonfarm_productivity", {})), fmt_date((data.get("nonfarm_productivity", {}) or {}).get("date"))),
        ("Real output", _metric_text(data.get("nonfarm_output", {})), fmt_date((data.get("nonfarm_output", {}) or {}).get("date"))),
        ("Hourly compensation", _metric_text(data.get("nonfarm_compensation", {})), fmt_date((data.get("nonfarm_compensation", {}) or {}).get("date"))),
        ("Unit labor costs", _metric_text(data.get("nonfarm_unit_labor_cost", {})), fmt_date((data.get("nonfarm_unit_labor_cost", {}) or {}).get("date"))),
    ]


def _participation_metrics(data: dict) -> list[tuple[str, str, str]]:
    capture = data.get("capture_summary", {}) or {}
    median = capture.get("median_real_earnings", {}) or {}
    summary = data.get("earnings_distribution_summary")
    summary = summary.copy() if isinstance(summary, pd.DataFrame) else pd.DataFrame()
    peers = summary.loc[summary.get("Series", pd.Series("", index=summary.index)).astype(str).ne("All full-time workers")].copy() if not summary.empty else pd.DataFrame()
    if not peers.empty:
        peers["Since 2020"] = pd.to_numeric(peers.get("Since 2020"), errors="coerce")
        valid = peers.dropna(subset=["Since 2020"])
        strongest = valid.sort_values("Since 2020", ascending=False).iloc[0] if not valid.empty else pd.Series(dtype=object)
        weakest = valid.sort_values("Since 2020", ascending=True).iloc[0] if not valid.empty else pd.Series(dtype=object)
    else:
        strongest = weakest = pd.Series(dtype=object)
    return [
        ("Typical worker", fmt_number(median.get("Since 2020"), 1, signed=True, suffix="%"), "real median weekly earnings since 2020"),
        ("Women-to-men earnings", fmt_number(capture.get("women_to_men_earnings_pct"), 1, suffix="%"), "current four-quarter average"),
        ("Strongest group growth", str(strongest.get("Series") or "n/a"), fmt_number(strongest.get("Since 2020"), 1, signed=True, suffix="% since 2020")),
        ("Broad-participation spread", fmt_number(capture.get("group_growth_spread_ppts"), 1, suffix=" pts"), f"{str(weakest.get('Series') or 'weakest group')} to strongest"),
    ]


def _render_distribution_of_gains(data: dict) -> None:
    capture = data.get("capture_summary", {}) or {}
    productivity = capture.get("productivity", {}) or {}; real_comp = capture.get("real_compensation", {}) or {}; labor_share = capture.get("labor_share", {}) or {}
    render_section("Distribution of gains", "A paired treatment of aggregate worker capture and broad participation across demographic groups.")
    render_summary_row([
        ("Productivity since 2020", fmt_number(productivity.get("since_2020"), 1, signed=True, suffix="%"), fmt_date(productivity.get("date"))),
        ("Real compensation since 2020", fmt_number(real_comp.get("since_2020"), 1, signed=True, suffix="%"), fmt_date(real_comp.get("date"))),
        ("Productivity–comp gap", fmt_number(capture.get("productivity_real_comp_gap"), 1, signed=True, suffix=" pts"), "positive = productivity ahead"),
        ("Broad-participation spread", fmt_number(capture.get("group_growth_spread_ppts"), 1, suffix=" pts"), "weakest to strongest group"),
    ], key_prefix="economic-impact-distribution")
    left, right = st.columns(2)
    with left:
        with st.container(border=True, key="economic-impact-panel-worker-capture"):
            render_panel_heading("Productivity versus worker capture", "Each series rebased to its first 2020 observation")
            render_plotly_chart(worker_capture_history(data.get("value_transmission_history"), height=500), width="stretch", config={"displayModeBar": False, "responsive": True}, key="economic-impact-worker-capture-history")
    with right:
        with st.container(border=True, key="economic-impact-panel-participation"):
            participation_view = st.radio("Participation view", ["Change since 2020", "History · Sex", "History · Race and ethnicity"], horizontal=True, label_visibility="collapsed", key="economic-impact-participation-view")
            if participation_view == "Change since 2020":
                render_panel_heading("Real earnings change since 2020", "Four-quarter averages"); figure, chart_key = earnings_distribution_change(data.get("earnings_distribution_summary"), height=500), "economic-impact-earnings-distribution-change"
            else:
                dimension = participation_view.split(" · ", 1)[1]
                render_panel_heading("Real median weekly earnings", f"{dimension} · four-quarter average · first available 2020 average = 100")
                figure, chart_key = earnings_distribution_history(data.get("earnings_distribution_history"), dimension, height=500), f"economic-impact-earnings-distribution-{dimension.casefold().replace(' ', '-')}"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=chart_key)


def _render_economic_ledger(data: dict, commercialization_data) -> None:
    datasets = {
        "Productivity and costs": data.get("productivity_history"),
        "Worker capture": data.get("value_transmission_history"),
        "Earnings distribution": data.get("earnings_distribution_history"),
        "Information investment": data.get("investment_history"),
        "Inflation": data.get("cpi_history"),
        "Commercial validation": filtered_ledger(commercialization_data, pillars=["Revenue realization", "Paid demand", "Enterprise adoption"]),
    }
    with st.expander("Economic-outcomes data", expanded=False):
        view = st.radio("Ledger", list(datasets), horizontal=True, key="economic-impact-ledger-view")
        st.dataframe(arrow_safe_dataframe(datasets.get(view)), width="stretch", height=440, hide_index=True)

def render_economic_impact_tab(economic_impact_data: dict, commercialization_data=None, tab_read=None) -> None:
    render_tab_header("Economic Outcomes", "Productivity, worker compensation, median earnings, and broad participation alongside rising AI-related investment and adoption.", "BLS / BEA / FRED / primary company disclosures")
    _render_floating_terms("economic_impact")
    render_domain_read(tab_read, label="Economic Outcomes Read", domain="economic_outcomes")
    _render_pulse(economic_impact_data, commercialization_data)
    _render_distribution_of_gains(economic_impact_data)
    render_section("Investment validation", "Information-processing investment alongside output and productivity.")
    with st.container(key="full-width-layout-economic-investment-validation"):
        with st.container(border=True, key="economic-impact-panel-validation"):
            render_panel_heading("Investment versus realized performance", "Each series rebased to its first 2020 observation")
            render_plotly_chart(investment_vs_output(economic_impact_data.get("investment_history"), economic_impact_data.get("productivity_history"), height=470), width="stretch", config={"displayModeBar": False, "responsive": True}, key="economic-impact-investment-validation")
    render_section("Production economy", "Manufacturing productivity, real output, and unit labor costs.")
    mprod = economic_impact_data.get("manufacturing_productivity", {}); mout = economic_impact_data.get("manufacturing_output", {}); ulc = economic_impact_data.get("nonfarm_unit_labor_cost", {})
    render_summary_row([
        ("Manufacturing productivity", _metric_text(mprod), fmt_date(mprod.get("date"))),
        ("Manufacturing real output", _metric_text(mout), fmt_date(mout.get("date"))),
        ("Nonfarm unit labor costs", _metric_text(ulc), fmt_date(ulc.get("date"))),
    ], key_prefix="economic-impact-production")
    _render_economic_ledger(economic_impact_data, commercialization_data)

