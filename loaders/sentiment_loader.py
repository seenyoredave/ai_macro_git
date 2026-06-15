"""
Sentiment loader.

Uses SPY option open interest to estimate
a market put/call ratio sentiment proxy.

Higher values = defensive sentiment.
Lower values = risk-seeking sentiment.
"""

import numpy as np 
import yfinance as yf 
import streamlit as st 


@st.cache_data(ttl=3600)
def load_put_call():

    try:

        spy = yf.Ticker("SPY")

        expiration = spy.options[0]

        chain = spy.option_chain(expiration)

        total_puts = chain.puts["openInterest"].sum()

        total_calls = chain.calls["openInterest"].sum()

        pcr = (
            total_puts / total_calls
            if total_calls > 0
            else np.nan
        )

        return {
            "PutCallRatio": float(pcr),
            "Source": "SPY Options"
        }

    except Exception as e:

        print(f"PCR failed: {e}")

        return {
            "PutCallRatio": np.nan
        }
    
