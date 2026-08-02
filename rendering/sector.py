from __future__ import annotations

import streamlit as st

from rendering.ticker_state import add_ticker, mutate_and_rerun, remove_ticker
from rendering.dataframe import arrow_safe_dataframe
from rendering.labels import sector_display_name

def render_basket_tier_smoke_test(df, use_expander=True, expanded=False):
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

    def render_contents():
        st.dataframe(
            arrow_safe_dataframe(tier_view),
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

    if use_expander:
        with st.expander("Basket tier review", expanded=expanded):
            render_contents()
    else:
        render_contents()

def render_basket_tier_developer_tool(sector_data):
    st.subheader("Basket tier review")

    if not sector_data:
        st.info("No sector data available for basket tier review.")
        return

    sectors = list(sector_data.keys())

    selected_sector = st.selectbox(
        "Select sector",
        sectors,
        format_func=lambda sector: sector_display_name(sector),
        key="basket_tier_module_sector",
    )

    df = sector_data.get(selected_sector)

    if df is None or df.empty:
        st.warning("No data available for selected sector.")
        return

    st.markdown(f"### {sector_display_name(selected_sector)} basket tiers")
    render_basket_tier_smoke_test(
        df,
        use_expander=False,
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
