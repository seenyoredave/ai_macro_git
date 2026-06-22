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
    sector_config = SECTOR_CONFIG.get(sector)

    if sector_config is None:
        raise KeyError(f"Sector not found in SECTOR_CONFIG: {sector}")

    if tickers is None:
        tickers = sector_config["basket"]

    assert_no_benchmarks(tickers)

    raw_data = load_sector_data(
        {t: t for t in tickers},
        sector=sector
    )

    df = resolve_sector_dataframe(raw_data)

    # Critical: fresh yfinance pulls do not automatically carry sector identity.
    # Downstream factor code expects this column.
    df["Sector"] = sector

    ai_exposure_score = sector_config.get("ai_exposure_score", {})

    df = add_basket_tiers(
        df,
        ai_exposure_score=ai_exposure_score
    )

    # Keep Sector after tiering, just in case add_basket_tiers copies/filters.
    df["Sector"] = sector

    return df