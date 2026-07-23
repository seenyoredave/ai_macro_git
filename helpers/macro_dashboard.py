"""AI macro dashboard rendering helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.sector_assessment import select_current_sector_assessment
from config.debug_config import DEBUG, debug_print
from config.metric_definitions import METRIC_DEFINITIONS
from helpers.gaps import industrial_growth_gap, liquidity_gap, validation_gap
from helpers.labels import (
    adoption_label,
    liquidity_label,
    sector_display_name,
    short_regime_label,
    speculation_label,
    validation_label,
)
from helpers.visualization import (
    build_capital_stress_gauge,
    build_component_score_chart,
    build_concentration_gauge,
    build_development_gauge,
    build_equity_gauge,
    build_metric_history,
    build_positioning_map,
    build_power_stress_gauge,
    build_rotation_matrix,
)


def chart_box(fig):
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", height=350)


def fmt_score(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:.0f}"


def fmt_percent(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value * 100:.1f}%"


def fmt_multiple(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:.1f}x"


def fmt_decimal(value):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:.2f}"


def fmt_dollars(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value):
        return "No Data"
    magnitude = abs(float(value))
    if magnitude >= 1e12:
        return f"${value / 1e12:.2f}T"
    if magnitude >= 1e9:
        return f"${value / 1e9:.1f}B"
    if magnitude >= 1e6:
        return f"${value / 1e6:.1f}M"
    return f"${value:,.0f}"


def metric_help(key, fallback="Definition unavailable."):
    return METRIC_DEFINITIONS.get(key, fallback)


def get_ai_equity_value(macro_df):
    """Return the average current sector AEI value from the macro dataframe."""
    if macro_df is None or macro_df.empty:
        return np.nan

    for col in ["AEI Score", "Sector Score", "AI Equity Index"]:
        if col in macro_df.columns:
            values = pd.to_numeric(macro_df[col], errors="coerce")
            return float(values.mean()) if values.notna().any() else np.nan

    return np.nan


def _fmt_signed(value, decimals=2):
    value = pd.to_numeric(value, errors="coerce")
    return "No Data" if pd.isna(value) else f"{value:+.{decimals}f}"


def render_trend_strip(trend):
    trend = trend or {}
    current = trend.get("current", np.nan)
    velocity = trend.get("velocity", np.nan)
    acceleration = trend.get("acceleration", np.nan)

    st.markdown(
        f"""
        <div style="text-align:center;font-size:0.85rem;margin-top:-8px;color:#d1d5db;">
            <b>Archived</b>: {fmt_decimal(current)}
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Velocity</b>: {_fmt_signed(velocity)}
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Accel</b>: {_fmt_signed(acceleration)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_no_data_panel(title, message="No valid current or archived value is available."):
    st.markdown(
        f"""
        <div style="height:285px;border:1px solid #374151;border-radius:12px;
                    background:rgba(17,24,39,.65);display:flex;flex-direction:column;
                    align-items:center;justify-content:center;text-align:center;padding:24px;">
            <div style="font-size:1.15rem;font-weight:700;margin-bottom:10px;">{title}</div>
            <div style="font-size:1.6rem;font-weight:700;color:#9ca3af;margin-bottom:8px;">No Data</div>
            <div style="font-size:.85rem;color:#9ca3af;max-width:320px;">{message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_source_caption(source, fallback_date):
    if source == "Archive Fallback":
        suffix = f" from {fallback_date}" if fallback_date else ""
        st.caption(f"Current inputs were insufficient; using the last valid archived value{suffix}.")
    elif source == "Unavailable":
        st.caption("Current inputs and compatible archive history were insufficient.")


def _render_metric_panel(
    title,
    value,
    gauge_builder,
    trend,
    *,
    help_text,
    source="Current",
    fallback_date=None,
    history_range=(0, 100),
):
    with st.container(border=True):
        st.subheader(title, help=help_text)
        gauge_col, history_col = st.columns([1, 1.15])

        with gauge_col:
            if pd.notna(pd.to_numeric(value, errors="coerce")):
                st.plotly_chart(gauge_builder(value), width="stretch", config={"responsive": True})
            else:
                render_no_data_panel(title)
            render_trend_strip(trend)
            _render_source_caption(source, fallback_date)

        with history_col:
            st.plotly_chart(
                build_metric_history(
                    trend,
                    title,
                    y_range=history_range,
                    adaptive_range=True,
                    min_span=20,
                    step=title in {"Power Stress Index", "Capital Stress"},
                    flat_annotation=(
                        "No change in filing/fundamental inputs during this archive window."
                        if title == "Capital Stress"
                        else None
                    ),
                ),
                width="stretch",
                config={"responsive": True},
            )


def _component_table(component_group):
    rows = []
    for name, payload in (component_group or {}).items():
        payload = payload or {}
        rows.append({
            "Component": name,
            "Score": fmt_decimal(payload.get("score", np.nan)),
            "Weight": fmt_percent(payload.get("weight", np.nan)),
            "Primary Raw": fmt_decimal(payload.get("raw", np.nan)),
            "Secondary Raw": fmt_decimal(payload.get("secondary_raw", np.nan)),
            "Observations": payload.get("observations", ""),
        })
    return pd.DataFrame(rows)


def _capital_component_table(capital_result):
    components = (capital_result or {}).get("components", {}) or {}
    rows = []

    for name, payload in components.items():
        raw = payload.get("raw", np.nan)
        secondary = payload.get("secondary_raw", np.nan)
        total = payload.get("obligation_total", np.nan)

        if name == "Cash Flow Strain":
            measure = (
                f"sum(FCF)/sum(Revenue) = {fmt_percent(raw)}; "
                f"sum(CapEx)/sum(OCF) = {fmt_multiple(secondary)}"
            )
        elif name == "Book Leverage":
            measure = f"sum(Net Debt)/sum(EBITDA) = {fmt_multiple(raw)}"
        elif name == "Committed Burden":
            measure = (
                f"sum(Commitments)/sum(OCF) = {fmt_multiple(raw)}; "
                f"sum(Commitments) = {fmt_dollars(total)}"
            )
        else:
            measure = (
                f"sum(Contingent Exposure)/sum(OCF) = {fmt_multiple(raw)}; "
                f"sum(Contingent Exposure) = {fmt_dollars(total)}"
            )

        rows.append({
            "Component": name,
            "Score": _fmt_signed(payload.get("score", np.nan), decimals=1),
            "Weight": fmt_percent(payload.get("weight", np.nan)),
            "Equation / Current Inputs": measure,
            "Companies": payload.get("observations", 0),
        })

    return pd.DataFrame(rows)


def assessment_card(title, row, border_color):
    if row is None:
        st.html(f"""
        <div style="border:1px solid {border_color};border-left:6px solid {border_color};
                    border-radius:12px;padding:18px;background:#111827;min-height:150px;">
            <div style="font-size:0.9rem;letter-spacing:1px;color:#9ca3af;
                        text-transform:uppercase;font-weight:700;margin-bottom:8px;">{title}</div>
            <div style="font-size:1.5rem;font-weight:700;margin-bottom:12px;">No Data</div>
            <div style="font-size:0.85rem;color:#9ca3af;">Insufficient eligible history or fundamentals.</div>
        </div>
        """)
        return

    display_sector = sector_display_name(row["Sector"])
    aei = pd.to_numeric(row["Sector Score"], errors="coerce")
    pressure = pd.to_numeric(row["Pressure"], errors="coerce")

    if title == "Biggest Risk":
        breadth = pd.to_numeric(row.get("Risk Breadth Score", np.nan), errors="coerce")
        adverse = pd.to_numeric(row.get("Adverse Signals", np.nan), errors="coerce")
        valid = pd.to_numeric(row.get("Valid Signals", np.nan), errors="coerce")
        signal_text = (
            f"{int(adverse)} / {int(valid)}"
            if pd.notna(adverse) and pd.notna(valid)
            else "No Data"
        )
        st.html(f"""
        <div style="border:1px solid {border_color};border-left:6px solid {border_color};
                    border-radius:12px;padding:18px;background:#111827;min-height:150px;">
            <div style="font-size:0.9rem;letter-spacing:1px;color:#9ca3af;
                        text-transform:uppercase;font-weight:700;margin-bottom:8px;">{title}</div>
            <div style="font-size:1.5rem;font-weight:700;margin-bottom:12px;">{display_sector}</div>
            <div style="display:flex;justify-content:space-between;font-size:0.9rem;">
                <span>Deterioration Breadth</span><b>{fmt_percent(breadth / 100) if pd.notna(breadth) else "No Data"}</b>
            </div>
            <div style="display:flex;justify-content:space-between;font-size:0.9rem;">
                <span>Adverse / Valid Signals</span><b>{signal_text}</b>
            </div>
        </div>
        """)
        return

    st.html(f"""
    <div style="border:1px solid {border_color};border-left:6px solid {border_color};
                border-radius:12px;padding:18px;background:#111827;min-height:150px;">
        <div style="font-size:0.9rem;letter-spacing:1px;color:#9ca3af;
                    text-transform:uppercase;font-weight:700;margin-bottom:8px;">{title}</div>
        <div style="font-size:1.5rem;font-weight:700;margin-bottom:12px;">{display_sector}</div>
        <div style="display:flex;justify-content:space-between;font-size:0.9rem;">
            <span>AEI Score</span><b>{fmt_score(aei)}</b>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:0.9rem;">
            <span>Pressure Score</span><b>{fmt_score(pressure)}</b>
        </div>
    </div>
    """)


def _snapshot_values(macro_df, fred_data, sector_data, regime_metrics):
    industrial_payload = fred_data.get("Industrial Production YoY", np.nan)
    industrial_growth = (
        industrial_payload.get("value", np.nan)
        if isinstance(industrial_payload, dict)
        else industrial_payload
    )

    aei = regime_metrics.get("AI Equity Index", get_ai_equity_value(macro_df))
    adi = regime_metrics.get("AI Development Intensity", np.nan)
    return {
        "aei": aei,
        "adi": adi,
        "power_stress": regime_metrics.get("Power Stress Index", np.nan),
        "concentration_hhi": regime_metrics.get("Concentration HHI", np.nan),
        "capital_stress": regime_metrics.get("Capital Stress", np.nan),
        "speculation_gap": regime_metrics.get("Speculation Gap", np.nan),
        "validation_gap": validation_gap(
            sector_data=sector_data,
            fred_data=fred_data,
            sector="ENTERPRISE_AI_SOFTWARE",
        ),
        "liquidity_gap": liquidity_gap(macro_df=macro_df, fred_data=fred_data),
        "industrial_gap": industrial_growth_gap(adi, industrial_growth),
    }


def _render_snapshot_heading(aei):
    header_col, metric_col = st.columns([2, 1])
    with header_col:
        st.subheader("AI Economy Snapshot", help=metric_help("AI Economy Snapshot"))
    with metric_col:
        st.metric(
            "Current Equity Regime",
            short_regime_label(aei),
            help=(
                "Classifies the current AI Equity Index reading.\n\n"
                "Weak: <30 | Neutral: 30–59 | Strong: 60–79 | Extended: 80+"
            ),
        )
    st.markdown("---")


def _render_equity_and_development(values, trends, regime_metrics):
    left, right = st.columns(2)
    with left:
        _render_metric_panel(
            "AI Equity Index",
            values["aei"],
            build_equity_gauge,
            trends.get("aei"),
            help_text=metric_help("AI Equity Index"),
            source=regime_metrics.get("AEI Source", "Current"),
            fallback_date=regime_metrics.get("AEI Fallback Date"),
        )
    with right:
        _render_metric_panel(
            "AI Development Intensity",
            values["adi"],
            build_development_gauge,
            trends.get("adi"),
            help_text=metric_help("AI Development Intensity"),
            source=regime_metrics.get("ADI Source", "Current"),
            fallback_date=regime_metrics.get("ADI Fallback Date"),
        )

    with st.expander("ADI Component Detail", expanded=False):
        adi_components = (regime_metrics.get("ADI Components", {}) or {}).get("components", {})
        st.dataframe(_component_table(adi_components), width="stretch", hide_index=True)
        st.caption("ADI is constituted when at least three of four top-level pillars are valid.")
        if regime_metrics.get("ADI Source") == "Archive Fallback":
            st.caption(
                "The headline ADI is carried forward; component detail reflects "
                "the current run's available inputs."
            )
    st.markdown("---")


def _render_power_and_concentration(values, trends, regime_metrics):
    left, right = st.columns(2)
    with left:
        _render_metric_panel(
            "Power Stress Index",
            values["power_stress"],
            build_power_stress_gauge,
            trends.get("power_stress"),
            help_text=metric_help("Power Stress Index"),
            source=regime_metrics.get("Power Stress Source", "Current"),
            fallback_date=regime_metrics.get("Power Stress Fallback Date"),
            history_range=(-100, 100),
        )
    with right:
        _render_metric_panel(
            "Concentration HHI",
            values["concentration_hhi"],
            build_concentration_gauge,
            trends.get("concentration"),
            help_text=metric_help("Concentration HHI"),
        )
    st.markdown("---")


def _render_capital_stress(values, trend, regime_metrics):
    capital_result = regime_metrics.get("Capital Stress Components", {}) or {}
    with st.container(border=True):
        st.header("Capital Stress", help=metric_help("Capital Stress"))
        gauge_col, history_col, component_col = st.columns([1, 1.15, 1.35])

        with gauge_col:
            if pd.notna(pd.to_numeric(values["capital_stress"], errors="coerce")):
                st.plotly_chart(
                    build_capital_stress_gauge(values["capital_stress"]),
                    width="stretch",
                    config={"responsive": True},
                )
            else:
                render_no_data_panel("Capital Stress")
            render_trend_strip(trend)
            _render_source_caption(
                regime_metrics.get("Capital Stress Source", "Current"),
                regime_metrics.get("Capital Stress Fallback Date"),
            )

        with history_col:
            st.plotly_chart(
                build_metric_history(
                    trend,
                    "Capital Stress",
                    y_range=(-100, 100),
                    adaptive_range=True,
                    min_span=20,
                    step=True,
                    flat_annotation=(
                        "No change in filing/fundamental inputs during this archive window."
                    ),
                ),
                width="stretch",
                config={"responsive": True},
            )

        with component_col:
            st.plotly_chart(
                build_component_score_chart(
                    capital_result.get("components", {}),
                    "Capital Stress Components",
                    x_range=(-100, 100),
                ),
                width="stretch",
                config={"responsive": True},
            )

    with st.expander("Capital Stress Detail", expanded=False):
        st.dataframe(
            _capital_component_table(capital_result),
            width="stretch",
            hide_index=True,
        )
        if regime_metrics.get("Capital Stress Source") == "Archive Fallback":
            st.caption(
                "The headline Capital Stress value is carried forward; component "
                "detail reflects the current run's available inputs."
            )
    st.markdown("---")


def _render_gap_metrics(values):
    gap_specs = [
        ("Speculation Gap", values["speculation_gap"], speculation_label),
        ("Economic Validation Gap", values["validation_gap"], validation_label),
        ("Liquidity Support Gap", values["liquidity_gap"], liquidity_label),
        ("AI–Industrial Growth Gap", values["industrial_gap"], adoption_label),
    ]
    for column, (title, value, label_fn) in zip(st.columns(4), gap_specs):
        with column:
            help_key = "AI-Industrial Growth Gap" if title.startswith("AI–") else title
            st.metric(title, fmt_score(value), help=metric_help(help_key))
            st.caption(label_fn(value))
    st.markdown("---")


def render_regime_snapshot(
    macro_df,
    fred_data=None,
    power_stress_trend=None,
    concentration_trend=None,
    sector_data=None,
    regime_metrics=None,
    *,
    aei_trend=None,
    adi_trend=None,
    capital_stress_trend=None,
):
    """Render the macro snapshot from a small set of coherent sections."""
    fred_data = fred_data or {}
    sector_data = sector_data or {}
    regime_metrics = regime_metrics or {}
    trends = {
        "aei": aei_trend or {},
        "adi": adi_trend or {},
        "power_stress": power_stress_trend or {},
        "concentration": concentration_trend or {},
    }
    values = _snapshot_values(macro_df, fred_data, sector_data, regime_metrics)

    if DEBUG:
        debug_print("\n=== REGIME SNAPSHOT ===")
        debug_print("AEI:", values["aei"])
        debug_print("ADI:", values["adi"])
        debug_print("Speculation Gap:", values["speculation_gap"])
        debug_print("Power Stress:", values["power_stress"])
        debug_print("Capital Stress:", values["capital_stress"])

    _render_snapshot_heading(values["aei"])
    _render_equity_and_development(values, trends, regime_metrics)
    _render_power_and_concentration(values, trends, regime_metrics)
    _render_capital_stress(values, capital_stress_trend or {}, regime_metrics)
    _render_gap_metrics(values)

def render_sector_assessment(macro_df, sector_data=None):
    st.subheader("Current Sector Assessment", help=metric_help("Current Sector Assessment"))

    if macro_df is None or macro_df.empty:
        st.warning("Sector assessment unavailable. Check sector metric calculations.")
        return

    required_cols = ["Sector", "Sector Score", "Pressure"]
    missing = [col for col in required_cols if col not in macro_df.columns]
    if missing:
        st.warning(f"Sector assessment unavailable. Missing columns: {missing}")
        return

    assessment_df = macro_df.copy()
    if assessment_df[["Sector Score", "Pressure"]].notna().sum().min() == 0:
        st.warning("Sector assessment unavailable. Check AEI and Pressure calculations.")
        return

    selections = select_current_sector_assessment(assessment_df, sector_data=sector_data)
    selected_rows = selections.get("rows", {})

    col1, col2, col3 = st.columns(3)
    with col1:
        assessment_card("Most Crowded", selected_rows.get("Most Crowded"), "#7c3aed")
    with col2:
        assessment_card("Fastest Mover", selected_rows.get("Fastest Mover"), "#60a5fa")
    with col3:
        assessment_card("Biggest Risk", selected_rows.get("Biggest Risk"), "#94a3b8")

    st.markdown("---")


def render_positioning_charts(macro_df):
    st.subheader("Sector Positioning and Rotation")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### AI Sector Positioning Map")
        chart_box(build_positioning_map(macro_df))
    with col2:
        st.markdown("### AI Sector Rotation Matrix")
        chart_box(build_rotation_matrix(macro_df))

    st.markdown("---")


def render_sector_table(macro_df):
    required = ["Sector", "Sector Score", "Pressure", "Avg Return", "Forward P/E", "Beta"]
    missing = [col for col in required if col not in macro_df.columns]
    if missing:
        st.error(f"Sector Data unavailable. Missing columns: {missing}")
        return

    table = macro_df[required].copy()
    table["Sector"] = table["Sector"].apply(sector_display_name)
    table = table.rename(columns={
        "Sector Score": "AEI Score",
        "Avg Return": "1Y Return",
    })
    table["AEI Score"] = table["AEI Score"].map(fmt_score)
    table["Pressure"] = table["Pressure"].map(fmt_score)
    table["1Y Return"] = table["1Y Return"].map(fmt_percent)
    table["Forward P/E"] = table["Forward P/E"].map(fmt_multiple)
    table["Beta"] = table["Beta"].map(fmt_decimal)

    with st.expander("Sector Data", expanded=False):
        st.dataframe(table, width="stretch", hide_index=True)


def render_macro_data(fred_data):
    if not fred_data:
        st.warning("No FRED data available")
        return

    rows = []
    for indicator, payload in fred_data.items():
        if isinstance(payload, dict):
            value = payload.get("value", None)
            date = payload.get("date", None)
        else:
            value = payload
            date = None
        rows.append({"Indicator": indicator, "Value": value, "Date": date})

    with st.expander("FRED Data", expanded=False):
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Market data cache: 1 hour | FRED cache: 24 hours")


def render_edgar_data(sector_data):
    if not sector_data:
        st.warning("No EDGAR data available")
        return

    rows = []
    for sector, df in sector_data.items():
        if df is None or df.empty:
            continue

        cols = [
            "Ticker",
            "Company",
            "Market Cap",
            "Revenue",
            "Revenue Growth",
            "CapEx",
            "CapEx Growth",
        ]
        available = [col for col in cols if col in df.columns]
        sector_snapshot = df[available].copy()
        sector_snapshot.insert(0, "Sector", sector_display_name(sector))
        rows.append(sector_snapshot)

    if not rows:
        st.warning("No EDGAR rows available")
        return

    with st.expander("EDGAR Data", expanded=False):
        st.dataframe(pd.concat(rows, ignore_index=True), width="stretch", hide_index=True)
