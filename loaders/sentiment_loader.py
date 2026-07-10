"""
Sentiment loader.

Uses SPY option open interest to estimate a market put/call ratio sentiment
proxy. This data is archived for future velocity/acceleration work only; it is
not an active regime or gap model input.
"""

import numpy as np
import yfinance as yf
import streamlit as st
import pandas as pd

from archive.archive_reader import (
    latest_nonempty_row,
    load_put_call_history,
    rows_for_date,
)
from config.debug_config import debug_print
from helpers.macro_normalization import normalize_put_call


def _put_call_payload(raw_pcr, source):
    return {
        "PutCallRatio": float(raw_pcr) if not pd.isna(raw_pcr) else np.nan,
        "Normalized PutCall": normalize_put_call(raw_pcr),
        "Source": source,
    }


def load_put_call_archive_for_today():
    df = load_put_call_history()

    if df is None or df.empty:
        return None

    today_df = rows_for_date(df)

    if today_df.empty:
        return None

    row = latest_nonempty_row(today_df)

    if row is None:
        return None

    pcr = pd.to_numeric(pd.Series([row.get("PutCallRatio", np.nan)]), errors="coerce").iloc[0]

    if pd.isna(pcr):
        return None

    normalized = row.get("Normalized PutCall", normalize_put_call(pcr))

    return {
        "PutCallRatio": float(pcr),
        "Normalized PutCall": normalized,
        "Source": "Put/Call Archive",
    }


def load_latest_put_call_archive():
    df = load_put_call_history()

    if df is None or df.empty:
        return None

    row = latest_nonempty_row(df)

    if row is None:
        return None

    pcr = pd.to_numeric(pd.Series([row.get("PutCallRatio", np.nan)]), errors="coerce").iloc[0]

    if pd.isna(pcr):
        return None

    return {
        "PutCallRatio": float(pcr),
        "Normalized PutCall": row.get("Normalized PutCall", normalize_put_call(pcr)),
        "Source": "Put/Call Archive Fallback",
    }


@st.cache_data(ttl=3600)
def load_put_call():

    archived_today = load_put_call_archive_for_today()

    if archived_today is not None:
        debug_print("Loading today's put/call ratio from put_call_history.csv")
        return archived_today

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

        return _put_call_payload(pcr, "SPY Options")

    except Exception as e:

        debug_print("PCR live load failed:", e)

        fallback = load_latest_put_call_archive()

        if fallback is None:
            debug_print("PCR archive fallback unavailable")
            return _put_call_payload(np.nan, "Put/Call Unavailable")

        return fallback
