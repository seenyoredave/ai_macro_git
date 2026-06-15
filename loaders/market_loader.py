import pandas as pd
import numpy as np
import streamlit as st 
import yfinance as yf 


from concurrent.futures import ThreadPoolExecutor

from loaders.edgar_loader import load_edgar 
from loaders.fred_loader import load_fred
from loaders.sentiment_loader import load_put_call
from pathlib import Path


#################################################
# FALLBACK FUNCTION FOR CLOUD CALL FAILS
#################################################

def load_yf_history_fallback(tickers):
    project_root = Path(__file__).resolve().parents[1]
    path = project_root / "archive" / "yf_history.csv"

    if not path.exists():
        return pd.DataFrame()

    fallback = pd.read_csv(path)

    if "Ticker" in fallback.columns:
        fallback = fallback[fallback["Ticker"].isin(tickers.keys())]

    return fallback

#################################################
# YFINANCE LOADER
#################################################

@st.cache_data(ttl=3600)
def load_yfinance(ticker_tuple):

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

            print(f"\n{ticker}")

            def safe_num(*keys):

                for key in keys:

                    val = f_info.get(key)

                    if val is None:
                        val = info.get(key)

                    if val is not None and not pd.isna(val):
                        return float(val)

                return np.nan

            #################################################
            # 1 YEAR RETURN
            #################################################

            clean_close = hist["Close"].dropna()

            print("Rows in clean_close:", len(clean_close))

            if len(clean_close) > 0:

                print("First date:", clean_close.index[0])
                print("Last date:", clean_close.index[-1])
                print("First price:", clean_close.iloc[0])
                print("Last price:", clean_close.iloc[-1])

            if len(clean_close) < 252:

                one_year_return = np.nan

            else:

                end_price = clean_close.iloc[-1]

                start_price = clean_close.iloc[-252]

                one_year_return = (
                    end_price / start_price
                ) - 1

                print("Start price:", start_price)
                print("End price:", end_price)
                print("1Y Return:", one_year_return)

            #################################################
            # RETURN ROW
            #################################################

            return {

                "Ticker": ticker,
                "Company": company,

                "Price":
                    safe_num(
                        "last_price",
                        "regularMarketPrice"
                    ),

                "Beta":
                    safe_num(
                        "beta"
                    ),

                "P/E":
                    safe_num(
                        "trailing_pe",
                        "trailingPE"
                    ),

                "Forward P/E":
                    safe_num(
                        "forward_pe",
                        "forwardPE"
                    ),

                "Market Cap":
                    safe_num(
                        "market_cap",
                        "marketCap"
                    ),

                "Revenue":
                    safe_num(
                        "total_revenue",
                        "totalRevenue"
                    ),

                "52W High":
                    safe_num(
                        "year_high",
                        "fiftyTwoWeekHigh"
                    ),

                "52W Low":
                    safe_num(
                        "year_low",
                        "fiftyTwoWeekLow"
                    ),

                "1Y Return":
                    one_year_return
            }

        except Exception as e:

            print(f"{ticker} failed -> {e}")
            return None

    #################################################
    # PARALLEL DOWNLOAD
    #################################################

    with ThreadPoolExecutor(max_workers=10) as executor:

        results = list(
            executor.map(
                lambda x: fetch_company(*x),
                tickers.items()
            )
        )

    rows = [r for r in results if r]

    df = pd.DataFrame(rows)

    if df.empty:
        st.warning("Live Yahoo Finance data unavailable. Using cached yf_history.csv snapshot.")
        df = load_yf_history_fallback(tickers)

    return df 



#################################################
# MASTER DATA LOADER
#################################################

@st.cache_data(ttl=3600)
def load_sector_data(tickers):
    raw_yf = load_yfinance(tuple(sorted(tickers.items())))
    raw_edgar = load_edgar(tickers)

    return {
        "yfinance": raw_yf,
        "edgar": raw_edgar,
    }