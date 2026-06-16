import pandas as pd
import numpy as np
import streamlit as st
import yfinance as yf

from pathlib import Path
from datetime import date
from concurrent.futures import ThreadPoolExecutor

from loaders.edgar_loader import load_edgar
from loaders.fred_loader import load_fred
from loaders.sentiment_loader import load_put_call


#################################################
# ARCHIVE SETTINGS
#################################################

ARCHIVE_DIR = Path("data/archive/yfinance")
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def get_today_archive_path() -> Path:
    today = date.today().isoformat()
    return ARCHIVE_DIR / f"yfinance_{today}.csv"


def get_latest_archive_path() -> Path | None:
    files = sorted(ARCHIVE_DIR.glob("yfinance_*.csv"))

    if not files:
        return None

    return files[-1]


def read_archive(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def write_archive(df: pd.DataFrame, path: Path) -> None:
    df.to_csv(path, index=False)


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

                "Price": safe_num(
                    "last_price",
                    "regularMarketPrice"
                ),

                "Beta": safe_num(
                    "beta"
                ),

                "P/E": safe_num(
                    "trailing_pe",
                    "trailingPE"
                ),

                "Forward P/E": safe_num(
                    "forward_pe",
                    "forwardPE"
                ),

                "Market Cap": safe_num(
                    "market_cap",
                    "marketCap"
                ),

                "Revenue": safe_num(
                    "total_revenue",
                    "totalRevenue"
                ),

                "52W High": safe_num(
                    "year_high",
                    "fiftyTwoWeekHigh"
                ),

                "52W Low": safe_num(
                    "year_low",
                    "fiftyTwoWeekLow"
                ),

                "1Y Return": one_year_return
            }

        except Exception as e:
            print(f"{ticker} failed -> {e}")
            return None

    #################################################
    # GENTLER PARALLEL DOWNLOAD
    #################################################

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
# YFINANCE LOADER WITH ARCHIVE REDIRECT
#################################################

@st.cache_data(ttl=3600)
def load_yfinance(ticker_tuple):

    today_path = get_today_archive_path()

    #################################################
    # 1. USE TODAY'S ARCHIVE IF IT EXISTS
    #################################################

    if today_path.exists():
        print(f"Loading today's yfinance archive: {today_path}")
        return read_archive(today_path)

    #################################################
    # 2. OTHERWISE TRY YFINANCE
    #################################################

    try:
        print("No yfinance archive found for today. Pulling from yfinance...")

        df = pull_yfinance(ticker_tuple)

        if df.empty:
            raise ValueError("yfinance returned an empty DataFrame")

        write_archive(df, today_path)

        print(f"Saved today's yfinance archive: {today_path}")

        return df

    #################################################
    # 3. IF YFINANCE FAILS, FALL BACK TO LATEST ARCHIVE
    #################################################

    except Exception as e:

        print(f"yfinance pull failed -> {e}")

        latest_path = get_latest_archive_path()

        if latest_path is not None:
            print(f"Using latest available yfinance archive: {latest_path}")
            return read_archive(latest_path)

        raise RuntimeError(
            "yfinance failed and no prior archive exists."
        ) from e


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