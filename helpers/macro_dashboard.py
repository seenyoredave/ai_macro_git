### These functions build the AI macro dashboard tools

import streamlit as st
import pandas as pd
import numpy as np

from helpers.gaps import (
    validation_gap,
    liquidity_gap,
    adoption_gap
)

from helpers.labels import (
    validation_label,
    liquidity_label,
    adoption_label,
    short_regime_label,
    sector_display_name
)

from helpers.visualization import (
    build_maturity_gauge,
    build_divergence_gauge,
    build_power_stress_gauge,
    build_concentration_gauge,
    build_positioning_map,
    build_rotation_matrix
)

from config.debug_config import debug_print
from config.debug_config import DEBUG
from config.metric_definitions import METRIC_DEFINITIONS
from analytics.sector_assessment import select_current_sector_assessment


def chart_box(fig):
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", height=350)

def fmt_score(value):
    return "No Data" if pd.isna(value) else f"{value:.0f}"

def fmt_percent(value):
    return "No Data" if pd.isna(value) else f"{value * 100:.1f}%"

def fmt_multiple(value):
    return "No Data" if pd.isna(value) else f"{value:.1f}x"

def fmt_decimal(value):
    return "No Data" if pd.isna(value) else f"{value:.2f}"

def metric_help(key, fallback="Definition unavailable."):
    """
    Safe wrapper for metric definitions.

    This prevents dashboard crashes during refactors when a metric title
    has changed but config/metric_definitions.py has not yet been updated.
    """
    return METRIC_DEFINITIONS.get(key, fallback)

def get_ai_maturation_value(macro_df):
    """
    Returns the average AI maturation value from the macro dataframe.

    Supports old and new column names during refactor:
    - Maturation Index
    - AMI
    - Cycle Score
    - Sector Score
    """

    if macro_df is None or macro_df.empty:
        return np.nan

    candidate_columns = [
        "Maturation Index",
        "AMI",
        "Cycle Score",
        "Sector Score",
    ]

    for col in candidate_columns:
        if col in macro_df.columns:
            values = pd.to_numeric(macro_df[col], errors="coerce")
            return values.mean()

    return np.nan


########################
# D/DX AND D2/DX2 TABS
########################

def render_trend_strip(trend):

    current = trend.get("current", np.nan)
    velocity = trend.get("velocity", np.nan)
    acceleration = trend.get("acceleration", np.nan)

    st.markdown(
        f"""
        <div style="
            text-align:center;
            font-size:0.85rem;
            margin-top:-10px;
        ">
            <b>Current</b>: {current:.1f}
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Velocity</b>: {velocity:+.2f}
            &nbsp;&nbsp;|&nbsp;&nbsp;
            <b>Accel</b>: {acceleration:+.2f}
        </div>
        """,
        unsafe_allow_html=True
    )

def assessment_card(title, row, border_color):

    if row is None:
        card = f"""
        <div style="border:1px solid {border_color}; border-left:6px solid {border_color}; border-radius:12px; padding:18px; background:#111827; min-height:150px;">
            <div style="font-size:0.9rem; letter-spacing:1px; color:#9ca3af; text-transform:uppercase; font-weight:700; margin-bottom:8px;">
                {title}
            </div>

            <div style="font-size:1.5rem; font-weight:700; margin-bottom:12px;">
                No Data
            </div>

            <div style="font-size:0.85rem; color:#9ca3af;">
                Insufficient eligible history or fundamentals.
            </div>
        </div>
        """
        st.html(card)
        return

    display_sector = sector_display_name(row["Sector"])

    cycle = row["Sector Score"]
    pressure = row["Pressure"]

    card = f"""
    <div style="border:1px solid {border_color}; border-left:6px solid {border_color}; border-radius:12px; padding:18px; background:#111827; min-height:150px;">
        <div style="font-size:0.9rem; letter-spacing:1px; color:#9ca3af; text-transform:uppercase; font-weight:700; margin-bottom:8px;">
            {title}
        </div>

        <div style="font-size:1.5rem; font-weight:700; margin-bottom:12px;">
            {display_sector}
        </div>

        <div style="display:flex; justify-content:space-between; font-size:0.9rem;">
            <span>Cycle Score</span>
            <b>{cycle:.0f}</b>
        </div>

        <div style="display:flex; justify-content:space-between; font-size:0.9rem;">
            <span>Pressure Score</span>
            <b>{pressure:.0f}</b>
        </div>
    </div>
    """

    st.html(card)

def render_regime_snapshot(
    macro_df,
    fred_data=None,
    sentiment_data=None,
    cycle_trend=None,
    divergence_trend=None,
    power_stress_trend=None,
    concentration_trend=None,
    sector_data=None,
    regime_metrics=None,
):

    ### SAFE DEFAULTS ###

    fred_data = fred_data or {}
    sentiment_data = sentiment_data or {}
    sector_data = sector_data or {}
    regime_metrics = regime_metrics or {}

    ### FRED PULLS ###

    industrial_prod = (
        fred_data.get("Industrial Production", {}).get("value", np.nan)
    )

    ### CORE VALUES ###

    ami = get_ai_maturation_value(macro_df)
    
    avg_pressure = pd.to_numeric(
        macro_df["Pressure"],
        errors="coerce"
    ).mean()

    ai_divergence = regime_metrics.get("Divergence", np.nan)
    
    power_stress = (
        power_stress_trend.get("current", np.nan)
        if power_stress_trend
        else np.nan
    )

    concentration_hhi = (
        concentration_trend.get("current", np.nan)
        if concentration_trend
        else np.nan
    )

    ### GAUGES ###

    ami_fig = build_maturity_gauge(ami)
    divergence_fig = build_divergence_gauge(ai_divergence)
    power_fig = build_power_stress_gauge(power_stress)
    concentration_fig = build_concentration_gauge(concentration_hhi)

    ### GAP SCORES ###

    validation_gap_score = validation_gap(
        sector_data=sector_data,
        fred_data=fred_data,
        sector="ENTERPRISE_AI_SOFTWARE",
    )

    liquidity_gap_score = liquidity_gap(
        macro_df=macro_df,
        fred_data=fred_data,
    )

    adoption_gap_score = adoption_gap(
        ami,
        industrial_prod
    )

    if DEBUG:
        debug_print("DEBUG POWER STRESS INDEX:", power_stress)

        debug_print("\n=== REGIME SNAPSHOT ===")
        debug_print("DEBUG sector_data keys:", list(sector_data.keys()) if sector_data else [])
        debug_print("DEBUG AMI:", ami)
        debug_print("DEBUG Divergence:", ai_divergence)
        debug_print("DEBUG Economic Validation Gap:", validation_gap_score)
        debug_print("DEBUG Liquidity Support Gap:", liquidity_gap_score)
        debug_print("DEBUG Adoption Gap:", adoption_gap_score)

    ### REGIME SNAPSHOT ###

    header_col, metric_col = st.columns([2, 1])

    with header_col:
        st.subheader(
            "AI Economy Snapshot",
            help=(
                f"Maturation Index: {metric_help('Maturation Index')}\n\n"
                f"Divergence Estimate: {metric_help('Divergence Estimate')}\n\n"
                f"Power Stress Index: {metric_help('Power Stress Index')}\n\n"
                f"Concentration HHI: {metric_help('Concentration HHI')}"
            )
        )

    with metric_col:
        st.metric(
            "Current Regime",
            short_regime_label(ami),
            help=(
                "Early phase: < 30\n\n"
                "Expansion phase: 30-59\n\n"
                "Late expansion phase: 60-79\n\n"
                "Mature buildout phase: 80+"
            )
        )

    st.markdown("---")

    ###############
    # GAUGES
    ###############

    col1, col2 = st.columns(2)

    with col1:
        st.plotly_chart(
            ami_fig,
            width="stretch",
            config={"responsive": True}
        )

        if cycle_trend:
            render_trend_strip(cycle_trend)

    with col2:
        st.plotly_chart(
            divergence_fig,
            width="stretch",
            config={"responsive": True}
        )

        if divergence_trend:
            render_trend_strip(divergence_trend)

    st.markdown("---")

    col3, col4 = st.columns(2)

    with col3:
        st.plotly_chart(
            power_fig,
            width="stretch",
            config={"responsive": True}
        )

        if power_stress_trend:
            render_trend_strip(power_stress_trend)

    with col4:
        st.plotly_chart(
            concentration_fig,
            width="stretch",
            config={"responsive": True}
        )

        if concentration_trend:
            render_trend_strip(concentration_trend)

    ###############
    # GAPS
    ###############

    st.markdown("---")

    col1, col2, col3 = st.columns(3)

    with col1:
        if pd.notna(validation_gap_score):
            st.metric(
                "Economic Validation Gap",
                fmt_score(validation_gap_score),
                help=metric_help("Economic Validation Gap"),
                width="stretch",
            )
            st.caption(
                validation_label(validation_gap_score),
                width="stretch",
            )
        else:
            st.metric(
                "Economic Validation Gap",
                "No Data",
                help=metric_help("Economic Validation Gap"),
                width="stretch",
            )

    with col2:
        st.metric(
            "Liquidity Support Gap",
            fmt_score(liquidity_gap_score),
            help=metric_help("Liquidity Support Gap"),
            width="stretch",
        )
        st.caption(
            liquidity_label(liquidity_gap_score),
            width="stretch",
        )

    with col3:
        st.metric(
            "AI Adoption Gap",
            fmt_score(adoption_gap_score),
            help=metric_help("Adoption Gap"),
            width="stretch",
        )
        st.caption(
            adoption_label(adoption_gap_score),
            width="stretch",
        )

    st.markdown("---")

def render_sector_assessment(macro_df, sector_data=None):

    st.subheader(
        "Current Sector Assessment",
        help=metric_help("Current Sector Assessment")
    )
    st.markdown("---")

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
        st.warning("Sector assessment unavailable. Check Sector Score and Pressure calculations.")
        return

    selections = select_current_sector_assessment(
        assessment_df,
        sector_data=sector_data,
    )

    selected_rows = selections.get("rows", {})

    col1, col2, col3 = st.columns(3)

    with col1:
        assessment_card(
            "Most Crowded",
            selected_rows.get("Most Crowded"),
            "#7c3aed",
        )

    with col2:
        assessment_card(
            "Fastest Mover",
            selected_rows.get("Fastest Mover"),
            "#60a5fa",
        )

    with col3:
        assessment_card(
            "Biggest Risk",
            selected_rows.get("Biggest Risk"),
            "#94a3b8",
        )

    st.markdown("---")

def render_positioning_charts(macro_df):

    st.subheader("Sector Positioning and Rotation")
    st.markdown("---")

    fig_mv = build_positioning_map(macro_df)
    fig_rotation = build_rotation_matrix(macro_df)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### AI Sector Positioning Map")
        chart_box(fig_mv)

    with col2:
        st.markdown("### AI Sector Rotation Matrix")
        chart_box(fig_rotation)

    st.markdown("---")

def render_sector_cards(macro_df):

    st.subheader("Key Sector Metrics")
    st.markdown("___")

    required = [
        "Sector",
        "Sector Score",
        "Pressure",
        "Avg Return",
        "Forward P/E",
        "Beta"
    ]

    missing = [c for c in required if c not in macro_df.columns]

    if missing:
        st.error(f"Missing columns: {missing}")
        return

    rows = macro_df.to_dict("records")

    for i in range(0, len(rows), 3):

        cols = st.columns(3)

        for col, row in zip(cols, rows[i:i + 3]):

            display_sector = sector_display_name(row["Sector"])

            card = f"""
            <div style="
                border:1px solid #374151;
                border-radius:12px;
                padding:20px;
                background:#111827;
                min-height:260px;
            ">

            <h3 style="margin-bottom:4px;">
                {display_sector}
            </h3>

            <div style="
                display:flex;
                justify-content:space-between;
                margin-bottom:8px;
            ">
                <span>Sector Score</span>
                <b>{fmt_score(row['Sector Score'])}</b>
            </div>

            <div style="
                display:flex;
                justify-content:space-between;
                margin-bottom:16px;
            ">
                <span>Pressure</span>
                <b>{fmt_score(row['Pressure'])}</b>
            </div>

            <hr style="border-color:#374151;">

            <div style="
                display:flex;
                justify-content:space-between;
                margin-top:12px;
            ">
                <span>1Y Return</span>
                <span>{fmt_percent(row['Avg Return'])}</span>
            </div>

            <div style="
                display:flex;
                justify-content:space-between;
            ">
                <span>Forward P/E</span>
                <span>{fmt_multiple(row['Forward P/E'])}</span>
            </div>

            <div style="
                display:flex;
                justify-content:space-between;
            ">
                <span>Beta</span>
                <span>{fmt_decimal(row['Beta'])}</span>
            </div>

            </div>
            """

            with col:
                st.markdown(
                    card,
                    unsafe_allow_html=True
                )

        st.markdown("---")

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

        rows.append({
            "Indicator": indicator,
            "Value": value,
            "Date": date
        })

    df = pd.DataFrame(rows)

    with st.expander("FRED Data", expanded=False):

        st.dataframe(
            df,
            width="stretch"
        )

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

        available = [
            col for col in cols
            if col in df.columns
        ]

        sector_snapshot = df[available].copy()
        sector_snapshot.insert(0, "Sector", sector)

        rows.append(sector_snapshot)

    if not rows:
        st.warning("No EDGAR rows available")
        return

    edgar_df = pd.concat(rows, ignore_index=True)

    with st.expander("EDGAR Data", expanded=False):
        st.dataframe(edgar_df, width="stretch")