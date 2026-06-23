import streamlit as st
import numpy as np
import pandas as pd

from helpers.visualization import factor_color

from config.debug_config import debug_print
from config.debug_config import DEBUG

from helpers.add_remove_ticker import (
    add_ticker,
    remove_ticker,
    mutate_and_rerun
)

from helpers.labels import sector_display_name
from config.factor_config import FACTOR_HELP


def render_basket_tier_smoke_test(df):
    required_cols = [
        "Ticker",
        "Company",
        "Market Cap",
        "Revenue",
        "1Y Return",
        "Basket Score",
        "Basket Tier",
        "Basket Weight",
        "AI Weight",
        "Effective Basket Weight",
    ]

    available = [
        col for col in required_cols
        if col in df.columns
    ]

    if "Basket Score" not in df.columns:
        st.warning("Basket tiers not available.")
        return

    tier_view = (
        df[available]
        .copy()
        .sort_values("Basket Score", ascending=False)
    )

    with st.expander("🧙 One Tier Test to Rule Them All", expanded=False):
        st.caption(
            "Smoke test for basket tiering. Tier 1 should generally contain the obvious economic leaders; Tier 4 should generally contain smaller or less representative names."
        )

        st.dataframe(
            tier_view,
            width="stretch",
            height=350
        )

        tier_counts = (
            tier_view["Basket Tier"]
            .value_counts()
            .sort_index()
            .rename_axis("Tier")
            .reset_index(name="Count")
        )

        st.bar_chart(
            tier_counts,
            x="Tier",
            y="Count"
        )


def render_factor_cards(scored_factors):
    if scored_factors is None or scored_factors.empty:
        st.info("No factor scores available.")
        return

    factor_rows = scored_factors.to_dict("records")

    for i in range(0, len(factor_rows), 2):
        cols = st.columns(2)

        for col, factor in zip(cols, factor_rows[i:i + 2]):
            name = factor.get("Factor", "Unknown Factor")
            display_name = name.replace("_", " ").title()

            factor_score = factor.get("Score", np.nan)
            raw_value = factor.get("Raw Value", np.nan)

            score_display = (
                "N/A"
                if pd.isna(factor_score)
                else f"{factor_score:.1f}"
            )

            raw_display = (
                "N/A"
                if pd.isna(raw_value)
                else f"{raw_value:.3f}"
            )

            border = factor_color(factor_score)

            help_text = FACTOR_HELP.get(
                name,
                "Factor used in sector scoring."
            )

            with col:
                st.markdown(
                    f"""
                    <div style="
                        background:#111827;
                        border-left:8px solid {border};
                        padding:16px;
                        border-radius:10px;
                        margin-bottom:10px;
                        min-height:110px;
                    ">
                        <b title="{help_text}">{display_name} ⓘ </b><br>
                        Raw Value: {raw_display}<br>
                        Score: {score_display}
                    </div>
                    """,
                    unsafe_allow_html=True
                )


def render_leaders_table(sector, df):
    display_sector = sector_display_name(sector)
    st.header(f"{display_sector} Leaders")

    display_cols = [
        "Company",
        "Price",
        "P/E",
        "Forward P/E",
        "Beta",
        "1Y Return",
        "Basket Tier",
        "Basket Weight",
        "AI Weight",
    ]

    available = [
        col for col in display_cols
        if col in df.columns
    ]

    if not available:
        st.info("No displayable columns available.")
        return

    st.dataframe(
        df[available],
        width="stretch"
    )


def render_ticker_controls(sector):
    with st.expander("➕ Add / Remove Tickers"):
        st.subheader("Add Ticker")

        ticker_input = st.text_input(
            "Enter Ticker",
            key=f"add_input_{sector}"
        )

        if st.button(
            "Add Ticker",
            key=f"add_button_{sector}"
        ):
            mutate_and_rerun(
                add_ticker,
                sector,
                ticker_input
            )

        basket = st.session_state.sectors[sector]["basket"]

        if basket:
            st.subheader("Remove Ticker")

            remove_ticker_symbol = st.selectbox(
                "Select ticker to remove",
                basket,
                key=f"remove_select_{sector}"
            )

            if st.button(
                "Remove Ticker",
                key=f"remove_button_{sector}"
            ):
                mutate_and_rerun(
                    remove_ticker,
                    sector,
                    remove_ticker_symbol
                )


def render_sector_dashboard(sector, df, metrics):
    
    if DEBUG: 
        debug_print("Sector:", sector)
        debug_print("DF shape:", None if df is None else df.shape)
        debug_print("Metric keys:", None if metrics is None else metrics.keys())

    if df is None or df.empty:
        st.warning("No data available for this sector.")
        return

    score = metrics.get("Sector Score", np.nan)
    pressure_score = metrics.get("Sector Pressure", np.nan)
    scored_factors = metrics.get("Scored Factors", pd.DataFrame())
    display_sector = sector_display_name(sector)

    strategy = metrics.get("Cycle Strategy", {})
    strategy = strategy or {
        "regime": "No Data",
        "action": "Insufficient data",
        "risk": "Unable to assess",
        "positioning": "No signal",
    }
    
    if DEBUG: 
        debug_print("Sector Score:", score)
        debug_print("Sector Pressure:", pressure_score)
        debug_print("Scored Factors type:", type(scored_factors))
        debug_print(
            "Scored Factors shape:",
            None if scored_factors is None else scored_factors.shape
        )
        debug_print(
            "Scored Factors columns:",
            None if scored_factors is None else scored_factors.columns.tolist()
        )

    st.header(f"{display_sector} Snapshot")

    score_display = (
        "N/A"
        if pd.isna(score)
        else f"{score:.1f}"
    )

    pressure_display = (
        "N/A"
        if pd.isna(pressure_score)
        else f"{pressure_score:.1f}"
    )

    col1, col2, col3 = st.columns([1, 1, 1.5])

    col1.metric("Sector Score", score_display)
    col2.metric("Sector Pressure", pressure_display)
    col3.metric("Regime", strategy["regime"])

    st.markdown("---")

    st.header("Factor Dashboard")
    render_factor_cards(scored_factors)

    st.markdown("---")

    render_leaders_table(sector, df)

    render_ticker_controls(sector)

    if DEBUG:
        debug_print(
            df[
                [
                    "Ticker",
                    "Basket Score",
                    "Basket Tier",
                    "Basket Weight"
                ]
            ]
            .sort_values(
                "Basket Score",
                ascending=False
            )
        )

    render_basket_tier_smoke_test(df)