from __future__ import annotations

import pandas as pd
import streamlit as st

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
from rendering.common import _render_floating_terms
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
from rendering.dataframe import arrow_safe_dataframe


def _row(frame: pd.DataFrame, series: str, metric: str | None = None) -> dict:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return {}
    mask = frame.get("Series", pd.Series("", index=frame.index)).astype(str).eq(series)
    if metric is not None and "Metric" in frame.columns:
        mask &= frame["Metric"].astype(str).eq(metric)
    rows = frame.loc[mask]
    return rows.iloc[-1].to_dict() if not rows.empty else {}


def _yoy_text(row: dict) -> str:
    value = pd.to_numeric(row.get("YoY Change"), errors="coerce")
    return fmt_number(value * 100.0, 1, signed=True, suffix="%")


def _render_signature(data: dict) -> None:
    render_section("Employment and real pay", "Employment and inflation-adjusted pay across industries directly involved in AI production and infrastructure.", first=True)
    with st.container(key="full-width-layout-workforce-outcomes-matrix"):
        with st.container(border=True, key="workforce-panel-outcomes-matrix"):
            render_panel_heading("Employment and real-pay outcomes", "Latest values in cells · color shows where each measure sits within its 2020-present range")
            render_plotly_chart(workforce_outcomes_matrix(data.get("transmission_matrix"), height=560), width="stretch", config={"displayModeBar": False, "responsive": True}, key="workforce-outcomes-matrix")

def _render_pulse(data: dict) -> None:
    matrix = data.get("transmission_matrix", pd.DataFrame())
    positive_jobs = int((pd.to_numeric(matrix.get("Employment YoY"), errors="coerce") > 0).sum()) if isinstance(matrix, pd.DataFrame) else 0
    positive_real = int((pd.to_numeric(matrix.get("Real earnings YoY"), errors="coerce") > 0).sum()) if isinstance(matrix, pd.DataFrame) else 0
    information_hires = _row(data.get("labor_flow_latest", pd.DataFrame()), "Information", "Hires rate")
    information_layoffs = _row(data.get("labor_flow_latest", pd.DataFrame()), "Information", "Layoffs and discharges rate")
    render_section(
        "Current labor-market conditions",
        "Current employment, real pay, openings, hiring, quits, and layoffs across covered industries.",
        compact=True,
    )
    render_statline([
        ("Employment breadth", f"{positive_jobs}/4", "direct production and deployment channels growing YoY"),
        ("Real-earnings breadth", f"{positive_real}/4", "direct channels with purchasing-power gains YoY"),
        ("Information hires", fmt_number(information_hires.get("Value"), 1, suffix="%"), f"monthly hires rate · {fmt_date(information_hires.get('Date'))}"),
        ("Information layoffs", fmt_number(information_layoffs.get("Value"), 1, suffix="%"), f"layoffs/discharges rate · {fmt_date(information_layoffs.get('Date'))}"),
    ], key_prefix="workforce-pulse")


def _render_workforce_channels(data: dict) -> None:
    render_section("Employment, hiring, pay, and task exposure", "Views of employment, labor flows, pay, and research estimates of task exposure.")
    with st.container(key="full-width-layout-workforce-channels"):
        with st.container(border=True, key="workforce-panel-channel-workbench"):
            view = st.radio("Channel", ["Employment", "Labor flows", "Compensation", "Exposure benchmark"], horizontal=True, label_visibility="collapsed", key="workforce-channel-view")
            if view == "Labor flows":
                measure = st.radio("Labor-flow measure", ["Job openings level", "Job openings rate", "Hires rate", "Quits rate", "Layoffs and discharges rate"], horizontal=True, index=1, label_visibility="collapsed", key="workforce-flow-view")
                if measure == "Job openings level":
                    render_panel_heading("Job openings by supporting labor market", "Thousands of openings")
                    figure, key = level_history(data.get("job_openings_history"), value_suffix="K"), "workforce-labor-flow-job-openings-level"
                else:
                    render_panel_heading(measure, "Percent of industry employment")
                    figure, key = labor_flow_history(data.get("labor_flows_history"), measure), f"workforce-labor-flow-{measure.casefold().replace(' ', '-')}"
            elif view == "Compensation":
                basis = st.radio("Earnings basis", ["Inflation-adjusted", "Nominal"], horizontal=True, index=0, label_visibility="collapsed", key="workforce-earnings-basis")
                cpi_history = data.get("cpi_history"); earnings_history_frame = data.get("earnings_history"); cpi_date = None
                if isinstance(cpi_history, pd.DataFrame) and not cpi_history.empty:
                    cpi_dates = pd.to_datetime(cpi_history.get("Date"), errors="coerce", format="mixed")
                    earnings_end = pd.to_datetime(earnings_history_frame.get("Date"), errors="coerce", format="mixed").max() if isinstance(earnings_history_frame, pd.DataFrame) and not earnings_history_frame.empty else None
                    eligible = cpi_dates.loc[cpi_dates <= earnings_end] if pd.notna(earnings_end) else cpi_dates
                    cpi_date = eligible.max()
                subtitle = "BLS CES · nominal dollars per hour" if basis == "Nominal" else f"BLS CES · purchasing power in {fmt_date(cpi_date)} CPI dollars"
                subtitle += " · dashed = U.S. total private"
                render_panel_heading("Average hourly earnings", subtitle)
                figure, key = earnings_history(data.get("earnings_history"), cpi_history, inflation_adjusted=basis == "Inflation-adjusted"), f"workforce-earnings-history-{basis.casefold().replace('-', '_')}"
            elif view == "Exposure benchmark":
                render_panel_heading("Tasks potentially exposed to LLMs", "2023 research benchmark · unweighted occupation medians")
                figure, key = occupation_exposure_by_group(data.get("occupation_exposure_by_group"), height=500), "workforce-exposure-by-group"
            else:
                employment_view = st.radio("Employment view", ["History", "Current change"], horizontal=True, label_visibility="collapsed", key="workforce-employment-view")
                if employment_view == "Current change":
                    render_panel_heading("Current employment change", "Year over year"); figure, key = current_momentum(data.get("employment_latest"), height=480), "workforce-employment-momentum"
                else:
                    render_panel_heading("Employment history", "January 2020 = 100"); figure, key = indexed_history(data.get("employment_history"), height=480), "workforce-employment-history"
            render_plotly_chart(figure, width="stretch", config={"displayModeBar": False, "responsive": True}, key=key)


def _render_workforce_ledger(data: dict) -> None:
    datasets = {
        "Employment": data.get("employment_history"),
        "Hourly earnings": data.get("earnings_history"),
        "Labor flows": data.get("labor_flows_history"),
        "Job openings": data.get("job_openings_history"),
        "Occupation exposure": data.get("occupation_exposure"),
        "Inflation": data.get("cpi_history"),
    }
    with st.expander("Workforce data", expanded=False):
        view = st.radio("Ledger", list(datasets), horizontal=True, key="workforce-ledger-view")
        st.dataframe(arrow_safe_dataframe(datasets.get(view)), width="stretch", height=440, hide_index=True)

def render_workforce_tab(workforce_data: dict, tab_read=None) -> None:
    inject_panel_height_rules({})
    render_tab_header("Workforce", "Employment, hiring, separations, real pay, and task exposure in industries tied to AI production and deployment.", "U.S. Bureau of Labor Statistics")
    _render_floating_terms("workforce")
    render_domain_read(tab_read, label="Read", domain="workforce")
    _render_signature(workforce_data)
    _render_pulse(workforce_data)
    _render_workforce_channels(workforce_data)
    _render_workforce_ledger(workforce_data)

