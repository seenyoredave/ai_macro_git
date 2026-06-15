from loaders.market_loader import load_yfinance
from config.benchmark_config import QQQ_MEMBERS, SPY_MEMBERS, DIA_MEMBERS


#################################################
# BENCHMARK UNIVERSES (SOURCE OF TRUTH)
#################################################

BENCHMARK_UNIVERSES = {
    "QQQ": QQQ_MEMBERS,
    "SPY": SPY_MEMBERS,
    "DIA": DIA_MEMBERS
}


#################################################
# LOAD SINGLE BENCHMARK RAW DATA
#################################################

def load_benchmark(name: str):
    """
    Returns raw yfinance dataframe for benchmark constituents.
    """

    if name not in BENCHMARK_UNIVERSES:
        raise ValueError(f"Unknown benchmark: {name}")

    basket = BENCHMARK_UNIVERSES[name]

    if not basket:
        return None

    return load_yfinance(tuple(sorted(basket.items())))


#################################################
# LOAD ALL BENCHMARKS (RAW ONLY)
#################################################

def load_all_benchmarks():
    """
    IMPORTANT:
    - raw only
    - no normalization
    - no metrics
    """

    return {
        name: load_benchmark(name)
        for name in BENCHMARK_UNIVERSES.keys()
    }