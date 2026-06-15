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

    if not raw_data:
        st.error("load_sector_data returned empty raw_data")
        st.write("Sector:", sector)
        st.write("Tickers:", tickers)
        st.stop()
        
    print(type(tickers))
    print(tickers)

    df = resolve_sector_dataframe(raw_data)
        
    df = add_basket_tiers(df)

    return df