import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor

from loaders.edgar_loader import load_edgar


#################################################
# YF HISTORY SETTINGS
#################################################

YF_HISTORY_PATH = Path("archive/yf_history.csv")


def read_yf_history_for_date(tickers, sector=None, target_date=None):
    if not YF_HISTORY_PATH.exists():
        return None

    df = pd.read_csv(YF_HISTORY_PATH)

    if df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    target_date = str(target_date or date.today())
    ticker_set = set(tickers.keys())

    df["Date"] = df["Date"].astype(str)

    filtered = df[
        (df["Date"] == target_date)
        &
        (df["Ticker"].isin(ticker_set))
    ].copy()

    if sector is not None and "Sector" in filtered.columns:
        filtered = filtered[filtered["Sector"] == sector].copy()

    found = set(filtered["Ticker"].dropna())

    if not ticker_set.issubset(found):
        return None

    return filtered


def read_latest_yf_history(tickers, sector=None):
    if not YF_HISTORY_PATH.exists():
        return None

    df = pd.read_csv(YF_HISTORY_PATH)

    if df.empty or "Date" not in df.columns or "Ticker" not in df.columns:
        return None

    ticker_set = set(tickers.keys())

    df["Date"] = df["Date"].astype(str)

    filtered = df[df["Ticker"].isin(ticker_set)].copy()

    if sector is not None and "Sector" in filtered.columns:
        filtered = filtered[filtered["Sector"] == sector].copy()

    if filtered.empty:
        return None

    latest_date = filtered["Date"].max()
    latest = filtered[filtered["Date"] == latest_date].copy()

    found = set(latest["Ticker"].dropna())

    if not ticker_set.issubset(found):
        return None

    return latest


#################################################
# RAW YFINANCE PULL
#################################################

def pull_yfinance(ticker_tuple):
    tickers = dict(ticker_tuple)

    def fetch_company(ticker, company):
        try:
            t = yf.Ticker(ticker)

            f_info = getattr(t, "fast_info", {}) or {}
            info = getattr(t, "info", {}) or {}

            hist = t.history(
                period="2y",
                auto_adjust=True
            )

            if hist.empty:
                return None

            hist = hist.dropna(subset=["Close"])

            def safe_num(*keys):
                for key in keys:
                    val = f_info.get(key)

                    if val is None:
                        val = info.get(key)

                    if val is not None and not pd.isna(val):
                        return float(val)

                return np.nan

            clean_close = hist["Close"].dropna()

            if len(clean_close) < 252:
                one_year_return = np.nan
            else:
                end_price = clean_close.iloc[-1]
                start_price = clean_close.iloc[-252]
                one_year_return = (end_price / start_price) - 1

            return {
                "Ticker": ticker,
                "Company": company,
                "Price": safe_num("last_price", "regularMarketPrice"),
                "Beta": safe_num("beta"),
                "P/E": safe_num("trailing_pe", "trailingPE"),
                "Forward P/E": safe_num("forward_pe", "forwardPE"),
                "Market Cap": safe_num("market_cap", "marketCap"),
                "Revenue": safe_num("total_revenue", "totalRevenue"),
                "52W High": safe_num("year_high", "fiftyTwoWeekHigh"),
                "52W Low": safe_num("year_low", "fiftyTwoWeekLow"),
                "1Y Return": one_year_return,
            }

        except Exception as e:
            print(f"{ticker} failed -> {e}")
            return None

    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(
            executor.map(
                lambda x: fetch_company(*x),
                tickers.items()
            )
        )

    rows = [r for r in results if r]

    return pd.DataFrame(rows)


#################################################
# YFINANCE LOADER
#################################################

@st.cache_data(ttl=3600)
def load_yfinance(ticker_tuple, sector=None):
    tickers = dict(ticker_tuple)

    archived_today = read_yf_history_for_date(
        tickers,
        sector=sector
    )

    if archived_today is not None:
        print(f"Loading today's yfinance rows from yf_history.csv: {sector}")
        return archived_today

    try:
        print(f"No yf_history rows found for today. Pulling yfinance: {sector}")

        df = pull_yfinance(ticker_tuple)

        if df.empty:
            raise ValueError("yfinance returned an empty DataFrame")

        return df

    except Exception as e:
        print(f"yfinance pull failed -> {e}")

        fallback = read_latest_yf_history(
            tickers,
            sector=sector
        )

        if fallback is not None:
            print(f"Using latest yf_history.csv fallback: {sector}")
            return fallback

        raise RuntimeError(
            "yfinance failed and no usable yf_history fallback exists."
        ) from e


#################################################
# MASTER DATA LOADER
#################################################

@st.cache_data(ttl=3600)
def load_sector_data(tickers, sector=None):
    raw_yf = load_yfinance(
        tuple(sorted(tickers.items())),
        sector=sector
    )

    raw_edgar = load_edgar(tickers)

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
    }