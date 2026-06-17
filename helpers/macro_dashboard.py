### These functions build the AI macro dashboard tools


import streamlit as st
import pandas as pd
import numpy as np

from helpers.macro_normalization import(
    normalize_consumer_sentiment,
    normalize_put_call   
)

from helpers.gaps import (
    gap_score,
    liquidity_gap,
    adoption_gap
)

from helpers.labels import (
    reality_gap_label,
    liquidity_label,
    adoption_label,
    short_regime_label,
    sector_display_name
)

from analytics.regime_engine import ai_cdi_index

from helpers.visualization import (
    build_maturity_gauge,
    build_divergence_gauge,
    build_power_stress_gauge,
    build_concentration_gauge,
    build_positioning_map,
    build_rotation_matrix
)

from config.debug_config import debug_print 
from config.metric_definitions import METRIC_DEFINITIONS 

  
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

    display_sector = sector_display_name(row["Sector"])

    cycle = row["Cycle Score"]
    pressure = row["Heat"]

    card = f"""
    <div style="border:1px solid {border_color}; border-left:6px solid {border_color}; border-radius:12px; padding:18px; background:#111827; min-height:150px;">
        <div style="font-size:0.9rem; letter-spacing:1px; color:#9ca3af; text-transform:uppercase; font-weight:700; margin-bottom:8px;">
            {title}
        </div>

        <div style="font-size:1.5rem; font-weight:700; margin-bottom:12px;">
            {display_sector}
        </div>

        <div style="display:flex; justify-content:space-between; font-size:0.9rem;">
            <span>Cycle</span>
            <b>{cycle:.0f}</b>
        </div>

        <div style="display:flex; justify-content:space-between; font-size:0.9rem;">
            <span>Pressure</span>
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
        concentration_trend=None
    ):
        
        fred_data = fred_data or {}
        sentiment_data = sentiment_data or {}
        
        ### FRED PULLS ###
        
        consumer_data = fred_data.get("Consumer Sentiment", {})
        fed_consumer_raw = consumer_data.get("value", np.nan)
        fed_funds = (fred_data.get("Fed Funds Rate", {}).get("value", np.nan))
        industrial_prod = (fred_data.get("Industrial Production", {}).get("value", np.nan))      
        
        ### KEY METRICS ###
        
        pcr = sentiment_data.get("PutCallRatio",np.nan)
        ai_temp = macro_df["Cycle Score"].mean()
        ai_divergence = ai_cdi_index(macro_df)
        power_stress = (power_stress_trend.get("current", np.nan)
            if power_stress_trend
            else np.nan
        )
        concentration_hhi = (concentration_trend.get("current", np.nan)
            if concentration_trend
            else np.nan
        )
  
        consumer_norm = normalize_consumer_sentiment(fed_consumer_raw)
        investor_norm = normalize_put_call(pcr)
        reality_gap = gap_score(investor_norm,consumer_norm)
        liquidity_gap_score = liquidity_gap(ai_temp,fed_funds)
        adoption_gap_score = adoption_gap(ai_temp,industrial_prod)
        temp_fig = build_maturity_gauge(ai_temp)
        divergence_fig = build_divergence_gauge(ai_divergence)
        power_fig = build_power_stress_gauge(power_stress)
        concentration_fig = build_concentration_gauge(concentration_hhi)
        
        print("DEBUG POWER STRESS INDEX:", power_stress)
        
        debug_print("\n=== REGIME SNAPSHOT ===")
        debug_print("DEBUG AI Temp:", ai_temp)
        debug_print("DEBUG Divergence Estimate:", ai_divergence)
        debug_print("DEBUG Put/Call Ratio:", pcr)
        debug_print("DEBUG Consumer Raw:", fed_consumer_raw)
        debug_print("DEBUG Consumer Norm:", consumer_norm)
        debug_print("DEBUG Investor Norm:", investor_norm)
        debug_print("DEBUG Reality Gap:", reality_gap)
        debug_print("DEBUG Liquidity Gap:", liquidity_gap_score)
        debug_print("DEBUG Adoption Gap:", adoption_gap_score)

        ### REGIME SNAPSHOT ###
        
        header_col, metric_col = st.columns([2, 1])
        
        with header_col: 
            st.subheader(
                "AI Economy Snapshot",
                help=(
                    f"Maturation Cycle: {METRIC_DEFINITIONS['Maturation Cycle']}\n\n"
                    f"Divergence Estimate: {METRIC_DEFINITIONS['Divergence Estimate']}\n\n"
                    f"Power Stress Index: {METRIC_DEFINITIONS['Power Stress Index']}\n\n"
                    f"Concentration HHI: {METRIC_DEFINITIONS['Concentration HHI']}"
                )
            )
        
        ai_temp = macro_df["Cycle Score"].mean()

        with metric_col:
            st.metric(
                "Current Regime",
                short_regime_label(ai_temp),
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
        
        
        col1,col2 = st.columns(2)    

        with col1:
            st.plotly_chart(
                temp_fig,
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
         
        col1,col2,col3 = st.columns(3)
            
        with col1:

            if pd.notna(reality_gap):
        
                st.metric("AI Reality Gap",fmt_score(reality_gap),help=METRIC_DEFINITIONS["Reality Gap"], width='stretch')
                st.caption(reality_gap_label(reality_gap),width='stretch')

            else:

                st.metric("AI Reality Gap","No Data")
                
        with col2:
            
            st.metric("AI Liquidity Gap",fmt_score(liquidity_gap_score),help=METRIC_DEFINITIONS["Liquidity Gap"])
            st.caption(liquidity_label(liquidity_gap_score))
        
        with col3:
            
            st.metric("AI Adoption Gap",fmt_score(adoption_gap_score),help=METRIC_DEFINITIONS["Adoption Gap"])
            st.caption(adoption_label(adoption_gap_score))
        
            
        st.markdown("---")
    
            
def render_sector_assessment(macro_df):

    st.subheader("Current Sector Assessment")
    st.markdown("---")

    assessment_df = macro_df.copy()

    required_cols = ["Cycle Score", "Heat"]

    if assessment_df[required_cols].notna().sum().min() == 0:
        st.warning("Sector assessment unavailable. Check Cycle Score and Heat calculations.")
        return

    assessment_df["Opportunity"] = (
        assessment_df["Heat"] - assessment_df["Cycle Score"]
    )

    assessment_df["Risk"] = (
        assessment_df["Cycle Score"] - assessment_df["Heat"]
    )

    crowded = assessment_df.loc[assessment_df["Cycle Score"].idxmax()]
    opportunity = assessment_df.loc[assessment_df["Opportunity"].idxmax()]
    risk = assessment_df.loc[assessment_df["Risk"].idxmax()]

    col1, col2, col3 = st.columns(3)

    with col1:
        assessment_card("Most Crowded", crowded, "#7c3aed")

    with col2:
        assessment_card("Biggest Opportunity", opportunity, "#60a5fa")

    with col3:
        assessment_card("Biggest Risk", risk, "#94a3b8")

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
        "Cycle Score",
        "Heat",
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
        
            
        for col, row in zip(cols, rows[i:i+3]):

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
                <span>Cycle Maturity</span>
                <b>{fmt_score(row['Cycle Score'])}</b>
            </div>

            <div style="
                display:flex;
                justify-content:space-between;
                margin-bottom:16px;
            ">
                <span>Pressure</span>
                <b>{fmt_score(row['Heat'])}</b>
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

        # SAFE EXTRACTION (prevents dict leakage into UI)
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
            "Revenue Growth"
        ]

        available = [
            col for col in cols
            if col in df.columns
        ]

        temp = df[available].copy()
        temp.insert(0, "Sector", sector)

        rows.append(temp)

    if not rows:
        st.warning("No EDGAR rows available")
        return

    edgar_df = pd.concat(rows, ignore_index=True)

    with st.expander("EDGAR Data", expanded=False):
        st.dataframe(edgar_df, width="stretch")
    