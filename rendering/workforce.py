from __future__ import annotations

import pandas as pd
import streamlit as st

from rendering.evidence_gateway import render_evidence_gateway
from rendering.visual_system import render_plotly_chart
from rendering.charts_workforce import (
    current_momentum,
    earnings_history,
    indexed_history,
    labor_flow_history,
    level_history,
    occupation_exposure_by_group,
    workforce_outcomes_matrix,
)
from rendering.components import (
    fmt_date,
    fmt_number,
    inject_panel_height_rules,
    render_domain_read,
    render_panel_heading,
    render_section,
    render_statline,
    render_tab_header,
)


def _row(frame: pd.DataFrame, series: str, metric: str | None = None) -> dict:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    mask = frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq(series)
    if metric is not None and "Metric" in frame.columns:
        mask &= frame["Metric"].astype(str).eq(metric)
    rows = frame.loc[mask]
    return rows.iloc[-1].to_dict() if not rows.empty else {}


def _render_current_state(data: dict) -> None:
    matrix = data.get("transmission_matrix", pd.DataFrame())
    positive_jobs = int((pd.to_numeric(matrix.get("Employment YoY"), errors="coerce") > 0).sum()) if isinstance(matrix, pd.DataFrame) else 0
    positive_real = int((pd.to_numeric(matrix.get("Real earnings YoY"), errors="coerce") > 0).sum()) if isinstance(matrix, pd.DataFrame) else 0
    information_hires = _row(data.get("labor_flow_latest", pd.DataFrame()), "Information", "Hires rate")
    information_layoffs = _row(data.get("labor_flow_latest", pd.DataFrame()), "Information", "Layoffs and discharges rate")
    render_section(
        "Employment and labor flows",
        "Employment, real pay, job openings, hiring, quits, and layoffs across covered industries.",
        first=True,
        compact=True,
    )
    render_statline(
        [
            ("Employment breadth", f"{positive_jobs}/4", "direct production and deployment channels growing YoY"),
            ("Real-earnings breadth", f"{positive_real}/4", "direct channels with purchasing-power gains YoY"),
            ("Information hires", fmt_number(information_hires.get("Value"), 1, suffix="%"), f"monthly hires rate · {fmt_date(information_hires.get('Date'))}"),
            ("Information layoffs", fmt_number(information_layoffs.get("Value"), 1, suffix="%"), f"layoffs/discharges rate · {fmt_date(information_layoffs.get('Date'))}"),
        ],
        key_prefix="workforce-pulse",
    )


def _render_observed_outcomes(data: dict) -> None:
    render_section(
        "Employment and real pay",
        "Employment and inflation-adjusted pay in industries tied directly to AI production and infrastructure.",
    )
    with st.container(key="full-width-layout-workforce-outcomes-matrix"):
        with st.container(border=True, key="workforce-panel-outcomes-matrix"):
            render_panel_heading(
                "Employment and real pay",
                "Latest readings · color shows each measure within its 2020-present range",
            )
            render_plotly_chart(
                workforce_outcomes_matrix(data.get("transmission_matrix"), height=560),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="workforce-outcomes-matrix",
            )


def _render_labor_market_dynamics(data: dict) -> None:
    render_section(
        "Labor-market detail",
        "Employment history, labor flows, earnings, and published estimates of LLM task exposure.",
    )
    with st.container(key="full-width-layout-workforce-dynamics"):
        with st.container(border=True, key="workforce-panel-dynamics"):
            view = st.radio(
                "Labor-market view",
                ["Employment", "Labor flows"],
                horizontal=True,
                label_visibility="collapsed",
                key="workforce-dynamics-view",
            )
            if view == "Labor flows":
                measure = st.radio(
                    "Labor-flow measure",
                    ["Job openings level", "Job openings rate", "Hires rate", "Quits rate", "Layoffs and discharges rate"],
                    horizontal=True,
                    index=1,
                    label_visibility="collapsed",
                    key="workforce-flow-view",
                )
                if measure == "Job openings level":
                    render_panel_heading("Job openings by supporting labor market", "Thousands of openings")
                    figure = level_history(data.get("job_openings_history"), value_suffix="K")
                    chart_key = "workforce-labor-flow-job-openings-level"
                else:
                    render_panel_heading(measure, "Percent of industry employment")
                    figure = labor_flow_history(data.get("labor_flows_history"), measure)
                    chart_key = f"workforce-labor-flow-{measure.casefold().replace(' ', '-')}"
            else:
                employment_view = st.radio(
                    "Employment view",
                    ["History", "Current change"],
                    horizontal=True,
                    label_visibility="collapsed",
                    key="workforce-employment-view",
                )
                if employment_view == "Current change":
                    render_panel_heading("Current employment change", "Year over year")
                    figure = current_momentum(data.get("employment_latest"), height=480)
                    chart_key = "workforce-employment-momentum"
                else:
                    render_panel_heading("Employment history", "January 2020 = 100")
                    figure = indexed_history(data.get("employment_history"), height=480)
                    chart_key = "workforce-employment-history"
            render_plotly_chart(
                figure,
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key=chart_key,
            )


def _render_compensation(data: dict) -> None:
    render_section(
        "Compensation",
        "Nominal and inflation-adjusted hourly earnings across covered industries.",
    )
    cpi_history = data.get("cpi_history")
    earnings_history_frame = data.get("earnings_history")
    cpi_date = None
    if isinstance(cpi_history, pd.DataFrame) and not cpi_history.empty:
        cpi_dates = pd.to_datetime(cpi_history.get("Date"), errors="coerce", format="mixed")
        earnings_end = (
            pd.to_datetime(earnings_history_frame.get("Date"), errors="coerce", format="mixed").max()
            if isinstance(earnings_history_frame, pd.DataFrame) and not earnings_history_frame.empty
            else None
        )
        eligible = cpi_dates.loc[cpi_dates <= earnings_end] if pd.notna(earnings_end) else cpi_dates
        cpi_date = eligible.max()

    with st.container(key="full-width-layout-workforce-compensation"):
        with st.container(border=True, key="workforce-panel-compensation"):
            basis = st.radio(
                "Earnings basis",
                ["Inflation-adjusted", "Nominal"],
                horizontal=True,
                index=0,
                label_visibility="collapsed",
                key="workforce-earnings-basis",
            )
            subtitle = (
                "BLS CES · nominal dollars per hour"
                if basis == "Nominal"
                else f"BLS CES · purchasing power in {fmt_date(cpi_date)} CPI dollars"
            )
            subtitle += " · dashed = U.S. total private"
            render_panel_heading("Average hourly earnings", subtitle)
            render_plotly_chart(
                earnings_history(
                    data.get("earnings_history"),
                    cpi_history,
                    inflation_adjusted=basis == "Inflation-adjusted",
                ),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key=f"workforce-earnings-history-{basis.casefold().replace('-', '_')}",
            )


def _render_exposure_benchmark(data: dict) -> None:
    render_section(
        "Exposure benchmark",
        "Published estimates of occupational tasks potentially exposed to large language models.",
    )
    with st.container(key="full-width-layout-workforce-exposure"):
        with st.container(border=True, key="workforce-panel-exposure"):
            render_panel_heading(
                "Tasks potentially exposed to LLMs",
                "2023 research benchmark · unweighted occupation medians",
            )
            render_plotly_chart(
                occupation_exposure_by_group(data.get("occupation_exposure_by_group"), height=500),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="workforce-exposure-by-group",
            )


def render_workforce_tab(workforce_data: dict, tab_read=None) -> None:
    inject_panel_height_rules({})
    render_tab_header(
        "Workforce",
        "Employment, hiring, separations, real pay, and task exposure in AI-linked industries.",
        "U.S. Bureau of Labor Statistics",
        terms_key="workforce",
    )
    render_domain_read(tab_read, label="Read", domain="workforce")
    _render_current_state(workforce_data)
    _render_observed_outcomes(workforce_data)
    _render_labor_market_dynamics(workforce_data)
    _render_compensation(workforce_data)
    _render_exposure_benchmark(workforce_data)
    render_evidence_gateway("workforce")
