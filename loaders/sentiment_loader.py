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
import pandas as pd 
from pathlib import Path 

PUT_CALL_ARCHIVE = Path("archive/put_call_history.csv")

def load_latest_put_call_archive():

    if not PUT_CALL_ARCHIVE.exists():
        return np.nan

    df = pd.read_csv(PUT_CALL_ARCHIVE)

    if df.empty:
        return np.nan

    series = pd.to_numeric(
        df["PutCallRatio"],
        errors="coerce"
    ).dropna()

    if series.empty:
        return np.nan

    return float(series.iloc[-1])

@st.cache_data(ttl=3600)
def load_put_call():

    try:
        spy = yf.Ticker("SPY")

        options = spy.options

        if not options:
            raise ValueError("No SPY option expirations returned")

        expiration = options[0]

        chain = spy.option_chain(expiration)

        total_puts = chain.puts["openInterest"].sum()
        total_calls = chain.calls["openInterest"].sum()

        if total_calls <= 0:
            raise ValueError("SPY calls open interest is zero or unavailable")

        pcr = total_puts / total_calls

        if pd.isna(pcr):
            raise ValueError("Put/call ratio calculated as NaN")

        return {
            "PutCallRatio": float(pcr),
            "Source": "SPY Options"
        }

    except Exception as e:

        import traceback

        print("\n=== PCR FAILURE ===")
        print(e)

        traceback.print_exc()

        fallback_pcr = load_latest_put_call_archive()

        return {
            "PutCallRatio": fallback_pcr,
            "Source": "Put/Call Archive Fallback"
        }
