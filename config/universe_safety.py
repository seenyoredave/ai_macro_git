

from config.market_config import MARKET_BENCHMARKS

def assert_no_benchmarks(tickers):
    overlap = set(tickers) & set(MARKET_BENCHMARKS.keys())
    if overlap:
        raise ValueError(f"Benchmarks leaked into universe: {overlap}")