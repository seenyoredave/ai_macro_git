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


def get_sector_data(sector, tickers=None, raw_universe_data=None):
    sector_config = SECTOR_CONFIG.get(sector)

    if sector_config is None:
        raise KeyError(f"Sector not found in SECTOR_CONFIG: {sector}")

    if tickers is None:
        tickers = sector_config["basket"]

    assert_no_benchmarks(tickers)

    if raw_universe_data is None:
        raw_data = load_sector_data(
            {t: t for t in tickers},
            sector=sector
        )
    else:
        ticker_set = set(tickers)

        raw_yf = raw_universe_data["yfinance"]
        raw_yf = raw_yf[raw_yf["Ticker"].isin(ticker_set)].copy()

        raw_edgar = {
            ticker: raw_universe_data["edgar"].get(ticker, {})
            for ticker in ticker_set
        }

        raw_data = {
            "yfinance": raw_yf,
            "edgar": raw_edgar,
        }

    df = resolve_sector_dataframe(raw_data)

    df["Sector"] = sector

    ai_exposure_score = sector_config.get("ai_exposure_score", {})

    df = add_basket_tiers(
        df,
        ai_exposure_score=ai_exposure_score
    )

    df["Sector"] = sector

    return df