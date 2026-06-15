"""
download market data
↓
build sector dataframe
↓
return sector dataframe
"""

from config.sector_config import SECTOR_CONFIG
from config.universe_safety import assert_no_benchmarks
from loaders.market_loader import load_sector_data
from analytics.sector_dataframe import resolve_sector_dataframe
from analytics.basket_tiering import add_basket_tiers 


def get_sector_data(sector, tickers=None):

    # session-state driven universe (primary)
    if tickers is None:
        tickers = SECTOR_CONFIG[sector]["basket"]

    assert_no_benchmarks(tickers)

    raw_data = load_sector_data({t: t for t in tickers})

    import streamlit as st

    st.write("Raw data type:", type(raw_data))

    if isinstance(raw_data, dict):
        st.write("Raw data keys:", list(raw_data.keys()))
        st.write("Raw data sample:", {
            k: type(v).__name__ for k, v in list(raw_data.items())[:5]
        })
    else:
        st.write("Raw data preview:", raw_data)
    
    if not raw_data:
        st.error("load_sector_data returned empty raw_data")
        st.write("Sector:", sector)
        st.write("Tickers:", tickers)
        st.stop()
        
    print(type(tickers))
    print(tickers)
    
    df = resolve_sector_dataframe(raw_data)
    
    import streamlit as st

    if df.empty or "Ticker" not in df.columns:
        st.error("Sector builder created an invalid dataframe before basket tiering.")
        st.write("Sector:", sector)
        st.write("Tickers:", tickers)
        st.write("Columns:", list(df.columns))
        st.write("Shape:", df.shape)
        st.write("Preview:", df.head())
        st.stop()
        
    df = add_basket_tiers(df)

    return df