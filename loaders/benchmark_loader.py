from config.benchmark_config import (
    ACTIVE_BENCHMARKS,
    BENCHMARK_UNIVERSES,
    BENCHMARK_WEIGHTS,
)
from loaders.market_loader import load_yfinance


def load_benchmark(name: str):
    if name not in BENCHMARK_UNIVERSES:
        raise ValueError(f"Unknown benchmark: {name}")

    members = BENCHMARK_UNIVERSES[name]
    if not members:
        return None

    frame = load_yfinance(tuple(sorted(members.items()))).copy()
    weights = BENCHMARK_WEIGHTS.get(name)
    if not weights:
        raise ValueError(f"Active benchmark {name} has no configured weights")

    frame["Benchmark Weight"] = frame["Ticker"].map(weights)
    return frame


def load_all_benchmarks():
    return {name: load_benchmark(name) for name in ACTIVE_BENCHMARKS}
