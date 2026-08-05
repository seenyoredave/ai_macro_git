from __future__ import annotations

import os

import requests
import streamlit as st

from config.debug_config import debug_print

SEC_TICKER_URL = "https://www.sec.gov/files/company_tickers.json"


SEC_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


DEFAULT_SEC_USER_AGENT = "AI Macro Dashboard contact@example.com"


def _optional_streamlit_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception as exc:
        debug_print(f"Optional Streamlit secret unavailable: {name} -> {exc}")
        return default


def _sec_user_agent():
    return (
        os.getenv("SEC_USER_AGENT")
        or _optional_streamlit_secret("SEC_USER_AGENT")
        or DEFAULT_SEC_USER_AGENT
    )


def sec_headers():
    return {
        "User-Agent": _sec_user_agent(),
        "Accept-Encoding": "gzip, deflate",
        "Host": "data.sec.gov",
    }


def sec_ticker_headers():
    return {
        "User-Agent": _sec_user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }


@st.cache_data(ttl=86400)
def load_ticker_cik_map():
    response = requests.get(
        SEC_TICKER_URL,
        headers=sec_ticker_headers(),
        timeout=30,
    )
    response.raise_for_status()

    raw = response.json()
    ticker_map = {}

    for _, row in raw.items():
        ticker = str(row.get("ticker", "")).upper().strip()
        cik = str(row.get("cik_str", "")).zfill(10)

        if ticker and cik:
            ticker_map[ticker] = cik

    return ticker_map


@st.cache_data(ttl=86400)
def fetch_company_facts(cik):
    url = SEC_COMPANY_FACTS_URL.format(cik=cik)
    response = requests.get(url, headers=sec_headers(), timeout=30)
    response.raise_for_status()
    return response.json()
