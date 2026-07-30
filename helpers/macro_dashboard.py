"""AI macro dashboard rendering helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from analytics.deployment_funding_mix import calculate_deployment_funding_mix
from analytics.financial_conditions import (
    nfci_condition,
    nfci_direction,
    nfci_snapshot,
    nfci_summary,
)
from analytics.sector_assessment import select_current_sector_assessment
from config.debug_config import DEBUG, debug_print
from config.metric_definitions import METRIC_DEFINITIONS
from helpers.gaps import industrial_growth_gap
from helpers.dataframe_display import arrow_safe_dataframe
from helpers.labels import (
    adoption_label,
    sector_display_name,
    speculation_label,
    validation_label,
)
from helpers.visualization import (
    build_borrower_strain_gauge,
    build_component_score_chart,
    build_concentration_gauge,
    build_development_gauge,
    build_equity_gauge,
    build_lender_strain_gauge,
    build_nfci_history,
    build_nfci_sparkline,
    build_metric_history,
    build_mini_line_history,
    build_positioning_map,
    build_power_stress_gauge,
    build_rotation_matrix,
)


def chart_box(fig, *, key):
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", height=350, key=key)


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
    key_prefix,
):
    with st.container(border=True):
        st.subheader(title, help=help_text)
        gauge_col, history_col = st.columns([1, 1.15])

        with gauge_col:
            if pd.notna(pd.to_numeric(value, errors="coerce")):
                st.plotly_chart(
                    gauge_builder(value),
                    width="stretch",
                    config={"responsive": True},
                    key=f"{key_prefix}-gauge",
                )
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
                    step=title in {"Power Stress Index", "Borrower Strain"},
                    flat_annotation=(
                        "No change in filing/fundamental inputs during this archive window."
                        if title == "Borrower Strain"
                        else None
                    ),
                    revision_date=trend.get("revision_date"),
                    revision_label=trend.get("revision_label"),
                ),
                width="stretch",
                config={"responsive": True},
                key=f"{key_prefix}-history",
            )
            if trend.get("history_note"):
                st.caption(trend["history_note"])


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


def _lender_strain_component_table(lender_strain_result):
    components = (lender_strain_result or {}).get("components", {}) or {}
    rows = []

    for name, payload in components.items():
        raw = payload.get("raw", np.nan)
        secondary = payload.get("secondary_raw", np.nan)

        if name == "Bank Credit Tightening":
            measure = f"SLOOS net tightening: {fmt_decimal(raw)}%"
        elif name == "Bank Capital Strain":
            measure = f"Regulatory Tier 1 capital / risk-weighted assets: {fmt_decimal(raw)}%"
        elif name == "Private Credit Impairment":
            portfolio_cost = pd.to_numeric(
                payload.get("portfolio_cost_mm", np.nan), errors="coerce"
            )
            observations = payload.get("observations", "")
            measure = (
                f"BDC non-accruals at cost: {fmt_decimal(raw)}%; "
                f"{observations} lenders; portfolio cost {fmt_dollars(portfolio_cost * 1e6)}"
            )
        else:
            reported_assets = pd.to_numeric(
                payload.get("reported_assets_bn", np.nan), errors="coerce"
            )
            measure = (
                f"High-leverage portfolio share: {fmt_decimal(raw)}%; "
                f"PIK / borrowings: {fmt_decimal(secondary)}%; "
                f"reported assets {fmt_dollars(reported_assets * 1e9)}"
            )

        normalization = payload.get("normalization", {}) or {}
        if name == "PE Portfolio Financing Strain":
            methods = sorted(
                {
                    str(item.get("method"))
                    for item in normalization.values()
                    if isinstance(item, dict) and item.get("method")
                }
            )
            normalization_text = " / ".join(methods)
        else:
            normalization_text = str(normalization.get("method", ""))

        rows.append({
            "Component": name,
            "Score": _fmt_signed(payload.get("score", np.nan), decimals=1),
            "Intended Weight": fmt_percent(payload.get("weight", np.nan)),
            "Active Weight": fmt_percent(payload.get("active_weight", np.nan)),
            "Current Measure": measure,
            "Normalization": normalization_text,
            "As Of": payload.get("as_of", ""),
            "Source": payload.get("source", ""),
        })

    return pd.DataFrame(rows)


def _borrower_strain_component_table(borrower_strain_result):
    components = (borrower_strain_result or {}).get("components", {}) or {}
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
        elif name == "Debt Capacity Strain":
            positive_count = payload.get("positive_ebitda_companies", 0)
            impaired_count = payload.get("impaired_companies", 0)
            net_cash_count = payload.get("net_cash_companies", 0)
            measure = (
                f"Positive-EBITDA net leverage = {fmt_multiple(raw)}; "
                f"negative-EBITDA net debt/revenue = {fmt_multiple(secondary)}; "
                f"branches {positive_count}/{impaired_count}/{net_cash_count}"
            )
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
            "Current Measure": measure,
            "Companies": payload.get("observations", 0),
        })

    return pd.DataFrame(rows)


def _styled_card_container(key, border_color, *, min_height=150):
    """Return a keyed Streamlit container with the dashboard card treatment."""
    st.html(
        f"""
        <style>
        .st-key-{key} {{
            border: 1px solid {border_color} !important;
            border-left: 6px solid {border_color} !important;
            border-radius: 12px !important;
            padding: 18px !important;
            background: #111827 !important;
            min-height: {min_height}px;
        }}
        .st-key-{key} [data-testid="stMetricLabel"] p {{
            font-size: 1.02rem !important;
            letter-spacing: 0.8px !important;
            color: #d1d5db !important;
            text-transform: uppercase !important;
            font-weight: 700 !important;
        }}
        .st-key-{key} [data-testid="stMetricValue"] {{
            font-size: 1.70rem !important;
            font-weight: 700 !important;
        }}
        .st-key-{key} [data-testid="stCaptionContainer"] p {{
            color: #cbd5e1 !important;
            line-height: 1.35 !important;
        }}
        </style>
        """
    )
    return st.container(key=key, border=True)


def _assessment_detail_row(label, value):
    st.markdown(
        f"""
        <div style="display:flex;justify-content:space-between;font-size:0.9rem;
                    color:#cbd5e1;line-height:1.55;">
            <span>{label}</span><b style="color:#f3f4f6;">{value}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )


def assessment_card(title, row, border_color, help_key):
    key = {
        "Most Crowded": "assessment-most-crowded",
        "Fastest Mover": "assessment-fastest-mover",
        "Biggest Risk": "assessment-biggest-risk",
    }.get(title, f"assessment-{title.lower().replace(' ', '-')}")

    with _styled_card_container(key, border_color):
        if row is None:
            st.metric(title, "No Data", help=metric_help(help_key))
            st.caption("Insufficient eligible history or fundamentals.")
            return

        display_sector = sector_display_name(row["Sector"])
        aei = pd.to_numeric(row["Sector Score"], errors="coerce")
        pressure = pd.to_numeric(row["Pressure"], errors="coerce")
        st.metric(title, display_sector, help=metric_help(help_key))

        if title == "Biggest Risk":
            breadth = pd.to_numeric(row.get("Risk Breadth Score", np.nan), errors="coerce")
            adverse = pd.to_numeric(row.get("Adverse Signals", np.nan), errors="coerce")
            valid = pd.to_numeric(row.get("Valid Signals", np.nan), errors="coerce")
            signal_text = (
                f"{int(adverse)} / {int(valid)}"
                if pd.notna(adverse) and pd.notna(valid)
                else "No Data"
            )
            _assessment_detail_row(
                "Deterioration Breadth",
                fmt_percent(breadth / 100) if pd.notna(breadth) else "No Data",
            )
            _assessment_detail_row("Adverse / Valid Signals", signal_text)
            return

        _assessment_detail_row("AEI Score", fmt_score(aei))
        _assessment_detail_row("Pressure Score", fmt_score(pressure))


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
        "borrower_strain": regime_metrics.get("Borrower Strain", np.nan),
        "lender_strain": regime_metrics.get(
            "Lender Strain", np.nan
        ),
        "speculation_gap": regime_metrics.get("Speculation Gap", np.nan),
        "validation_gap": regime_metrics.get("Economic Validation Gap", np.nan),
        "industrial_gap": industrial_growth_gap(adi, industrial_growth),
    }


def _render_snapshot_heading():
    st.subheader("AI Economy Snapshot")
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
            key_prefix="macro-aei",
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
            key_prefix="macro-adi",
        )

    with st.expander("ADI Component Detail", expanded=False):
        adi_components = (regime_metrics.get("ADI Components", {}) or {}).get("components", {})
        st.dataframe(arrow_safe_dataframe(_component_table(adi_components)), width="stretch", hide_index=True)
        st.caption("ADI is constituted when at least three of four top-level pillars are valid.")
        if regime_metrics.get("ADI Source") == "Archive Fallback":
            st.caption(
                "Headline: archive. Component detail: available current inputs."
            )


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
            key_prefix="macro-power-stress",
        )
    with right:
        _render_metric_panel(
            "Concentration HHI",
            values["concentration_hhi"],
            build_concentration_gauge,
            trends.get("concentration"),
            help_text=metric_help("Concentration HHI"),
            key_prefix="macro-concentration-hhi",
        )


def _fmt_years(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value):
        return "No Data"
    return f"{value:.1f} yrs"


def _fmt_signed_decimal(value):
    value = pd.to_numeric(value, errors="coerce")
    if pd.isna(value):
        return "No Data"
    return f"{value:+.2f}"


def _recent_metric_series(history, *, years=5):
    if history is None or not isinstance(history, pd.DataFrame) or history.empty:
        return pd.DataFrame(columns=["Date", "Value"])
    if "Date" not in history.columns or "Value" not in history.columns:
        return pd.DataFrame(columns=["Date", "Value"])

    out = history[["Date", "Value"]].copy()
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce", format="mixed")
    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")
    out = out.dropna(subset=["Date", "Value"]).sort_values("Date", kind="stable")
    if out.empty:
        return out

    cutoff = out["Date"].max() - pd.DateOffset(years=years)
    return out[out["Date"] >= cutoff].reset_index(drop=True)


def _funding_mix_card(
    title,
    value_text,
    fig,
    border_color,
    card_key,
    help_key,
):
    with _styled_card_container(card_key, border_color, min_height=175):
        st.metric(title, value_text, help=metric_help(help_key))
        st.plotly_chart(
            fig,
            width="stretch",
            config={"responsive": True},
            key=f"{card_key}-chart",
        )


def _render_deployment_funding_mix(regime_metrics, sector_data=None):
    funding_mix = regime_metrics.get("Deployment Funding Mix", {}) or {}
    if not funding_mix:
        funding_mix = calculate_deployment_funding_mix(sector_data or {})
    current = funding_mix.get("current", {}) or {}
    series = funding_mix.get("series", {}) or {}

    with st.container(border=True):
        coverage_series = _recent_metric_series(
            series.get("internal_funding_coverage"),
            years=5,
        )
        reserve_series = _recent_metric_series(
            series.get("cash_reserve_coverage_years"),
            years=5,
        )
        debt_series = _recent_metric_series(
            series.get("debt_financing_pulse"),
            years=5,
        )
        commitment_series = _recent_metric_series(
            series.get("forward_commitment_load"),
            years=5,
        )

        specs = [
            (
                "Internal Funding Coverage",
                fmt_multiple(current.get("internal_funding_coverage", np.nan)),
                build_mini_line_history(
                    coverage_series,
                    reference=1.0,
                    color="#a78bfa",
                ),
                "#7c3aed",
                "funding-mix-coverage",
                "Internal Funding Coverage",
            ),
            (
                "Cash Reserve Runway",
                _fmt_years(current.get("cash_reserve_coverage_years", np.nan)),
                build_mini_line_history(
                    reserve_series,
                    reference=1.0,
                    color="#60a5fa",
                ),
                "#60a5fa",
                "funding-mix-reserves",
                "Cash Reserve Runway",
            ),
            (
                "Debt Financing Pulse",
                _fmt_signed_decimal(current.get("debt_financing_pulse", np.nan)),
                build_mini_line_history(
                    debt_series,
                    reference=0.0,
                    color="#8b5cf6",
                ),
                "#8b5cf6",
                "funding-mix-debt-pulse",
                "Debt Financing Pulse",
            ),
            (
                "Forward Commitment Load",
                fmt_multiple(current.get("forward_commitment_load", np.nan)),
                build_mini_line_history(
                    commitment_series,
                    reference=1.0,
                    color="#c4b5fd",
                    fill=True,
                ),
                "#94a3b8",
                "funding-mix-commitments",
                "Forward Commitment Load",
            ),
        ]

        for column, spec in zip(st.columns(4), specs):
            with column:
                _funding_mix_card(*spec)


def _render_borrower_strain(values, trend, regime_metrics):
    borrower_strain_result = regime_metrics.get("Borrower Strain Components", {}) or {}
    with st.container(border=True):
        st.subheader("Borrower Strain")
        gauge_col, history_col, component_col = st.columns([1, 1.15, 1.35])

        with gauge_col:
            if pd.notna(pd.to_numeric(values["borrower_strain"], errors="coerce")):
                st.plotly_chart(
                    build_borrower_strain_gauge(values["borrower_strain"]),
                    width="stretch",
                    config={"responsive": True},
                    key="borrower-strain-gauge",
                )
            else:
                render_no_data_panel("Borrower Strain")
            render_trend_strip(trend)
            _render_source_caption(
                regime_metrics.get("Borrower Strain Source", "Current"),
                regime_metrics.get("Borrower Strain Fallback Date"),
            )

        with history_col:
            st.plotly_chart(
                build_metric_history(
                    trend,
                    "Borrower Strain",
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
                key="borrower-strain-history",
            )

        with component_col:
            st.plotly_chart(
                build_component_score_chart(
                    borrower_strain_result.get("components", {}),
                    "Borrower Strain Components",
                    x_range=(-100, 100),
                ),
                width="stretch",
                config={"responsive": True},
                key="borrower-strain-components",
            )

    with st.expander("Borrower Strain Detail", expanded=False):
        st.dataframe(
            arrow_safe_dataframe(_borrower_strain_component_table(borrower_strain_result)),
            width="stretch",
            hide_index=True,
        )
        if regime_metrics.get("Borrower Strain Source") == "Archive Fallback":
            st.caption(
                "Headline: archive. Component detail: available current inputs."
            )


def _render_lender_strain(values, trend, regime_metrics):
    lender_strain_result = (
        regime_metrics.get("Lender Strain Components", {}) or {}
    )
    with st.container(border=True):
        st.subheader("Lender Strain", help=metric_help("Lender Strain"))
        gauge_col, history_col, component_col = st.columns([1, 1.15, 1.35])

        with gauge_col:
            if pd.notna(
                pd.to_numeric(values["lender_strain"], errors="coerce")
            ):
                st.plotly_chart(
                    build_lender_strain_gauge(
                        values["lender_strain"]
                    ),
                    width="stretch",
                    config={"responsive": True},
                    key="lender-strain-gauge",
                )
            else:
                render_no_data_panel("Lender Strain")
            render_trend_strip(trend)
            _render_source_caption(
                regime_metrics.get(
                    "Lender Strain Source", "Current"
                ),
                regime_metrics.get("Lender Strain Fallback Date"),
            )

        with history_col:
            st.plotly_chart(
                build_metric_history(
                    trend,
                    "Lender Strain",
                    y_range=(-100, 100),
                    adaptive_range=True,
                    min_span=20,
                    step=True,
                    flat_annotation=(
                        "No change in quarterly/annual credit inputs during this archive window."
                    ),
                ),
                width="stretch",
                config={"responsive": True},
                key="lender-strain-history",
            )

        with component_col:
            st.plotly_chart(
                build_component_score_chart(
                    lender_strain_result.get("components", {}),
                    "Lender Strain Components",
                    x_range=(-100, 100),
                ),
                width="stretch",
                config={"responsive": True},
                key="lender-strain-components",
            )

    with st.expander("Lender Strain Detail", expanded=False):
        bank_channel = pd.to_numeric(
            lender_strain_result.get("bank_channel_score", np.nan), errors="coerce"
        )
        nonbank_channel = pd.to_numeric(
            lender_strain_result.get("nonbank_channel_score", np.nan), errors="coerce"
        )
        elevated = int(lender_strain_result.get("elevated_pillars", 0) or 0)
        st.caption(
            f"Bank channel: {fmt_decimal(bank_channel)} | "
            f"Nonbank channel: {fmt_decimal(nonbank_channel)} | "
            f"Adverse breadth: {elevated} of 4 pillars above neutral"
        )
        st.dataframe(
            arrow_safe_dataframe(_lender_strain_component_table(lender_strain_result)),
            width="stretch",
            hide_index=True,
        )


def _render_financial_conditions_confirmation(fred_data, nfci_history):
    snapshot = nfci_snapshot(fred_data or {}, nfci_history)
    value = snapshot["value"]
    change = snapshot["three_month_change"]

    with st.container(border=True):
        st.subheader(
            "Financial Conditions Confirmation",
            help=metric_help("NFCI"),
        )
        condition_col, value_col, direction_col, spark_col = st.columns(
            [1.35, 0.8, 1.05, 2.2]
        )
        with condition_col:
            st.caption("CURRENT CONDITION")
            st.markdown(f"### {nfci_condition(value)}")
        with value_col:
            st.caption("NFCI")
            st.markdown(f"### {_fmt_signed(value, decimals=3)}")
        with direction_col:
            st.caption("3-MONTH DIRECTION")
            st.markdown(f"### {nfci_direction(change)}")
            if pd.notna(pd.to_numeric(change, errors="coerce")):
                st.caption(f"Change: {_fmt_signed(change, decimals=3)}")
        with spark_col:
            st.plotly_chart(
                build_nfci_sparkline(snapshot["history"], months=12),
                width="stretch",
                config={"displayModeBar": False, "responsive": True},
                key="finance-nfci-sparkline",
            )
        st.caption(nfci_summary(value, change))

    with st.expander("Financial Conditions Detail", expanded=False):
        st.markdown(
            "The Chicago Fed National Financial Conditions Index summarizes "
            "weekly U.S. financial conditions across money markets, debt and "
            "equity markets, banking, leverage, funding risk, and shadow banking."
        )
        st.markdown(
            "**How to read it:** Negative values indicate conditions are looser "
            "than the long-run average; positive values indicate tighter "
            "conditions; zero represents the long-run average. The three-month "
            "direction shows whether support is strengthening or weakening."
        )
        meta_left, meta_middle, meta_right = st.columns(3)
        meta_left.metric("Latest NFCI", _fmt_signed(value, decimals=3))
        meta_middle.metric("3-Month Change", _fmt_signed(change, decimals=3))
        meta_right.metric("Observation Date", snapshot.get("as_of") or "No Data")
        st.plotly_chart(
            build_nfci_history(snapshot["history"]),
            width="stretch",
            config={"responsive": True},
            key="finance-nfci-detail-history",
        )
        st.caption(
            f"Source: Chicago Fed NFCI via {snapshot.get('source', 'FRED')}. "
            "Frequency: weekly. This is an independent confirmation signal, "
            "not a component of Lender Strain."
        )


def _render_gap_score_card(
    title, value, interpretation, accent_color, help_key, card_key
):
    """Render a gap card with its original per-metric helper restored."""
    with _styled_card_container(card_key, accent_color):
        st.metric(title, fmt_score(value), help=metric_help(help_key))
        st.caption(interpretation)


def _render_gap_metrics(values):
    st.subheader("Gap Scores")
    gap_specs = [
        (
            "Speculation Gap",
            values["speculation_gap"],
            speculation_label,
            "#7c3aed",
            "Speculation Gap",
            "gap-speculation",
        ),
        (
            "Economic Validation Gap",
            values["validation_gap"],
            validation_label,
            "#60a5fa",
            "Economic Validation Gap",
            "gap-economic-validation",
        ),
        (
            "AI–Industrial Growth Gap",
            values["industrial_gap"],
            adoption_label,
            "#94a3b8",
            "AI-Industrial Growth Gap",
            "gap-industrial-growth",
        ),
    ]
    for column, (
        title, value, label_fn, accent_color, help_key, card_key
    ) in zip(st.columns(3), gap_specs):
        with column:
            _render_gap_score_card(
                title,
                value,
                label_fn(value),
                accent_color,
                help_key,
                card_key,
            )
    st.markdown("---")


def _snapshot_render_inputs(
    macro_df,
    fred_data=None,
    power_stress_trend=None,
    concentration_trend=None,
    sector_data=None,
    regime_metrics=None,
    *,
    aei_trend=None,
    adi_trend=None,
):
    """Normalize the shared inputs used by the macro and finance tabs."""
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
    return fred_data, sector_data, regime_metrics, trends, values


def render_ai_macro_snapshot(
    macro_df,
    fred_data=None,
    power_stress_trend=None,
    concentration_trend=None,
    sector_data=None,
    regime_metrics=None,
    *,
    aei_trend=None,
    adi_trend=None,
):
    """Render the market, development, constraint, and gap metrics."""
    fred_data, sector_data, regime_metrics, trends, values = _snapshot_render_inputs(
        macro_df,
        fred_data=fred_data,
        power_stress_trend=power_stress_trend,
        concentration_trend=concentration_trend,
        sector_data=sector_data,
        regime_metrics=regime_metrics,
        aei_trend=aei_trend,
        adi_trend=adi_trend,
    )

    if DEBUG:
        debug_print("\n=== AI MACRO SNAPSHOT ===")
        debug_print("AEI:", values["aei"])
        debug_print("ADI:", values["adi"])
        debug_print("Speculation Gap:", values["speculation_gap"])
        debug_print("Power Stress:", values["power_stress"])

    _render_snapshot_heading()
    _render_equity_and_development(values, trends, regime_metrics)
    _render_power_and_concentration(values, trends, regime_metrics)
    st.markdown("---")
    _render_gap_metrics(values)


def render_finance_snapshot(
    macro_df,
    fred_data=None,
    sector_data=None,
    regime_metrics=None,
    *,
    borrower_strain_trend=None,
    lender_strain_trend=None,
    nfci_history=None,
):
    """Render funding, borrower strain, lender strain, and financial conditions."""
    fred_data, sector_data, regime_metrics, _trends, values = _snapshot_render_inputs(
        macro_df,
        fred_data=fred_data,
        sector_data=sector_data,
        regime_metrics=regime_metrics,
    )

    if DEBUG:
        debug_print("\n=== FINANCE SNAPSHOT ===")
        debug_print("Borrower Strain:", values["borrower_strain"])
        debug_print("Lender Strain:", values["lender_strain"])

    st.subheader("AI Buildout Financing")
    st.markdown("---")
    _render_deployment_funding_mix(regime_metrics, sector_data)
    _render_borrower_strain(values, borrower_strain_trend or {}, regime_metrics)
    _render_lender_strain(
        values, lender_strain_trend or {}, regime_metrics
    )
    _render_financial_conditions_confirmation(fred_data, nfci_history)



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
    borrower_strain_trend=None,
    lender_strain_trend=None,
    nfci_history=None,
):
    """Render the complete macro and credit-conditions snapshot."""
    render_ai_macro_snapshot(
        macro_df=macro_df,
        fred_data=fred_data,
        power_stress_trend=power_stress_trend,
        concentration_trend=concentration_trend,
        sector_data=sector_data,
        regime_metrics=regime_metrics,
        aei_trend=aei_trend,
        adi_trend=adi_trend,
    )
    st.markdown("---")
    render_finance_snapshot(
        macro_df=macro_df,
        fred_data=fred_data,
        sector_data=sector_data,
        regime_metrics=regime_metrics,
        borrower_strain_trend=borrower_strain_trend,
        lender_strain_trend=lender_strain_trend,
        nfci_history=nfci_history,
    )


def render_sector_assessment(macro_df, sector_data=None):
    st.subheader("Current Sector Assessment")

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
        assessment_card("Most Crowded", selected_rows.get("Most Crowded"), "#7c3aed", "Trading Pressure")
    with col2:
        assessment_card("Fastest Mover", selected_rows.get("Fastest Mover"), "#60a5fa", "Sector Movement")
    with col3:
        assessment_card("Biggest Risk", selected_rows.get("Biggest Risk"), "#94a3b8", "Risk Breadth")

    st.markdown("---")


def render_positioning_charts(macro_df):
    st.subheader("Sector Positioning and Rotation")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Earnings Support", help=metric_help("Earnings Support"))
        chart_box(build_positioning_map(macro_df), key="legacy-earnings-support")
    with col2:
        st.subheader("Speculative Load", help=metric_help("Speculative Load"))
        chart_box(build_rotation_matrix(macro_df), key="legacy-speculative-load")

    st.markdown("---")


def render_sector_table(macro_df, *, use_expander=True, expanded=False):
    required = [
        "Sector",
        "Sector Score",
        "Pressure",
        "Avg Return",
        "Forward EV/EBIT",
        "Loss-Making EV Share",
        "Beta",
    ]
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
    table["Forward EV/EBIT"] = table["Forward EV/EBIT"].map(fmt_multiple)
    if "Loss-Making EV Share" in table.columns:
        table["Loss-Making EV Share"] = table["Loss-Making EV Share"].map(fmt_percent)
    table["Beta"] = table["Beta"].map(fmt_decimal)

    def render_table():
        st.dataframe(arrow_safe_dataframe(table), width="stretch", hide_index=True)

    if use_expander:
        with st.expander("Sector Data", expanded=expanded):
            render_table()
    else:
        render_table()

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
        st.dataframe(arrow_safe_dataframe(pd.DataFrame(rows)), width="stretch", hide_index=True)
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
        st.dataframe(arrow_safe_dataframe(pd.concat(rows, ignore_index=True)), width="stretch", hide_index=True)
